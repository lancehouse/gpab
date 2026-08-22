"""Sensory — Objective 05, GTK4 port of
pab_assessment.objective.sections.sensory.

Dermatomes live in 04 Neurological; this section covers reduced acuity
(hyposensitivity) and heightened sensitivity (central sensitisation)
findings. Field ids and collect()/load() keys are 1:1 with the TUI (JSON
key "sensory" in _objective.json).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import FlagButton, RadioGroup, TouchEntry, AutoTextView, make_subsection_header
from ...section_base import SectionBase

_SEV4 = [("Norm", "success"), ("Mild", "warning"), ("Mod", "error"), ("Sev", "error")]

# (display label, data id, has detail entry?)
_HYPO_ITEMS: list[tuple[str, str, bool]] = [
    ("Sharp/blunt (Neuropen)", "sn_sharp_blunt", True),
    ("Two-point discrimination", "sn_tpd", True),
    ("Light touch (hypoaesthesia)", "sn_lt", True),
    ("Body perception impaired", "sn_body", False),
]
_HYPER_ITEMS: list[tuple[str, str, bool]] = [
    ("Static allodynia (monofilament)", "sn_static_allodynia", True),
    ("Dynamic allodynia (brush)", "sn_dynamic_allodynia", True),
    ("2° hyperalgesia (algometer)", "sn_secondary_hyper", True),
    ("Pin prick hyperalgesia", "sn_pin_prick", True),
    ("Cold hyperalgesia (ice 5 s)", "sn_cold", True),
    ("Heat hyperalgesia", "sn_heat", True),
    ("Temporal summation", "sn_temporal_sum", True),
    ("Conditioned pain modulation", "sn_cpm", True),
    ("Nerve trunk palpation", "sn_nerve_palpation", True),
]


class SensorySection(Gtk.Box, SectionBase):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None

        self._flags: dict[str, FlagButton] = {}
        self._details: dict[str, TouchEntry] = {}

        title = Gtk.Label(label="05 Sensory")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        self.append(make_subsection_header("Reduced Sensory Acuity (hyposensitivity)"))
        for label, sid, has_detail in _HYPO_ITEMS:
            self.append(self._flag_row(label, sid, has_detail))
        self.append(Gtk.Label(label="Body perception detail:", halign=Gtk.Align.START))
        self.body_detail = AutoTextView("sn_body_detail", min_lines=2)
        self.body_detail.textview.get_buffer().connect("changed", self._field_changed)
        self.append(self.body_detail)

        self.append(make_subsection_header("Heightened Sensitivity / Central Sensitisation"))
        ppt_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ppt_row.add_css_class("grid-row")
        ppt_lbl = Gtk.Label(label="PPT (algometer)")
        ppt_lbl.set_halign(Gtk.Align.START)
        ppt_lbl.set_size_request(180, -1)
        ppt_row.append(ppt_lbl)
        self.ppt = RadioGroup(_SEV4, "sn_ppt")
        self.ppt.connect("changed", self._field_changed)
        ppt_row.append(self.ppt)
        ppt_detail = TouchEntry("sn_ppt_detail", placeholder="kPa / region / notes")
        ppt_detail.set_hexpand(True)
        ppt_detail.connect("changed", self._field_changed)
        self._details["sn_ppt_detail"] = ppt_detail
        ppt_row.append(ppt_detail)
        self.append(ppt_row)

        for label, sid, has_detail in _HYPER_ITEMS:
            self.append(self._flag_row(label, sid, has_detail, detail_placeholder="region / value"))

        self.append(Gtk.Label(label="Notes:", halign=Gtk.Align.START))
        self.notes = AutoTextView("sn_notes", min_lines=2)
        self.notes.textview.get_buffer().connect("changed", self._field_changed)
        self.append(self.notes)

    def _flag_row(self, label: str, sid: str, has_detail: bool, detail_placeholder: str = "region / detail") -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("grid-row")
        btn = FlagButton(label, sid, compact=False)
        btn.connect("changed", self._field_changed)
        self._flags[sid] = btn
        row.append(btn)
        if has_detail:
            did = f"{sid}_detail"
            entry = TouchEntry(did, placeholder=detail_placeholder)
            entry.set_hexpand(True)
            entry.connect("changed", self._field_changed)
            self._details[did] = entry
            row.append(entry)
        return row

    def _field_changed(self, *_args) -> None:
        if self._loading:
            return
        if self._on_changed:
            self._on_changed()

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    def focus_first_field(self) -> None:
        self._flags[_HYPO_ITEMS[0][1]].grab_focus()

    def collect(self) -> dict:
        data: dict = {"sn_ppt": self.ppt.value}
        for sid, btn in self._flags.items():
            data[sid] = btn.value
        for did, entry in self._details.items():
            data[did] = entry.text.strip()
        data["sn_body_detail"] = self.body_detail.text
        data["sn_notes"] = self.notes.text
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            self.ppt.set_value(data.get("sn_ppt"))
            for sid, btn in self._flags.items():
                btn.set_value(data.get(sid))
            for did, entry in self._details.items():
                entry.text = data.get(did, "")
            self.body_detail.text = data.get("sn_body_detail", "")
            self.notes.text = data.get("sn_notes", "")
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        return self.ppt.value is not None
