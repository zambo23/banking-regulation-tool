"""Recognise documents that are not in English, so the downloaders keep English texts only.

The EU sources publish translations next to the English text, often as separate listings, and their
file names follow no single convention (..._bg_tra.pdf, ..._FI_COR.pdf, 2011-188pt.pdf, ...-enbg_0.pdf,
bg_-_jc_2014_43_..., the non-ISO cz, ee and dk), while some carry the English title. So a PDF is judged
by its text, read from its first pages with pdftotext:
- Cyrillic or Greek script: not English;
- more common function words of another EU language (der/und, le/et, el/y, het/van, och/att, w/się,
  și/în, ...) than of English (the/of/and/which/shall, ...): not English;
- a language code in the file name and few English function words: not English.
An English table (an annex listing indices or currencies) has few function words in any language, so it
counts as English. Files that are not PDFs are judged by their name only.

Checked against the 3,596 files downloaded by 2026-10-14: 464 found not English, the English tables kept.
"""

from __future__ import annotations

import re
import shutil
import subprocess

LANGUAGE_CODES = "bg|cs|cz|da|dk|de|ee|el|es|et|fi|fr|ga|hr|hu|it|lt|lv|mt|nl|pl|pt|ro|sk|sl|sv"
# a language code at the end of a file stem (optionally _tra/_cor[N] and _N), or at its start (bg_-_...)
LANGUAGE_NAME = re.compile(
    rf"(?:^|[_\-\s\d]|en)(?:{LANGUAGE_CODES})(?:[_\-\s](?:tra|cor)\d*)?(?:[_\-](?:\d+|bis))?_?$"
    rf"|^(?:{LANGUAGE_CODES})_-_|[_\-\s](?:{LANGUAGE_CODES})[_\-\s](?:tra|cor)\d*", re.IGNORECASE)

ENGLISH = set("the of and to in for is on that by with be as are or which shall this an should from not "
              "have has been its their such where".split())
# frequent function words of the other EU languages that are not also English words
FOREIGN = set("""
der die und das ist von mit für nicht auf den dem des eine einer zu im sowie oder
le la les et du une est pour dans sur que qui aux par ces sont être leur
el los las y del por con para una lo como entre sus ser según
il di che della delle nel dei degli alla sono essere gli
het van een voor op met zijn niet worden deze aan bij
och att för som av med på inte eller skall ska
og af ikke til skal eller fra ved
ja ei tai sekä ovat että
w z na się że jest oraz lub przez dla
se je pro že nebo jsou podle
és az hogy vagy szerint
și în cu pentru care sau prin
ir yra arba pagal kad
un ar vai kas
ning või mis
li ta tal fil u jew
iz za koje kao ili su
""".split())
WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
PAGES = 5  # pages of a PDF read for the check


def name_suggests_translation(filename: str) -> bool:
    stem = filename.rpartition(".")[0] if "." in filename else filename
    return bool(LANGUAGE_NAME.search(stem))


def text_is_not_english(text: str, name_hint: bool = False) -> bool:
    words = [w.lower() for w in WORD.findall(text)]
    if len(words) < 30:
        return name_hint  # too little text to judge
    letters = [c for c in text if c.isalpha()]
    script = sum(1 for c in letters if "Ͱ" <= c <= "Ͽ" or "Ѐ" <= c <= "ӿ") / len(letters)
    english = sum(w in ENGLISH for w in words) / len(words)
    foreign = sum(w in FOREIGN for w in words) / len(words)
    return script > 0.3 or (foreign > 0.02 and foreign > english) or (name_hint and english < 0.10)


def pdf_text(content: bytes) -> str | None:
    """Text of the first pages of a PDF, or None when pdftotext is not installed."""
    if not shutil.which("pdftotext"):
        return None
    result = subprocess.run(["pdftotext", "-l", str(PAGES), "-", "-"], input=content, capture_output=True)
    return result.stdout.decode("utf-8", errors="replace")


def is_not_english(filename: str, content: bytes | None = None) -> bool:
    """True when a downloaded file is a translation: by its text for a PDF, by its name otherwise."""
    name_hint = name_suggests_translation(filename)
    if content is not None and content[:5] == b"%PDF-":
        text = pdf_text(content)
        if text is not None:
            return text_is_not_english(text, name_hint)
    return name_hint
