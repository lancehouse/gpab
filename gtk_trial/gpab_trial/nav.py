"""Left sidebar section nav — GTK4 port of assessment_view.py's SectionNav.

Mirrors the TUI's structure: full-width stacked buttons in a fixed-width
left sidebar, active section highlighted. Sections not yet built in this
trial (03-09) are shown as disabled placeholders so the sidebar reads the
same as the real TUI's — see plan's "explicitly out of scope" list.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject  # noqa: E402

SIDEBAR_WIDTH = 190  # px — TUI uses `width: 20` (character cells); this is the touch-scaled equivalent

# Matches assessment_view.py's SectionNav.SECTION_LABELS order exactly.
SECTION_LABELS = [
    ("01_consent", "01 Consent"),
    ("02_subjective", "02 Subjective"),
    ("03_medical", "03 Medical"),
    ("04_objective", "04 Objective — Neuro"),
    ("04_pain_classification", "05 Pain Class"),
    ("05_outcome_measures", "06 Outcomes"),
    ("06_diagnosis", "07 Diagnosis"),
    ("07_barriers", "08 Barriers"),
    ("08_rx_plan", "09 Rx & Plan"),
]

# Sections this trial actually implements — everything else renders disabled.
# "04_objective" only ever opens Neurological here — the TUI's Objective mode
# has its own 8-section sidebar (General/Active/Passive/.../Special); this
# trial builds just the one tab, so the label above says so rather than
# implying the rest of Objective mode is reachable.
BUILT_SECTIONS = {"01_consent", "02_subjective", "04_objective"}


class SectionNav(Gtk.Box):
    __gsignals__ = {
        "section-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_size_request(SIDEBAR_WIDTH, -1)
        # Explicit False: without this, a hexpand=True descendant (there was
        # one on the nav buttons below) propagates its expand request up
        # through the widget tree, and the root box then gives this sidebar
        # ~half the window instead of respecting SIDEBAR_WIDTH.
        self.set_hexpand(False)
        self.add_css_class("section-nav")
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.set_margin_start(4)
        self.set_margin_end(4)

        self._buttons: dict[str, Gtk.Button] = {}
        self.active_section = "01_consent"

        for section_id, label in SECTION_LABELS:
            btn = Gtk.Button(label=label)
            btn.add_css_class("nav-button")
            # No hexpand: a vertical box already gives each child its full
            # width via the default FILL halign — hexpand here would only
            # propagate upward and blow out the sidebar's own width (see
            # SectionNav.__init__).
            if section_id not in BUILT_SECTIONS:
                btn.set_sensitive(False)
                btn.set_tooltip_text("Not built in this trial — see gtk_trial/CLAUDE.md")
            else:
                btn.connect("clicked", self._on_clicked, section_id)
            self._buttons[section_id] = btn
            self.append(btn)

        self.set_active("01_consent")

    def _on_clicked(self, _btn, section_id: str) -> None:
        self.set_active(section_id)
        self.emit("section-selected", section_id)

    def set_active(self, section_id: str) -> None:
        for sid, btn in self._buttons.items():
            if sid == section_id:
                btn.add_css_class("nav-active")
            else:
                btn.remove_css_class("nav-active")
        self.active_section = section_id
