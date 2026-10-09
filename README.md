# banking-regulation-tool

A "second brain" for **EU banking regulation, focused on credit risk**.

Python scripts download the official texts from EUR-Lex, the EBA and ECB Banking Supervision, and track every version in Excel registers. An AI coding agent (Claude Code, Codex, …) then compiles those texts into an interlinked Markdown wiki. Every claim is cited to the article or paragraph, its legal force is stated, and it points to the exact file version it relies on. When a source changes, the wiki shows which articles have gone stale.

It follows the *LLM Wiki* pattern popularised by Andrej Karpathy: compile the documents once into a maintained knowledge base, instead of re-reading raw PDFs for every question.

```text
 EUR-Lex · EBA · ECB          data/00-source            data/02-wiki               data/03-output
 ─────────────────── ──►  registers (.xlsx)    ──►  interlinked Markdown   ──►  memos, comparisons,
   src/ downloaders       data/01-raw (texts)       wiki, written by the        reports
                          versioned, immutable      agent per AGENTS.md
```

## What it covers

| Source | Script | What is downloaded |
| --- | --- | --- |
| EUR-Lex, via the EBA Interactive Single Rulebook act list | `download_isrb.py` | CRR, CRD, BRRD, DORA, … the current consolidated text (or the original act if never amended) |
| EBA publications | `download_eba_publications.py <type>` | `guidelines`, `rts`, `its`, `reports`, `cp` (consultation papers) |
| ECB Banking Supervision | `download_ecb_guides.py` | supervisory guides, with superseded editions tracked |

The corpus is about 1,400 documents. The wiki deliberately covers **credit risk** first:

- **core:** the definition of default, the standardised approach, IRB, credit risk mitigation, NPE, provisioning, loan origination, large exposures, counterparty credit risk and securitisation;
- **context:** own funds, Pillar 2, governance and stress testing, as far as they bear on credit risk.

Other areas are compiled only on request.

## Quick start

Requirements: Python 3.10+ and, optionally, [poppler](https://poppler.freedesktop.org/) (`pdftotext`), which the scripts use to read EBA references from PDFs and the agent uses to read PDFs.

```bash
git clone git@github.com:zambo23/banking-regulation-tool.git
cd banking-regulation-tool
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
brew install poppler            # macOS; apt install poppler-utils on Debian/Ubuntu

python src/download_isrb.py                          # EU acts (EUR-Lex)
python src/download_eba_publications.py guidelines   # also: rts, its, reports, cp
python src/download_ecb_guides.py                    # ECB supervisory guides
```

Every script accepts `--check`, which reports what is new or outdated without downloading anything. The scripts are safe to re-run daily. A changed document is saved as a new version next to the old one, and both are logged in the register's `history` sheet.

`data/` is git-ignored: the downloaded texts and the wiki stay on your machine.

## Working with the agent

Start your agent from the repository root. It reads [`AGENTS.md`](AGENTS.md) (Claude Code reads it through `CLAUDE.md`), which defines the wiki's structure, citation rules and workflows. Then just ask:

| Goal | Example prompt |
| --- | --- |
| Plan a topic | `Propose the sources for "collateral valuation"; flag gaps; don't compile yet.` |
| Compile | `compile "definition of default"` |
| Ask | `When can a forborne exposure return to non-defaulted status? Cite the sources.` |
| Client memo | `Senior consultant; client: P2P lending platform in Ireland, SME borrowers. What are the requirements, and can it outsource credit scoring? Write a memo.` |
| Health check | `audit`: stale sources, uncompiled changes, broken links, duplicates, gaps |

What the agent does by default:

- states the legal force of every claim: law, comply-or-explain guidelines, ECB expectations, non-binding reports or proposals;
- separates what it checked against a downloaded text from what it is recalling from its own knowledge, which it marks *To verify*;
- asks before merging, deleting or reorganising anything in the wiki.

See [`docs/how-to-query.md`](docs/how-to-query.md) for how to write effective prompts and get memos.

## Repository layout

```text
src/                    download scripts + shared register code (register.py)
data/00-source/         one Excel register per source: `documents` (current) + `history` (all versions)
data/01-raw/            downloaded texts, never edited; old versions kept next to new ones
data/02-wiki/           the knowledge base: index.md, log.md, <topic>/<article>.md
data/03-output/         disposable outputs: memos, reports, graphs
docs/                   user guides
AGENTS.md               the rules every agent follows (CLAUDE.md points to it)
```

## Design choices

- **Sources are immutable.** Files in `data/01-raw` are never edited or renamed; the registers track them by path.
- **Citations are versioned.** Each wiki article lists the exact file it relies on, such as a CRR consolidation date or an EBA `_vN` version, so an audit can tell when it's out of date.
- **Legal force is explicit.** EBA RTS/ITS files are the EBA's *final drafts*: the adopted law is the Commission regulation in EUR-Lex. Consultation papers are never presented as rules in force.
- **No scraping of EUR-Lex pages.** EUR-Lex returns a bot challenge to scripts, so acts are resolved through the Publications Office SPARQL endpoint and downloaded from Cellar.

## Limitations

- **Not downloaded yet:**
  - Commission delegated and implementing regulations (the adopted RTS/ITS);
  - ECB Regulations;
  - the EBA Q&A;
  - national law and national supervisory guidance.
  
  The agent flags claims that rely on these.
- **EBA versions are inferred** from HTTP headers and file contents, because the EBA publishes no version metadata. The `later_same_reference` column is only a hint that a document may be superseded.
- **No tests yet,** and no build or lint setup.
- **Not legal advice.** The output supports analysis, but the primary texts remain authoritative.

## License

[MIT](LICENSE)
