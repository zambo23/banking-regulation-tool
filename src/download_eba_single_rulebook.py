"""Download the final texts on the EBA Single Rulebook regulatory activity pages.

The EBA publications listing (download_eba_publications.py) misses the final versions of many
guidelines and technical standards, e.g. EBA/GL/2017/16 on PD and LGD estimation. Their final texts
are on the Single Rulebook pages, one page per regulatory product, grouped by topic:
    https://www.eba.europa.eu/regulation-and-policy/<topic>            topic page
    https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/<topic>/<product>
(a few products sit elsewhere, e.g. at the site root). The site has no sitemap. The breadcrumb menu of a
topic page (nav.breadcrumb-sw) lists every product of that topic, while the topic page body shows only
some of them, so the menu is the listing.

Products migrated from the old site often keep their final texts in a "Documents" box in the product
description instead (e.g. the downturn LGD guidelines, EBA/GL/2019/03); those files are read too, with
phase "Documents (product page)" and no status or dates.

A product page has versions and phases:
- versions: the current one (the plain URL), "Previous versions" (?version=<year>) and "Ongoing
  versions", each a link in .activity-versions__buttons. An amending act becomes the current version
  while the act it amends stays a previous version, often still in force (e.g. EBA/GL/2016/07).
- phases: a timeline (Consultation, Final Report, Consolidated Document, ...), each linked as
  ?phase=<name>; the version's own URL shows its latest phase. Each phase page has a status box
  (Status, Application date, Compliance deadline) and document cards: the English file, with its
  translations listed separately under "Other languages".
Consultation phases are skipped: they are proposals, and the consultation papers are in the EBA
consultation register. Only the English file of each card is downloaded.

Each document is identified by its product, phase title and card title (doc_id). Re-running the
script is the update mechanism: when a card's file URL or "Last update" date changes, the file is
downloaded and, if its bytes differ, saved as a new version (suffix _vN) and logged in the "history"
sheet. Documents that disappear from the site are kept with status "not listed".

Usage:
    uv run src/download_eba_single_rulebook.py           # read all products, download new or changed files
    uv run src/download_eba_single_rulebook.py --check   # only report what would change; download and write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from download_eba_publications import EBA_REF
from language import is_not_english
from register import read_sheet, write_register

ROOT = Path(__file__).resolve().parent.parent
REGISTER_PATH = ROOT / "data" / "00-source" / "eba_single_rulebook.xlsx"
DOWNLOAD_DIR = ROOT / "data" / "01-raw" / "eba-single-rulebook"

SITE = "https://www.eba.europa.eu"
START_URL = f"{SITE}/regulation-and-policy/credit-risk"  # any topic page: its menu lists all topics

USER_AGENT = "banking-regulation-tool/0.1 (EBA Single Rulebook downloader)"
REQUEST_PAUSE_S = 0.5
PROGRESS_ITEMS = 25  # print a progress line every N products
RETRIES = 3
FILE_EXTENSION = re.compile(r"\.(pdf|xlsx?|xlsm|docx?|zip|csv)$", re.IGNORECASE)
# a translation link in a product's document box reads "bg български", "en English", ...
LANGUAGE_LINK = re.compile(r"^[a-z]{2}\s+\S")
DOCUMENT_BOX = "Documents (product page)"
NOT_ENGLISH = "not English"  # register status of a translation: its file is not kept, and it is not retried

DEAD_LINK = "dead link"  # register status when the EBA site answers 404: not counted as a failure, retried next run


def is_dead_link(exc: Exception) -> bool:
    return isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 404

DOCUMENT_COLUMNS = [
    "doc_id", "topic", "product", "product_url", "product_version", "is_current_version", "phase",
    "phase_title", "phase_status", "application_date", "compliance_deadline", "title", "eba_reference",
    "last_update", "file_type", "url", "page_url", "version", "sha256", "local_file", "status",
    "first_seen_at", "last_seen_at", "downloaded_at", "last_checked_at",
]
HISTORY_COLUMNS = [
    "doc_id", "version", "product", "phase", "title", "last_update", "url", "sha256", "local_file",
    "change_reason", "downloaded_at",
]


@dataclass
class Document:
    topic: str
    product: str
    product_url: str
    product_version: str     # "current", a year such as "2016", or "ongoing: <label>"
    phase: str               # timeline label, e.g. "Final Report"
    phase_title: str         # heading of the phase page, e.g. "Final Report on Guidelines on ..."
    phase_status: str        # e.g. "Applicable", "In force"
    application_date: str    # ISO date or ""
    compliance_deadline: str
    title: str               # card title: the file name, "Compliance table", ...
    last_update: str         # ISO date or ""
    url: str
    page_url: str

    @property
    def doc_id(self) -> str:
        key = "|".join((self.product_url, self.phase_title, self.title))
        return hashlib.sha1(key.encode()).hexdigest()[:10]

    @property
    def filename(self) -> str:
        """Old-style links end in a UUID (/documents/10180/<n>/<name>.pdf/<uuid>): take the segment with an extension."""
        segments = unquote(urlsplit(self.url).path).replace("+", " ").split("/")
        return next((seg for seg in reversed(segments) if FILE_EXTENSION.search(seg)), segments[-1])

    @property
    def extension(self) -> str:
        return self.filename.rpartition(".")[2].lower() or "bin"


def fetch(session: requests.Session, url: str, timeout: int = 60) -> requests.Response:
    """GET with a pause, retrying on HTTP 429 and 5xx after 30 s, 60 s, ..."""
    for attempt in range(RETRIES + 1):
        time.sleep(REQUEST_PAUSE_S)
        resp = session.get(url, timeout=timeout)
        if (resp.status_code != 429 and resp.status_code < 500) or attempt == RETRIES:
            break
        print(f"  ... HTTP {resp.status_code} from EBA, waiting {30 * (attempt + 1)}s before retry {attempt + 1}/{RETRIES}")
        time.sleep(30 * (attempt + 1))
    resp.raise_for_status()
    return resp


def soup_of(session: requests.Session, url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch(session, url).text, "html.parser")


def menu_children(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """(label, URL) of the entries under the deepest level of the breadcrumb menu."""
    items = soup.select("nav.breadcrumb-sw li.breadcrumb-sw__item")
    if not items:
        return []
    return [(a.get_text(" ", strip=True), urljoin(SITE, a["href"]))
            for a in items[-1].select(".breadcrumb-sw__item-children a[href]")]


def list_products(session: requests.Session) -> list[tuple[str, str, str]]:
    """(topic, product title, product URL) for every product on every topic page."""
    start = soup_of(session, START_URL)
    topics = {}
    for a in start.select("nav.breadcrumb-sw a[href^='/regulation-and-policy/']"):
        if a["href"].count("/") == 2:  # /regulation-and-policy/<topic>
            topics[urljoin(SITE, a["href"])] = a.get_text(" ", strip=True)
    if not topics:
        raise RuntimeError("No topics in the Single Rulebook menu: the page layout may have changed")
    print(f"  {len(topics)} topics")
    products: dict[str, tuple[str, str, str]] = {}
    for url, topic in topics.items():
        for title, product_url in menu_children(soup_of(session, url)):
            products.setdefault(product_url.split("#")[0], (topic, title, product_url.split("#")[0]))
    if not products:
        raise RuntimeError("No products in the topic menus: the page layout may have changed")
    return list(products.values())


def iso(text: str) -> str:
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"\d{1,2} [A-Z][a-z]+ \d{4}", text)
    return datetime.strptime(m.group(0), "%d %B %Y").date().isoformat() if m else ""


def version_links(soup: BeautifulSoup, product_url: str) -> list[tuple[str, str]]:
    """(label, URL) of the current version and every previous or ongoing version."""
    versions = [("current", product_url)]
    buttons = soup.select_one(".activity-versions__buttons")
    for menu in buttons.select(".dropdown-menu") if buttons else []:
        toggle = menu.find_previous_sibling(["button", "a", "span"])
        group = toggle.get_text(" ", strip=True).lower() if toggle else ""
        for a in menu.select("a[href]"):
            label = a.get_text(" ", strip=True)
            versions.append((f"ongoing: {label}" if "ongoing" in group else label,
                             urljoin(SITE, a["href"]).split("#")[0]))
    return versions


def phase_links(soup: BeautifulSoup, version_url: str) -> list[tuple[str, str]]:
    """(phase label, URL) of the linked phases on the timeline, consultations excluded."""
    timeline = soup.select(".timeline__item")
    if not timeline:  # a page without phases (e.g. a handbook): its documents are on the page itself
        return [("", version_url)]
    phases = []
    for item in timeline:
        name = item.find("b")
        link = item.find("a", href=True)
        if name is None or link is None or "consultation" in name.get_text().lower():
            continue
        phases.append((name.get_text(" ", strip=True), urljoin(SITE, link["href"]).split("#")[0]))
    return phases  # empty for a product still under consultation


def read_phase(soup: BeautifulSoup, base: dict, page_url: str) -> list[Document]:
    content = soup.select_one(".grid-with-sidebar > div") or soup
    heading = content.find("h2")
    box = {}
    for li in content.select(".box-data__items li"):
        label, _, value = li.get_text(" ", strip=True).partition(":")
        box[label.strip().lower()] = value.strip()
    documents = []
    for card in content.select(".document-download"):
        link = card.select_one(".card-body .document-download__download a[href]")
        title = card.select_one(".card-body h6")
        if link is None or title is None:
            continue
        updated = card.select_one(".card-body .document-download__document-updated")
        documents.append(Document(
            **base, phase_title=heading.get_text(" ", strip=True) if heading else base["phase"],
            phase_status=box.get("status", ""), application_date=iso(box.get("application date", "")),
            compliance_deadline=iso(box.get("compliance deadline", "")), title=title.get_text(" ", strip=True),
            last_update=iso(updated.get_text(" ", strip=True)) if updated else "",
            url=urljoin(SITE, link["href"]), page_url=page_url,
        ))
    return documents


def read_document_box(soup: BeautifulSoup, base: dict, page_url: str) -> list[Document]:
    """Files listed in the product description's "Documents" box (div.well).

    Products migrated from the old site keep their final texts there instead of in a phase, e.g. the
    downturn LGD guidelines (EBA/GL/2019/03). Translations ("bg български", ...), web pages and links to other
    sites (national authorities, which refuse scripted requests with HTTP 403) are skipped.
    """
    documents = []
    for a in soup.select(".node__header .well a[href], .rich-text .well a[href]"):
        label = a.get_text(" ", strip=True)
        url = urljoin(SITE, a["href"])
        path = unquote(urlsplit(url).path)
        is_file = "/sites/default/files/" in path or "/documents/10180/" in path or FILE_EXTENSION.search(path)
        on_eba = urlsplit(url).netloc.lower().endswith("eba.europa.eu")  # not national authorities' sites
        if not label or LANGUAGE_LINK.match(label) or not is_file or not on_eba:
            continue
        documents.append(Document(**base, phase_title=DOCUMENT_BOX, phase_status="", application_date="",
                                  compliance_deadline="", title=label, last_update="", url=url, page_url=page_url))
    return documents


def scrape_product(session: requests.Session, topic: str, product: str, product_url: str) -> list[Document]:
    documents, seen_pages = [], set()
    current = soup_of(session, product_url)
    documents += read_document_box(current, {"topic": topic, "product": product, "product_url": product_url,
                                             "product_version": "current", "phase": DOCUMENT_BOX}, product_url)
    for version, version_url in version_links(current, product_url):
        page = current if version_url == product_url else soup_of(session, version_url)
        for phase, phase_url in phase_links(page, version_url):
            if phase_url in seen_pages:
                continue
            seen_pages.add(phase_url)
            phase_page = page if phase_url == version_url else soup_of(session, phase_url)
            base = {"topic": topic, "product": product, "product_url": product_url,
                    "product_version": version, "phase": phase}
            documents += read_phase(phase_page, base, phase_url)
    return documents


def eba_reference(document: Document, path: Path | None) -> str:
    """EBA/<kind>/YYYY/NN from the card title, file name, phase title, or page 1 of the PDF."""
    sources = [document.title, document.filename, document.phase_title]
    if path and path.suffix == ".pdf" and shutil.which("pdftotext"):
        result = subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(path), "-"],
                                capture_output=True, text=True, errors="replace")
        sources.append(result.stdout)
    for text in sources:
        m = EBA_REF.search(text)
        if m:
            return f"EBA/{m.group(1).upper()}/{m.group(2)}/{int(m.group(3)):02d}"
    return ""


def file_path(document: Document, doc_id: str, version: int) -> Path:
    stem = re.sub(r"[^\w.-]+", "_", document.filename.rpartition(".")[0] or document.filename).strip("_")[:80]
    topic = re.sub(r"[^a-z0-9]+", "-", document.topic.lower()).strip("-") or "other"
    date = document.last_update or document.application_date or "undated"
    return DOWNLOAD_DIR / topic / f"{date}_{stem}_{doc_id}_v{version}.{document.extension}"


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report changes without downloading or writing")
    args = parser.parse_args()

    now = datetime.now().isoformat(timespec="seconds")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    print(f"Reading the Single Rulebook topics from {START_URL}")
    products = list_products(session)
    print(f"  {len(products)} products listed")

    found: list[Document] = []
    failures = 0
    for i, (topic, product, product_url) in enumerate(products):
        if i and i % PROGRESS_ITEMS == 0:
            print(f"  ... {i}/{len(products)} products read, {len(found)} documents so far")
        try:
            found += scrape_product(session, topic, product, product_url)
        except requests.RequestException as exc:
            if is_dead_link(exc):
                print(f"  {DEAD_LINK:10} {product[:70]} (product page)")
            else:
                failures += 1
                print(f"  ! {product[:70]}: {exc}", file=sys.stderr)
    print(f"  {len(found)} documents on {len(products)} product pages")

    previous = {r["doc_id"]: r for r in read_sheet(REGISTER_PATH, "documents")}
    history = read_sheet(REGISTER_PATH, "history")
    documents, statuses, seen = [], Counter(), set()

    for i, document in enumerate(found):
        if i and i % (PROGRESS_ITEMS * 10) == 0:
            print(f"  ... {i}/{len(found)} documents checked")
        doc_id = document.doc_id
        if doc_id in seen:  # the same card reached through two versions or phases
            continue
        seen.add(doc_id)
        prev = previous.get(doc_id)
        row = dict(prev) if prev else {"doc_id": doc_id, "version": 0, "first_seen_at": now}
        documents.append(row)
        local = ROOT / row["local_file"] if row.get("local_file") else None
        if prev and prev.get("status") == NOT_ENGLISH and prev.get("url") == document.url:
            reason = None  # a translation found earlier
        elif not prev or not prev.get("local_file"):
            reason = "new"
        elif local is None or not local.exists():
            reason = "local file missing"
        elif prev.get("url") != document.url:
            reason = "file replaced under a new URL"
        elif (prev.get("last_update") or "") != document.last_update:
            reason = "last update date changed"
        else:
            reason = ""

        try:
            if reason and not args.check:
                resp = fetch(session, document.url, timeout=300)
                if "text/html" in resp.headers.get("Content-Type", ""):
                    raise RuntimeError("server returned an HTML page instead of a document")
                sha = hashlib.sha256(resp.content).hexdigest()
                if is_not_english(document.filename, resp.content):
                    reason = None  # English texts only: a translation is not saved
                elif prev and sha == prev.get("sha256") and local and local.exists():
                    reason = ""  # new URL or date, same bytes: same version
                else:
                    version = max(int(row.get("version") or 0) + (0 if reason == "local file missing" else 1), 1)
                    path = file_path(document, doc_id, version)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(resp.content)
                    row.update(version=version, sha256=sha, local_file=relative(path), downloaded_at=now,
                               eba_reference=eba_reference(document, path))
                    history.append({**{c: row.get(c) for c in HISTORY_COLUMNS}, "product": document.product,
                                    "phase": document.phase_title, "title": document.title,
                                    "last_update": document.last_update, "url": document.url,
                                    "change_reason": reason})
            if reason is None:
                status = NOT_ENGLISH
                row.update(local_file="", sha256="")
            else:
                status = ("new" if reason == "new" else "updated") if reason else "up-to-date"
        except (requests.RequestException, RuntimeError) as exc:
            if is_dead_link(exc):
                status = DEAD_LINK  # the EBA's own broken link: recorded, not a failure
            else:
                failures += 1
                status = f"error: {exc}"
                print(f"  ! {document.title[:70]}: {exc}", file=sys.stderr)

        row.update(topic=document.topic, product=document.product, product_url=document.product_url,
                   product_version=document.product_version,
                   is_current_version=document.product_version == "current", phase=document.phase,
                   phase_title=document.phase_title, phase_status=document.phase_status,
                   application_date=document.application_date, compliance_deadline=document.compliance_deadline,
                   title=document.title, last_update=document.last_update, file_type=document.extension,
                   url=document.url, page_url=document.page_url, status=status, last_seen_at=now,
                   last_checked_at=now)
        if not row.get("eba_reference"):
            row["eba_reference"] = eba_reference(document, None)
        statuses[status.split(":")[0]] += 1
        repeated = status == DEAD_LINK and prev and prev.get("status") == DEAD_LINK  # known: stay quiet
        if status not in ("up-to-date", NOT_ENGLISH) and not repeated and not (args.check and status == "new"):
            print(f"  {status:10} {document.product[:45]} | {document.title[:50]}" + (f"  ({reason})" if reason else ""))

    for doc_id, r in previous.items():
        if doc_id not in seen:
            r.update(status="not listed", is_current_version=False, last_checked_at=now)
            documents.append(r)
            statuses["not listed"] += 1
            print(f"  not listed {(r.get('product') or '')[:45]} | {(r.get('title') or '')[:50]}")

    # a reference found on one card of a phase (the final report) also applies to its compliance table, ...
    # but not across the cards of a product's document box, which are unrelated documents
    by_phase: dict[tuple, str] = {}
    for d in documents:
        if d.get("eba_reference") and d.get("phase_title") != DOCUMENT_BOX:
            by_phase.setdefault((d["product_url"], d["phase_title"]), d["eba_reference"])
    for d in documents:
        if not d.get("eba_reference") and d.get("phase_title") != DOCUMENT_BOX:
            d["eba_reference"] = by_phase.get((d.get("product_url"), d.get("phase_title")), "")

    print("  " + ", ".join(f"{n} {s}" for s, n in statuses.items()))
    if args.check:
        print("Nothing written (--check)")
        return 0

    documents.sort(key=lambda d: (d.get("topic") or "", d.get("product") or "", d.get("application_date") or "",
                                  d.get("title") or ""))
    write_register(REGISTER_PATH, {"documents": (DOCUMENT_COLUMNS, documents),
                                   "history": (HISTORY_COLUMNS, history)})
    print(f"Register written to {relative(REGISTER_PATH)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
