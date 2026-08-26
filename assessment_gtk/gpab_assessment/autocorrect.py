"""Fixed-table autocorrect, shared by TouchEntry and AutoTextView.

Not a spelling model — a plain typo->correction lookup, seeded from a scan of
this clinician's own real session notes (see git history for how the seed
list was built). Only fires on an exact (case-insensitive) match against a
known typo, so it never "corrects" a real word it doesn't recognise the way
a dictionary-based checker would.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_DATA_PATH = Path(__file__).parent / "autocorrect_data.json"
_TRAILING_WORD_RE = re.compile(r"[A-Za-z']+$")

with _DATA_PATH.open() as _f:
    _CORRECTIONS: dict[str, str] = json.load(_f)


def _match_case(original: str, replacement: str) -> str:
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def find_correction(preceding_text: str) -> tuple[int, str] | None:
    """If `preceding_text` ends in a known typo, return (word_len, corrected).

    `word_len` is how many trailing characters of `preceding_text` the typo
    occupies (i.e. what the caller should delete before inserting the
    correction). Returns None if no correction applies.
    """
    m = _TRAILING_WORD_RE.search(preceding_text)
    if not m:
        return None
    word = m.group(0)
    correction = _CORRECTIONS.get(word.lower())
    if correction is None or correction == word.lower():
        return None
    return len(word), _match_case(word, correction)
