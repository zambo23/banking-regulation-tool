"""Download the chapters of the Basel Framework (BCBS consolidated standards) from bis.org.

The Basel Framework (https://www.bis.org/committees/bcbs/basel-framework) is organised in 14
standards (SCO, CAP, RBC, CRE, ...) split into chapters (CRE20, CRE36, ...). Each chapter exists in
versions identified by two dates in the URL:
    .../standard/cre/20/inforce/<effective date>/published/<published date>
A version's text never changes under its URL; BIS publishes an amendment as a new published date,
so the URL is the version key (like a CELEX id).

The listing is the framework timeline (.../basel-framework/timeline?page=N), which lists every
chapter version with a BIS status: "Current", "Forthcoming" (effective in the future),
"Superseded" (replaced by a version with a later effective date) or "Removed on <date>" (replaced
before taking effect by a later publication with the same effective date). Its pager does not end
(pages past the last one repeat it) and its order is not stable between requests, so the full
timeline and the framework page are used to find the chapters, then each chapter's own timeline
to list its versions.
BIS marks a few older versions "Current" next to the newer one; current_doc_id names the latest.

Only Current and Forthcoming versions are downloaded; the others are recorded in the register.
A file once downloaded is kept when its version is later superseded. Each download saves the
chapter column of the version page (status box, paragraphs, footnotes and FAQs) as a standalone
HTML file. The full page is not kept: its navigation and cache tokens change on every request,
whereas the chapter column is byte-stable, so its SHA-256 identifies the text. The chapter PDFs
(.../basel-framework/<node>/chapter.pdf) are not used: they are rendered on request and the
server sometimes returns another version of the chapter under the same link.

Usage:
    python3 src/download_basel.py           # read the timeline, download new current/forthcoming versions
    python3 src/download_basel.py --check   # only report what would change; download and write nothing
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
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from register import read_sheet, write_register

ROOT = Path(__file__).resolve().parent.parent
REGISTER_PATH = ROOT / "data" / "00-source" / "bis_basel_framework.xlsx"
DOWNLOAD_DIR = ROOT / "data" / "01-raw" / "bis-basel"

FRAMEWORK_URL = "https://www.bis.org/committees/bcbs/basel-framework"
TIMELINE_URL = f"{FRAMEWORK_URL}/timeline"
PAGE_SIZE = 25  # versions per timeline page
MAX_PAGES = 100  # safety stop for the pager loop
DOWNLOADED_STATUSES = ("Current", "Forthcoming")

USER_AGENT = "banking-regulation-tool/0.1 (Basel Framework downloader)"
REQUEST_PAUSE_S = 0.5

DOCUMENT_COLUMNS = [
    "doc_id", "chapter", "standard", "standard_title", "chapter_title", "description",
    "effective_date", "published_date", "bis_status", "current_doc_id", "url", "sha256",
    "local_file", "status", "first_seen_at", "last_seen_at", "downloaded_at", "last_checked_at",
]
HISTORY_COLUMNS = [
    "doc_id", "chapter", "effective_date", "published_date", "bis_status", "url", "sha256",
    "local_file", "change_reason", "downloaded_at",
]
VERSION_PATH = re.compile(r"/standard/([a-z]+)/(\d+)/inforce/(\d{4}-\d{2}-\d{2})/published/(\d{4}-\d{2}-\d{2})$")


@dataclass
class Version:
    standard: str        # CRE
    chapter: str         # CRE20
    chapter_title: str
    description: str
    effective_date: str  # ISO date, from the URL
    published_date: str  # ISO date, from the URL
    bis_status: str      # Current, Forthcoming, Superseded, Removed on <date>
    url: str

    @property
    def doc_id(self) -> str:
        return f"{self.chapter}_{self.effective_date}_{self.published_date}"


def read_timeline(session: requests.Session, params: dict, versions: dict[str, Version],
                  standards: dict[str, str]) -> None:
    """Add the chapter versions of one timeline listing (all pages) to versions."""
    for page in range(MAX_PAGES):
        time.sleep(REQUEST_PAUSE_S)
        resp = session.get(TIMELINE_URL, params={**params, "page": page}, timeout=60)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for option in soup.select("select[name=standard] option[value]"):
            if option["value"]:
                standards[option["value"]] = option.get_text(strip=True).split(":", 1)[-1].strip()
        cards = soup.select("a.card-link[href*='/inforce/']")
        added = 0
        for card in cards:
            url = urljoin(FRAMEWORK_URL, card["href"])
            match = VERSION_PATH.search(url)
            if match is None or url in versions:
                continue
            values = {}
            for item in card.select("li.card-highlighted__item"):
                label, value = item.select_one(".card-highlighted__label"), item.find_all("span")[-1]
                values[label.get_text(strip=True) if label else ""] = value.get_text(" ", strip=True)
            standard, number, effective, published = match.groups()
            badge = card.select_one(".card-header .badge")
            heading = card.select_one(".card-heading")
            description = card.select_one(".card-description")
            versions[url] = Version(
                standard=standard.upper(),
                chapter=badge.get_text(strip=True) if badge else f"{standard.upper()}{number}",
                chapter_title=heading.get_text(" ", strip=True) if heading else "",
                description=description.get_text(" ", strip=True) if description else "",
                effective_date=effective, published_date=published,
                bis_status=values.get("Status", ""), url=url,
            )
            added += 1
        if len(cards) < PAGE_SIZE or (page and not added):  # past the last page the pager repeats it
            break


def scrape_timeline(session: requests.Session) -> tuple[list[Version], dict[str, str]]:
    """Every chapter version, and the standard titles from the timeline filter.

    The full timeline and the framework page find the chapters, but the timeline's order is not stable between requests, so a
    version can slip past a page boundary. Each chapter's own timeline then lists all its versions.
    """
    versions: dict[str, Version] = {}
    standards: dict[str, str] = {}
    read_timeline(session, {}, versions, standards)
    if not versions:
        raise RuntimeError("No chapter versions parsed from the timeline: the page layout may have changed")
    time.sleep(REQUEST_PAUSE_S)
    home = session.get(FRAMEWORK_URL, timeout=60)  # links the current version of every chapter
    home.raise_for_status()
    links = [urljoin(FRAMEWORK_URL, a["href"]) for a in BeautifulSoup(home.text, "html.parser").select("a[href*='/inforce/']")]
    chapters = sorted({m.group(1, 2) for m in map(VERSION_PATH.search, [*versions, *links]) if m})
    print(f"  {len(chapters)} chapters on the timeline and the framework page; reading each chapter's versions")
    for standard, number in chapters:
        read_timeline(session, {"standard": standard.upper(), "chapter": number}, versions, standards)
    return list(versions.values()), standards


def current_versions(versions: list[Version]) -> dict[str, str]:
    """Chapter -> doc_id of its current version. BIS marks a few older versions "Current" too
    (e.g. SRP31 effective 2019-12-15 and 2026-01-01); the latest effective, then published, wins."""
    current = {}
    for v in sorted((v for v in versions if v.bis_status == "Current"), key=lambda v: (v.effective_date, v.published_date)):
        current[v.chapter] = v.doc_id
    return current


def chapter_column(html: str, version: Version) -> str:
    """The chapter column of a version page, checked against the version's effective date."""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("div.chapters-content")
    column = content.find_parent("div", class_="col-md-7") if content else None
    if column is None:
        raise RuntimeError("no chapter content on the page: the page layout may have changed")
    stated = re.search(r"Effective as of:\s*(\d{1,2} \w{3} \d{4})", column.get_text(" ", strip=True))
    if stated and datetime.strptime(stated.group(1), "%d %b %Y").date().isoformat() != version.effective_date:
        raise RuntimeError(f"page states effective date {stated.group(1)}, URL says {version.effective_date}")
    return str(column)


