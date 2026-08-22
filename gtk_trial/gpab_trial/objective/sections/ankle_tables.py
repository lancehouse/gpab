"""Ankle Python table widgets — GTK4 port of
pab_assessment.objective.sections.ankle_tables.

Same shape as Hip/Knee: OP table + Accessory Glides (subtalar) table
sharing one combined notes field, plus a strength grid with its own notes.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import AutoTextView
from ..passive_widgets import BilateralNormTable, StrengthGridTable

_AK_OP_ROWS: list[tuple[str, str]] = [
    ("Dorsiflexion", "ak_op_df"),
    ("Plantarflexion", "ak_op_pf"),
    ("Inversion", "ak_op_inv"),
    ("Eversion", "ak_op_ev"),
]

_AK_ACC_ROWS: list[tuple[str, str]] = [
    ("AP Glide", "ak_acc_ap"),
    ("Subtalar", "ak_acc_st"),
]

_AK_STR_ROWS: list[tuple[str, str]] = [
    ("Dorsiflexion (TA)", "ak_str_df"),
    ("Plantarflexion (GS)", "ak_str_pf"),
    ("Eversion (peroneals)", "ak_str_ev"),
]


class AnklePassiveTables(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.op = BilateralNormTable("Overpressure", _AK_OP_ROWS, notes_id=None,
                                      txt_placeholder="findings / //")
        self.append(self.op)
        self.acc = BilateralNormTable("Accessory Glides", _AK_ACC_ROWS, notes_id=None,
                                       txt_placeholder="grade / findings")
        self.append(self.acc)

        self.append(Gtk.Label(label="OP notes:", halign=Gtk.Align.START))
        self.notes = AutoTextView("ak_op_notes", min_lines=2)
        self.append(self.notes)

    def connect_changed(self, callback) -> None:
        self.op.connect_changed(callback)
        self.acc.connect_changed(callback)
        self.notes.textview.get_buffer().connect("changed", lambda *_a: callback())

    def collect(self) -> dict:
        data = self.op.collect()
        data.update(self.acc.collect())
        data["ak_op_notes"] = self.notes.text
        return data

    def load(self, data: dict) -> None:
        self.op.load(data)
        self.acc.load(data)
        self.notes.text = data.get("ak_op_notes", "")


class AnkleMuscleTables(StrengthGridTable):
    def __init__(self) -> None:
        super().__init__("Strength — Ankle", _AK_STR_ROWS, unit="kg / grade", notes_id="mu_ak_notes")
