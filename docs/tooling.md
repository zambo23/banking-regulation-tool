# Tooling

How to set up the environment, run the download scripts, and which external tools the project and the agent use. Folder layout and file names are in [folder-structure.md](folder-structure.md).

## Rules

- Use `uv`, not `pip`.
- Python 3.10+. Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`; commit both.
- Run every script through `uv run`, from the repo root: `uv run src/cli.py --help`. It uses the project environment (`.venv`), so there is nothing to activate.
- Add a dependency with `uv add <package>`, remove one with `uv remove <package>`. Don't edit the dependency list by hand.

## Requirements

| Tool | Used for | Required |
|---|---|---|
| Python 3.10+ | the download scripts in `src/`. uv installs it if the machine has none | yes |
| [uv](https://docs.astral.sh/uv/) | managing the environment and dependencies, and running the scripts. Use `uv`, not `pip` | yes |
| [poppler](https://poppler.freedesktop.org/) (`pdftotext`) | reading EBA references from page 1 of PDFs (scripts); reading PDFs during `compile` (agent) | optional for the scripts, needed by the agent |
| graphify (`uv tool install graphifyy`) | turning the wiki into a knowledge graph | optional |

There is no build system, linter or test suite yet.

## Setup

Dependencies (`requests`, `beautifulsoup4`, `openpyxl`) are declared in `pyproject.toml`; `uv.lock` pins their exact versions. The project is an application, not a package (`[tool.uv] package = false`), so nothing is built or installed.

```bash
uv sync
```

`uv sync` creates `.venv` and installs the locked versions. `uv run` does the same on first use, so this step is optional.

## Commands

`src/cli.py` is the single entry point for the downloaders. `uv run src/cli.py --help` lists everything.

```bash
uv run src/cli.py update                 # run every downloader in parallel; safe to run daily
uv run src/cli.py isrb                   # EBA Interactive Single Rulebook acts, current EUR-Lex consolidated texts
uv run src/cli.py ecb                    # ECB Banking Supervision supervisory guides
uv run src/cli.py esma                   # ESMA library, section "Guidelines and Technical standards"
uv run src/cli.py basel                  # Basel Framework (BCBS standards), current and forthcoming chapter versions
uv run src/cli.py eba-sr                 # EBA Single Rulebook product pages: final texts with status and dates
uv run src/cli.py eba guidelines rts     # EBA publications listing, one or more of: guidelines, rts, its, reports, cp
uv run src/cli.py graph                  # interactive source map, see below
```

| Option | Applies to | Effect |
|---|---|---|
| `--check` | all | report what is outdated; download and write nothing |
| `--sequential` | `update`, `eba` | run one downloader at a time (default: in parallel) |
| `--rescan-references` | `eba` | re-read `eba_reference` for every downloaded file (run after changing `EBA_REF`) |

- Re-running is how documents get updated. A new version is saved as a new file, never over the old one.
- `eba-sr` reads about 420 product pages and their phases on every run (10–20 minutes); the first run also downloads about 1,500 files.
- `basel` reads about 130 timeline pages (one per chapter) on every run, about two minutes; it downloads only versions it has not saved yet.
- The EBA `reports` (~470 items) and `cp` (~490 items) listings take several minutes.
- Progress is shown live. Every line is prefixed with the time and the job name (`16:08:23 [esma] ... 50/775 items checked`). Each job logs when it starts and when it finishes, with its duration. Every minute a `[cli] still running: …` line lists the jobs not yet done and how long each has run. The long loops print a progress line every 50 items (every 5 pages while reading a listing), and ESMA logs its rate-limit waits.
- The same lines are saved to `data/logs/<YYYY-MM-DD_HHMMSS>_<command>.log`, e.g. to see afterwards which job was slow or failed.
- In parallel mode, each script writes its own register, so jobs don't conflict. The run ends with a per-job summary with durations, and the exit code is non-zero if any job failed. An EBA job exits 1 on any download error, e.g. a dead link on the EBA site.
- The CLI runs the scripts in `src/` as subprocesses with the same interpreter (the project environment, under `uv run`), from the repository root. Each script still runs on its own, e.g. `uv run src/download_eba_publications.py rts --check`. They must be run as `uv run src/<script>.py`: they import the shared Excel code as `from register import ...`, which only resolves that way.

## Reading PDFs

```bash
pdftotext -layout <file> -
```

## Source map

`uv run src/cli.py graph` writes `data/03-output/<YYYY-MM-DD>_source-map.html`, a self-contained page (open it in any browser, no network needed) that maps the document collection:

- **Outer ring**: every document in the registers, one sector per source in order of legal force (EUR-Lex acts, EBA RTS and ITS, EBA guidelines, ESMA, ECB guides, Basel Framework, EBA reports, EBA consultations). Each Basel chapter version is a separate node. ESMA documents are coloured by their listed type. Documents cited by the wiki sit nearest the centre.
- **Inner ring**: the topic wikis and their articles.
- **Links**, all taken from recorded data: article cites source (frontmatter), article links to article (`[[wikilinks]]`), ECB edition superseded by (`superseded_by`), same EBA reference on a later item (`later_same_reference`, a hint only), act to its upcoming consolidation (`next_celex`).
- **Views**: documents cited by the wiki (default), plus titles matching a credit-risk word list, or all documents (`…_source-map.html#all`). Filter by legal force, search titles, references and paths, and click any node for its details, file path and links.

Re-run it after updating sources or compiling, so the map reflects the current registers and wiki. The generator is `src/source_map.py` with its page template `src/source_map.html`.

## Knowledge graph

Run graphify from `data/03-output` on `../02-wiki`, and write its output to `data/03-output/graphify-out/`, never inside `data/02-wiki`. The graph is a navigation aid: INFERRED edges are model guesses, and answers still come from the articles and their citations.
