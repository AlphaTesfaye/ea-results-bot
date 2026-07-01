"""
scraper_core.py
----------------
Fetches and parses the Ethiopian Airlines careers "Results" page into a
list of Announcement objects, each with a candidate table.
"""

import re
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

URL = "https://corporate.ethiopianairlines.com/AboutEthiopian/careers/results"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ResultsMonitor/1.0; personal use)"
}
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 10


@dataclass
class Announcement:
    position: str = ""
    location: str = ""
    announcement_type: str = ""
    description: str = ""
    candidates: List[Dict[str, str]] = field(default_factory=list)

    def fingerprint(self) -> str:
        """Stable hash identifying this exact announcement + candidate list.
        Used to detect 'is this new?' between polling runs.

        Deliberately excludes the raw scraped `description` blob - that text
        is captured by walking nearby page elements and can shift slightly
        between fetches (whitespace, stray nearby content, etc.) even when
        the announcement itself hasn't changed. Using only the structured
        fields below keeps the fingerprint stable across re-fetches.
        """
        payload = "|".join([
            self.position.strip().lower(),
            self.location.strip().lower(),
            self.announcement_type.strip().lower(),
            str(len(self.candidates)),
            *sorted("|".join(f"{k}={v}" for k, v in c.items()) for c in self.candidates),
        ])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fetch_page(url: str = URL) -> str:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"Fetch attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SECONDS * attempt
                print(f"Retrying in {wait}s...")
                time.sleep(wait)
    raise last_error


def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_table(table) -> List[Dict[str, str]]:
    rows = table.find_all("tr")
    if not rows:
        return []
    headers = [clean_text(th.get_text()) for th in rows[0].find_all(["th", "td"])]
    headers = [h if h else f"col_{i}" for i, h in enumerate(headers)]

    data = []
    for tr in rows[1:]:
        cells = [clean_text(td.get_text()) for td in tr.find_all(["td", "th"])]
        if not any(cells):
            continue
        row = {headers[i] if i < len(headers) else f"col_{i}": val
               for i, val in enumerate(cells)}
        data.append(row)
    return data


def parse_announcements(html: str) -> List[Announcement]:
    soup = BeautifulSoup(html, "lxml")
    announcements: List[Announcement] = []
    tables = soup.find_all("table")

    for table in tables:
        ann = Announcement()
        node = table
        collected_text = []
        steps = 0
        while node and steps < 60:
            node = node.find_previous(
                lambda tag: tag.name in ("p", "li", "div", "h1", "h2", "h3")
                and tag.get_text(strip=True)
            )
            steps += 1
            if not node:
                break
            txt = clean_text(node.get_text())
            collected_text.append(txt)
            if re.search(r"post[i]?on\s*:", txt, re.I):
                break

        block_text = " | ".join(reversed(collected_text))

        pos_match = re.search(r"post[i]?on\s*:\s*(.*?)\s*(?:location\s*:|description\s*:|$)",
                               block_text, re.I)
        loc_match = re.search(r"location\s*:\s*(.*?)\s*(?:description\s*:|$)",
                               block_text, re.I)
        # Real page uses "Description :" followed by a short headline like
        # "CALL FOR WRITTEN EXAM" before the long body text kicks in.
        ann_match = re.search(r"description\s*:\s*(.*?)(?:\(|AMONG\b|$)", block_text, re.I)

        def strip_trailing_pipe(s: str) -> str:
            return clean_text(re.sub(r"\|\s*$", "", s or "").strip())

        ann.position = strip_trailing_pipe(pos_match.group(1)) if pos_match else ""
        ann.location = strip_trailing_pipe(loc_match.group(1)) if loc_match else ""
        ann.announcement_type = strip_trailing_pipe(ann_match.group(1)) if ann_match else ""

        if not ann.announcement_type:
            # Fallback: look for a "CALL FOR ..." style headline anywhere in the block
            fallback = re.search(r"(CALL FOR [A-Z&,./\- ]+)", block_text, re.I)
            if fallback:
                ann.announcement_type = clean_text(fallback.group(1))
        ann.description = block_text[:1000]

        ann.candidates = parse_table(table)
        announcements.append(ann)

    return announcements
