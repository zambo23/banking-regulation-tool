"""Convert the PDFs in data/01-raw to Markdown in data/02-raw-md, with markitdown.

Each PDF gets one .md file at the same relative path, with the extension changed:
    data/01-raw/eurlex/CRR/02013R0575-20260626.pdf -> data/02-raw-md/eurlex/CRR/02013R0575-20260626.md
The first line of each file is an HTML comment naming its source PDF. Files in data/01-raw never change
(a new version is a new file), so a PDF whose .md exists is skipped: re-running converts only new PDFs.
When markitdown extracts less than half the words pdftotext finds (it occasionally misreads a PDF
with a good text layer), the pdftotext text is written instead, and the header says so.
A PDF without a text layer (a scan) still gets a .md with a note, so it is not retried on every run;
a PDF that fails to convert gets none, and is retried next time. Each .md is written to a temporary
name and renamed when complete, so an interrupted run leaves no partial files.

The wiki never cites these files: it cites the PDF, whose path and SHA-256 the registers track.

Usage:
    uv run src/convert_pdfs.py             # convert every PDF that has no .md yet
    uv run src/convert_pdfs.py --check     # only count what would be converted; write nothing
    uv run src/convert_pdfs.py --force     # reconvert every PDF, e.g. after upgrading markitdown
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "01-raw"
MD_DIR = ROOT / "data" / "02-raw-md"
WORKERS = max(1, (os.cpu_count() or 2) - 2)  # leave two cores free
PROGRESS_ITEMS = 50  # print a progress line every N files
# markitdown (pdfminer) occasionally returns almost nothing for a PDF that has a good text layer, e.g. the
# iText-produced OJ text of the WTR (32023R1113): blank lines instead of 19,000 words. When it finds less than
# this share of the words pdftotext finds, the pdftotext text is used instead.
FALLBACK_SHARE = 0.5
FALLBACK_MIN_WORDS = 200


def target(pdf: Path) -> Path:
    return MD_DIR / pdf.relative_to(RAW_DIR).with_suffix(".md")


def convert(pdf: Path) -> tuple[Path, int, float]:
    """Convert one PDF; return it with the number of characters extracted and the seconds taken."""
    from markitdown import MarkItDown  # imported in the worker process

    started = time.monotonic()
    text = MarkItDown().convert(str(pdf)).text_content.strip()
    converter = f"markitdown {version('markitdown')}"
    if shutil.which("pdftotext"):
        plain = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True,
                               errors="replace").stdout.strip()
        words = len(plain.split())
        if words >= FALLBACK_MIN_WORDS and len(text.split()) < FALLBACK_SHARE * words:
            text, converter = plain, "pdftotext -layout, because markitdown extracted too little text"
    header = f"<!-- source: {pdf.relative_to(ROOT).as_posix()} (converted with {converter}) -->\n\n"
    body = text if text else "_No text layer: this PDF is probably a scan. Read the PDF itself._"
    out = target(pdf)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(header + body + "\n", encoding="utf-8")
    tmp.replace(out)
    return pdf, len(text), time.monotonic() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="count the PDFs to convert; write nothing")
    parser.add_argument("--force", action="store_true", help="reconvert PDFs that already have a .md file")
    args = parser.parse_args()

    for leftover in MD_DIR.rglob("*.md.tmp"):  # from an interrupted run
        leftover.unlink()
    pdfs = sorted(p for p in RAW_DIR.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    todo = pdfs if args.force else [p for p in pdfs if not target(p).exists()]
    print(f"{len(pdfs)} PDFs in {RAW_DIR.relative_to(ROOT)}, {len(todo)} to convert into {MD_DIR.relative_to(ROOT)}")
    if args.check or not todo:
        if args.check:
            print("Nothing written (--check)")
        return 0

    print(f"  converting with markitdown {version('markitdown')}, {WORKERS} workers")
    begun = time.monotonic()
    done = no_text = failures = 0
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(convert, pdf): pdf for pdf in todo}
        for future in as_completed(futures):
            pdf = futures[future]
            try:
                _, chars, seconds = future.result()
                done += 1
                no_text += chars == 0
                if chars == 0:
                    print(f"  no text  {pdf.relative_to(RAW_DIR)}")
                elif seconds > 60:
                    print(f"  slow     {pdf.relative_to(RAW_DIR)} ({seconds:.0f}s)")
            except Exception as exc:  # a broken or encrypted PDF must not stop the run
                failures += 1
                print(f"  ! {pdf.relative_to(RAW_DIR)}: {type(exc).__name__}: {str(exc)[:150]}", file=sys.stderr)
            finished = done + failures
            if finished % PROGRESS_ITEMS == 0:
                elapsed = time.monotonic() - begun
                left = elapsed / finished * (len(todo) - finished)
                print(f"  ... {finished}/{len(todo)} converted, about {left / 60:.0f} min left")

    print(f"  {done} converted ({no_text} without a text layer), {failures} failed, "
          f"in {(time.monotonic() - begun) / 60:.1f} min")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
