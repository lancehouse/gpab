"""Hip Python table widgets — GTK4 port of
pab_assessment.objective.sections.hip_tables.

HipPassiveTables — bilateral OP table + accessory glides table, sharing
                   ONE combined notes field below both (unlike Shoulder,
                   which gives OP and Accessory Glides their own separate
                   notes) — built from two BilateralNormTable instances
                   (each with notes_id=None) plus a manually-appended
                   shared AutoTextView.
HipMuscleTables  — hip strength bilateral grid (kg or 0-5) + notes, via
                   the shared StrengthGridTable's notes_id support.

Field ids match the TUI exactly. Cross-table arrow-nav between the OP
table and the Accessory table is not chained (each has its own internal
up/down nav) — same simplification RegionContainer already makes for
every tab except "active" (ROM).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import AutoTextView
from ..passive_widgets import BilateralNormTable, StrengthGridTable

_HP_OP_ROWS: list[tuple[str, str]] = [
    ("Flexion", "hp_op_flex"),
    ("Extension", "hp_op_ext"),
    ("Abduction", "hp_op_abd"),
    ("Adduction", "hp_op_add"),
    ("Int Rotation", "hp_op_ir"),
    ("Ext Rotation", "hp_op_er"),
]

_HP_ACC_ROWS: list[tuple[str, str]] = [
    ("Distraction", "hp_acc_dist"),
    ("Lateral", "hp_acc_lat"),
]

_HP_STR_ROWS: list[tuple[str, str]] = [
    ("Flexion", "hp_str_flex"),
    ("Extension", "hp_str_ext"),
    ("Abduction", "hp_str_abd"),
    ("Adduction", "hp_str_add"),
    ("Int Rotation", "hp_str_ir"),
    ("Ext Rotation", "hp_str_er"),
]


class HipPassiveTables(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.op = BilateralNormTable("Overpressure", _HP_OP_ROWS, notes_id=None,
                                      txt_placeholder="findings / //")
        self.append(self.op)
        self.acc = BilateralNormTable("Accessory Glides", _HP_ACC_ROWS, notes_id=None,
                                       txt_placeholder="grade / findings")
        self.append(self.acc)

        self.append(Gtk.Label(label="OP notes:", halign=Gtk.Align.START))
        self.notes = AutoTextView("hp_op_notes", min_lines=2)
        self.append(self.notes)

    def connect_changed(self, callback) -> None:
        self.op.connect_changed(callback)
        self.acc.connect_changed(callback)
        self.notes.textview.get_buffer().connect("changed", lambda *_a: callback())

    def collect(self) -> dict:
        data = self.op.collect()
        data.update(self.acc.collect())
        data["hp_op_notes"] = self.notes.text
        return data

    def load(self, data: dict) -> None:
        self.op.load(data)
        self.acc.load(data)
        self.notes.text = data.get("hp_op_notes", "")


class HipMuscleTables(StrengthGridTable):
    def __init__(self) -> None:
        super().__init__("Strength — Hip", _HP_STR_ROWS, unit="kg / grade", notes_id="mu_hp_notes")
