"""Top subsection nav bar — GTK4 port of assessment_view.py's
#subsection_nav_bar, generalised 2026-08-26 to cover every section, not
just Subjective.

This is the app's ONE persistent top bar — there is deliberately no separate
app-title bar above it (that duplicated the OS window title for no benefit
and cost a full extra row of vertical space; removed per feedback). It's
shown permanently across every sidebar tab, and its CONTENT now changes to
match whichever tab is currently active: app.py calls set_headings() on
every _show_section(), sourcing the (label, anchor_id) pairs from the exact
same SUBJ_GRID_DATA/OBJ_GRID_DATA tables that already drive the Ctrl+T grid
overview (grid_overview.py) — so this bar and Ctrl+T can never show a
different subsection breakdown for the same tab, by construction, not by
two people remembering to keep two lists in sync.

Originally this only ever showed Subjective's own 11 items, permanently,
regardless of the active tab — clicking one switched to Subjective and
focused a field there (SubjectiveSection.jump_to()). That was a real bug,
not a design choice: it looked especially wrong on Consent/Medical/etc,
where the bar showed Subjective's chips while a totally different section
was on screen (Alt+letter jump shortcuts and SubjectiveSection.jump_to()
are UNTOUCHED by this change — app.py's _ALT_KEY_MAP still works exactly as
before; only this bar's own visible content and click behaviour changed).
Clicking a chip now always jumps to an anchor WITHIN the currently active
section (app.py's _jump_within_current_section, the same scroll-to-anchor
mechanism Ctrl+T/Ctrl+F already use), not a hardcoded Subjective jump_to()
call — so behaviour is uniform across every tab, this one included.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject  # noqa: E402


class SubsectionNavBar(Gtk.Box):
    """Chip row reflecting the active section's own subsections — content
    rebuilt on every set_headings() call (app.py's _show_section), not
    fixed at construction time."""

    __gsignals__ = {
        "jump": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.add_css_class("subsection-nav-bar")
        self._headings: list[tuple[str, str]] = []

    def set_headings(self, headings: list[tuple[str, str]]) -> None:
        """headings: (label, anchor_id) pairs, same shape as one
        SUBJ_GRID_DATA/OBJ_GRID_DATA row's third element. No-ops if it's
        the exact same list already shown (set_active on the sidebar can
        call this more than once per real tab change) — rebuilding the
        button row on every call would needlessly steal focus/flash."""
        if headings == self._headings:
            return
        self._headings = headings
        child = self.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.remove(child)
            child = nxt
        for label, anchor_id in headings:
            btn = Gtk.Button(label=label)
            btn.add_css_class("subsection-nav-btn")
            btn.connect("clicked", self._on_clicked, anchor_id)
            self.append(btn)

    def _on_clicked(self, _btn, anchor_id: str) -> None:
        self.emit("jump", anchor_id)