def standalone(column: str, version: Version) -> bytes:
    title = f"{version.chapter} {version.chapter_title} (effective {version.effective_date}, published {version.published_date})"
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>{title}</title>\n<base href=\"https://www.bis.org/\">\n"
            f"<link rel=\"canonical\" href=\"{version.url}\">\n</head>\n<body>\n{column}\n</body>\n</html>\n").encode()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report changes without downloading or writing")
    args = parser.parse_args()

    now = datetime.now().isoformat(timespec="seconds")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    print(f"Reading {TIMELINE_URL}")
    versions, standards = scrape_timeline(session)
    print(f"  {len(versions)} chapter versions listed, {len({v.chapter for v in versions})} chapters")

    previous = {r["doc_id"]: r for r in read_sheet(REGISTER_PATH, "documents")}
    history = read_sheet(REGISTER_PATH, "history")
    current = current_versions(versions)
    documents, statuses, failures, seen = [], Counter(), 0, set()

    for version in sorted(versions, key=lambda v: v.doc_id):
        if version.doc_id in seen:
            continue
        seen.add(version.doc_id)
        prev = previous.get(version.doc_id)
        row = dict(prev) if prev else {"doc_id": version.doc_id, "first_seen_at": now}
        documents.append(row)
        local = ROOT / row["local_file"] if row.get("local_file") else None
        moved = prev and prev.get("bis_status") != version.bis_status
        reason = ""

        try:
            if version.bis_status not in DOWNLOADED_STATUSES and not local:
                status = "not downloaded"
            elif local and local.exists():
                status = "up-to-date"
            else:
                reason = "local file missing" if local else "new"
                if not args.check:
                    resp = session.get(version.url, timeout=120)
                    time.sleep(REQUEST_PAUSE_S)
                    resp.raise_for_status()
                    content = standalone(chapter_column(resp.text, version), version)
                    path = DOWNLOAD_DIR / version.standard / f"{version.doc_id}.html"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                    row.update(sha256=hashlib.sha256(content).hexdigest(), local_file=relative(path), downloaded_at=now)
                    history.append({**{c: row.get(c) for c in HISTORY_COLUMNS}, "chapter": version.chapter,
                                    "effective_date": version.effective_date, "published_date": version.published_date,
                                    "bis_status": version.bis_status, "url": version.url, "change_reason": reason})
                status = "new" if reason == "new" else "updated"
        except (requests.RequestException, RuntimeError) as exc:
            failures += 1
            status = f"error: {exc}"
            print(f"  ! {version.doc_id}: {exc}", file=sys.stderr)

        if moved:
            print(f"  status     {version.doc_id} {version.chapter_title[:60]}: {prev.get('bis_status')} -> {version.bis_status}")
        row.update(chapter=version.chapter, standard=version.standard, standard_title=standards.get(version.standard, ""),
                   chapter_title=version.chapter_title, description=version.description,
                   effective_date=version.effective_date, published_date=version.published_date,
                   bis_status=version.bis_status, current_doc_id=current.get(version.chapter, ""),
                   url=version.url, status=status, last_seen_at=now, last_checked_at=now)
        statuses[status.split(":")[0]] += 1
        if status not in ("up-to-date", "not downloaded"):
            print(f"  {status:10} {version.doc_id} {version.chapter_title[:60]} [{version.bis_status}]")

    for doc_id, r in previous.items():
        if doc_id not in seen:
            r.update(status="not listed", current_doc_id=current.get(r.get("chapter"), ""), last_checked_at=now)
            documents.append(r)
            statuses["not listed"] += 1
            print(f"  not listed {doc_id} {(r.get('chapter_title') or '')[:60]}")

    print("  " + ", ".join(f"{n} {s}" for s, n in statuses.items()))
    if args.check:
        print("Nothing written (--check)")
        return 0

    documents.sort(key=lambda d: (d["chapter"], d["effective_date"], d["published_date"]))
    write_register(REGISTER_PATH, {"documents": (DOCUMENT_COLUMNS, documents),
                                   "history": (HISTORY_COLUMNS, history)})
    print(f"Register written to {relative(REGISTER_PATH)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
