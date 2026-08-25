"""Objective-mode sidebar — GTK4 port of
pab_assessment.objective.objective_view.ObjectiveSidebar.

Shown INSTEAD of the assessment SectionNav while in Objective mode (see
app.py's _enter_objective_mode/_exit_objective_mode) — the TUI uses two
entirely separate sidebars that swap wholesale, not one long combined list,
so switching modes doesn't blow out the sidebar's vertical space with
every section from both modes at once.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject  # noqa: E402

from ..nav import SIDEBAR_WIDTH

# (section_id, label) — order and labels match ObjectiveSidebar.SECTION_LABELS
# exactly. section_id values are the TUI's own ids (01_general, 07_functional,
# 02_active, ...), not this app's per-file names, so app.py's dispatch stays
# a direct 1:1 mirror of assessment_view.py's ids.
SECTION_LABELS: list[tuple[str, str]] = [
    ("01_general", "01 General Obs"),
    ("07_functional", "02 Functional"),
    ("02_active", "03 Active Mvmt"),
    ("03_passive", "04 Passive/OP"),
    ("04_neurological", "05 Neurological"),
    ("05_sensory", "06 Sensory"),
    ("06_muscle", "07 Muscle Test"),
    ("08_special", "08 Special Tests"),
    ("09_crps", "09 CRPS"),
]

# Every Objective tab in the TUI's own list is now built.
BUILT_SECTIONS = {
    "01_general", "07_functional", "02_active", "03_passive",
    "04_neurological", "05_sensory", "06_muscle", "08_special", "09_crps",
}


class ObjectiveNav(Gtk.Box):
    __gsignals__ = {
        "section-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "back": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_size_request(SIDEBAR_WIDTH, -1)
        self.set_hexpand(False)
        self.add_css_class("section-nav")
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.set_margin_start(4)
        self.set_margin_end(4)

        self._buttons: dict[str, Gtk.Button] = {}
        self.active_section = "01_general"

        for section_id, label in SECTION_LABELS:
            btn = Gtk.Button(label=label)
            btn.add_css_class("nav-button")
            if section_id not in BUILT_SECTIONS:
                btn.set_sensitive(False)
                btn.set_tooltip_text("Not yet built")
            else:
                btn.connect("clicked", self._on_clicked, section_id)
            self._buttons[section_id] = btn
            self.append(btn)

        back_btn = Gtk.Button(label="← Subjective")
        back_btn.add_css_class("nav-button")
        back_btn.add_css_class("nav-back")
        back_btn.set_margin_top(8)
        back_btn.connect("clicked", lambda _b: self.emit("back"))
        self.append(back_btn)

        self.set_active("01_general")

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
