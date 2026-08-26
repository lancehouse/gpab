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
import re
from pathlib import Path

import enchant

from .search import _iter_descendants, _FIELD_LABELS, _SECTION_SHORT
from .widgets import AutoTextView, TouchEntry

_DICT_LANG = "en_AU"
_PERSONAL_PATH = Path(__file__).parent / "spellcheck_personal_dict.json"
_WORD_RE = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
_MAX_SUGGESTIONS = 8

_checker = enchant.Dict(_DICT_LANG)


def _load_personal() -> set[str]:
    try:
        return {w.lower() for w in json.loads(_PERSONAL_PATH.read_text())}
    except Exception:
        return set()


_personal: set[str] = _load_personal()


def is_known(word: str) -> bool:
    return word.lower() in _personal or _checker.check(word)


def suggest(word: str) -> list[str]:
    return _checker.suggest(word)[:_MAX_SUGGESTIONS]


def add_to_personal(word: str) -> None:
    """Whitelist `word` (case-insensitively) permanently, across sessions."""
    lw = word.lower()
    if lw in _personal:
        return
    _personal.add(lw)
    _PERSONAL_PATH.write_text(json.dumps(sorted(_personal), indent=2) + "\n")


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
