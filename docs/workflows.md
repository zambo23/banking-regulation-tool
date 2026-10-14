# Workflows

The tasks the agent runs on this repository. The rules they rely on (scope, legal force, article format, citation) are in [llm-wiki.md](llm-wiki.md).

## Update sources

Run `uv run src/cli.py update` (see [tooling.md](tooling.md#commands)); it is safe to run daily. A new version of a document is saved as a new file and logged in the register's `history` sheet; nothing is overwritten. New PDFs are then converted to Markdown in `data/02-raw-md`. Then run `audit` to find articles that rely on outdated versions.

## Regulatory watch

To see what is new without downloading anything, run `uv run src/cli.py update --check`. Report the new or changed items that matter for credit risk (see [Scope](llm-wiki.md#scope-credit-risk-first)) with their legal force, then download and compile them only after the user confirms.

## `compile <scope>`

Compile sources into the wiki. A scope is required because the corpus is too large to compile in one pass. The scope can be file paths, a folder, a register filter (for example "current ECB guides", "EBA guidelines tagged credit risk since 2020") or a topic ("everything on the definition of default").

1. **Select**: resolve the scope through the registers in `data/00-source`. Skip superseded editions unless asked for history. Skip files already in `log.md` with the same SHA-256. If a file is out of scope (see [Scope](llm-wiki.md#scope-credit-risk-first)), list it and skip it.
2. **Read** the whole file. For a PDF, read its Markdown version in `data/02-raw-md` when there is one (same path, `.md`); otherwise use `pdftotext -layout <file> -`. Cite the `data/01-raw` file either way.
3. **Classify** it into one or more topic wikis.
4. **Write**: create articles for new concepts and update existing ones. Cite every claim as described in [Citing regulation](llm-wiki.md#citing-regulation).
5. **Link** the new content to related articles.
6. **Index**: update every `<topic>/index.md` touched, and `index.md` if a topic wiki was added.
7. **Log**: append an entry to `log.md`. Never rename, move or edit files in `data/01-raw`: the registers track them by path.

Finish with a summary: sources processed or skipped (with reasons), articles created and updated, stub links, and open questions.

## Query

1. Read `index.md`, then the relevant `<topic>/index.md` files.
2. Read only the articles you need.
3. Answer with `[[wikilinks]]` to the articles used, keeping their pinpoint citations and legal force.
4. If the wiki can't answer, say so plainly and suggest which sources to compile. The registers in `data/00-source` show what has been downloaded.
5. When an answer is a valuable original analysis or comparison, offer to save it: to `data/04-output/` if it's one-off, or as a wiki article if it has lasting value. An article distilled from an output cites the output file.

If the user allows it, you may also read the raw sources in `data/01-raw` directly (or their Markdown versions in `data/02-raw-md`), and use general knowledge for texts that aren't downloaded. Always say which claims rest on what: anything not checked against a downloaded text is marked **To verify**.

## Memos and reports (`data/04-output`)

For a client memo, the user can start the session with the prompt in [agent-prompt-strategy-regulation.md](agent-prompt-strategy-regulation.md); for a model validation, with [agent-prompt-model-validator.md](agent-prompt-model-validator.md). The conventions below apply to every file output:

- Name it `<YYYY-MM-DD>_<short-name>.<ext>` (kebab-case), directly in `data/04-output/` unless a workflow names a subfolder.
- Default to a self-contained `.html` file (inline CSS, no external assets, prints cleanly to PDF); use `.md` if asked.
- Structure: a header (to, from, date, subject), the bottom line first, then the detail, then next steps.
- Tag statements **Checked** (verified against a file in `data/01-raw`) or **To verify** (not yet checked). Label legal force as in [Source authority](llm-wiki.md#source-authority).
- End with a sources table: each source's `data/01-raw/...` path (or "not in source library"), its legal force and its verification status, plus a draft disclaimer while any **To verify** remains.

Outputs are not sources for the wiki unless an article explicitly cites them.

## Source map

`uv run src/cli.py graph` writes an interactive map of the registers and the wiki to `data/04-output/<YYYY-MM-DD>_source-map.html` (see [tooling.md](tooling.md#source-map)). Every link in it comes from recorded data; use it to see coverage, superseded editions and uncompiled sources, not as a source itself.

## Knowledge graph (optional)

The wiki can be turned into a graph with graphify (how to run it: [tooling.md](tooling.md#knowledge-graph)). Its output goes to `data/04-output/graphify-out/`, never inside `data/03-wiki`. The graph is a navigation aid: INFERRED edges are model guesses, and answers still come from the articles and their citations.

## `audit` / `lint`

A health check of the wiki. Report:

- **Stale sources**: articles citing a file that the registers now mark as outdated. That is:
  - a newer `_vN` file of the same document;
  - an ISRB act whose `current_celex` has changed;
  - an ECB guide with `edition_status=superseded`;
  - an EBA item with `later_same_reference`, or with `status=not listed`;
  - an ESMA item with `status=not listed`;
  - an EBA Single Rulebook document with `is_current_version` false (a previous version: check whether the current version amends or replaces it; an amended guideline often stays in force), or with `status=not listed`;
  - a Basel chapter version with `bis_status` Superseded or "Removed on …", or `status=not listed`, or Current but not its chapter's `current_doc_id`. A Forthcoming version is not stale; note when it has become Current.
- **Uncompiled changes**: sources in scope whose SHA-256 isn't in `log.md`.
- **Duplicates**: overlapping articles that are candidates for a merge.
- **Broken links**: `[[wikilinks]]` to articles that don't exist.
- **Contradictions**: conflicting claims across articles.
- **Orphans**: articles with no links in or out.
- **Isolated topic wikis**.
- **Gaps**: concepts often cited but without an article.
- **Index drift**: index entries that don't match the files, and the reverse.

For each problem, propose a concrete fix and name the files involved. **Wait for explicit confirmation before applying anything.** Never merge, delete or reorganise on your own initiative.
