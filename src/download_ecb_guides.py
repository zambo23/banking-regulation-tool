"""Download the English PDFs of the ECB Banking Supervision supervisory guides.

The guides page loads its list from an HTML snippet (the `data-snippets` attribute); each
entry has a date, a title and an explicit English link (`a[lang=en]`).

Two kinds of versioning are tracked:
- Editions: the list keeps old editions next to new ones (e.g. four "ECB guide to internal
  models"). Entries are grouped by a normalised title (guide_key); the newest entry of each
  group is "current", older ones are "superseded" and point to their successor.
- File versions: re-running the script detects a replaced file when the link's cache hash
  (the ?query on the title link), Last-Modified or Content-Length changes and the downloaded
  bytes differ. New versions are saved next to the old ones (suffix _vN) and logged in the
  "history" sheet. Entries that disappear from the list are kept with status "not listed".

Usage:
    python src/download_ecb_guides.py           # check all guides, download new or changed files
    python src/download_ecb_guides.py --check   # only report what would change; download and write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from register import read_sheet, write_register

ROOT = Path(__file__).resolve().parent.parent
REGISTER_PATH = ROOT / "data" / "00-source" / "ecb_supervisory_guides.xlsx"
DOWNLOAD_DIR = ROOT / "data" / "01-raw" / "ecb-guides"

PAGE_URL = "https://www.bankingsupervision.europa.eu/framework/supervisory-policy/html/supervisoryguides.en.html"

USER_AGENT = "banking-regulation-tool/0.1 (ECB supervisory guides downloader)"
REQUEST_PAUSE_S = 0.5

DOCUMENT_COLUMNS = [
    "doc_id", "publication_date", "title", "guide_key", "edition_status", "superseded_by",
    "last_updated_note", "url", "link_hash", "version", "last_modified", "content_length", "sha256",
    "local_file", "status", "first_seen_at", "last_seen_at", "downloaded_at", "last_checked_at",
]
HISTORY_COLUMNS = [
    "doc_id", "version", "publication_date", "title", "url", "link_hash", "last_modified",
    "content_length", "sha256", "local_file", "change_reason", "downloaded_at",
]


@dataclass
class Guide:
    publication_date: str  # ISO date
    title: str
    url: str        # English PDF, without query string
    link_hash: str  # cache-busting query of the title link; changes when ECB replaces the file
    last_updated_note: str

    @property
    def doc_id(self) -> str:
        """File name without language and extension, e.g. ssm.supervisory_guides_202609."""
        name = urlsplit(self.url).path.rsplit("/", 1)[-1]
        return re.sub(r"\.?en\.pdf$", "", name)


def guide_key(title: str) -> str:
    """Normalised title used to group editions of the same guide."""
    key = title.lower()
    key = re.sub(r"\s*[-–]\s*consolidated version$", "", key)
    key = re.sub(r"^(ecb|ssm)\s+", "", key)
    return " ".join(key.split())


def scrape_guides(session: requests.Session) -> list[Guide]:
    page = session.get(PAGE_URL, timeout=60)
    page.raise_for_status()
    holder = BeautifulSoup(page.text, "html.parser").select_one("[data-snippets]")
    if holder is None:
        raise RuntimeError("No data-snippets list on the guides page: the page layout may have changed")
    snippet = session.get(urljoin(PAGE_URL, holder["data-snippets"]), timeout=60)
    snippet.raise_for_status()

    guides = []
    for dt in BeautifulSoup(snippet.text, "html.parser").find_all("dt"):
        dd = dt.find_next_sibling("dd")
        title_link = dd.select_one(".title a[href]") if dd else None
        if title_link is None:
            continue
        english = dd.select_one("a[lang=en][href]")
        url = urljoin(PAGE_URL, (english or title_link)["href"])
        note = dd.select_one(".last-updated")
        guides.append(Guide(
            publication_date=dt.get("isodate") or datetime.strptime(dt.get_text(strip=True), "%d %B %Y").date().isoformat(),
            title=title_link.get_text(" ", strip=True),
            url=url.split("?", 1)[0],
            link_hash=urlsplit(title_link["href"]).query,
            last_updated_note=note.get_text(strip=True) if note else "",
        ))
    if not guides:
        raise RuntimeError("No guides parsed from the snippet: the page layout may have changed")
    return guides


def match_previous(guides: list[Guide], previous: list[dict]) -> list[dict | None]:
    """Pair each listed guide with its register row: same URL first, then same date and title."""
    by_url = {r["url"]: r for r in previous}
    matched: list[dict | None] = [by_url.get(g.url) for g in guides]
    used = {id(r) for r in matched if r}
    by_date_title = defaultdict(list)
    for r in previous:
        if id(r) not in used:
            by_date_title[(r["publication_date"], r["title"])].append(r)
    for i, g in enumerate(guides):
        if matched[i] is None and by_date_title.get((g.publication_date, g.title)):
            matched[i] = by_date_title[(g.publication_date, g.title)].pop(0)
    return matched


def fetch(session: requests.Session, url: str, method: str = "GET") -> requests.Response:
    time.sleep(REQUEST_PAUSE_S)
    resp = session.request(method, url, timeout=300, allow_redirects=True)
    resp.raise_for_status()
    if method == "GET" and "pdf" not in resp.headers.get("Content-Type", ""):
        raise RuntimeError(f"expected a PDF, got {resp.headers.get('Content-Type')}")
    return resp


def server_meta(resp: requests.Response) -> dict[str, str]:
    return {"last_modified": resp.headers.get("Last-Modified", ""),
            "content_length": resp.headers.get("Content-Length", "")}


def mark_editions(documents: list[dict]) -> None:
    """Newest listed entry per guide_key is current; older ones point to the next newer edition."""
    groups = defaultdict(list)
    for d in documents:
        if d["status"] != "not listed":
            groups[d["guide_key"]].append(d)
    for editions in groups.values():
        editions.sort(key=lambda d: d["publication_date"], reverse=True)
        for newer, d in zip([None, *editions], editions):
            d["edition_status"] = "superseded" if newer else "current"
            d["superseded_by"] = newer["doc_id"] if newer else ""


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report changes without downloading or writing")
    args = parser.parse_args()

    now = datetime.now().isoformat(timespec="seconds")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    print(f"Reading {PAGE_URL}")
    guides = scrape_guides(session)
    print(f"  {len(guides)} guides listed")

    previous = read_sheet(REGISTER_PATH, "documents")
    history = read_sheet(REGISTER_PATH, "history")
    matched = match_previous(guides, previous)
    documents, statuses, failures = [], Counter(), 0
    taken = {r["doc_id"] for r in previous}

    for guide, prev in zip(guides, matched):
        if prev:
            row = dict(prev)
        else:
            doc_id = guide.doc_id if guide.doc_id not in taken else f"{guide.doc_id}~{guide.publication_date}"
            row = {"doc_id": doc_id, "version": 0, "first_seen_at": now}
        taken.add(row["doc_id"])
        documents.append(row)
        local = ROOT / row["local_file"] if row.get("local_file") else None
        reason = ""

        try:
            if not prev:
                reason = "new"
            elif prev["url"] != guide.url:
                reason = "file replaced under a new URL"
            elif local is None or not local.exists():
                reason = "local file missing"
            elif guide.link_hash != (prev.get("link_hash") or ""):
                reason = "link hash changed"
            else:
                meta = server_meta(fetch(session, guide.url, "HEAD"))
                changed = [k for k in meta if meta[k] and str(prev.get(k) or "") != meta[k]]
                reason = f"server {', '.join(changed)} changed" if changed else ""

            if reason and not args.check:
                resp = fetch(session, guide.url)
                sha = hashlib.sha256(resp.content).hexdigest()
                if prev and sha == prev.get("sha256") and local and local.exists():
                    reason = ""  # signals moved but the bytes are identical: same version
                else:
                    version = int(row.get("version") or 0) + (0 if reason == "local file missing" else 1)
                    version = max(version, 1)
                    path = DOWNLOAD_DIR / f"{guide.publication_date}_{row['doc_id']}_v{version}.pdf"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(resp.content)
                    row.update(version=version, sha256=sha, local_file=relative(path), downloaded_at=now)
                    history.append({**{c: row.get(c) for c in HISTORY_COLUMNS}, **server_meta(resp),
                                    "publication_date": guide.publication_date, "title": guide.title,
                                    "url": guide.url, "link_hash": guide.link_hash, "change_reason": reason})
                row.update(server_meta(resp), link_hash=guide.link_hash)
            status = ("new" if not prev else "updated") if reason else "up-to-date"
        except (requests.RequestException, RuntimeError) as exc:
            failures += 1
            status = f"error: {exc}"
            print(f"  ! {guide.title[:70]}: {exc}", file=sys.stderr)

        row.update(publication_date=guide.publication_date, title=guide.title, guide_key=guide_key(guide.title),
                   url=guide.url, last_updated_note=guide.last_updated_note,
                   status=status, last_seen_at=now, last_checked_at=now)
        statuses[status.split(":")[0]] += 1
        if status != "up-to-date":
            print(f"  {status:10} {guide.publication_date} {guide.title[:80]}" + (f"  ({reason})" if reason else ""))

    listed = {id(r) for r in matched if r}
    for r in previous:
        if id(r) not in listed:
            r.update(status="not listed", edition_status="", superseded_by="", last_checked_at=now)
            documents.append(r)
            statuses["not listed"] += 1
            print(f"  not listed {r['publication_date']} {r['title'][:80]}")

    mark_editions(documents)
    superseded = sum(d.get("edition_status") == "superseded" for d in documents)
    print("  " + ", ".join(f"{n} {s}" for s, n in statuses.items()) + f"; {superseded} superseded editions")
    if args.check:
        print("Nothing written (--check)")
        return 0

    documents.sort(key=lambda d: (d["publication_date"], d["title"]), reverse=True)
    write_register(REGISTER_PATH, {"documents": (DOCUMENT_COLUMNS, documents),
                                   "history": (HISTORY_COLUMNS, history)})
    print(f"Register written to {relative(REGISTER_PATH)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
