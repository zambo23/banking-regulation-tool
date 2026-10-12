"""Single entry point for the source downloaders.

Each subcommand runs one or more of the download scripts in src/ with the same Python
interpreter. The scripts stay runnable on their own; this only saves remembering them.

Usage:
    python3 src/cli.py update                 # run every downloader in parallel (safe to run daily)
    python3 src/cli.py update --check         # only report what would change; download and write nothing
    python3 src/cli.py isrb                   # EBA Interactive Single Rulebook acts, current EUR-Lex consolidated texts
    python3 src/cli.py ecb                    # ECB Banking Supervision supervisory guides
    python3 src/cli.py esma                   # ESMA library, section "Guidelines and Technical standards"
    python3 src/cli.py eba guidelines rts     # EBA publications listing, one or more types
    python3 src/cli.py eba reports --rescan-references   # re-read eba_reference for every downloaded file
    python3 src/cli.py graph                  # write the source map to data/03-output/<today>_source-map.html

EBA types: guidelines, rts, its, reports (~470 items), cp (~490 items). Reports and cp take several minutes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from download_eba_publications import PUBLICATION_TYPES

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def job(name: str, script: str, *args: str) -> tuple[str, list[str]]:
    return name, [sys.executable, str(SRC / script), *args]


def run(jobs: list[tuple[str, list[str]]], parallel: bool) -> int:
    """Run the jobs, print each one's output as a block, and return the worst exit code."""
    if not parallel or len(jobs) == 1:
        codes = [subprocess.run(cmd, cwd=ROOT).returncode for _, cmd in jobs]
    else:
        # each script writes its own register, so they can run side by side
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            results = list(pool.map(lambda j: subprocess.run(j[1], cwd=ROOT, capture_output=True, text=True), jobs))
        for (name, _), result in zip(jobs, results):
            print(f"=== {name}")
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
        codes = [r.returncode for r in results]
    if len(jobs) > 1:
        print("\nSummary:")
        for (name, _), code in zip(jobs, codes):
            print(f"  {name:<16} {'ok' if code == 0 else f'exit {code}'}")
    return max(codes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    check = argparse.ArgumentParser(add_help=False)
    check.add_argument("--check", action="store_true", help="report changes without downloading or writing")
    sequential = argparse.ArgumentParser(add_help=False)
    sequential.add_argument("--sequential", action="store_true", help="run one downloader at a time, streaming output")

    commands.add_parser("update", parents=[check, sequential], help="run every downloader")
    commands.add_parser("isrb", parents=[check], help="EUR-Lex consolidated texts of the ISRB acts")
    commands.add_parser("ecb", parents=[check], help="ECB supervisory guides")
    commands.add_parser("esma", parents=[check], help="ESMA guidelines and technical standards")
    eba = commands.add_parser("eba", parents=[check, sequential], help="EBA publications, one or more types")
    eba.add_argument("types", nargs="+", choices=PUBLICATION_TYPES, metavar="type",
                     help=f"one or more of: {', '.join(PUBLICATION_TYPES)}")
    eba.add_argument("--rescan-references", action="store_true",
                     help="re-read eba_reference for every downloaded document, not only new or changed ones")
    graph = commands.add_parser("graph", help="write an interactive map of the documents and the wiki")
    graph.add_argument("--output", help="where to write the HTML page (default: data/03-output/<today>_source-map.html)")
    args = parser.parse_args()

    if args.command == "graph":
        return run([job("graph", "source_map.py", *(["--output", args.output] if args.output else []))], parallel=False)

    flags = ["--check"] if args.check else []
    if args.command == "isrb":
        jobs = [job("isrb", "download_isrb.py", *flags)]
    elif args.command == "ecb":
        jobs = [job("ecb", "download_ecb_guides.py", *flags)]
    elif args.command == "esma":
        jobs = [job("esma", "download_esma.py", *flags)]
    elif args.command == "eba":
        eba_flags = flags + (["--rescan-references"] if args.rescan_references else [])
        jobs = [job(f"eba {t}", "download_eba_publications.py", t, *eba_flags) for t in args.types]
    else:
        jobs = [job("isrb", "download_isrb.py", *flags), job("ecb", "download_ecb_guides.py", *flags),
                job("esma", "download_esma.py", *flags)]
        jobs += [job(f"eba {t}", "download_eba_publications.py", t, *flags) for t in PUBLICATION_TYPES]
    return run(jobs, parallel=not getattr(args, "sequential", False))


if __name__ == "__main__":
    sys.exit(main())
