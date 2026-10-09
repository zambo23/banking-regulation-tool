"""Download the documents in the EBA publications listing filtered on one document type.

Supported types are listed in PUBLICATION_TYPES (Guidelines, draft RTS, draft ITS, Reports, Consultation papers); each has its own
register in data/00-source and its own download folder in data/01-raw.

Every item of the listing (all pages) links directly to an English file, mostly the final
report PDF, sometimes an Excel/Word template or a zip. Each item becomes one document in the
register, identified by a stable doc_id assigned on first sight.

Re-running the script is the update mechanism. A document gets a new version when
- its URL is unchanged but the server's ETag / Last-Modified / Content-Length changed and the
  downloaded content differs, or
- its URL changed while publication date and title stayed the same (EBA re-uploaded the file).
New versions are saved next to the old ones (suffix _vN) and logged in the "history" sheet.
Items that disappear from the listing are kept in the register with status "not listed".

The EBA reference (e.g. EBA/GL/YYYY/NN, EBA/RTS/YYYY/NN) is read from the title, the file
name or, when poppler's `pdftotext` is installed, page 1 of the PDF; references of the
listing's own kind are preferred. Documents sharing a reference with a later item (amending
or consolidated versions, corrigenda) are flagged in "later_same_reference" so possibly
superseded texts are easy to spot.

Usage:
    python src/download_eba_publications.py guidelines        # check all items, download new or changed files
    python src/download_eba_publications.py rts --check       # only report what would change; download and write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from register import read_sheet, write_register

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class PublicationType:
    label: str
    document_type: str  # value of the listing's document_type filter
    ref_kind: str       # preferred kind in EBA/<kind>/YYYY/NN references
    register: Path
    download_dir: Path


PUBLICATION_TYPES = {
    "guidelines": PublicationType("Guidelines", "250", "GL",
                                  ROOT / "data" / "00-source" / "eba_guidelines.xlsx",
                                  ROOT / "data" / "01-raw" / "eba-guidelines"),
    "rts": PublicationType("Draft Regulatory Technical Standards", "248", "RTS",
                           ROOT / "data" / "00-source" / "eba_rts.xlsx",
                           ROOT / "data" / "01-raw" / "eba-rts"),
    "its": PublicationType("Draft Implementing Technical Standards", "247", "ITS",
                           ROOT / "data" / "00-source" / "eba_its.xlsx",
                           ROOT / "data" / "01-raw" / "eba-its"),
    "reports": PublicationType("Reports", "257", "REP",
                               ROOT / "data" / "00-source" / "eba_reports.xlsx",
                               ROOT / "data" / "01-raw" / "eba-reports"),
    "cp": PublicationType("Consultation papers", "244", "CP",
                          ROOT / "data" / "00-source" / "eba_consultation_papers.xlsx",
                          ROOT / "data" / "01-raw" / "eba-consultation-papers"),
}

LISTING_URL = "https://www.eba.europa.eu/publications-and-media/publications"
MAX_PAGES = 200  # safety stop for the pager loop

USER_AGENT = "banking-regulation-tool/0.1 (EBA publications downloader)"
REQUEST_PAUSE_S = 0.5

DATE = re.compile(r"\b\d{1,2} [A-Z][a-z]+ \d{4}\b")
# Separators exclude line breaks: "EBA/Rep/2022" followed by a date line "08 April 2022" is not EBA/REP/2022/08.
EBA_REF = re.compile(r"\bEBA[ \t/_-]*(GL|RTS|ITS|REP|CP|REC|OP|DC)[ \t/_-]*(\d{4})[ \t/_-]+(\d{1,2})\b", re.IGNORECASE)

DOCUMENT_COLUMNS = [
    "doc_id", "publication_date", "title", "eba_reference", "later_same_reference", "file_type",
    "url", "press_release_url", "version", "etag", "last_modified", "content_length", "sha256",
    "local_file", "status", "first_seen_at", "last_seen_at", "downloaded_at", "last_checked_at",
]
HISTORY_COLUMNS = [
    "doc_id", "version", "publication_date", "title", "url", "etag", "last_modified",
    "content_length", "sha256", "local_file", "change_reason", "downloaded_at",
]


@dataclass
class Item:
    publication_date: str  # ISO date
    title: str
    url: str
    press_release_url: str

    @property
    def filename(self) -> str:
        return unquote(urlsplit(self.url).path.rsplit("/", 1)[-1])

    @property
    def is_page(self) -> bool:
        """True for publications released as a web page (e.g. Risk Assessment Reports) instead of a file."""
        return "/sites/default/files/" not in urlsplit(self.url).path

    @property
    def extension(self) -> str:
        return "html" if self.is_page else (self.filename.rpartition(".")[2].lower() or "bin")


def scrape_listing(session: requests.Session, ptype: PublicationType) -> list[Item]:
    items = []
    params = {"text": "", "document_type": ptype.document_type, "media_topics": "All"}
    for page in range(MAX_PAGES):
        resp = session.get(LISTING_URL, params={**params, "page": page}, timeout=60)
        resp.raise_for_status()
        teasers = BeautifulSoup(resp.text, "html.parser").select("article.teaser")
        if not teasers:
            break
        for teaser in teasers:
            link = teaser.select_one(".teaser__title a[href]")
            when = teaser.select_one(".link-icon--calendar") or teaser.select_one(".teaser__metadata")
            day = DATE.search(when.get_text(" ", strip=True)) if when else None
            if link is None or day is None:
                continue
            press = next((a["href"] for a in teaser.select(".teaser__actions a[href]")
                          if "press-releases" in a["href"]), "")
            items.append(Item(
                publication_date=datetime.strptime(day.group(0), "%d %B %Y").date().isoformat(),
                title=link.get_text(strip=True),
                url=urljoin(LISTING_URL, link["href"]),
                press_release_url=urljoin(LISTING_URL, press) if press else "",
            ))
        time.sleep(REQUEST_PAUSE_S)
    if not items:
        raise RuntimeError("No items parsed from the EBA listing: the page layout may have changed")
    return items


def match_previous(items: list[Item], previous: list[dict]) -> list[dict | None]:
    """Pair each listed item with its register row: same URL first, then same date and title."""
    by_url = {r["url"]: r for r in previous}
    matched: list[dict | None] = [by_url.get(item.url) for item in items]
    used = {id(r) for r in matched if r}
    by_date_title = defaultdict(list)
    for r in previous:
        if id(r) not in used:
            by_date_title[(r["publication_date"], r["title"])].append(r)
    for i, item in enumerate(items):
        if matched[i] is None:
            candidates = by_date_title.get((item.publication_date, item.title))
            if candidates:
                matched[i] = candidates.pop(0)
    return matched


def new_doc_id(item: Item, taken: set[str]) -> str:
    digest = hashlib.sha1(item.url.encode()).hexdigest()
    for length in range(8, len(digest) + 1):
        if digest[:length] not in taken:
            return digest[:length]
    raise RuntimeError(f"Cannot allocate a doc_id for {item.url}")


def head(session: requests.Session, url: str) -> dict[str, str]:
    time.sleep(REQUEST_PAUSE_S)
    resp = session.head(url, timeout=60, allow_redirects=True)
    resp.raise_for_status()
    return {"etag": resp.headers.get("ETag", ""), "last_modified": resp.headers.get("Last-Modified", ""),
            "content_length": resp.headers.get("Content-Length", "")}


def file_path(ptype: PublicationType, item: Item, doc_id: str, version: int) -> Path:
    stem = item.filename if item.is_page else item.filename.rpartition(".")[0] or item.filename
    stem = re.sub(r"[^\w.-]+", "_", stem).strip("_")[:80]
    year = item.publication_date[:4]
    return ptype.download_dir / year / f"{item.publication_date}_{stem}_{doc_id}_v{version}.{item.extension}"


def download(session: requests.Session, item: Item) -> tuple[bytes, dict[str, str]]:
    time.sleep(REQUEST_PAUSE_S)
    resp = session.get(item.url, timeout=300)
    resp.raise_for_status()
    if not item.is_page and "text/html" in resp.headers.get("Content-Type", ""):
        raise RuntimeError("server returned an HTML page instead of a document")
    meta = {"etag": resp.headers.get("ETag", ""), "last_modified": resp.headers.get("Last-Modified", ""),
            "content_length": resp.headers.get("Content-Length", str(len(resp.content)))}
    return resp.content, meta


def fingerprint(item: Item, content: bytes) -> str:
    """SHA-256 of a file; for web pages, of the normalised <main> text, so page chrome and tokens don't count."""
    if item.is_page:
        main = BeautifulSoup(content, "html.parser").find("main")
        if main is not None:
            content = " ".join(main.get_text(" ").split()).encode()
    return hashlib.sha256(content).hexdigest()


