"""F10 bottom notes overlay — GTK4 port of assessment_view.py's NotesOverlay.

Freeform clinical notes, differentials, reminders — not tied to any one
section. Saved under the legacy "scratchpad" JSON key (backward-compat name
from the TUI's own history), alongside the numbered sections' data, not as
one of them.

Note: sections/scratchpad.py (a full standalone "Scratchpad" tab) exists in
the TUI source but is dead code — not registered in assessment_view.py's
`sections` dict or anywhere else, fully superseded by this overlay. Nothing
was ported from it for that reason. Likewise sections/objective.py and
sections/placeholder.py are unreferenced stubs (confirmed via grep — zero
imports anywhere in the TUI) predating sections that are now fully built;
neither has anything left to port either.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .widgets import AutoTextView


class NotesOverlay(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("notes-overlay")
        self.set_visible(False)

        # expand=False: a fixed-size panel docked at the bottom of the
        # window — unlike every in-form notes field, this one must not grow
        # and push the rest of the layout around as the user types.
        self.textview = AutoTextView("notes_overlay", min_lines=6, expand=False)
        self.append(self.textview)

    @property
    def text(self) -> str:
        return self.textview.text

    def load_text(self, notes: str) -> None:
        self.textview.text = notes or ""

    def connect_changed(self, callback) -> None:
        self.textview.textview.get_buffer().connect("changed", callback)

    def grab_focus(self) -> bool:
        return self.textview.grab_focus()
