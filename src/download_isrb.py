"""Download the current EUR-Lex consolidated versions of the EBA Interactive Single Rulebook acts.

The EBA page lists the level 1 acts and links each to a EUR-Lex consolidated version.
The EBA link may lag behind EUR-Lex, so the script uses it only to identify the act and
asks the Publications Office (SPARQL endpoint) for the newest version in force today that
exists in English. That is the latest consolidated text, or the original act when no English
consolidation exists (acts never amended, e.g. DORA). Files are fetched from the Cellar
repository, because eur-lex.europa.eu answers scripted requests with a bot challenge.

Re-running the script is the update mechanism: acts whose current version changed since the
last run are downloaded again, older files are kept, and every downloaded version is logged
in the "history" sheet of the Excel register.

Usage:
    python src/download_isrb.py           # check versions and download what is new or missing
    python src/download_isrb.py --check   # only report which acts are outdated; change nothing
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup

from register import read_sheet, write_register

ROOT = Path(__file__).resolve().parent.parent
REGISTER_PATH = ROOT / "data" / "00-source" / "isrb_documents.xlsx"
DOWNLOAD_DIR = ROOT / "data" / "01-raw" / "eurlex"

ISRB_URL = "https://www.eba.europa.eu/regulation-and-policy/single-rulebook/interactive-single-rulebook"
SPARQL_URL = "https://publications.europa.eu/webapi/rdf/sparql"
EURLEX_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"

# Cellar manifestation types per output format, in order of preference.
FORMATS = {
    "pdf": ["pdfa2a", "pdfa1a", "pdfa2u", "pdfx", "pdf"],
    "html": ["xhtml", "html"],
}

USER_AGENT = "banking-regulation-tool/0.1 (ISRB document downloader)"
REQUEST_PAUSE_S = 1.0

DOCUMENT_COLUMNS = [
    "short_name", "title", "legal_act", "act_celex", "isrb_url",
    "eba_eurlex_url", "eba_celex", "current_celex", "version_date", "next_celex",
    "eurlex_url", "pdf_source_url", "pdf_file", "pdf_sha256",
    "html_source_url", "html_file", "html_sha256",
    "status", "downloaded_at", "last_checked_at",
]
HISTORY_COLUMNS = [
    "short_name", "current_celex", "version_date", "eurlex_url",
    "pdf_file", "pdf_sha256", "html_file", "html_sha256", "downloaded_at",
]


@dataclass
class Act:
    short_name: str
    title: str
    legal_act: str
    isrb_url: str
    eba_eurlex_url: str
    eba_celex: str
    act_celex: str
    consolidations: list[str] = field(default_factory=list)  # consolidated CELEX ids, newest first

    @property
    def original_celex(self) -> str:
        return f"3{self.act_celex}"


def act_celex_of(celex: str) -> str:
    """'02013R0575-20260626' or '32013R0575' -> '2013R0575' (the act, independent of version)."""
    m = re.match(r"^[0-9](\d{4}[A-Z]{1,2}\d{3,}(?:\(\d+\))?)", celex)
    if not m:
        raise ValueError(f"Unrecognised CELEX number: {celex}")
    return m.group(1)


def version_date_of(celex: str) -> date | None:
    m = re.search(r"-(\d{8})$", celex)
    return datetime.strptime(m.group(1), "%Y%m%d").date() if m else None


def sparql(session: requests.Session, query: str) -> list[dict[str, str]]:
    resp = session.post(SPARQL_URL, data={"query": query},
                        headers={"Accept": "application/sparql-results+json"}, timeout=180)
    resp.raise_for_status()
    return [{k: v["value"] for k, v in b.items()} for b in resp.json()["results"]["bindings"]]


def scrape_isrb(session: requests.Session) -> list[Act]:
    resp = session.get(ISRB_URL, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if table is None:
        raise RuntimeError("ISRB table not found: the EBA page layout may have changed")

    acts = []
    for row in table.select("tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        title_link = cells[1].find("a", href=True)
        eurlex_link = cells[2].find("a", href=True)
        if title_link is None or eurlex_link is None:
            continue
        m = re.search(r"CELEX:([0-9A-Z()\-]+)", unquote(eurlex_link["href"]))
        if not m:
            print(f"  ! no CELEX in {eurlex_link['href']}, skipped", file=sys.stderr)
            continue
        eba_celex = m.group(1)
        acts.append(Act(
            short_name=eurlex_link.get_text(strip=True),
            title=title_link.get_text(strip=True),
            legal_act=" ".join(cells[0].get_text().split()),
            isrb_url=urljoin(ISRB_URL, title_link["href"]),
            eba_eurlex_url=eurlex_link["href"],
            eba_celex=eba_celex,
            act_celex=act_celex_of(eba_celex),
        ))
    if not acts:
        raise RuntimeError("No acts parsed from the ISRB page: the EBA page layout may have changed")
    return acts


def fetch_consolidations(session: requests.Session, acts: list[Act]) -> None:
    """Fill act.consolidations with every consolidated CELEX id known to the Publications Office."""
    filters = " || ".join(f'STRSTARTS(STR(?celex), "0{a.act_celex}-")' for a in acts)
    rows = sparql(session, f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        SELECT DISTINCT ?celex WHERE {{
          ?work cdm:resource_legal_id_celex ?celex .
          FILTER({filters})
        }}""")
    found = {r["celex"] for r in rows}
    for act in acts:
        prefix = f"0{act.act_celex}-"
        act.consolidations = sorted((c for c in found if c.startswith(prefix) and version_date_of(c)),
                                    reverse=True)


