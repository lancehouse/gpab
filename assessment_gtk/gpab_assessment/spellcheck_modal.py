"""Ctrl+S spell-check modal — streamlined vs. Word/LibreOffice's own dialogs:
one popup, one word at a time, numbered suggestions you pick with a single
keystroke, no "Change/Change All/AutoCorrect/Options..." button maze.

Walks every free-text field currently in the widget tree (spellcheck.py's
collect_fields()) in order, stopping at each word the dictionary doesn't
recognise. A replacement is applied as a precise in-place edit of the
field's own buffer/entry (spellcheck.replace_span), so it rides the
section's existing autosave path exactly like a real keystroke — no
report-side or storage-side changes needed anywhere.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

from . import spellcheck

_CONTEXT_RADIUS = 40  # chars of context shown either side of the flagged word


class SpellcheckModal(Gtk.Window):
    """Escape ends the pass. 1-9 replace with that numbered suggestion.
    S skips this occurrence. Shift+S skips this word for the rest of the
    pass. D whitelists the word permanently (spellcheck_personal_dict.json)."""

    def __init__(self, parent: Gtk.Window, win) -> None:
        super().__init__(transient_for=parent, modal=True, title="Spell Check")
        self.set_default_size(520, 320)

        self._fields = spellcheck.collect_fields(win)
        self._field_idx = 0
        self._scan_pos = 0
        self._skip_words: set[str] = set()
        self._current: tuple | None = None  # (widget, start, end, word, label)
        self._suggestions: list[str] = []

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(16)
        box.set_margin_end(16)

        self.field_label = Gtk.Label(xalign=0.0)
        self.field_label.add_css_class("dim-label")
        box.append(self.field_label)

        self.context_label = Gtk.Label(xalign=0.0)
        self.context_label.set_wrap(True)
        self.context_label.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        box.append(self.context_label)

        self.suggestions_box = Gtk.ListBox()
        self.suggestions_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.suggestions_box.connect("row-activated", self._on_row_activated)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(self.suggestions_box)
        box.append(scroll)

        hint = Gtk.Label(xalign=0.0)
        hint.set_markup(
            '<span size="small" alpha="70%">'
            "1–9 replace · S skip · Shift+S skip word · D add to dictionary · Esc stop"
            "</span>"
        )
        box.append(hint)

        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda _b: self.close())
        close_btn.set_halign(Gtk.Align.END)
        box.append(close_btn)

        self.set_child(box)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        self._advance()

    # ------------------------------------------------------------------
    # Pass driver
    # ------------------------------------------------------------------

    def _advance(self) -> None:
        while self._field_idx < len(self._fields):
            widget, label = self._fields[self._field_idx]
            text = widget.text
            hit = spellcheck.find_next_misspelling(text, self._scan_pos, self._skip_words)
            if hit is None:
                self._field_idx += 1
                self._scan_pos = 0
                continue
            start, end, word = hit
            self._current = (widget, start, end, word, label)
            self._show_word(text, start, end, word, label)
            return
        self._show_done()

    def _show_word(self, text: str, start: int, end: int, word: str, label: str) -> None:
        self.field_label.set_label(label)

        lo = max(0, start - _CONTEXT_RADIUS)
        hi = min(len(text), end + _CONTEXT_RADIUS)
        before = GLib.markup_escape_text(text[lo:start])
        flagged = GLib.markup_escape_text(word)
        after = GLib.markup_escape_text(text[end:hi])
        ellipsis_l = "…" if lo > 0 else ""
        ellipsis_r = "…" if hi < len(text) else ""
        self.context_label.set_markup(
            f'{ellipsis_l}{before}<span underline="error" underline_color="#e53935">'
            f"{flagged}</span>{after}{ellipsis_r}"
        )

        self._suggestions = spellcheck.suggest(word)
        row = self.suggestions_box.get_row_at_index(0)
        while row is not None:
            self.suggestions_box.remove(row)
            row = self.suggestions_box.get_row_at_index(0)
        if not self._suggestions:
            lbl = Gtk.Label(label="(no suggestions)", xalign=0.0)
            lbl.add_css_class("dim-label")
            lbl.set_margin_top(4)
            lbl.set_margin_bottom(4)
            lbl.set_margin_start(6)
            self.suggestions_box.append(lbl)
        for i, sug in enumerate(self._suggestions, start=1):
            lbl = Gtk.Label(label=f"{i}  {sug}", xalign=0.0)
            lbl.set_margin_top(4)
            lbl.set_margin_bottom(4)
            lbl.set_margin_start(6)
            self.suggestions_box.append(lbl)

    def _show_done(self) -> None:
        self.field_label.set_label("")
        self.context_label.set_markup("<b>Spell check complete.</b> No more flagged words.")
        row = self.suggestions_box.get_row_at_index(0)
        while row is not None:
            self.suggestions_box.remove(row)
            row = self.suggestions_box.get_row_at_index(0)
        self._current = None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _apply(self, replacement: str) -> None:
        widget, start, end, _word, _label = self._current
        spellcheck.replace_span(widget, start, end, replacement)
        self._scan_pos = start + len(replacement)
        self._advance()

    def _skip(self) -> None:
        _widget, _start, end, _word, _label = self._current
        self._scan_pos = end
        self._advance()

    def _skip_word(self) -> None:
        _widget, _start, end, word, _label = self._current
        self._skip_words.add(word.lower())
        self._scan_pos = end
        self._advance()

    def _add_to_dictionary(self) -> None:
        _widget, _start, end, word, _label = self._current
        spellcheck.add_to_personal(word)
        self._scan_pos = end
        self._advance()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _on_row_activated(self, _box, row: Gtk.ListBoxRow) -> None:
        if self._current is None:
            return
        idx = row.get_index()
        if 0 <= idx < len(self._suggestions):
            self._apply(self._suggestions[idx])

    def _on_key(self, _ctrl, keyval, _keycode, state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name == "Escape":
            self.close()
            return True
        if self._current is None:
            return False
        shift_held = bool(state & Gdk.ModifierType.SHIFT_MASK)
        if name.isdigit() and name != "0":
            idx = int(name) - 1
            if 0 <= idx < len(self._suggestions):
                self._apply(self._suggestions[idx])
            return True
        if name.lower() == "s":
            self._skip_word() if shift_held else self._skip()
            return True
        if name.lower() == "d":
            self._add_to_dictionary()
            return True
        return False
