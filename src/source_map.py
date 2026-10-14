"""Write an interactive map of the source collection to data/03-output/<date>_source-map.html.

Nodes are the documents in the registers (data/00-source), the wiki articles and their topic
wikis. Edges come only from recorded facts:
- a wiki article cites a source file (the article's frontmatter `sources[].path`);
- a wiki article links to another article (`[[wikilink]]`);
- an ECB guide edition is superseded by a newer one (`superseded_by`);
- an EBA item shares its reference with a later item (`later_same_reference`, only a hint);
- an act has a published, future-dated consolidation (`next_celex`).
Basel Framework chapters are listed one node per chapter version, with BIS's status
(Current, Forthcoming, Superseded, Removed on <date>).
"Credit-risk keyword" is a title match on a fixed word list, a filter aid, not a classification.

The page is self-contained (inline data, CSS and JavaScript) and opens in any browser.

Usage:
    uv run src/source_map.py                       # write data/03-output/<today>_source-map.html
    uv run src/source_map.py --output map.html     # write somewhere else
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from register import read_sheet

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "data" / "00-source"
WIKI_DIR = ROOT / "data" / "02-wiki"
OUTPUT_DIR = ROOT / "data" / "03-output"

# register file -> (group shown in the map, legal force)
EBA_REGISTERS = {
    "eba_rts.xlsx": ("EBA RTS", "rts-its"),
    "eba_its.xlsx": ("EBA ITS", "rts-its"),
    "eba_guidelines.xlsx": ("EBA guidelines", "guideline"),
    "eba_reports.xlsx": ("EBA reports", "report"),
    "eba_consultation_papers.xlsx": ("EBA consultations", "consultation"),
}
# ESMA library type -> legal force; other types (final reports, compliance tables, reference
# documents, statements) get their own category, because a final report may hold draft RTS or guidelines
ESMA_FORCE = {"Guidelines & Recommendations": "guideline", "Consultation Paper": "consultation", "Report": "report"}
FORCE_LABELS = {
    "law": "Law (EUR-Lex act)",
    "rts-its": "EBA final draft RTS/ITS",
    "guideline": "Guideline (EBA, ESMA; comply-or-explain)",
    "ecb": "ECB supervisory guide (not law)",
    "basel": "Basel standard (BCBS; not EU law)",
    "report": "Report (not binding)",
    "consultation": "Consultation (proposal only)",
    "esma-other": "ESMA final report, table or reference",
    "article": "Wiki article",
    "topic": "Topic wiki",
}
CREDIT_KEYWORDS = re.compile(
    r"credit|default|\bIRB\b|internal.rating|\bLGD\b|\bPD\b|\bCCF\b|non.performing|\bNPE|\bNPL|forbear|"
    r"provision|IFRS ?9|expected credit loss|collateral|mitigation|large exposure|securiti|counterparty|"
    r"loan|mortgage|real estate|immovable|\bADC\b|retail|output floor|risk weight|standardised approach|"
    r"internal model|benchmarking|concentration|leverag|ECAI|rating", re.IGNORECASE)
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


def files_of(value: str | None) -> list[str]:
    """Register file cells may hold several paths joined by '; ' (multi-part EUR-Lex items)."""
    return [f for f in (value or "").split("; ") if f]


def add_document(nodes: dict, by_file: dict, node_id: str, files: list[str], **fields) -> None:
    fields["credit"] = bool(CREDIT_KEYWORDS.search(fields.get("title") or ""))
    nodes[node_id] = {"id": node_id, "kind": "doc", "cited": False, **fields}
    for f in files:
        by_file[f] = node_id


def read_registers(nodes: dict, edges: list, by_file: dict) -> None:
    for act in read_sheet(SOURCE_DIR / "isrb_documents.xlsx", "documents"):
        node_id = f"act:{act['short_name']}"
        files = files_of(act.get("pdf_file")) + files_of(act.get("html_file"))
        add_document(nodes, by_file, node_id, files, group="EUR-Lex acts", force="law",
                     label=act["short_name"], title=act.get("title") or act["short_name"],
                     date=act.get("version_date") or "", ref=act.get("current_celex") or "",
                     status=act.get("status") or "", path=(files or [""])[0], url=act.get("eurlex_url") or "")
        if act.get("next_celex"):
            next_id = f"next:{act['short_name']}"
            nodes[next_id] = {"id": next_id, "kind": "upcoming", "group": "EUR-Lex acts", "force": "law",
                              "label": f"{act['short_name']} (upcoming)", "title": f"Upcoming consolidation of {act['short_name']}",
                              "date": act["next_celex"].rsplit("-", 1)[-1], "ref": act["next_celex"],
                              "status": "published, not yet applicable; not downloaded", "path": "", "url": "",
                              "credit": nodes[node_id]["credit"], "cited": False}
            edges.append({"s": node_id, "t": next_id, "kind": "upcoming"})

    for register, (group, force) in EBA_REGISTERS.items():
        rows = read_sheet(SOURCE_DIR / register, "documents")
        prefix = register.removesuffix(".xlsx")
        for r in rows:
            add_document(nodes, by_file, f"{prefix}:{r['doc_id']}", files_of(r.get("local_file")),
                         group=group, force=force, label=r.get("eba_reference") or r["title"][:40],
                         title=r["title"], date=r.get("publication_date") or "", ref=r.get("eba_reference") or "",
                         status=r.get("status") or "", path=r.get("local_file") or "", url=r.get("url") or "")
        for r in rows:
            for later in files_of(r.get("later_same_reference")):
                edges.append({"s": f"{prefix}:{r['doc_id']}", "t": f"{prefix}:{later}", "kind": "same-ref"})

    guides = read_sheet(SOURCE_DIR / "ecb_supervisory_guides.xlsx", "documents")
    for g in guides:
        add_document(nodes, by_file, f"ecb:{g['doc_id']}", files_of(g.get("local_file")),
                     group="ECB guides", force="ecb", label=g["title"][:40], title=g["title"],
                     date=g.get("publication_date") or "", ref=g.get("edition_status") or "",
                     status=g.get("status") or "", path=g.get("local_file") or "", url=g.get("url") or "")
    for g in guides:
        if g.get("superseded_by"):
            edges.append({"s": f"ecb:{g['doc_id']}", "t": f"ecb:{g['superseded_by']}", "kind": "supersedes"})

    for r in read_sheet(SOURCE_DIR / "esma_library.xlsx", "documents"):
        add_document(nodes, by_file, f"esma:{r['doc_id']}", files_of(r.get("local_file")),
                     group="ESMA", force=ESMA_FORCE.get(r.get("doc_type"), "esma-other"),
                     label=r.get("esma_reference") or r["title"][:40], title=r["title"],
                     date=r.get("publication_date") or "", ref=r.get("esma_reference") or "",
                     status=r.get("status") or "", path=r.get("local_file") or "", url=r.get("url") or "")

    for r in read_sheet(SOURCE_DIR / "bis_basel_framework.xlsx", "documents"):
        add_document(nodes, by_file, f"basel:{r['doc_id']}", files_of(r.get("local_file")),
                     group="Basel Framework", force="basel", label=f"{r['chapter']} ({r['effective_date']})",
                     title=f"{r['chapter']} {r.get('chapter_title') or ''}".strip(), date=r.get("published_date") or "",
                     ref=r["doc_id"], status=r.get("bis_status") or "", path=r.get("local_file") or "",
                     url=r.get("url") or "")


def read_wiki(nodes: dict, edges: list, by_file: dict) -> list[str]:
    """Add topic and article nodes; return source paths cited by the wiki that no register knows."""
    articles = {p.relative_to(WIKI_DIR).with_suffix("").as_posix(): p
                for p in sorted(WIKI_DIR.glob("*/*.md")) if p.stem != "index"}
    by_base = defaultdict(list)
    for name in articles:
        by_base[name.rsplit("/", 1)[-1]].append(name)
    unknown = []
    for name, path in articles.items():
        text = path.read_text()
        topic = name.split("/", 1)[0]
        topic_id = f"topic:{topic}"
        if topic_id not in nodes:
            nodes[topic_id] = {"id": topic_id, "kind": "topic", "group": "Wiki", "force": "topic", "label": topic,
                               "title": f"Topic wiki: {topic}", "date": "", "ref": "", "status": "",
                               "path": f"data/02-wiki/{topic}/index.md", "url": "", "credit": True, "cited": False}
        h1 = re.search(r"(?m)^# (.+)$", text)
        updated = re.search(r"(?m)^updated: (\S+)", text)
        title = h1.group(1) if h1 else name
        node_id = f"article:{name}"
        nodes[node_id] = {"id": node_id, "kind": "article", "group": "Wiki", "force": "article", "label": title,
                          "title": title, "date": updated.group(1) if updated else "", "ref": name, "status": "",
                          "path": f"data/02-wiki/{name}.md", "url": "", "credit": True, "cited": False}
        edges.append({"s": node_id, "t": topic_id, "kind": "topic"})
        frontmatter = re.match(r"---\n(.*?)\n---", text, re.S)
        for cited in re.findall(r"path:\s*(\S+)", frontmatter.group(1) if frontmatter else ""):
            target = by_file.get(cited)
            if target:
                nodes[target]["cited"] = True
                edges.append({"s": node_id, "t": target, "kind": "cites"})
            else:
                unknown.append(cited)
        body = re.sub(r"```.*?```", "", text, flags=re.S)
        for link in {m.strip() for m in WIKILINK.findall(body)}:
            candidates = [link] if link in articles else [f"{topic}/{link}"] if f"{topic}/{link}" in articles \
                else by_base.get(link, []) if "/" not in link else []
            if len(candidates) == 1 and candidates[0] != name:
                edges.append({"s": node_id, "t": f"article:{candidates[0]}", "kind": "link"})
    return unknown


def build(output: Path) -> None:
    nodes, edges, by_file = {}, [], {}
    read_registers(nodes, edges, by_file)  # registers and wiki both record paths relative to the repository root
    unknown = read_wiki(nodes, edges, by_file)
    # drop dangling edges and duplicates (an article citing both the PDF and HTML of one act)
    edges = list({(e["s"], e["t"], e["kind"]): e for e in edges if e["s"] in nodes and e["t"] in nodes}.values())
    data = {"generated": date.today().isoformat(), "forces": FORCE_LABELS,
            "nodes": list(nodes.values()), "edges": edges}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(TEMPLATE.read_text().replace("/*DATA*/null", payload))

    docs = [n for n in nodes.values() if n["kind"] == "doc"]
    print(f"{len(docs)} documents, {sum(n['cited'] for n in docs)} cited by the wiki, "
          f"{sum(n['kind'] == 'article' for n in nodes.values())} articles, {len(edges)} edges")
    for path in sorted(set(unknown)):
        print(f"  ! cited but not in any register: {path}", file=sys.stderr)
    print(f"Written to {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}")


TEMPLATE = Path(__file__).with_name("source_map.html")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / f"{date.today().isoformat()}_source-map.html",
                        help="where to write the HTML page")
    args = parser.parse_args()
    build(args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
