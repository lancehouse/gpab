"""General Observation — Objective 01, GTK4 port of
pab_assessment.objective.sections.general.

Field ids and collect()/load() keys are 1:1 with the TUI (JSON key
"general" in _objective.json).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import RadioGroup, MultiSelectGroup, TouchEntry, AutoTextView, make_subsection_header
from ...section_base import SectionBase

_SEV4 = [("Norm", "success"), ("Mild", "warning"), ("Mod", "error"), ("Sev", "error")]
_LORD3 = [("Norm", "success"), ("↑Inc", "warning"), ("↓Dec", "warning")]
_KYPH3 = [("Norm", "success"), ("↑Inc", "warning"), ("↓Dec", "warning")]
_LEAN4 = [("None", "success"), ("Left", "warning"), ("Right", "warning"), ("Fwd", "default")]
_BRTH4 = [("Norm", "success"), ("Apical", "warning"), ("Abdo", "warning"), ("Paradx", "error")]
_SCAP5 = [("Norm", "success"), ("Prot", "warning"), ("Retr", "warning"),
          ("Elev", "warning"), ("Depr", "warning")]

# (row label, data-key, gang options)
_POSTURE_ROWS: list[tuple[str, str, list]] = [
    ("Lumbar lordosis", "go_lx_lord", _LORD3),
    ("Thoracic kyphosis", "go_tx_kyph", _KYPH3),
    ("Antalgic lean", "go_lean", _LEAN4),
    ("Sway posture", "go_sway", _SEV4),
    ("Breathing", "go_breath", _BRTH4),
    ("Scapular L", "go_scap_l", _SCAP5),
    ("Scapular R", "go_scap_r", _SCAP5),
    ("Muscle wasting", "go_wasting", _SEV4),
]


class GeneralSection(Gtk.Box, SectionBase):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None

        self._groups: dict[str, Gtk.Widget] = {}  # RadioGroup or MultiSelectGroup, keyed by field id
        self._cmt_entries: dict[str, TouchEntry] = {}

        title = Gtk.Label(label="01 General Observation")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        self.append(make_subsection_header("Physical", "go_physical"))
        self.general_notes = AutoTextView("go_general_notes", min_lines=2)
        self.general_notes.textview.get_buffer().connect("changed", self._field_changed)
        self.append(self.general_notes)

        mob_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mob_lbl = Gtk.Label(label="General mobility:")
        mob_lbl.set_halign(Gtk.Align.START)
        mob_lbl.set_size_request(160, -1)
        mob_row.append(mob_lbl)
        self.transfer_cmt = AutoTextView("go_transfer_cmt", min_lines=2)
        self.transfer_cmt.textview.get_buffer().connect("changed", self._field_changed)
        mob_row.append(self.transfer_cmt)
        self.append(mob_row)

        self.append(make_subsection_header("Posture", "go_posture"))
        for label, key, opts in _POSTURE_ROWS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(150, -1)
            row.append(lbl)
            if key == "go_lean":
                grp = MultiSelectGroup(opts, key)
            else:
                grp = RadioGroup(opts, key)
            grp.connect("changed", self._field_changed)
            self._groups[key] = grp
            row.append(grp)
            cmt_id = f"{key}_cmt"
            entry = TouchEntry(cmt_id, placeholder="…")
            entry.set_hexpand(True)
            entry.connect("changed", self._field_changed)
            self._cmt_entries[cmt_id] = entry
            row.append(entry)
            self.append(row)

        self.append(Gtk.Label(label="Posture notes:", halign=Gtk.Align.START))
        self.posture_notes = AutoTextView("go_posture_notes", min_lines=2)
        self.posture_notes.textview.get_buffer().connect("changed", self._field_changed)
        self.append(self.posture_notes)

    def _field_changed(self, *_args) -> None:
        if self._loading:
            return
        if self._on_changed:
            self._on_changed()

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    def focus_first_field(self) -> None:
        self.general_notes.grab_focus()

    def collect(self) -> dict:
        data: dict = {}
        for key, grp in self._groups.items():
            data[key] = grp.value
        for cid, entry in self._cmt_entries.items():
            data[cid] = entry.text.strip()
        data["go_general_notes"] = self.general_notes.text
        data["go_transfer_cmt"] = self.transfer_cmt.text
        data["go_posture_notes"] = self.posture_notes.text
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            for key, grp in self._groups.items():
                grp.set_value(data.get(key))
            for cid, entry in self._cmt_entries.items():
                entry.text = data.get(cid, "")
            self.general_notes.text = data.get("go_general_notes", "")
            self.transfer_cmt.text = data.get("go_transfer_cmt", "")
            self.posture_notes.text = data.get("go_posture_notes", "")
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        return bool(self.general_notes.text.strip())
