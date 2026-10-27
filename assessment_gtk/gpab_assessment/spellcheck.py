"""Ctrl+S spell-check pass — dictionary lookup, personal word list, and the
live-widget field walk it runs over.

Backend is `enchant` (pyenchant), a thin binding over the system's
`libenchant`/hunspell dictionaries — installed via the `python3-enchant`
system package, picked up here through the venv's `--system-site-packages`
setup (see requirements.txt: not listed there for the same reason PyGObject
itself isn't — both are system packages this venv inherits, not pip
installs). `en_AU` is the language; not a spelling model, just check()/
suggest() calls against a real dictionary — this is deliberately NOT the
same thing as autocorrect.py's fixed-typo table (that fires inline on a
known exact typo while typing; this runs as an explicit reviewed pass and
can flag anything the dictionary doesn't recognise).

Physio notes are full of legitimate clinical shorthand a general-English
dictionary doesn't know (allodynia, nociceptive, SIJ, PRN...) — flagging
those every pass would make this useless. `spellcheck_personal_dict.json`
is a whitelist of such words, seeded from a real scan of this clinician's
own session notes (same provenance as autocorrect_data.json) and grown
via the modal's "add to dictionary" action, which persists here so a term
is never flagged again in any future session.

Where the word list lives (moved 2026-10-11): the live, growing list is
~/.local/share/pab/spellcheck_personal_dict.json — outside git and shared by
gpabd and gpabs, same home as sticky_note.json. It used to be written into
this package directory, which gave the dev checkout and the gpab-stable
worktree separate copies that drifted apart, dirtied stable's git tree on
every "add to dictionary", and conflicted on every dev->main promotion.
The copy beside this file is now a read-only seed: used only to create the
user file the first time it doesn't exist, never written to.

Suggestions (reworked 2026-10-27): hunspell's own suggest() ignores how
common a word is, so "wiht" offered "whit" before "with" and "stil" never
offered "still" — on this clinician's 111 recorded real typos it put the
right word first only 75% of the time. suggest() now pools hunspell's
candidates with every known word within ~2 edits (spell_freq_en.json's
common-English list, built by scripts/build_spell_freq.py, plus the personal
list and KB vocabulary) and ranks them by edit cost (adjacent-key slips,
swapped letters and a missing apostrophe cost less than other edits) minus
how common the word is; run-together words ("moderateand") also get a
two-word split. A correction picked here is learned (autocorrect.learn) and
comes first from then on, and is applied inline while typing.

Known words beyond the dictionary: short all-caps abbreviations (THR, BPI,
TBAx — 2+ capitals, 6 letters or fewer) aren't flagged, and clinical terms
used at least twice across clinical_kb.db's text are accepted (a term seen
only once there can be a typo in the KB itself).

Field walk: rather than depend on search.py's hand-maintained _FIELD_LABELS
id list (which can drift — see pab's CLAUDE.md "Keeping docs and search in
sync"), collect_fields() walks the live widget tree directly for every
AutoTextView/TouchEntry instance, whether or not it has a curated label.
_FIELD_LABELS is still consulted, best-effort, to show a nicer name in the
modal — a field missing from it just falls back to showing its bare
field_id, degrading gracefully rather than being skipped. Gtk.Stack keeps
every child in the tree regardless of which page is visible, so this
reaches every assessment section and every currently-mounted objective
region without needing the user to click through tabs first — the one gap
is a region toggled OFF, whose widgets are genuinely unmounted (see
region_topbar.py); a toggled-off region isn't covered until switched on.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import collections
import sqlite3

import enchant

from . import autocorrect
from .objective.kb_db import open_db
from .search import _iter_descendants, _FIELD_LABELS, _SECTION_SHORT
from .widgets import AutoTextView, TouchEntry

_DICT_LANG = "en_AU"
_PERSONAL_PATH = Path.home() / ".local" / "share" / "pab" / "spellcheck_personal_dict.json"
_SEED_PATH = Path(__file__).parent / "spellcheck_personal_dict.json"
_FREQ_PATH = Path(__file__).parent / "spell_freq_en.json"
_WORD_RE = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
_MAX_SUGGESTIONS = 8

_checker = enchant.Dict(_DICT_LANG)


def _load_personal() -> set[str]:
    path = _PERSONAL_PATH if _PERSONAL_PATH.exists() else _SEED_PATH
    try:
        return {w.lower() for w in json.loads(path.read_text())}
    except Exception:
        return set()


def _save_personal() -> None:
    """Atomic write (temp file + rename) so a crash mid-write can never leave
    a truncated word list behind."""
    _PERSONAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_PERSONAL_PATH.parent, prefix=".spellcheck_dict.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(sorted(_personal), indent=2) + "\n")
        os.replace(tmp, _PERSONAL_PATH)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


_personal: set[str] = _load_personal()


def _load_freq() -> dict[str, float]:
    try:
        return json.loads(_FREQ_PATH.read_text())
    except Exception:
        return {}


_KB_TEXT = (
    ("condition", "name"), ("condition", "short_name"), ("condition", "context"),
    ("test", "name"), ("test", "also_known_as"), ("test", "procedure"),
    ("test", "positive_finding"), ("test", "clinical_notes"), ("test", "pitfalls"),
    ("condition_feature", "feature_name"), ("condition_feature", "feature_value"),
    ("red_flag", "flag_text"), ("subjective_checklist", "question_text"),
    ("subjective_checklist", "positive_finding"), ("differentiator", "narrative"),
    ("cluster", "name"), ("cluster", "clinical_interpretation"), ("clinical_concept", "content"),
)


def _load_kb_words() -> set[str]:
    """Lowercase words used 2+ times in the KB's clinical text (not its
    reference columns). Empty if the DB isn't reachable."""
    counts: collections.Counter = collections.Counter()
    try:
        con = open_db()
    except Exception:
        return set()
    try:
        for table, col in _KB_TEXT:
            try:
                for (v,) in con.execute(f"SELECT {col} FROM {table}"):
                    for w in _WORD_RE.findall(v or ""):
                        if len(w) >= 4 and not w.isupper():
                            counts[w.lower()] += 1
            except sqlite3.Error:
                continue
    finally:
        con.close()
    return {w for w, n in counts.items() if n >= 2}


