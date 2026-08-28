"""Ctrl+S spell-check modal — streamlined vs. Word/LibreOffice's own dialogs:
one popup, one word at a time, numbered suggestions you pick with a single
keystroke, no "Change/Change All/AutoCorrect/Options..." button maze.

Walks every free-text field currently in the widget tree (spellcheck.py's
collect_fields()) in order, stopping at each word the dictionary doesn't
recognise. A replacement is applied as a precise in-place edit of the
field's own buffer/entry (spellcheck.replace_span), so it rides the
section's existing autosave path exactly like a real keystroke — no
report-side or storage-side changes needed anywhere.

The context preview (context_view) is itself an editable Gtk.TextView, not
a read-only Label with a separate correction box — real notes sometimes
have two words jumbled together (a missing/misplaced space) that a
single-word dictionary suggestion can't fix at all, so the fastest real
fix is often just hand-editing the snippet directly and moving on. The
flagged word is marked bold + red-underlined via a Gtk.TextTag anchored
with Gtk.TextMarks (not fixed character offsets), so the highlight and
the suggestion-apply actions both stay correct even after the user has
already typed elsewhere in the box. Return commits whatever's currently in
the box (which may be untouched, hand-edited, or suggestion-substituted)
back into the field in place of the whole context window and advances —
see _commit_and_advance.

Digit/S/D shortcuts are only reached while context_view does NOT have
keyboard focus — GTK stops a key event's propagation the moment the
focused TextView consumes it (typing 's' inserts the letter, not the skip
action), the same "focused text-input eats the keystroke first" behaviour
search_widget.py's docstring already documents having to design around —
so default focus is deliberately kept off context_view (see _show_word)
and the user "opts in" to hand-editing by clicking/tapping into it.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango  # noqa: E402

from . import spellcheck

_CONTEXT_RADIUS = 150  # chars of context shown either side of the flagged word


class SpellcheckModal(Gtk.Window):
    """Escape ends the pass. 1-9 replace with that numbered suggestion.
    S skips this occurrence. Shift+S skips this word for the rest of the
    pass. D whitelists the word permanently (spellcheck_personal_dict.json).
    Editing the context text directly and pressing Enter there commits
    whatever's in the box instead."""

    def __init__(self, parent: Gtk.Window, win) -> None:
        super().__init__(transient_for=parent, modal=True, title="Spell Check")
        self.set_default_size(560, 520)

        self._fields = spellcheck.collect_fields(win)
        self._field_idx = 0
        self._scan_pos = 0
        self._skip_words: set[str] = set()
        self._current: dict | None = None
        self._suggestions: list[str] = []
        self._word_start_mark: Gtk.TextMark | None = None
        self._word_end_mark: Gtk.TextMark | None = None

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(16)
        box.set_margin_end(16)

        self.field_label = Gtk.Label(xalign=0.0)
        self.field_label.add_css_class("dim-label")
        box.append(self.field_label)

        self.context_view = Gtk.TextView()
        self.context_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.context_view.set_accepts_tab(False)
        self.context_view.add_css_class("spellcheck-context-view")
        self._flag_tag = self.context_view.get_buffer().create_tag(
            "flagged", weight=Pango.Weight.BOLD, underline=Pango.Underline.ERROR
        )
        rgba = Gdk.RGBA()
        rgba.parse("#e53935")
        self._flag_tag.set_property("underline-rgba", rgba)
        context_key_ctrl = Gtk.EventControllerKey()
        context_key_ctrl.connect("key-pressed", self._on_context_key)
        self.context_view.add_controller(context_key_ctrl)
        self.context_scroll = Gtk.ScrolledWindow()
        self.context_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.context_scroll.set_min_content_height(160)
        self.context_scroll.set_child(self.context_view)
        box.append(self.context_scroll)

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
            "edit the text above directly, then Enter · Esc stop"
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
            self._show_word(widget, text, start, end, word, label)
            return
        self._show_done()

    def _show_word(self, widget, text: str, start: int, end: int, word: str, label: str) -> None:
        self.field_label.set_label(label)

        lo = max(0, start - _CONTEXT_RADIUS)
        hi = min(len(text), end + _CONTEXT_RADIUS)
        self._current = {
            "widget": widget, "lo": lo, "hi": hi,
            "word_end": end, "word": word, "label": label,
        }

        buf = self.context_view.get_buffer()
        buf.set_text(text[lo:hi])
        it_s = buf.get_iter_at_offset(start - lo)
        it_e = buf.get_iter_at_offset(end - lo)
        if self._word_start_mark is not None:
            buf.delete_mark(self._word_start_mark)
            buf.delete_mark(self._word_end_mark)
        self._word_start_mark = buf.create_mark(None, it_s, left_gravity=True)
        self._word_end_mark = buf.create_mark(None, it_e, left_gravity=False)
        buf.apply_tag(self._flag_tag, it_s, it_e)
        # scroll_to_iter needs a laid-out view to compute a position against
        # — right after set_text() the TextView hasn't relaid-out yet (same
        # "measure after GTK gets a chance to relayout" issue AutoTextView's
        # own height recompute works around), so defer one idle tick. Center
        # (yalign=0.5) rather than just "on screen" — a flagged word near
        # either edge of the ±150-char window was otherwise landing right at
        # the top/bottom edge of the scroll view, forcing a manual scroll to
        # actually read it.
        mark = self._word_start_mark
        GLib.idle_add(lambda: self._center_on_mark(mark))

    def _center_on_mark(self, mark: Gtk.TextMark) -> bool:
        buf = self.context_view.get_buffer()
        self.context_view.scroll_to_iter(buf.get_iter_at_mark(mark), 0.0, True, 0.5, 0.5)
        return GLib.SOURCE_REMOVE

        self._suggestions = spellcheck.suggest(word)
        row = self.suggestions_box.get_row_at_index(0)
        while row is not None:
            self.suggestions_box.remove(row)
            row = self.suggestions_box.get_row_at_index(0)
        if not self._suggestions:
            lbl = Gtk.Label(label="(no suggestions — edit the text above directly)", xalign=0.0)
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

        # Default focus must NOT land on context_view — GTK auto-focuses the
        # first focusable widget on present()/on any child rebuild, which
        # would otherwise steal every digit/S/D keystroke as typed text (a
        # focused TextView consumes a key event outright, so it never
        # reaches _on_key; see module docstring). suggestions_box is a
        # neutral parking spot: it doesn't consume plain letter/digit keys
        # itself, so the shortcuts stay live by default and the user only
        # "opts in" to hand-editing by clicking or tapping into the context
        # box.
        self.suggestions_box.grab_focus()

    def _show_done(self) -> None:
        self.field_label.set_label("")
        buf = self.context_view.get_buffer()
        buf.set_text("Spell check complete. No more flagged words.")
        self._word_start_mark = None
        self._word_end_mark = None
        row = self.suggestions_box.get_row_at_index(0)
        while row is not None:
            self.suggestions_box.remove(row)
            row = self.suggestions_box.get_row_at_index(0)
        self._current = None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _commit_and_advance(self) -> None:
        """Splice the (possibly hand-edited) context box back into the field
        at [lo, hi) and resume scanning from `lo`, not from the end of the
        edited text — a free-form edit can touch anything in that window,
        including text after the originally-flagged word, so re-scanning the
        whole window is what actually catches a second problem in it rather
        than silently skipping past it. The just-fixed word itself is simply
        no longer unknown, so find_next_misspelling passes over it on its
        own; if it wasn't actually fixed, it's shown again — correct, since
        unfixed means unfixed, not an infinite loop (nothing here recurses
        without new user input each time)."""
        cur = self._current
        buf = self.context_view.get_buffer()
        s, e = buf.get_bounds()
        edited = buf.get_text(s, e, False)
        spellcheck.replace_span(cur["widget"], cur["lo"], cur["hi"], edited)
        self._scan_pos = cur["lo"]
        self._advance()

    def _apply_suggestion(self, replacement: str) -> None:
        buf = self.context_view.get_buffer()
        it_s = buf.get_iter_at_mark(self._word_start_mark)
        it_e = buf.get_iter_at_mark(self._word_end_mark)
        buf.delete(it_s, it_e)
        buf.insert(it_s, replacement)
        self._commit_and_advance()

    def _skip(self) -> None:
        self._scan_pos = self._current["word_end"]
        self._advance()

    def _skip_word(self) -> None:
        self._skip_words.add(self._current["word"].lower())
        self._scan_pos = self._current["word_end"]
        self._advance()

    def _add_to_dictionary(self) -> None:
        spellcheck.add_to_personal(self._current["word"])
        self._scan_pos = self._current["word_end"]
        self._advance()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _on_context_key(self, _ctrl, keyval, _keycode, _state) -> bool:
        if self._current is None:
            return False
        name = Gdk.keyval_name(keyval) or ""
        if name in ("Return", "KP_Enter"):
            self._commit_and_advance()
            return True
        return False

    def _on_row_activated(self, _box, row: Gtk.ListBoxRow) -> None:
        if self._current is None:
            return
        idx = row.get_index()
        if 0 <= idx < len(self._suggestions):
            self._apply_suggestion(self._suggestions[idx])

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
                self._apply_suggestion(self._suggestions[idx])
            return True
        if name.lower() == "s":
            self._skip_word() if shift_held else self._skip()
            return True
        if name.lower() == "d":
            self._add_to_dictionary()
            return True
        return False
