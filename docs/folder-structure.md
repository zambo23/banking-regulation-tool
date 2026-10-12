# Folder structure

What lives where in this repository, who writes it, and how files are named. The rules for building and maintaining the wiki are in [AGENTS.md](../AGENTS.md).

## Overview

```
banking-regulation-tool/
├── src/                     Python download scripts; cli.py is the entry point
├── data/                    git-ignored
│   ├── 00-source/           one Excel register per source
│   ├── 01-raw/              downloaded texts, every version kept
│   ├── 02-wiki/             the knowledge base
│   └── 03-output/           disposable query results
├── docs/                    guides and agent prompts
├── AGENTS.md                rules for agents
├── CLAUDE.md                points Claude Code to AGENTS.md
├── README.md                project overview
└── requirements.txt         Python dependencies
```

| Path | Content | Who writes |
|---|---|---|
| `src/` | Python download scripts; `cli.py` is the entry point, shared Excel code is in `register.py` | developer |
| `data/00-source/*.xlsx` | one register per source: a `documents` sheet (current state) and a `history` sheet (every downloaded version) | scripts only |
| `data/01-raw/` | downloaded English texts (PDF, HTML, xlsx, …); old versions are kept next to new ones | scripts only |
| `data/02-wiki/` | the knowledge base | agent |
| `data/03-output/` | disposable query results: memos, comparisons, reports, slide decks | agent |
| `docs/` | guides (`folder-structure.md`, `tooling.md`) and agent prompts (`agent-prompt-*.md`) | — |

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

File names in `data/01-raw`:

- `eurlex/<SHORT_NAME>/<CELEX>.{pdf,html}`, e.g. `eurlex/CRR/02013R0575-20260626.pdf`
- `eba-<type>/<YYYY>/<date>_<filename>_<doc_id>_v<N>.<ext>`
- `ecb-guides/<date>_<doc_id>_v<N>.pdf` (`doc_id` is the ECB file name without `.en.pdf`, with a `~` suffix when two entries share a file name)

A new version is saved as a new file (a new CELEX or `_vN`), never over the old one. The registers track files by path, so never rename, move or edit anything in `data/01-raw`.

## Wiki: `data/02-wiki`

```
02-wiki/
├── index.md                 entry point: every topic wiki, one line each
├── log.md                   append-only compile log
└── <topic>/
    ├── index.md             topic description and every article, one line each
    └── <article>.md         one concept, entity, process or act
```

- `log.md` records, for every source compiled, its `data/01-raw/...` path and SHA-256, and the articles created or updated. Newest entries are at the bottom.
- Folder and file names are lowercase kebab-case English, e.g. `irb-approach/lgd-downturn.md`.

## Outputs: `data/03-output`

- Files are named `<YYYY-MM-DD>_<short-name>.<ext>` (kebab-case), directly in `data/03-output/` unless a workflow names a subfolder.
- `linkedin/`: weekly LinkedIn posts (see [agent-prompt-linkedin-post.md](agent-prompt-linkedin-post.md)).
- `graphify-out/`: the knowledge graph of the wiki. It is never written inside `data/02-wiki`.

Outputs are not wiki sources unless an article explicitly cites them.