_freq: dict[str, float] = _load_freq()
_kb_words: set[str] = _load_kb_words()
_by_len: dict[int, list[str]] | None = None   # candidate index, built on first suggest()

_DEFAULT_ZIPF = 1.5     # a hunspell-only word missing from the frequency list
_VOCAB_ZIPF = 3.5       # personal / KB words: rare in general English, common here
_FREQ_WEIGHT = 0.35
_MAX_COST = 2.6
_KEY_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
_KEY_POS = {c: (r, i) for r, row in enumerate(_KEY_ROWS) for i, c in enumerate(row)}


def _is_abbreviation(word: str) -> bool:
    return len(word) <= 6 and sum(c.isupper() for c in word) >= 2


def is_known(word: str) -> bool:
    lw = word.lower()
    return (lw in _personal or lw in _kb_words or _is_abbreviation(word)
            or _checker.check(word))


def _zipf(word: str) -> float:
    if word in _freq:
        return _freq[word]
    if word in _personal or word in _kb_words:
        return _VOCAB_ZIPF
    return _DEFAULT_ZIPF


def _adjacent_keys(a: str, b: str) -> bool:
    if a in _KEY_POS and b in _KEY_POS:
        (r1, c1), (r2, c2) = _KEY_POS[a], _KEY_POS[b]
        return abs(r1 - r2) <= 1 and abs(c1 - c2) <= 1
    return False


def _edit_cost(a: str, b: str) -> float:
    """Damerau-Levenshtein distance, weighted for how typos actually happen:
    a neighbouring-key slip 0.7, two swapped letters 0.6, a left-out
    apostrophe 0.1, anything else 1. Gives up (inf) once every alignment
    is past _MAX_COST."""
    la, lb = len(a), len(b)
    prev2: list[float] = []
    prev = [float(j) for j in range(lb + 1)]
    for i in range(1, la + 1):
        cur = [float(i)] + [0.0] * lb
        for j in range(1, lb + 1):
            if a[i - 1] == b[j - 1]:
                sub = 0.0
            elif _adjacent_keys(a[i - 1], b[j - 1]):
                sub = 0.7
            else:
                sub = 1.0
            ins = 0.1 if b[j - 1] == "'" else 1.0
            v = min(prev[j] + 1.0, cur[j - 1] + ins, prev[j - 1] + sub)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                v = min(v, prev2[j - 2] + 0.6)
            cur[j] = v
        if min(cur) > _MAX_COST:
            return float("inf")
        prev2, prev = prev, cur
    return prev[lb]


def _candidate_index() -> dict[int, list[str]]:
    global _by_len
    if _by_len is None:
        _by_len = collections.defaultdict(list)
        for w in set(_freq) | _personal | _kb_words:
            _by_len[len(w)].append(w)
    return _by_len


# Short words a run-together split may produce; any other half must be 3+
# letters, or "scaned"/"stirre" split into junk like "scan ed"/"stir re".
_SHORT_WORDS = frozenset((
    "a an as at be by do go he if in is it me my no of on or so to up us we"
).split())