def fetch_english_items(session: requests.Session, celex_ids: list[str]) -> dict[str, dict[str, list[str]]]:
    """Map CELEX id -> manifestation type -> Cellar item URLs of the English expression."""
    values = " ".join(f'"{c}"^^xsd:string' for c in celex_ids)
    rows = sparql(session, f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        SELECT ?celex ?type ?item WHERE {{
          VALUES ?celex {{ {values} }}
          ?work cdm:resource_legal_id_celex ?celex .
          ?expr cdm:expression_belongs_to_work ?work ;
                cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> .
          ?manif cdm:manifestation_manifests_expression ?expr ;
                 cdm:manifestation_type ?type .
          ?item cdm:item_belongs_to_manifestation ?manif .
        }}""")
    items: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        items[r["celex"]][r["type"]].append(r["item"])
    return items


def pick_items(available: dict[str, list[str]], kind: str) -> list[str]:
    for manifestation_type in FORMATS[kind]:
        if available.get(manifestation_type):
            return sorted(available[manifestation_type])
    return []


def current_version(act: Act, items: dict[str, dict[str, list[str]]], today: date) -> str | None:
    """Newest version in force today with an English text; the original act if never consolidated in English."""
    in_force = [c for c in act.consolidations if version_date_of(c) <= today]
    for celex in [*in_force, act.original_celex]:
        if any(pick_items(items.get(celex, {}), kind) for kind in FORMATS):
            return celex
    return None


def next_version(act: Act, today: date) -> str:
    """Earliest consolidated version with a future date, i.e. already published but not yet applicable."""
    future = [c for c in act.consolidations if version_date_of(c) > today]
    return future[-1] if future else ""


def download(session: requests.Session, urls: list[str], target: Path) -> tuple[list[Path], list[str]]:
    """Download Cellar items to target (or target_partN when a manifestation is split into several items).

    Returns the written paths and their SHA-256 digests.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    paths, digests = [], []
    for i, url in enumerate(urls, start=1):
        time.sleep(REQUEST_PAUSE_S)
        resp = session.get(url, timeout=300)
        resp.raise_for_status()
        path = target if len(urls) == 1 else target.with_name(f"{target.stem}_part{i}{target.suffix}")
        path.write_bytes(resp.content)
        paths.append(path)
        digests.append(hashlib.sha256(resp.content).hexdigest())
    return paths, digests


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report outdated acts without downloading or writing")
    args = parser.parse_args()

    today = date.today()
    now = datetime.now().isoformat(timespec="seconds")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    print(f"Reading {ISRB_URL}")
    acts = scrape_isrb(session)
    print(f"  {len(acts)} acts listed")
    print("Querying the Publications Office for versions and English manifestations")
    fetch_consolidations(session, acts)
    candidates = [c for a in acts for c in [*a.consolidations, a.original_celex]
                  if (version_date_of(c) or today) <= today]
    items = fetch_english_items(session, candidates)

    previous = {r["act_celex"]: r for r in read_sheet(REGISTER_PATH, "documents")}
    history = read_sheet(REGISTER_PATH, "history")
    documents = []
    failures = 0

    for act in acts:
        prev = previous.get(act.act_celex, {})
        row = {**prev, **{k: getattr(act, k) for k in
                          ("short_name", "title", "legal_act", "act_celex", "isrb_url",
                           "eba_eurlex_url", "eba_celex")}}
        row["next_celex"] = next_version(act, today)
        row["last_checked_at"] = now
        documents.append(row)

        celex = current_version(act, items, today)
        if celex is None:
            failures += 1
            row["status"] = "error: no English text found"
            print(f"  {act.short_name:7} {'-':22} {row['status']}", file=sys.stderr)
            continue

        recorded = [f for k in FORMATS for f in (prev.get(f"{k}_file") or "").split("; ") if f]
        have_files = bool(recorded) and all((ROOT / f).exists() for f in recorded)
        up_to_date = prev.get("current_celex") == celex and have_files
        row["status"] = "up-to-date" if up_to_date else ("updated" if prev else "new")
        notes = [f"EBA page links {act.eba_celex}"] if act.eba_celex != celex else []
        if row["next_celex"]:
            notes.append(f"upcoming {row['next_celex']}")
        print(f"  {act.short_name:7} {celex:22} {row['status']}" + (f"  ({'; '.join(notes)})" if notes else ""))

        if up_to_date or args.check:
            continue
        row.update(current_celex=celex, eurlex_url=EURLEX_URL.format(celex=celex),
                   version_date=str(version_date_of(celex) or ""), downloaded_at=now)
        for kind in FORMATS:
            urls = pick_items(items[celex], kind)
            paths, digests = download(session, urls, DOWNLOAD_DIR / act.short_name / f"{celex}.{kind}")
            row[f"{kind}_source_url"] = "; ".join(urls)
            row[f"{kind}_file"] = "; ".join(relative(p) for p in paths)
            row[f"{kind}_sha256"] = "; ".join(digests)
        history.append({c: row.get(c) for c in HISTORY_COLUMNS})

    if args.check:
        outdated = sum(d["status"] != "up-to-date" for d in documents)
        print(f"{outdated} of {len(documents)} acts need downloading (nothing written, --check)")
        return 0

    write_register(REGISTER_PATH, {"documents": (DOCUMENT_COLUMNS, documents),
                                   "history": (HISTORY_COLUMNS, history)})
    print(f"Register written to {relative(REGISTER_PATH)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
