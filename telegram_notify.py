"""
telegram_notify.py
-------------------
Minimal Telegram Bot API wrapper. No external Telegram SDK needed -
just plain HTTP calls via requests.

Requires two environment variables:
  TELEGRAM_BOT_TOKEN  - from @BotFather
  TELEGRAM_CHAT_ID    - the chat/user/channel to post into
"""

import os
import time
import requests

TELEGRAM_API = "https://api.telegram.org"
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 10


def send_message(text: str, parse_mode: str = "HTML") -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set as environment "
            "variables (or GitHub Actions secrets)."
        )

    # Telegram hard limit is 4096 chars per message
    max_len = 4000
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)] or [text]

    for chunk in chunks:
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    f"{TELEGRAM_API}/bot{token}/sendMessage",
                    data={
                        "chat_id": chat_id,
                        "text": chunk,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code == 429:
                    # Telegram is rate-limiting us - it tells us exactly how long to wait.
                    retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                    print(f"Rate limited by Telegram. Waiting {retry_after}s as instructed...")
                    time.sleep(retry_after + 1)
                    continue  # don't count this against MAX_RETRIES, just try again
                if not resp.ok:
                    raise RuntimeError(f"Telegram send failed: {resp.status_code} {resp.text}")
                last_error = None
                break
            except (requests.exceptions.RequestException, RuntimeError) as e:
                last_error = e
                print(f"Telegram send attempt {attempt}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_SECONDS * attempt
                    print(f"Retrying in {wait}s...")
                    time.sleep(wait)
        if last_error:
            raise last_error
        # Small pacing gap between chunks/messages to stay well under Telegram's
        # per-chat rate limits when several announcements go out in one run.
        time.sleep(1.5)


def send_document(file_bytes, filename: str, caption: str = "", parse_mode: str = "HTML") -> None:
    """Send a file (e.g. an in-memory xlsx BytesIO buffer) as a Telegram document."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set as environment "
            "variables (or GitHub Actions secrets)."
        )

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            file_bytes.seek(0)  # in case a previous attempt consumed the stream
            resp = requests.post(
                f"{TELEGRAM_API}/bot{token}/sendDocument",
                data={
                    "chat_id": chat_id,
                    "caption": caption[:1024],  # Telegram caption limit
                    "parse_mode": parse_mode,
                },
                files={"document": (filename, file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                print(f"Rate limited by Telegram. Waiting {retry_after}s as instructed...")
                time.sleep(retry_after + 1)
                continue
            if not resp.ok:
                raise RuntimeError(f"Telegram document send failed: {resp.status_code} {resp.text}")
            return
        except (requests.exceptions.RequestException, RuntimeError) as e:
            last_error = e
            print(f"Telegram document send attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SECONDS * attempt
                print(f"Retrying in {wait}s...")
                time.sleep(wait)
    if last_error:
        raise last_error
