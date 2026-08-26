"""Ctrl+S spell-check modal — streamlined vs. Word/LibreOffice's own dialogs:
one popup, one word at a time, numbered suggestions you pick with a single
keystroke, no "Change/Change All/AutoCorrect/Options..." button maze.

Walks every free-text field currently in the widget tree (spellcheck.py's
collect_fields()) in order, stopping at each word the dictionary doesn't
recognise. A replacement is applied as a precise in-place edit of the
field's own buffer/entry (spellcheck.replace_span), so it rides the
section's existing autosave path exactly like a real keystroke — no
report-side or storage-side changes needed anywhere.

Two escape hatches beyond the numbered list, both because dictionary
suggestions and typing on a touchscreen are both fallible: the top
suggestion is rendered much larger (.spellcheck-top-suggestion) so it can
be read at a glance while moving quickly through a pass, and an editable
correction entry (pre-filled with the word as actually typed, not a
suggestion — easier to spot-fix your own typo than to start from an
unrelated dictionary guess) lets you hand-type a fix when nothing offered
is right. Digit/S/D shortcuts are only ever reached while that entry does
NOT have keyboard focus — GTK stops a key event's propagation the moment
the focused Entry consumes it (typing 's' produces the letter, not the
skip action), the same "focused text-input eats the keystroke first"
behaviour search_widget.py's docstring already documents having to design
around — so no extra bookkeeping is needed to keep the two from colliding.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

from . import spellcheck

_CONTEXT_RADIUS = 150  # chars of context shown either side of the flagged word


class SpellcheckModal(Gtk.Window):
    """Escape ends the pass. 1-9 replace with that numbered suggestion.
    S skips this occurrence. Shift+S skips this word for the rest of the
    pass. D whitelists the word permanently (spellcheck_personal_dict.json).
    Typing your own fix into the correction entry and pressing Enter there
    applies it instead."""

    def __init__(self, parent: Gtk.Window, win) -> None:
        super().__init__(transient_for=parent, modal=True, title="Spell Check")
        self.set_default_size(560, 460)

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

        self.correction_entry = Gtk.Entry()
        self.correction_entry.add_css_class("spellcheck-correction-entry")
        self.correction_entry.set_hexpand(True)
        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("enter", lambda _c: self.correction_entry.select_region(0, -1))
        self.correction_entry.add_controller(focus_ctrl)
        self.correction_entry.connect("activate", self._on_correction_activate)
        box.append(self.correction_entry)

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
            "1–9 replace · S skip · Shift+S skip word · D add to dictionary · "
            "type your own fix above then Enter · Esc stop"
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

        self.correction_entry.set_text(word)

        self._suggestions = spellcheck.suggest(word)
        row = self.suggestions_box.get_row_at_index(0)
        while row is not None:
            self.suggestions_box.remove(row)
            row = self.suggestions_box.get_row_at_index(0)
        if not self._suggestions:
            lbl = Gtk.Label(label="(no suggestions — try the correction field above)", xalign=0.0)
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
            if i == 1:
                lbl.add_css_class("spellcheck-top-suggestion")
            self.suggestions_box.append(lbl)

        # Default focus must NOT land on correction_entry — GTK auto-focuses
        # the first focusable widget on present()/on any child rebuild, which
        # would otherwise steal every digit/S/D keystroke as typed text (a
        # focused Entry consumes a key event outright, so it never reaches
        # _on_key; see module docstring). suggestions_box is a neutral
        # parking spot: it doesn't consume plain letter/digit keys itself, so
        # the shortcuts stay live by default and the user only "opts in" to
        # typing by clicking or tapping into the correction field.
        self.suggestions_box.grab_focus()

    def _show_done(self) -> None:
        self.field_label.set_label("")
        self.context_label.set_markup("<b>Spell check complete.</b> No more flagged words.")
        self.correction_entry.set_text("")
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

    def _on_correction_activate(self, entry: Gtk.Entry) -> None:
        if self._current is None:
            return
        text = entry.get_text().strip()
        if text:
            self._apply(text)

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
