"""Knee Python table widgets — GTK4 port of
pab_assessment.objective.sections.knee_tables.

Same shape as Hip's: OP table + Accessory Glides table sharing one
combined notes field, plus a strength grid with its own notes.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import AutoTextView
from ..passive_widgets import BilateralNormTable, StrengthGridTable

_KN_OP_ROWS: list[tuple[str, str]] = [
    ("Flexion", "kn_op_flex"),
    ("Extension", "kn_op_ext"),
]

_KN_ACC_ROWS: list[tuple[str, str]] = [
    ("AP Glide", "kn_acc_ap"),
    ("Patella Med", "kn_acc_pmed"),
    ("Patella Lat", "kn_acc_plat"),
]

_KN_STR_ROWS: list[tuple[str, str]] = [
    ("Extension (quads)", "kn_str_ext"),
    ("Flexion (hamstring)", "kn_str_flex"),
    ("Calf (heel raise)", "kn_str_calf"),
]


class KneePassiveTables(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.op = BilateralNormTable("Overpressure", _KN_OP_ROWS, notes_id=None,
                                      txt_placeholder="findings / //")
        self.append(self.op)
        self.acc = BilateralNormTable("Accessory Glides", _KN_ACC_ROWS, notes_id=None,
                                       txt_placeholder="grade / findings")
        self.append(self.acc)

        self.append(Gtk.Label(label="OP notes:", halign=Gtk.Align.START))
        self.notes = AutoTextView("kn_op_notes", min_lines=2)
        self.append(self.notes)

    def connect_changed(self, callback) -> None:
        self.op.connect_changed(callback)
        self.acc.connect_changed(callback)
        self.notes.textview.get_buffer().connect("changed", lambda *_a: callback())

    def collect(self) -> dict:
        data = self.op.collect()
        data.update(self.acc.collect())
        data["kn_op_notes"] = self.notes.text
        return data

    def load(self, data: dict) -> None:
        self.op.load(data)
        self.acc.load(data)
        self.notes.text = data.get("kn_op_notes", "")


class KneeMuscleTables(StrengthGridTable):
    def __init__(self) -> None:
        super().__init__("Strength — Knee / Calf", _KN_STR_ROWS, unit="kg / grade", notes_id="mu_kn_notes")
