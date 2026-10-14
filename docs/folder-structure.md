# Folder structure

What lives where in this repository, who writes it, and how files are named. The rules for building and maintaining the wiki are in [llm-wiki.md](llm-wiki.md), the tasks in [workflows.md](workflows.md).

## Overview

```
banking-regulation-tool/
├── src/                     Python download scripts; cli.py is the entry point
├── data/                    git-ignored
│   ├── 00-source/           one Excel register per source
│   ├── 01-raw/              downloaded texts, every version kept
│   ├── 02-raw-md/           Markdown versions of the PDFs in 01-raw
│   ├── 03-wiki/             the knowledge base
│   ├── 04-output/           disposable query results
│   └── logs/                one log file per downloader run
├── docs/                    project rules, guides and agent prompts
├── AGENTS.md                entry point for agents; links the docs
├── CLAUDE.md                points Claude Code to AGENTS.md
├── README.md                project overview
├── pyproject.toml           project metadata and Python dependencies
└── uv.lock                  exact dependency versions (uv)
```

| Path | Content | Who writes |
|---|---|---|
| `src/` | Python download scripts; `cli.py` is the entry point, shared Excel code is in `register.py` | developer |
| `data/00-source/*.xlsx` | one register per source: a `documents` sheet (current state) and a `history` sheet (every downloaded version) | scripts only |
| `data/01-raw/` | downloaded English texts (PDF, HTML, xlsx, …); old versions are kept next to new ones | scripts only |
| `data/02-raw-md/` | Markdown versions of the PDF files in `01-raw`, for cheaper reading during `compile`. No script writes it yet | — |
| `data/03-wiki/` | the knowledge base | agent |
| `data/04-output/` | disposable query results: memos, comparisons, reports, slide decks | agent |
| `data/logs/` | one log per `cli.py` downloader run, `<YYYY-MM-DD_HHMMSS>_<command>.log`; safe to delete | `cli.py` |
| `docs/` | project rules (`llm-wiki.md`, `workflows.md`), guides (`folder-structure.md`, `tooling.md`, `downloaders.md`), background (`banking-regulators.md`) and agent prompts (`agent-prompt-*.md`) | — |

## Sources: `data/00-source` and `data/01-raw`

The registers and the files they track:

| Register | Downloaded to | Script |
|---|---|---|
| `isrb_documents.xlsx` | `eurlex/` | `download_isrb.py` |
| `eba_guidelines.xlsx` | `eba-guidelines/` | `download_eba_publications.py guidelines` |
| `eba_rts.xlsx` | `eba-rts/` | `download_eba_publications.py rts` |
| `eba_its.xlsx` | `eba-its/` | `download_eba_publications.py its` |
| `eba_reports.xlsx` | `eba-reports/` | `download_eba_publications.py reports` |
| `eba_consultation_papers.xlsx` | `eba-consultation-papers/` | `download_eba_publications.py cp` |
| `ecb_supervisory_guides.xlsx` | `ecb-guides/` | `download_ecb_guides.py` |
| `esma_library.xlsx` | `esma/` | `download_esma.py` |
| `eba_single_rulebook.xlsx` | `eba-single-rulebook/` | `download_eba_single_rulebook.py` |
| `bis_basel_framework.xlsx` | `bis-basel/` | `download_basel.py` |

File names in `data/01-raw`:

- `eurlex/<SHORT_NAME>/<CELEX>.{pdf,html}`, e.g. `eurlex/CRR/02013R0575-20260626.pdf`
- `eba-<type>/<YYYY>/<date>_<filename>_<doc_id>_v<N>.<ext>`
- `esma/<YYYY>/<date>_<filename>_<doc_id>_v<N>.<ext>`
- `eba-single-rulebook/<topic>/<date>_<filename>_<doc_id>_v<N>.<ext>`, e.g. `eba-single-rulebook/model-validation/2017-11-20_Guidelines_on_PD_and_LGD_estimation_EBA-GL-2017-16_<doc_id>_v1.pdf`. `<topic>` is the Single Rulebook topic in kebab-case, and the date is the document's "Last update" (or the application date)
- `bis-basel/<STANDARD>/<CHAPTER>_<effective date>_<published date>.html`, e.g. `bis-basel/CRE/CRE36_2023-01-01_2022-12-08.html`: the chapter text of one Basel Framework version (paragraphs, footnotes, FAQs), cut from the bis.org page. The two dates come from the BIS URL and identify the version, so there is no `_vN`
- `ecb-guides/<date>_<doc_id>_v<N>.pdf` (`doc_id` is the ECB file name without `.en.pdf`, with a `~` suffix when two entries share a file name)

A new version is saved as a new file (a new CELEX, Basel version dates or `_vN`), never over the old one. The registers track files by path, so never rename, move or edit anything in `data/01-raw`.

## Markdown versions: `data/02-raw-md`

- One `.md` file per PDF in `data/01-raw`, at the same relative path with the extension changed: `01-raw/eurlex/CRR/02013R0575-20260626.pdf` becomes `02-raw-md/eurlex/CRR/02013R0575-20260626.md`. A new `_vN` or CELEX version of a PDF gets its own `.md` file.
- Derived files: never edit them by hand; regenerate them from the PDF. The converter is not chosen yet, and no script writes this folder so far.
- The wiki cites the `01-raw` file, never the `.md` file: the registers and `log.md` track `01-raw` paths and their SHA-256.

## Wiki: `data/03-wiki`

```
03-wiki/
├── index.md                 entry point: every topic wiki, one line each
├── log.md                   append-only compile log
└── <topic>/
    ├── index.md             topic description and every article, one line each
    └── <article>.md         one concept, entity, process or act
```

- `log.md` records, for every source compiled, its `data/01-raw/...` path and SHA-256, and the articles created or updated. Newest entries are at the bottom.
- Folder and file names are lowercase kebab-case English, e.g. `irb-approach/downturn-lgd.md`.

## Outputs: `data/04-output`

- Files are named `<YYYY-MM-DD>_<short-name>.<ext>` (kebab-case), directly in `data/04-output/` unless a workflow names a subfolder.
- `<YYYY-MM-DD>_source-map.html`: the source map (`uv run src/cli.py graph`).
- `linkedin/`: weekly LinkedIn posts (see [agent-prompt-linkedin-post.md](agent-prompt-linkedin-post.md)).
- `graphify-out/`: the knowledge graph of the wiki. It is never written inside `data/03-wiki`.

Outputs are not wiki sources unless an article explicitly cites them.
