# Tooling

How to set up the environment, run the download scripts, and which external tools the project and the agent use. Folder layout and file names are in [folder-structure.md](folder-structure.md).

## Rules

- Use `uv`, not `pip`.
- Python 3.10+, run as `python3`. Dependencies are in `requirements.txt`; there is no `pyproject.toml` or lock file.
- Run the CLI from the repo root: `python3 src/cli.py --help`.
- Add a new dependency to `requirements.txt` and install it with `uv pip install -r requirements.txt` before relying on it.

## Requirements

| Tool | Used for | Required |
|---|---|---|
| Python 3.10+ (`python3`) | the download scripts in `src/` | yes |
| [uv](https://docs.astral.sh/uv/) | creating the environment and installing dependencies. Use `uv`, not `pip` | yes |
| [poppler](https://poppler.freedesktop.org/) (`pdftotext`) | reading EBA references from page 1 of PDFs (scripts); reading PDFs during `compile` (agent) | optional for the scripts, needed by the agent |
| graphify (`uv tool install graphifyy`) | turning the wiki into a knowledge graph | optional |

There is no build system, linter or test suite yet.

## Setup

Dependencies (`requests`, `beautifulsoup4`, `openpyxl`) are listed in `requirements.txt`.

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Use `python3`, not `python`: some machines have no `python` command outside a virtual environment.

## Commands

`src/cli.py` is the single entry point for the downloaders. `python3 src/cli.py --help` lists everything.

```bash
python3 src/cli.py update                 # run every downloader in parallel; safe to run daily
python3 src/cli.py isrb                   # EBA Interactive Single Rulebook acts, current EUR-Lex consolidated texts
python3 src/cli.py ecb                    # ECB Banking Supervision supervisory guides
python3 src/cli.py eba guidelines rts     # EBA publications listing, one or more of: guidelines, rts, its, reports, cp
```

| Option | Applies to | Effect |
|---|---|---|
| `--check` | all | report what is outdated; download and write nothing |
| `--sequential` | `update`, `eba` | run one downloader at a time, streaming output (default: parallel, output printed per job when done) |
| `--rescan-references` | `eba` | re-read `eba_reference` for every downloaded file (run after changing `EBA_REF`) |

- Re-running is how documents get updated. A new version is saved as a new file, never over the old one.
- The EBA `reports` (~470 items) and `cp` (~490 items) listings take several minutes.
- In parallel mode, each script writes its own register, so jobs don't conflict. The run ends with a per-job summary, and the exit code is non-zero if any job failed. An EBA job exits 1 on any download error, e.g. a dead link on the EBA site.
- The CLI runs the scripts in `src/` as subprocesses with the same interpreter, from the repository root. Each script still runs on its own, e.g. `python3 src/download_eba_publications.py rts --check`. They must be run as `python3 src/<script>.py`: they import the shared Excel code as `from register import ...`, which only resolves that way.

## Reading PDFs

```bash
pdftotext -layout <file> -
```

## Knowledge graph

Run graphify from `data/03-output` on `../02-wiki`, and write its output to `data/03-output/graphify-out/`, never inside `data/02-wiki`. The graph is a navigation aid: INFERRED edges are model guesses, and answers still come from the articles and their citations.
