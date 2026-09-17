"""F10 notes panel — GTK4 port of assessment_view.py's NotesOverlay.

Freeform clinical notes, differentials, reminders — not tied to any one
section. Saved under the legacy "scratchpad" JSON key (backward-compat name
from the TUI's own history), alongside the numbered sections' data, not as
one of them.

Originally a fixed-size overlay docked at the bottom of the window (the
TUI's own layout). Moved 2026-09-17, per direct feedback, into the same
resizable right-hand slot the Ctrl+K KB panel uses (see app.py's
side_panel_stack/_show_side_panel) — the user is content with KB and notes
never being open together, so one shared slot that replaces its content on
toggle was simpler than two independent panels.

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
        self.add_css_class("notes-panel")
        self.set_hexpand(True)

        # expand=False + vexpand=True: not a growing form field (no
        # min/max-lines content-height tracking needed — this panel's own
        # height is whatever the side-panel slot gives it, exactly like the
        # KB panel), but it should still fill that slot fully rather than
        # sitting at its small min_lines height with dead space below.
        # Internal scrolling (policy NEVER/AUTOMATIC, set by AutoTextView)
        # takes over once notes content exceeds the panel's actual height.
        #
        # grid_nav=False, accepts_tab=True: per direct request 2026-09-17,
        # this panel should behave like a plain standalone text editor, not
        # a grid form field — see AutoTextView's docstring for why grid_nav
        # specifically also fixes a real bug (Down arrow getting stuck one
        # visual row above the true end of a word-wrapped last paragraph).
        self.textview = AutoTextView("notes_overlay", min_lines=6, expand=False,
                                      grid_nav=False, accepts_tab=True)
        self.textview.set_vexpand(True)
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
