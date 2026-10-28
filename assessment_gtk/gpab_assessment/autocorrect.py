"""Fixed-table autocorrect, shared by TouchEntry and AutoTextView.

Not a spelling model — a plain typo->correction lookup, seeded from a scan of
this clinician's own real session notes (see git history for how the seed
list was built). Only fires on an exact (case-insensitive) match against a
known typo, so it never "corrects" a real word it doesn't recognise the way
a dictionary-based checker would.

Two tables: the fixed seed (autocorrect_data.json, beside this file) and a
learned one (~/.local/share/pab/autocorrect_learned.json, shared by gpabd and
gpabs like the spell-check word list) that grows each time a suggestion is
picked in the Ctrl+S spell check (spellcheck.learn) — so a typo fixed once
there is fixed inline while typing from then on, and comes first in the
spell check's own suggestions. Learned entries win over the seed.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

_DATA_PATH = Path(__file__).parent / "autocorrect_data.json"
_LEARNED_PATH = Path.home() / ".local" / "share" / "pab" / "autocorrect_learned.json"
_TRAILING_WORD_RE = re.compile(r"[A-Za-z']+$")

with _DATA_PATH.open() as _f:
    _CORRECTIONS: dict[str, str] = json.load(_f)


def _read_learned() -> dict[str, str]:
    try:
        return {k.lower(): v for k, v in json.loads(_LEARNED_PATH.read_text()).items()}
    except Exception:
        return {}


_learned: dict[str, str] = _read_learned()


def _write_learned() -> None:
    """Atomic write (temp file + rename), same as the spell-check word list."""
    _LEARNED_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_LEARNED_PATH.parent, prefix=".autocorrect_learned.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(dict(sorted(_learned.items())), indent=2) + "\n")
        os.replace(tmp, _LEARNED_PATH)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def lookup(word: str) -> str | None:
    """Known correction for `word` (lowercase), learned first, else None."""
    w = word.lower()
    return _learned.get(w) or _CORRECTIONS.get(w)


def learn(typo: str, correction: str) -> None:
    """Remember typo -> correction for good. Re-reads the file first so a
    word learned meanwhile in the other app (gpabd vs gpabs) isn't lost."""
    t, c = typo.lower(), correction.lower()
    if not t or t == c:
        return
    _learned.update(_read_learned())
    if _learned.get(t) == c:
        return
    _learned[t] = c
    _write_learned()


def forget(word: str) -> None:
    """`word` was added to the spell check's dictionary — it's a real word,
    not a typo. Stored as word -> itself, which find_correction treats as
    "leave alone", so this also overrides a seed-table entry for it."""
    w = word.lower()
    _learned.update(_read_learned())
    if _learned.get(w) == w:
        return
    _learned[w] = w
    _write_learned()


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
    correction = lookup(word)
    if correction is None or correction == word.lower():
        return None
    return len(word), _match_case(word, correction)
