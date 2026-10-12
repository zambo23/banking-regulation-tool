# AGENTS.md

This file provides guidance to AI agents working in this repository.

## What this project is

A "second brain" for **EU banking regulation, focused on credit risk**. It follows the LLM Wiki pattern popularised by Andrej Karpathy. Instead of re-reading raw documents for every question, an LLM compiles them once into a persistent, interlinked Markdown wiki and keeps it up to date as sources change.

There are three layers:

1. **Sources** (`data/00-source`, `data/01-raw`): official texts downloaded by the Python scripts in `src/`, with an Excel register that tracks every version. They are immutable once downloaded.
2. **Wiki** (`data/02-wiki`): Markdown articles written and maintained by the agent. This is the knowledge base.
3. **Schema** (this file): the rules the agent follows to build, query and maintain the wiki.

The user decides which sources matter and asks the questions. The agent does the bookkeeping: summarising, cross-referencing, citing, indexing, and flagging content that has gone stale.

An agent here has two jobs:

- **Librarian**: compile sources into the wiki, answer questions from it, audit it. See [The wiki](#the-wiki-data02-wiki) and [Workflows](#workflows).
- **Developer**: maintain the download scripts. See [Source downloaders](#source-downloaders-src).

## Repository layout

Read [docs/folder-structure.md](docs/folder-structure.md) for what lives where, who writes each folder, and how files are named. The essentials:

- `src/`: the download scripts. `data/00-source/`: the registers. `data/01-raw/`: the downloaded texts. Only the scripts write to these.
- `data/02-wiki/` and `data/03-output/` are written by the agent.
- `data/` is git-ignored.

## Scope: credit risk first

The corpus covers much more than credit risk: about 2,200 documents, including AML, payments, MiCA, DORA and securities-markets rules from ESMA. Compile selectively.

- **Core**: the default definition, the standardised approach and IRB (PD, LGD, EAD/CCF, model governance and validation, internal models), credit risk mitigation, NPE and forbearance, provisioning (the IFRS 9 interplay and the prudential backstop), loan origination and monitoring, large exposures and concentration, counterparty credit risk, securitisation, credit-risk reporting and disclosure.
- **Context**: own funds, Pillar 2/SREP/ICAAP, internal governance, stress testing. Cover these only as far as they bear on credit risk.
- **Out of scope unless the user asks**: AML/CFT, payments, crypto-assets, operational resilience, deposit guarantee schemes, resolution, and most ESMA material (securities markets, funds, investor protection). ESMA documents on securitisation and credit rating agencies can bear on credit risk (securitisation is core; ratings feed the standardised approach).

### Source authority

Every claim must make its legal force clear. From most to least binding:

| Level | Sources in this repo | Force |
|---|---|---|
| 1 | CRR, CRD, BRRD, … (`eurlex/`) | law |
| 2 | delegated and implementing regulations adopting RTS/ITS | law. The EBA files in `eba-rts/` and `eba-its/` are the EBA's **final drafts**; the adopted text is the regulation published in EUR-Lex |
| 3 | EBA guidelines (`eba-guidelines/`) | comply-or-explain |
| — | ECB supervisory guides (`ecb-guides/`) | ECB supervisory expectations for significant institutions; not law |
| — | EBA reports (`eba-reports/`) | analysis and benchmarking; not binding |
| — | EBA consultation papers (`eba-consultation-papers/`) | **proposals only**; never present them as rules in force |
| 3 | ESMA guidelines and recommendations (`esma/`, `doc_type` "Guidelines & Recommendations") | comply-or-explain |
| — | other ESMA documents (`esma/`): final reports, compliance tables, reference documents, consultation papers | by type: a final report may contain final draft RTS/ITS (the adopted text is in EUR-Lex) or final guidelines; a consultation paper is a proposal; compliance tables and reference documents are information |

## The wiki (`data/02-wiki`)

### Structure

The file layout is in [docs/folder-structure.md](docs/folder-structure.md#wiki-data02-wiki). Keep these files up to date:

- `index.md`: lists every topic wiki with a one-line description and a link (`[[irb-approach/index|IRB approach]]`). Update it whenever a topic wiki is created or its scope changes.
- `log.md`: append-only. Each entry has the date and, for every source processed, its `data/01-raw/...` path, SHA-256 (from the register) and the articles created or updated. It is how the agent knows what has already been compiled.
- `<topic>/index.md`: a 2–3 line description of the topic wiki, then every article with a one-line description and a `[[link]]`. Update it whenever an article is created, renamed or substantially changed.

Suggested starting topic wikis (create them as material arrives, not in advance):
- `regulatory-framework`
- `default-and-npe`
- `standardised-approach`
- `irb-approach`
- `credit-risk-mitigation`
- `provisioning`
- `loan-origination-and-monitoring`
- `large-exposures`
- `counterparty-credit-risk`
- `securitisation`
- `supervision-and-pillar-2`
- `esg-risks`
- `macroprudential`
- `regulatory-framework` also holds cross-cutting initiatives such as the simplification agenda.

Ask the user before creating a topic wiki outside this list.

### Article format

Every article has, in this order:

1. YAML frontmatter, as in the example below.
2. An H1 title.
3. An introduction of 2–4 lines.
4. `## Key points`: 3–7 dense bullets.
5. Body sections (`##`).
6. `## Related articles`: `[[wikilinks]]`.
7. `## Sources`: the sources cited, each with its pinpoint references.

```yaml
---
tags: [irb, lgd, downturn]
created: 2026-10-09
updated: 2026-10-09
sources:
  - path: data/01-raw/eurlex/CRR/02013R0575-20260626.pdf
    ref: CRR, consolidated 2026-06-26
  - path: data/01-raw/eba-guidelines/2019/2019-03-06_..._v1.pdf
    ref: EBA/GL/2019/03
---
```

### Citing regulation

- Cite precisely: act plus article or paragraph (`CRR Art. 178(1)(b)`, `EBA/GL/2016/07 para. 23`). Quote short key definitions verbatim.
- Record the version a claim relies on. `sources[].path` is the exact versioned file: a CELEX consolidation date, or `_vN` and the EBA reference or `doc_id`. This is how stale content is detected later.
- State the legal force when it isn't law (guideline, ECB expectation, draft, proposal). Give application dates and transitional periods when relevant.
- Keep regulatory terminology as the sources use it ("obligor", "unlikely to pay", "downturn LGD"). Define a technical term the first time it appears.

### Writing and linking

- Clear, dense, no filler. Use bullets and short sections where they help scanning.
- Link every concept that has an article. Link important concepts that don't have one yet too (stub links), and list them in the session summary.
- Before creating an article, search for similar ones. Prefer updating an existing article. If two articles overlap, propose a merge to the user.

## Workflows

### Update sources

Run `python3 src/cli.py update` (see [docs/tooling.md](docs/tooling.md#commands)); it is safe to run daily. A new version of a document is saved as a new file and logged in the register's `history` sheet; nothing is overwritten. Then run `audit` to find articles that rely on outdated versions.

### Regulatory watch

To see what is new without downloading anything, run `python3 src/cli.py update --check`. Report the new or changed items that matter for credit risk (see [Scope](#scope-credit-risk-first)) with their legal force, then download and compile them only after the user confirms.

### `compile <scope>`

Compile sources into the wiki. A scope is required because the corpus is too large to compile in one pass. The scope can be file paths, a folder, a register filter (for example "current ECB guides", "EBA guidelines tagged credit risk since 2020") or a topic ("everything on the definition of default").

1. **Select**: resolve the scope through the registers in `data/00-source`. Skip superseded editions unless asked for history. Skip files already in `log.md` with the same SHA-256. If a file is out of scope (see [Scope](#scope-credit-risk-first)), list it and skip it.
2. **Read** the whole file. Use `pdftotext -layout <file> -` for PDFs.
3. **Classify** it into one or more topic wikis.
4. **Write**: create articles for new concepts and update existing ones. Cite every claim as described in [Citing regulation](#citing-regulation).
5. **Link** the new content to related articles.
6. **Index**: update every `<topic>/index.md` touched, and `index.md` if a topic wiki was added.
7. **Log**: append an entry to `log.md`. Never rename, move or edit files in `data/01-raw`: the registers track them by path.

Finish with a summary: sources processed or skipped (with reasons), articles created and updated, stub links, and open questions.

### Query

1. Read `index.md`, then the relevant `<topic>/index.md` files.
2. Read only the articles you need.
3. Answer with `[[wikilinks]]` to the articles used, keeping their pinpoint citations and legal force.
4. If the wiki can't answer, say so plainly and suggest which sources to compile. The registers in `data/00-source` show what has been downloaded.
5. When an answer is a valuable original analysis or comparison, offer to save it: to `data/03-output/` if it's one-off, or as a wiki article if it has lasting value. An article distilled from an output cites the output file.

If the user allows it, you may also read the raw sources in `data/01-raw` directly, and use general knowledge for texts that aren't downloaded. Always say which claims rest on what: anything not checked against a downloaded text is marked **To verify**.

### Memos and reports (`data/03-output`)

For a client memo, the user can start the session with the prompt in [docs/agent-prompt-strategy-regulation.md](docs/agent-prompt-strategy-regulation.md). The conventions below apply to every file output:

- Name it `<YYYY-MM-DD>_<short-name>.<ext>` (kebab-case), directly in `data/03-output/` unless a workflow names a subfolder.
- Default to a self-contained `.html` file (inline CSS, no external assets, prints cleanly to PDF); use `.md` if asked.
- Structure: a header (to, from, date, subject), the bottom line first, then the detail, then next steps.
- Tag statements **Checked** (verified against a file in `data/01-raw`) or **To verify** (not yet checked). Label legal force as in [Source authority](#source-authority).
- End with a sources table: each source's `data/01-raw/...` path (or "not in source library"), its legal force and its verification status, plus a draft disclaimer while any **To verify** remains.

Outputs are not sources for the wiki unless an article explicitly cites them.

### Source map

`python3 src/cli.py graph` writes an interactive map of the registers and the wiki to `data/03-output/<YYYY-MM-DD>_source-map.html` (see [docs/tooling.md](docs/tooling.md#source-map)). Every link in it comes from recorded data; use it to see coverage, superseded editions and uncompiled sources, not as a source itself.

### Knowledge graph (optional)

The wiki can be turned into a graph with graphify (how to run it: [docs/tooling.md](docs/tooling.md#knowledge-graph)). Its output goes to `data/03-output/graphify-out/`, never inside `data/02-wiki`. The graph is a navigation aid: INFERRED edges are model guesses, and answers still come from the articles and their citations.

### `audit` / `lint`

A health check of the wiki. Report:

- **Stale sources**: articles citing a file that the registers now mark as outdated. That is:
  - a newer `_vN` file of the same document;
  - an ISRB act whose `current_celex` has changed;
  - an ECB guide with `edition_status=superseded`;
  - an EBA item with `later_same_reference`, or with `status=not listed`;
  - an ESMA item with `status=not listed`.
- **Uncompiled changes**: sources in scope whose SHA-256 isn't in `log.md`.
- **Duplicates**: overlapping articles that are candidates for a merge.
- **Broken links**: `[[wikilinks]]` to articles that don't exist.
- **Contradictions**: conflicting claims across articles.
- **Orphans**: articles with no links in or out.
- **Isolated topic wikis**.
- **Gaps**: concepts often cited but without an article.
- **Index drift**: index entries that don't match the files, and the reverse.

For each problem, propose a concrete fix and name the files involved. **Wait for explicit confirmation before applying anything.** Never merge, delete or reorganise on your own initiative.

### Principles

The wiki must be:

- **consistent**: same naming, structure and style everywhere;
- **self-contained**: readable without the sources;
- **densely linked**;
- **traceable**: every claim leads to a versioned source;
- **current**: stale content is flagged, never silently kept;
- **cheap to read**, for humans and LLMs alike.

When a structural choice is ambiguous (new topic wiki, merge, reorganisation), ask the user.

## Source downloaders (`src/`)

`src/cli.py` is the entry point for the downloaders; setup, dependencies and commands are in [docs/tooling.md](docs/tooling.md). In short: install with `uv`, not `pip`, and run `python3 src/cli.py <command>` from the repository root. Shared Excel code lives in `src/register.py`.

Downloaded file names are listed in [docs/folder-structure.md](docs/folder-structure.md#sources-data00-source-and-data01-raw).

### EUR-Lex (`download_isrb.py`)

- The act list comes from the table at https://www.eba.europa.eu/regulation-and-policy/single-rulebook/interactive-single-rulebook. The EBA link is used only to identify the act, because it can lag behind EUR-Lex.
- `eur-lex.europa.eu` returns an AWS WAF challenge (HTTP 202, empty body) to scripted clients, so don't scrape it. Use the Publications Office SPARQL endpoint (`publications.europa.eu/webapi/rdf/sparql`) to resolve versions, and download Cellar item URLs (`.../resource/cellar/<id>/DOC_n`). Cellar content negotiation on `/resource/celex/<id>` misses some PDFs.
- Versioning uses CELEX ids:
  - `0YYYYTNNNN-YYYYMMDD` is a consolidated version.
  - `3YYYYTNNNN` is the original OJ act.
  - The "current" version is the newest consolidation dated today or earlier that has an English expression.
  - Future-dated consolidations already exist (e.g. CRR `-20270101`); they are recorded as `next_celex`, not downloaded.
  - Acts never amended (DORA, WTR) have a base-layer consolidation with no English text, so the original `3…` act is used instead.
- Filtering SPARQL with `STRSTARTS` over all CELEX ids is slow when combined with manifestation joins. Look up manifestations with `VALUES` on exact, typed (`xsd:string`) CELEX literals.

### EBA publications (`download_eba_publications.py`)

- To add a publication type, add an entry to `PUBLICATION_TYPES`: the listing's `document_type` id (250 Guidelines, 248 draft RTS, 247 draft ITS, 257 Reports, 244 Consultation papers, …; the ids come from the filter `<select>` on the page), the preferred reference kind, the register file and the download folder.
- The listing is the EBA publications page filtered on `document_type`, paged with `&page=N`. Each `article.teaser` links directly to a file (PDF, sometimes xlsx/docx/zip). A few items (Risk Assessment Reports) link to an HTML publication page instead of a file. That page is saved as `.html`, and because it sends no ETag/Last-Modified, its `sha256` is a hash of the normalised `<main>` text, which is compared on every run. The date is in `.link-icon--calendar`; some teasers also carry a "Publication" tag in the same metadata block. EBA's type tagging is loose: some items appear in more than one listing, and the RTS listing contains a few GL/ITS documents.
- EBA has no version metadata, so the register infers versions:
  - `doc_id` is assigned on first sight and never changes.
  - A new version is recorded when the same URL returns different ETag / Last-Modified / Content-Length headers and different bytes, or when an item with the same date and title appears under a new URL (a re-upload). Date + title alone isn't unique: a few pairs occur twice in the registers.
- `eba_reference` (EBA/<GL|RTS|ITS|REP|CP|…>/YYYY/NN, preferring the listing's own kind) comes from the title, the filename, or page 1 of the PDF via `pdftotext`.
- `later_same_reference` lists later items with the same reference (consolidated versions, corrigenda), as a hint that a document may be superseded. It is only a hint:
  - EBA has reused a number: EBA/REP/2025/11 appears on two different reports.
  - Some covers cite another document ("Report complementing EBA/REP/2021/18").
- The reference regex separators deliberately exclude newlines. Otherwise a cover line "EBA/Rep/2022" followed by "08 April 2022" would read as EBA/REP/2022/08.

### ESMA library (`download_esma.py`)

- The source is the ESMA library table filtered on section 35, "Guidelines and Technical standards" (`?f[0]=basic_section:35`). Each top-level `tbody` row has `td.views-field-*` cells: `created` (dd/mm/yyyy), `field-document-reference` (the ESMA reference), `title` (link to the document page), `field-document-section`, `field-document-type` and `field-main-document` (the file link). The `Info` cell holds nested tables of related documents and translations; only top-level rows are listings.
- Paging: `items_per_page=50` with `&page=N`. `items_per_page=100` works for page 0 only; later pages return HTTP 500.
- `doc_id` is a hash of the document page URL (`/document/<slug>`), which is steadier than the file URL. A new file URL with different bytes is a new version.
- Change detection uses ETag and Last-Modified only: ESMA answers HEAD requests with `Content-Length: 0`.

### ECB supervisory guides (`download_ecb_guides.py`)

- The guides page is rendered by JavaScript. The list itself is an HTML snippet named in the page's `data-snippets` attribute (`.../supervisoryguides_include.en.html`): `<dt isoDate>` + `<dd>` with `.title a` and an explicit English link `a[lang=en]`.
- The list keeps old editions next to new ones. `guide_key` (lowercased title without a leading "ECB"/"SSM" and without "- consolidated version") groups them; the newest is `edition_status=current`, and older ones are `superseded` with `superseded_by` pointing to the next edition.
- Change detection: the `?<hash>` on the title link is a cache key, not the file's MD5, and changes when the file is replaced. The server sends Last-Modified (unreliable: it reflects redeploys) and Content-Length, but no ETag. Any of these changing triggers a download; a new `_vN` version is recorded only if the SHA-256 differs.
