"""Download the English PDFs of ECB Banking Supervision's supervisory priorities, every edition.

The priorities page (https://www.bankingsupervision.europa.eu/framework/priorities/html/index.en.html)
loads its list of publications from an HTML snippet (index_additional.en.html), in the same <dt isoDate>
+ <dd> format as the supervisory guides page. Each entry has categories; this script keeps those
categorised "Supervisory priorities" or "Risk assessment" (the annual risk assessments published next to
the priorities until 2021) and skips press releases and blog posts (title links under /press/), even when
they share the category. Each edition has an explicit English
PDF link (a[lang=en] ending in .pdf), which is the file downloaded.

Each edition replaces the previous one: within each kind, the newest is edition_status "current" and
older ones are "superseded", with superseded_by naming the next edition. The priorities cover three
years (e.g. 2026-28) and are revised every year, usually in November or December.

Re-running the script is the update mechanism, as for the guides: a replaced file is detected when the
PDF link's cache hash, Last-Modified or Content-Length changes and the bytes differ; it is saved next to
the old one (suffix _vN) and logged in the "history" sheet.

Usage:
    uv run src/download_ecb_priorities.py           # check all editions, download new or changed files
    uv run src/download_ecb_priorities.py --check   # only report what would change; download and write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from download_ecb_guides import fetch, server_meta
from register import read_sheet, write_register

ROOT = Path(__file__).resolve().parent.parent
REGISTER_PATH = ROOT / "data" / "00-source" / "ecb_supervisory_priorities.xlsx"
DOWNLOAD_DIR = ROOT / "data" / "01-raw" / "ecb-priorities"

PAGE_URL = "https://www.bankingsupervision.europa.eu/framework/priorities/html/index.en.html"
KINDS = {"SUPERVISORY PRIORITIES": "supervisory priorities", "RISK ASSESSMENT": "risk assessment"}

USER_AGENT = "banking-regulation-tool/0.1 (ECB supervisory priorities downloader)"

DOCUMENT_COLUMNS = [
    "doc_id", "publication_date", "title", "kind", "edition_status", "superseded_by", "url", "page_url",
    "link_hash", "version", "last_modified", "content_length", "sha256", "local_file", "status",
    "first_seen_at", "last_seen_at", "downloaded_at", "last_checked_at",
]
HISTORY_COLUMNS = [
    "doc_id", "version", "publication_date", "title", "url", "link_hash", "last_modified",
    "content_length", "sha256", "local_file", "change_reason", "downloaded_at",
]


@dataclass
class Edition:
    publication_date: str  # ISO date
    title: str
    kind: str              # "supervisory priorities" or "risk assessment"
    url: str               # English PDF, without query string
    page_url: str          # the HTML version, when there is one
    link_hash: str         # cache-busting query of the PDF link

    @property
    def doc_id(self) -> str:
        """PDF file name without language and extension, e.g. ssm.supervisory_priorities202511."""
        name = urlsplit(self.url).path.rsplit("/", 1)[-1]
        return re.sub(r"\.?en\.pdf$", "", name)


def scrape_editions(session: requests.Session) -> list[Edition]:
    page = session.get(PAGE_URL, timeout=60)
    page.raise_for_status()
    holder = BeautifulSoup(page.text, "html.parser").select_one("[data-snippets]")
    if holder is None:
        raise RuntimeError("No data-snippets list on the priorities page: the page layout may have changed")
    snippet = session.get(urljoin(PAGE_URL, holder["data-snippets"]), timeout=60)
    snippet.raise_for_status()

    editions, seen = [], set()
    for dt in BeautifulSoup(snippet.text, "html.parser").find_all("dt"):
        dd = dt.find_next_sibling("dd")
        title_link = dd.select_one(".title a[href]") if dd else None
        if title_link is None:
            continue
        categories = [c.get_text(strip=True).upper() for c in dd.select(".category")]
        kind = next((KINDS[c] for c in categories if c in KINDS), None)
        # press releases and blog posts about an edition are listed too, under /press/; an edition itself
        # can carry their category as well, so the link decides, not the category
        if kind is None or urlsplit(title_link["href"]).path.startswith("/press/"):
            continue
        links = [a["href"] for a in dd.select("a[lang=en][href]")] + [title_link["href"]]
        pdf = next((h for h in links if ".pdf" in urlsplit(h).path), None)
        if pdf is None:
            continue
        url = urljoin(PAGE_URL, pdf).split("?", 1)[0]
        if url in seen:
            continue
        seen.add(url)
        html = next((h for h in links if urlsplit(h).path.endswith(".html")), "")
        editions.append(Edition(
            publication_date=dt.get("isodate") or datetime.strptime(dt.get_text(strip=True), "%d %B %Y").date().isoformat(),
            title=title_link.get_text(" ", strip=True), kind=kind, url=url,
            page_url=urljoin(PAGE_URL, html) if html else "", link_hash=urlsplit(pdf).query,
        ))
    if not editions:
        raise RuntimeError("No editions parsed from the snippet: the page layout may have changed")
    return editions


def mark_editions(documents: list[dict]) -> None:
    """Within each kind, the newest listed edition is current; older ones point to the next newer one."""
    groups = defaultdict(list)
    for d in documents:
        if d["status"] != "not listed":
            groups[d["kind"]].append(d)
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
    editions = scrape_editions(session)
    print(f"  {len(editions)} editions listed")

    previous = {r["doc_id"]: r for r in read_sheet(REGISTER_PATH, "documents")}
    history = read_sheet(REGISTER_PATH, "history")
    documents, statuses, failures, seen = [], Counter(), 0, set()

    for edition in editions:
        prev = previous.get(edition.doc_id)
        row = dict(prev) if prev else {"doc_id": edition.doc_id, "version": 0, "first_seen_at": now}
        seen.add(edition.doc_id)
        documents.append(row)
        local = ROOT / row["local_file"] if row.get("local_file") else None
        reason = ""

        try:
            if not prev or not prev.get("local_file"):
                reason = "new"
            elif local is None or not local.exists():
                reason = "local file missing"
            elif edition.link_hash != (prev.get("link_hash") or ""):
                reason = "link hash changed"
            else:
                meta = server_meta(fetch(session, edition.url, "HEAD"))
                changed = [k for k in meta if meta[k] and str(prev.get(k) or "") != meta[k]]
                reason = f"server {', '.join(changed)} changed" if changed else ""

            if reason and not args.check:
                resp = fetch(session, edition.url)
                sha = hashlib.sha256(resp.content).hexdigest()
                if prev and sha == prev.get("sha256") and local and local.exists():
                    reason = ""  # signals moved but the bytes are identical: same version
                else:
                    version = max(int(row.get("version") or 0) + (0 if reason == "local file missing" else 1), 1)
                    path = DOWNLOAD_DIR / f"{edition.publication_date}_{edition.doc_id}_v{version}.pdf"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(resp.content)
                    row.update(version=version, sha256=sha, local_file=relative(path), downloaded_at=now)
                    history.append({**{c: row.get(c) for c in HISTORY_COLUMNS}, **server_meta(resp),
                                    "publication_date": edition.publication_date, "title": edition.title,
                                    "url": edition.url, "link_hash": edition.link_hash, "change_reason": reason})
                row.update(server_meta(resp), link_hash=edition.link_hash)
            status = ("new" if not prev or not prev.get("local_file") else "updated") if reason else "up-to-date"
        except (requests.RequestException, RuntimeError) as exc:
            failures += 1
            status = f"error: {exc}"
            print(f"  ! {edition.title[:70]}: {exc}", file=sys.stderr)

        row.update(publication_date=edition.publication_date, title=edition.title, kind=edition.kind,
                   url=edition.url, page_url=edition.page_url, status=status, last_seen_at=now, last_checked_at=now)
        statuses[status.split(":")[0]] += 1
        if status != "up-to-date":
            print(f"  {status:10} {edition.publication_date} {edition.title[:80]}" + (f"  ({reason})" if reason else ""))

    for doc_id, r in previous.items():
        if doc_id not in seen:
            r.update(status="not listed", edition_status="", superseded_by="", last_checked_at=now)
            documents.append(r)
            statuses["not listed"] += 1
            print(f"  not listed {r['publication_date']} {r['title'][:80]}")

    mark_editions(documents)
    current = [d for d in documents if d.get("edition_status") == "current" and d["kind"] == "supervisory priorities"]
    print("  " + ", ".join(f"{n} {s}" for s, n in statuses.items())
          + (f"; current: {current[0]['title']}" if current else ""))
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