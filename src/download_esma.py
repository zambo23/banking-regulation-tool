"""Download the documents in the ESMA library section "Guidelines and Technical standards".

The ESMA library (https://www.esma.europa.eu/databases-library/esma-library) is a table filtered
on a section facet; section 35 is "Guidelines and Technical standards". Each row has a date, an
ESMA reference, a title linking to the document page, its sections and type, and a link to the
main document (usually an English PDF, sometimes an Excel file). Each row becomes one document in
the register, identified by a stable doc_id derived from its document page URL.

Re-running the script is the update mechanism. A document gets a new version when
- its file URL is unchanged but the server's ETag or Last-Modified changed and the downloaded
  content differs, or
- its file URL changed (ESMA re-uploaded the file) and the content differs.
Content-Length is recorded from the download but not compared: ESMA answers HEAD requests with
a Content-Length of 0. New versions are saved next to the old ones (suffix _vN) and logged in the
"history" sheet. Rows that disappear from the listing are kept with status "not listed"; rows
without a main document are kept with status "no file", and translations (file names such as
..._bg_tra.pdf, or titles in another language) with status "translation", without downloading them.

Usage:
    python3 src/download_esma.py           # check all items, download new or changed files
    python3 src/download_esma.py --check   # only report what would change; download and write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from register import read_sheet, write_register

ROOT = Path(__file__).resolve().parent.parent
REGISTER_PATH = ROOT / "data" / "00-source" / "esma_library.xlsx"
DOWNLOAD_DIR = ROOT / "data" / "01-raw" / "esma"

LISTING_URL = "https://www.esma.europa.eu/databases-library/esma-library"
SECTION = "35"  # "Guidelines and Technical standards"
PAGE_SIZE = 50  # 100 works on page 0 only: later pages return HTTP 500
MAX_PAGES = 100  # safety stop for the pager loop

USER_AGENT = "banking-regulation-tool/0.1 (ESMA library downloader)"
REQUEST_PAUSE_S = 0.5
PROGRESS_PAGES = 5  # print a progress line every N listing pages
PROGRESS_ITEMS = 50  # and every N items checked

DOCUMENT_COLUMNS = [
    "doc_id", "publication_date", "title", "esma_reference", "doc_type", "sections", "file_type",
    "url", "page_url", "version", "etag", "last_modified", "content_length", "sha256",
    "local_file", "status", "first_seen_at", "last_seen_at", "downloaded_at", "last_checked_at",
]
HISTORY_COLUMNS = [
    "doc_id", "version", "publication_date", "title", "url", "etag", "last_modified",
    "content_length", "sha256", "local_file", "change_reason", "downloaded_at",
]
CHANGE_HEADERS = ("etag", "last_modified")  # Content-Length is unreliable on HEAD
# The listing also carries translations of older guidelines as separate rows. Their file names end in a
# language code (..._bg_tra.pdf, ..._de_cor2.pdf, 2013-322_hr.pdf, 2011-188pt.pdf, ...-enbg_0.pdf, also
# the non-ISO cz and ee) or start with one (bg_-_jc_2014_43_...). ESMA sometimes gives a translation the
# English title, so the file name is checked first; a title with non-ASCII letters catches the rest.
LANGUAGES = "bg|cs|cz|da|de|ee|el|es|et|fi|fr|ga|hr|hu|it|lt|lv|mt|nl|pl|pt|ro|sk|sl|sv"
TRANSLATION_NAME = re.compile(
    rf"(?:^|[_\-\d]|en)(?:{LANGUAGES})(?:[_-](?:tra|cor)\d*)?(?:[_-](?:\d+|bis))?_?$|^(?:{LANGUAGES})_-_", re.IGNORECASE)
RETRIES = 3  # ESMA answers bursts with HTTP 429


@dataclass
class Item:
    publication_date: str  # ISO date
    title: str
    esma_reference: str
    doc_type: str
    sections: str
    page_url: str
    url: str  # main document; empty when the row has none

    @property
    def doc_id(self) -> str:
        return hashlib.sha1(self.page_url.encode()).hexdigest()[:8]

    @property
    def filename(self) -> str:
        return unquote(urlsplit(self.url).path.rsplit("/", 1)[-1])

    @property
    def is_translation(self) -> bool:
        stem = self.filename.rpartition(".")[0] or self.filename
        return bool(TRANSLATION_NAME.search(stem)) or any(c.isalpha() and ord(c) > 127 for c in self.title)

    @property
    def extension(self) -> str:
        if not self.url:
            return ""
        return self.filename.rpartition(".")[2].lower() or "bin"


def cell(row, field: str):
    return row.select_one(f":scope > td.views-field-{field}")


def scrape_listing(session: requests.Session) -> list[Item]:
    items = []
    for page in range(MAX_PAGES):
        params = {"f[0]": f"basic_section:{SECTION}", "items_per_page": PAGE_SIZE, "page": page}
        resp = session.get(LISTING_URL, params=params, timeout=60)
        resp.raise_for_status()
        table = BeautifulSoup(resp.text, "html.parser").select_one("table.views-table")
        # rows of the listing itself; the Info column holds nested tables of related documents
        rows = [r for r in table.select(":scope > tbody > tr") if cell(r, "title")] if table else []
        if not rows:
            break
        if page and page % PROGRESS_PAGES == 0:
            print(f"  ... listing page {page}, {len(items)} items so far")
        for row in rows:
            link = cell(row, "title").find("a", href=True)
            main = cell(row, "field-main-document").find("a", href=True)
            day = re.search(r"\d{2}/\d{2}/\d{4}", cell(row, "created").get_text())
            if link is None or day is None:
                continue
            items.append(Item(
                publication_date=datetime.strptime(day.group(0), "%d/%m/%Y").date().isoformat(),
                title=link.get_text(" ", strip=True),
                esma_reference=cell(row, "field-document-reference").get_text(" ", strip=True),
                doc_type=cell(row, "field-document-type").get_text(" ", strip=True),
                sections=cell(row, "field-document-section").get_text(" ", strip=True),
                page_url=urljoin(LISTING_URL, link["href"]),
                url=urljoin(LISTING_URL, main["href"]) if main else "",
            ))
        time.sleep(REQUEST_PAUSE_S)
    if not items:
        raise RuntimeError("No items parsed from the ESMA library: the page layout may have changed")
    return items


def request(session: requests.Session, method: str, url: str, timeout: int) -> requests.Response:
    """GET or HEAD with a pause, retrying on HTTP 429 after Retry-After (or 30 s, 60 s, ...)."""
    for attempt in range(RETRIES + 1):
        time.sleep(REQUEST_PAUSE_S)
        resp = session.request(method, url, timeout=timeout, allow_redirects=True)
        if resp.status_code != 429 or attempt == RETRIES:
            break
        wait = resp.headers.get("Retry-After", "")
        seconds = int(wait) if wait.isdigit() else 30 * (attempt + 1)
        print(f"  ... rate limited by ESMA (HTTP 429), waiting {seconds}s before retry {attempt + 1}/{RETRIES}")
        time.sleep(seconds)
    resp.raise_for_status()
    return resp


def head(session: requests.Session, url: str) -> dict[str, str]:
    resp = request(session, "HEAD", url, 60)
    return {"etag": resp.headers.get("ETag", ""), "last_modified": resp.headers.get("Last-Modified", "")}


def download(session: requests.Session, url: str) -> tuple[bytes, dict[str, str]]:
    resp = request(session, "GET", url, 300)
    if "text/html" in resp.headers.get("Content-Type", ""):
        raise RuntimeError("server returned an HTML page instead of a document")
    return resp.content, {"etag": resp.headers.get("ETag", ""), "last_modified": resp.headers.get("Last-Modified", ""),
                          "content_length": str(len(resp.content))}


def file_path(item: Item, version: int) -> Path:
    stem = re.sub(r"[^\w.-]+", "_", item.filename.rpartition(".")[0] or item.filename).strip("_")[:80]
    return DOWNLOAD_DIR / item.publication_date[:4] / f"{item.publication_date}_{stem}_{item.doc_id}_v{version}.{item.extension}"


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report changes without downloading or writing")
    args = parser.parse_args()

    now = datetime.now().isoformat(timespec="seconds")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    print(f"Reading {LISTING_URL} (section {SECTION}, Guidelines and Technical standards)")
    items = scrape_listing(session)
    print(f"  {len(items)} items listed")

    previous = {r["doc_id"]: r for r in read_sheet(REGISTER_PATH, "documents")}
    history = read_sheet(REGISTER_PATH, "history")
    documents, statuses, failures, seen = [], Counter(), 0, set()

    for i, item in enumerate(items):
        if i and i % PROGRESS_ITEMS == 0:
            print(f"  ... {i}/{len(items)} items checked")
        if item.doc_id in seen:  # the same document listed twice
            continue
        seen.add(item.doc_id)
        prev = previous.get(item.doc_id)
        row = dict(prev) if prev else {"doc_id": item.doc_id, "version": 0, "first_seen_at": now}
        documents.append(row)
        local = ROOT / row["local_file"] if row.get("local_file") else None
        reason = ""

        try:
            if not item.url:
                status = "no file"
            elif item.is_translation:
                status = "translation"  # English texts only; files fetched earlier are kept
            else:
                if not prev or not prev.get("local_file"):
                    reason = "new"
                elif prev.get("url") != item.url:
                    reason = "file re-uploaded under a new URL"
                elif local is None or not local.exists():
                    reason = "local file missing"
                else:
                    meta = head(session, item.url)
                    changed = [k for k in CHANGE_HEADERS if meta[k] and str(prev.get(k) or "") != meta[k]]
                    reason = f"server {', '.join(changed)} changed" if changed else ""

                if reason and not args.check:
                    content, meta = download(session, item.url)
                    sha = hashlib.sha256(content).hexdigest()
                    if prev and sha == prev.get("sha256") and local and local.exists():
                        reason = ""  # headers or URL moved but the bytes are identical: same version
                    else:
                        version = max(int(row.get("version") or 0) + (0 if reason == "local file missing" else 1), 1)
                        path = file_path(item, version)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(content)
                        row.update(version=version, sha256=sha, local_file=relative(path), downloaded_at=now)
                        history.append({**{c: row.get(c) for c in HISTORY_COLUMNS}, **meta,
                                        "publication_date": item.publication_date, "title": item.title,
                                        "url": item.url, "change_reason": reason})
                    row.update(meta)
                status = ("new" if not prev or not prev.get("local_file") else "updated") if reason else "up-to-date"
        except (requests.RequestException, RuntimeError) as exc:
            failures += 1
            status = f"error: {exc}"
            print(f"  ! {item.title[:70]}: {exc}", file=sys.stderr)

        row.update(publication_date=item.publication_date, title=item.title, esma_reference=item.esma_reference,
                   doc_type=item.doc_type, sections=item.sections, file_type=item.extension, url=item.url,
                   page_url=item.page_url, status=status, last_seen_at=now, last_checked_at=now)
        statuses[status.split(":")[0]] += 1
        if status not in ("up-to-date", "no file", "translation"):
            print(f"  {status:10} {item.publication_date} {item.title[:80]}" + (f"  ({reason})" if reason else ""))

    for doc_id, r in previous.items():
        if doc_id not in seen:
            r.update(status="not listed", last_checked_at=now)
            documents.append(r)
            statuses["not listed"] += 1
            print(f"  not listed {r['publication_date']} {r['title'][:80]}")

    print("  " + ", ".join(f"{n} {s}" for s, n in statuses.items()))
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
