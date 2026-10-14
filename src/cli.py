"""Single entry point for the source downloaders.

Each subcommand runs one or more of the download scripts in src/ with the same Python
interpreter. The scripts stay runnable on their own; this only saves remembering them.

Usage:
    uv run src/cli.py update                 # run every downloader in parallel (safe to run daily)
    uv run src/cli.py update --check         # only report what would change; download and write nothing
    uv run src/cli.py isrb                   # EBA Interactive Single Rulebook acts, current EUR-Lex consolidated texts
    uv run src/cli.py ecb                    # ECB Banking Supervision supervisory guides
    uv run src/cli.py esma                   # ESMA library, section "Guidelines and Technical standards"
    uv run src/cli.py basel                  # Basel Framework (BCBS standards), current and forthcoming chapter versions
    uv run src/cli.py eba-sr                 # EBA Single Rulebook product pages: final guidelines, RTS and ITS with status and dates
    uv run src/cli.py md                     # convert new PDFs in data/01-raw to Markdown in data/02-raw-md (update does it too)
    uv run src/cli.py eba guidelines rts     # EBA publications listing, one or more types
    uv run src/cli.py eba reports --rescan-references   # re-read eba_reference for every downloaded file
    uv run src/cli.py graph                  # write the source map to data/04-output/<today>_source-map.html

EBA types: guidelines, rts, its, reports (~470 items), cp (~490 items). Reports and cp take several minutes.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from download_eba_publications import PUBLICATION_TYPES

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
LOG_DIR = ROOT / "data" / "logs"
HEARTBEAT_S = 60  # how often to list the jobs still running


def job(name: str, script: str, *args: str) -> tuple[str, list[str]]:
    return name, [sys.executable, str(SRC / script), *args]


def duration(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"


class Log:
    """Print timestamped lines tagged with the job name, and copy them to a log file."""

    def __init__(self, path: Path, width: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.width = path, width
        self.file = path.open("a", encoding="utf-8")
        self.lock = threading.Lock()

    def __call__(self, name: str, text: str) -> None:
        line = f"{datetime.now():%H:%M:%S} [{name:<{self.width}}] {text}"
        with self.lock:
            print(line, flush=True)
            self.file.write(line + "\n")
            self.file.flush()


def run(jobs: list[tuple[str, list[str]]], parallel: bool, command: str,
        after: list[tuple[str, list[str]]] | None = None) -> int:
    """Run the jobs, streaming their output line by line, and return the worst exit code.

    Every line is prefixed with the time and the job name, and copied to data/logs/. Each job's
    start and end are logged, and while jobs run a heartbeat lists them with their elapsed time.
    The `after` jobs run one at a time once all `jobs` have finished (e.g. converting new PDFs).
    """
    after = after or []
    log = Log(LOG_DIR / f"{datetime.now():%Y-%m-%d_%H%M%S}_{command}.log",
              max(len(n) for n, _ in jobs + after + [("cli", [])]))
    log("cli", f"{len(jobs)} job(s), {'parallel' if parallel and len(jobs) > 1 else 'one at a time'}; log: {log.path.relative_to(ROOT)}")
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}  # scripts print as they go, not when their buffer fills
    running: dict[str, float] = {}
    results: dict[str, tuple[int, float]] = {}
    processes: list[subprocess.Popen] = []
    done = threading.Event()

    def execute(name: str, cmd: list[str]) -> None:
        started = time.monotonic()
        running[name] = started
        log(name, "started")
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        processes.append(proc)
        for line in proc.stdout:
            log(name, line.rstrip())
        code = proc.wait()
        running.pop(name, None)
        results[name] = (code, time.monotonic() - started)
        log(name, f"finished in {duration(results[name][1])}: {'ok' if code == 0 else f'exit {code}'}")

    def heartbeat() -> None:
        while not done.wait(HEARTBEAT_S):
            now = time.monotonic()
            busy = ", ".join(f"{n} ({duration(now - t)})" for n, t in list(running.items()))
            if busy:
                log("cli", f"still running: {busy}; {len(results)}/{len(jobs) + len(after)} done")

    begun = time.monotonic()
    threading.Thread(target=heartbeat, daemon=True).start()
    # each script writes its own register, so they can run side by side
    with ThreadPoolExecutor(max_workers=len(jobs) if parallel else 1) as pool:
        futures = [pool.submit(execute, name, cmd) for name, cmd in jobs]
        try:
            for future in futures:
                future.result()
        except KeyboardInterrupt:
            for future in futures:
                future.cancel()  # jobs not started yet
            for proc in processes:
                proc.terminate()
            log("cli", "interrupted; running jobs stopped")
    if len(results) < len(jobs):
        done.set()
        return 130
    try:
        for name, cmd in after:
            execute(name, cmd)
    except KeyboardInterrupt:
        for proc in processes:
            proc.terminate()
        log("cli", "interrupted; running jobs stopped")
        done.set()
        return 130
    done.set()

    if len(jobs) + len(after) > 1:
        log("cli", f"all jobs finished in {duration(time.monotonic() - begun)}")
        for name, _ in jobs + after:
            code, took = results[name]
            log("cli", f"  {name:<16} {'ok' if code == 0 else f'exit {code}':<8} {duration(took)}")
    return max(code for code, _ in results.values())


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
    commands.add_parser("basel", parents=[check], help="Basel Framework chapters (BCBS standards)")
    commands.add_parser("eba-sr", parents=[check], help="EBA Single Rulebook product pages (final texts, status, dates)")
    md = commands.add_parser("md", parents=[check], help="convert new PDFs in data/01-raw to Markdown in data/02-raw-md")
    md.add_argument("--force", action="store_true", help="reconvert every PDF, e.g. after upgrading markitdown")
    eba = commands.add_parser("eba", parents=[check, sequential], help="EBA publications, one or more types")
    eba.add_argument("types", nargs="+", choices=PUBLICATION_TYPES, metavar="type",
                     help=f"one or more of: {', '.join(PUBLICATION_TYPES)}")
    eba.add_argument("--rescan-references", action="store_true",
                     help="re-read eba_reference for every downloaded document, not only new or changed ones")
    graph = commands.add_parser("graph", help="write an interactive map of the documents and the wiki")
    graph.add_argument("--output", help="where to write the HTML page (default: data/04-output/<today>_source-map.html)")
    args = parser.parse_args()

    if args.command == "graph":
        cmd = job("graph", "source_map.py", *(["--output", args.output] if args.output else []))[1]
        return subprocess.run(cmd, cwd=ROOT).returncode

    flags = ["--check"] if args.check else []
    if args.command == "isrb":
        jobs = [job("isrb", "download_isrb.py", *flags)]
    elif args.command == "ecb":
        jobs = [job("ecb", "download_ecb_guides.py", *flags)]
    elif args.command == "esma":
        jobs = [job("esma", "download_esma.py", *flags)]
    elif args.command == "basel":
        jobs = [job("basel", "download_basel.py", *flags)]
    elif args.command == "eba-sr":
        jobs = [job("eba sr", "download_eba_single_rulebook.py", *flags)]
    elif args.command == "md":
        jobs = [job("md", "convert_pdfs.py", *flags, *(["--force"] if args.force else []))]
    elif args.command == "eba":
        eba_flags = flags + (["--rescan-references"] if args.rescan_references else [])
        jobs = [job(f"eba {t}", "download_eba_publications.py", t, *eba_flags) for t in args.types]
    else:
        jobs = [job("isrb", "download_isrb.py", *flags), job("ecb", "download_ecb_guides.py", *flags),
                job("esma", "download_esma.py", *flags), job("basel", "download_basel.py", *flags),
                job("eba sr", "download_eba_single_rulebook.py", *flags)]
        jobs += [job(f"eba {t}", "download_eba_publications.py", t, *flags) for t in PUBLICATION_TYPES]
    # after downloading, convert the new PDFs to Markdown (data/02-raw-md)
    after = [job("md", "convert_pdfs.py", *flags)] if args.command == "update" else []
    return run(jobs, parallel=not getattr(args, "sequential", False), command=args.command, after=after)


if __name__ == "__main__":
    sys.exit(main())
