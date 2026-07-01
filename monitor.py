"""
monitor.py
----------
One-shot check: fetch the EA careers results page, compare against
previously-seen announcements (stored in seen_state.json), and post
any new ones to Telegram.

Designed to be run every 5 minutes by an external scheduler (GitHub
Actions cron, in the recommended setup). It is intentionally NOT a
long-running loop - each run does one check and exits. State persists
between runs via seen_state.json, which the GitHub Actions workflow
commits back to the repo.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from scraper_core import fetch_page, parse_announcements, URL
from telegram_notify import send_message, send_document
from excel_export import build_candidate_xlsx, safe_filename

STATE_FILE = Path(__file__).parent / "seen_state.json"


def load_seen() -> set:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()))
        except (json.JSONDecodeError, ValueError):
            print("Warning: seen_state.json was unreadable, starting fresh.", file=sys.stderr)
    return set()


def save_seen(fingerprints: set) -> None:
    STATE_FILE.write_text(json.dumps(sorted(fingerprints), indent=2))


def format_message(ann) -> str:
    lines = [
        "🛫 <b>New Ethiopian Airlines Careers Announcement</b>",
        "",
        f"<b>Postion :</b> {ann.position or 'N/A'}",
        f"<b>Location :</b> {ann.location or 'N/A'}",
        f"<b>Announcement :</b> {ann.announcement_type or 'N/A'}",
    ]

    if ann.candidates:
        lines.append("")
        lines.append(f"<b>Candidates:</b> {len(ann.candidates)} (see attached Excel file)")
    else:
        lines.append("")
        lines.append("🔗 " + URL)

    return "\n".join(lines)


def send_announcement(ann) -> None:
    """Send the text summary, then the candidate list as an Excel attachment if present."""
    send_message(format_message(ann))
    if ann.candidates:
        xlsx_buffer = build_candidate_xlsx(ann)
        caption = f"📋 {ann.position or 'Candidate list'} ({len(ann.candidates)} candidates)"
        send_document(xlsx_buffer, safe_filename(ann), caption=caption)




def print_preview(announcements) -> None:
    """Human-readable dump of what was parsed, for local sanity-checking."""
    for i, a in enumerate(announcements, 1):
        print(f"\n[{i}] Position: {a.position!r}")
        print(f"    Location: {a.location!r}")
        print(f"    Type:     {a.announcement_type!r}")
        print(f"    Candidates: {len(a.candidates)}")
        if a.candidates:
            sample = a.candidates[0]
            print(f"    Sample row: {sample}")


def main():
    parser = argparse.ArgumentParser(description="Check EA careers results page and notify Telegram of new items.")
    parser.add_argument("--dry-run", action="store_true",
                         help="Fetch and parse only. Print a readable preview. No Telegram, no state changes.")
    parser.add_argument("--force-notify", action="store_true",
                         help="Send ONE real Telegram message using the first parsed announcement, "
                              "to confirm the bot/token/chat ID work end-to-end. Does not touch state.")
    args = parser.parse_args()

    print(f"Checking {URL} ...")
    try:
        html = fetch_page()
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

    announcements = parse_announcements(html)
    print(f"Parsed {len(announcements)} announcement block(s).")

    if args.dry_run:
        print_preview(announcements)
        print("\nDry run complete. No Telegram messages sent, no state saved.")
        return

    if args.force_notify:
        if not announcements:
            print("Nothing parsed, can't send a test message.")
            return
        test_ann = announcements[0]
        print(f"Sending a TEST Telegram message using: {test_ann.position!r} / {test_ann.announcement_type!r}")
        try:
            send_message("🧪 TEST MESSAGE (force-notify)")
            send_announcement(test_ann)
            print("Sent. Check Telegram now.")
        except Exception as e:
            print(f"Telegram send failed: {e}", file=sys.stderr)
        return

    seen = load_seen()
    new_ones = [a for a in announcements if a.fingerprint() not in seen]

    if not new_ones:
        print("No new announcements. Nothing to do.")
        return

    print(f"Found {len(new_ones)} new announcement(s). Notifying Telegram...")
    for i, ann in enumerate(new_ones, 1):
        try:
            send_announcement(ann)
            print(f"[{i}/{len(new_ones)}] Notified: {ann.position} / {ann.announcement_type}")
        except Exception as e:
            print(f"Failed to send Telegram message: {e}", file=sys.stderr)
            continue
        seen.add(ann.fingerprint())
        save_seen(seen)  # persist immediately - if the run crashes mid-batch, already-sent
                          # announcements won't be re-sent next time


if __name__ == "__main__":
    main()


