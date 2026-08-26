"""Region toggle chip bar — GTK4 port of
pab_assessment.objective.objective_view.RegionTopbar.

Shown in place of the Subjective mnemonic bar whenever any objective tab
is active (Neurological or a Phase 2 region tab — see app.py's
_show_section). Toggling a chip mounts/unmounts that region across every
Phase 2 region tab (Active Movement, Passive/OP, Muscle Testing, Special
Tests); Neurological and any other generic (non-region) tab are
unaffected, same as the TUI's RegionTopbar.RegionToggled handling.

Only regions with their own YAML file under assessment/pab_assessment/
objective/sections/yaml/ are offered. The TUI's own _ALL_REGIONS list also
includes "thoracic" and "elbow", but neither has its own YAML (Thoracic
ROM is a second group inside lumbar.yaml, not a separate region) — a chip
for either would toggle on and render nothing, so they're omitted here.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject  # noqa: E402

ALL_REGIONS: list[tuple[str, str]] = [
    ("cervical", "Cervical"),
    ("shoulder", "Shoulder"),
    ("lumbar", "Lumbar"),
    ("hip", "Hip"),
    ("knee", "Knee"),
    ("ankle", "Ankle"),
]


class RegionTopbar(Gtk.Box):
    __gsignals__ = {
        "region-toggled": (GObject.SignalFlags.RUN_FIRST, None, (str, bool)),
    }

    def __init__(self, active_regions: list[str]) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.add_css_class("subsection-nav-bar")

        label = Gtk.Label(label="Regions:")
        label.add_css_class("footer-desc")
        self.append(label)

        self._buttons: dict[str, Gtk.ToggleButton] = {}
        for region_id, disp in ALL_REGIONS:
            btn = Gtk.ToggleButton(label=disp)
            btn.add_css_class("subsection-nav-btn")
            btn.set_active(region_id in active_regions)
            btn.connect("toggled", self._on_toggled, region_id)
            self._buttons[region_id] = btn
            self.append(btn)

    def _on_toggled(self, btn: Gtk.ToggleButton, region_id: str) -> None:
        self.emit("region-toggled", region_id, btn.get_active())

    def set_active_regions(self, regions: list[str]) -> None:
        for region_id, btn in self._buttons.items():
            active = region_id in regions
            if btn.get_active() != active:
                btn.handler_block_by_func(self._on_toggled)
                btn.set_active(active)
                btn.handler_unblock_by_func(self._on_toggled)
