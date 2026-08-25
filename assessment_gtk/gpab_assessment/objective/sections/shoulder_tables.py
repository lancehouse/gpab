"""Shoulder Python table widgets — GTK4 port of
pab_assessment.objective.sections.shoulder_tables.

ShoulderPassiveTables — Overpressure + GH accessory glides + AC/SC joint,
                        three stacked bilateral tables (no PAIVM grid,
                        unlike Lumbar/Cervical) — each built directly on
                        the shared BilateralNormTable.
ShoulderMuscleTables  — Shoulder strength bilateral grid (kg or 0-5), via
                        the shared StrengthGridTable.

Field ids match the TUI exactly. AC/SC has no notes field in the TUI —
kept that way here.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..passive_widgets import BilateralNormTable, StrengthGridTable

_OP_ROWS: list[tuple[str, str]] = [
    ("Flexion", "sh_op_flex"),
    ("Extension", "sh_op_ext"),
    ("Abduction", "sh_op_abd"),
    ("Int Rot", "sh_op_ir"),
    ("Ext Rot", "sh_op_er"),
    ("Horiz Add", "sh_op_hadd"),
    ("Horiz Abd", "sh_op_habd"),
]

_ACC_ROWS: list[tuple[str, str]] = [
    ("Inferior", "sh_acc_inf"),
    ("Posterior", "sh_acc_post"),
    ("Anterior", "sh_acc_ant"),
]

_AC_SC_ROWS: list[tuple[str, str]] = [
    ("AC Stress", "sh_ac_pm_stress"),
    ("AC Palp", "sh_ac_pm_palp"),
    ("SC Stress", "sh_sc_pm_stress"),
]

_SH_STR_ROWS: list[tuple[str, str]] = [
    ("Flexion", "sh_str_flex"),
    ("Abduction", "sh_str_abd"),
    ("Int Rot", "sh_str_ir"),
    ("Ext Rot", "sh_str_er"),
    ("Scaption", "sh_str_scap"),
]


class ShoulderPassiveTables(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.op = BilateralNormTable("Overpressure", _OP_ROWS, notes_id="sh_pm_op_notes")
        self.append(self.op)
        self.acc = BilateralNormTable(
            "GH Accessory Glides", _ACC_ROWS, notes_id="sh_pm_acc_notes",
            txt_placeholder="grade / findings",
        )
        self.append(self.acc)
        self.acsc = BilateralNormTable("AC / SC Joint", _AC_SC_ROWS, notes_id=None)
        self.append(self.acsc)

    def connect_changed(self, callback) -> None:
        self.op.connect_changed(callback)
        self.acc.connect_changed(callback)
        self.acsc.connect_changed(callback)

    def collect(self) -> dict:
        data = self.op.collect()
        data.update(self.acc.collect())
        data.update(self.acsc.collect())
        return data

    def load(self, data: dict) -> None:
        self.op.load(data)
        self.acc.load(data)
        self.acsc.load(data)


class ShoulderMuscleTables(StrengthGridTable):
    def __init__(self) -> None:
        super().__init__("Strength — Shoulder", _SH_STR_ROWS, unit="kg or 0-5")