def _splits(t: str) -> list[tuple[float, str]]:
    """Run-together words ("moderateand" -> "moderate and"): one space
    inserted where both halves are common known words. Costed as one full
    edit, so a real one-letter typo fix of a common word still wins."""
    out = []
    for i in range(1, len(t)):
        a, b = t[:i], t[i:]
        if any(len(h) < 3 and h not in _SHORT_WORDS for h in (a, b)):
            continue
        za, zb = _freq.get(a, 0.0), _freq.get(b, 0.0)
        if za >= 3.0 and zb >= 3.0:
            out.append((1.0 - _FREQ_WEIGHT * min(za, zb), f"{a} {b}"))
    return out


# Never offered as a suggestion (still accepted if actually typed): one
# mis-tap away from landing in a clinical note — "wiht" offered "shit" 2nd.
_NEVER_SUGGEST = frozenset({"shit", "shat", "fuck", "fucks", "cunt", "piss", "crap", "twat", "wank"})


def suggest(word: str) -> list[str]:
    t = word.lower()
    cands = {c.lower() for c in _checker.suggest(word) if " " not in c and "-" not in c}
    letters = set(t)
    for length in range(len(t) - 2, len(t) + 3):
        for w in _candidate_index().get(length, ()):
            if len(letters & set(w)) >= min(len(letters), len(set(w))) - 2:
                cands.add(w)
    scored = _splits(t) if len(t) >= 5 else []
    for w in cands:
        cost = _edit_cost(t, w)
        if cost != float("inf"):
            scored.append((cost - _FREQ_WEIGHT * _zipf(w), w))
    ranked = [w for _score, w in sorted(scored) if w not in _NEVER_SUGGEST]
    learned = autocorrect.lookup(t)
    if learned and learned != t:
        ranked = [learned] + [w for w in ranked if w != learned]
    out: list[str] = []
    for w in ranked:
        w = autocorrect._match_case(word, w)
        if w not in out:
            out.append(w)
        if len(out) == _MAX_SUGGESTIONS:
            break
    return out


def learn(typo: str, correction: str) -> None:
    """A suggestion was picked for `typo`: remember it (see autocorrect)."""
    if typo.lower() not in _personal:
        autocorrect.learn(typo, correction)


def add_to_personal(word: str) -> None:
    """Whitelist `word` (case-insensitively) permanently, across sessions.
    It's a real word, so any learned "correction" of it is dropped too."""
    lw = word.lower()
    autocorrect.forget(lw)
    if lw in _personal:
        return
    _personal.add(lw)
    if _by_len is not None:
        _by_len.setdefault(len(lw), []).append(lw)
    _save_personal()


def find_next_misspelling(text: str, start: int, skip_words: set[str]) -> tuple[int, int, str] | None:
    """First unknown word in `text` at/after `start`, or None. Words in
    `skip_words` (lowercased, "skip for this pass" from the modal) are
    passed over without a dictionary lookup."""
    for m in _WORD_RE.finditer(text, start):
        word = m.group(0)
        if len(word) < 2 or word.lower() in skip_words or is_known(word):
            continue
        return m.start(), m.end(), word
    return None


def field_label(field_id: str) -> str:
    entry = _FIELD_LABELS.get(field_id)
    if entry is None:
        return field_id
    sec_id, _anchor_id, human_name = entry
    short = _SECTION_SHORT.get(sec_id, sec_id)
    return f"{short} › {human_name}"


def collect_fields(win) -> list[tuple[object, str]]:
    """(widget, human_label) for every free-text field currently in the
    live widget tree, in tree (roughly top-to-bottom) order."""
    fields = []
    for w in _iter_descendants(win):
        # AD-tab link mirrors (objective/sections/ad_form.py) are skipped:
        # the real field they mirror is already in this walk, and a stale
        # hidden mirror corrected here would overwrite that real field.
        if getattr(w, "is_link_mirror", False):
            continue
        if isinstance(w, (AutoTextView, TouchEntry)):
            fields.append((w, field_label(getattr(w, "field_id", ""))))
    return fields


def replace_span(widget, start: int, end: int, replacement: str) -> None:
    """Replace widget.text[start:end] with `replacement` in place — a
    precise buffer/entry edit, not a whole-field .text reassignment, so
    other flagged words in the same field and normal cursor/undo state are
    left alone. Fires the widget's own "changed" signal, so this rides the
    section's existing autosave path exactly like a real keystroke would."""
    if isinstance(widget, AutoTextView):
        buf = widget.textview.get_buffer()
        it_start = buf.get_iter_at_offset(start)
        it_end = buf.get_iter_at_offset(end)
        buf.delete(it_start, it_end)
        buf.insert(it_start, replacement)
    elif isinstance(widget, TouchEntry):
        widget.delete_text(start, end)
        widget.insert_text(replacement, start)
        widget.set_position(start + len(replacement))
    else:
        text = widget.text
        widget.text = text[:start] + replacement + text[end:]