def eba_reference(ptype: PublicationType, item: Item, path: Path | None) -> str:
    """EBA/<kind>/YYYY/NN from title, file name, or page 1 of the PDF (needs pdftotext).

    A reference of the listing's own kind wins over any other, e.g. EBA/RTS/... in the RTS listing.
    """
    sources = [item.title, item.filename]
    if path and path.suffix == ".pdf" and shutil.which("pdftotext"):
        result = subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(path), "-"],
                                capture_output=True, text=True, errors="replace")
        sources.append(result.stdout)
    refs = [m for text in sources for m in EBA_REF.finditer(text)]
    best = next((m for m in refs if m.group(1).upper() == ptype.ref_kind), refs[0] if refs else None)
    return f"EBA/{best.group(1).upper()}/{best.group(2)}/{int(best.group(3)):02d}" if best else ""


def flag_later_same_reference(documents: list[dict]) -> None:
    groups = defaultdict(list)
    for d in documents:
        if d.get("eba_reference"):
            groups[d["eba_reference"]].append(d)
    for d in documents:
        later = [o["doc_id"] for o in groups.get(d.get("eba_reference"), [])
                 if o["publication_date"] > d["publication_date"]]
        d["later_same_reference"] = "; ".join(later)


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("type", choices=PUBLICATION_TYPES, help="publication type to download")
    parser.add_argument("--check", action="store_true", help="report changes without downloading or writing")
    parser.add_argument("--rescan-references", action="store_true",
                        help="re-read eba_reference for every downloaded document, not only new or changed ones")
    args = parser.parse_args()
    ptype = PUBLICATION_TYPES[args.type]

    now = datetime.now().isoformat(timespec="seconds")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    print(f"Reading {LISTING_URL} ({ptype.label})")
    items = scrape_listing(session, ptype)
    print(f"  {len(items)} items listed")

    previous = read_sheet(ptype.register, "documents")
    history = read_sheet(ptype.register, "history")
    matched = match_previous(items, previous)
    taken = {r["doc_id"] for r in previous}
    documents, statuses, failures = [], Counter(), 0

    for item, prev in zip(items, matched):
        row = dict(prev) if prev else {"doc_id": new_doc_id(item, taken), "version": 0, "first_seen_at": now}
        taken.add(row["doc_id"])
        documents.append(row)
        local = ROOT / row["local_file"] if row.get("local_file") else None
        reason, fetched = "", None

        try:
            if not prev:
                reason = "new"
            elif prev["url"] != item.url:
                reason = "file re-uploaded under a new URL"
            elif local is None or not local.exists():
                reason = "local file missing"
            elif item.is_page:
                # Pages send no ETag/Last-Modified: fetch and compare the content fingerprint.
                fetched = download(session, item)
                reason = "page content changed" if fingerprint(item, fetched[0]) != prev.get("sha256") else ""
            else:
                meta = head(session, item.url)
                changed = [k for k in meta if meta[k] and str(prev.get(k) or "") != meta[k]]
                reason = f"server {', '.join(changed)} changed" if changed else ""

            if reason and not args.check:
                content, meta = fetched or download(session, item)
                sha = fingerprint(item, content)
                if prev and sha == prev.get("sha256") and local and local.exists():
                    reason = ""  # headers moved but the bytes are identical: same version
                else:
                    version = int(row.get("version") or 0) + (0 if reason == "local file missing" else 1)
                    path = file_path(ptype, item, row["doc_id"], max(version, 1))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                    row.update(version=max(version, 1), sha256=sha, local_file=relative(path), downloaded_at=now)
                    history.append({**{c: row.get(c) for c in HISTORY_COLUMNS}, **meta,
                                    "publication_date": item.publication_date, "title": item.title,
                                    "url": item.url, "change_reason": reason})
                row.update(meta)
            status = ("new" if not prev else "updated") if reason else "up-to-date"
        except (requests.RequestException, RuntimeError) as exc:
            failures += 1
            status = f"error: {exc}"
            print(f"  ! {item.title[:70]}: {exc}", file=sys.stderr)

        row.update(publication_date=item.publication_date, title=item.title, url=item.url,
                   press_release_url=item.press_release_url, file_type=item.extension,
                   status=status, last_seen_at=now, last_checked_at=now)
        if not args.check and row.get("local_file") and (status in ("new", "updated") or not row.get("eba_reference") or args.rescan_references):
            row["eba_reference"] = eba_reference(ptype, item, ROOT / row["local_file"])
        statuses[status.split(":")[0]] += 1
        if status != "up-to-date":
            print(f"  {status:10} {item.publication_date} {item.title[:80]}" + (f"  ({reason})" if reason else ""))

    listed = {id(r) for r in matched if r}
    for r in previous:
        if id(r) not in listed:
            r.update(status="not listed", last_checked_at=now)
            documents.append(r)
            statuses["not listed"] += 1
            print(f"  not listed {r['publication_date']} {r['title'][:80]}")

    print("  " + ", ".join(f"{n} {s}" for s, n in statuses.items()))
    if args.check:
        print("Nothing written (--check)")
        return 0

    flag_later_same_reference(documents)
    documents.sort(key=lambda d: (d["publication_date"], d["title"]), reverse=True)
    write_register(ptype.register, {"documents": (DOCUMENT_COLUMNS, documents),
                                   "history": (HISTORY_COLUMNS, history)})
    print(f"Register written to {relative(ptype.register)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
