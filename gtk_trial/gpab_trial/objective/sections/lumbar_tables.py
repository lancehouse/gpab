"""Lumbar Python table widgets — GTK4 port of
pab_assessment.objective.sections.lumbar_tables.

LumbarPassiveTables — Overpressure Normal-toggle+text table + PAIVM grid,
                      built directly on the shared OPPAIVMTable
                      (objective/passive_widgets.py) since this is exactly
                      that common shape with no region-specific extras.
LumbarMuscleTables  — Hip strength (Wagner FPX kg, via the shared
                      StrengthGridTable) + SIJ provocation signs (bespoke —
                      not part of the shared shape).

Field ids match the TUI exactly. Both widgets expose collect()/load() and
a connect_changed(callback) hook (RegionContainer's expected extras API).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import CheckButton, make_subsection_header
from ..passive_widgets import OPPAIVMTable, StrengthGridTable

# (label, prefix, bilateral) — bilateral rows show L | R columns in one row
_OP_ROWS: list[tuple[str, str, bool]] = [
    ("Tx Flexion", "op_tx_flex", False),
    ("Tx Extension", "op_tx_ext", False),
    ("Tx Rotation", "op_tx_rot", True),
    ("Lx Flexion", "op_lx_flex", False),
    ("Lx Extension", "op_lx_ext", False),
    ("Lx Lat Flex", "op_lx_lf", True),
]

_PAIVM_LEVELS = [(lvl, lvl) for lvl in ("T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5")]

_HIP_ROWS: list[tuple[str, str]] = [
    ("Hip flexion", "sh_hip_flex"),
    ("Hip extension", "sh_hip_ext"),
    ("Hip abduction", "sh_hip_abd"),
    ("Hip adduction", "sh_hip_add"),
    ("Hip int rotation", "sh_hip_ir"),
    ("Hip ext rotation", "sh_hip_er"),
]

_SIJ_ITEMS: list[tuple[str, str]] = [
    ("Sacral thrust", "sij_sacral"),
    ("Post thigh thrust", "sij_ptt"),
    ("Distraction supine", "sij_dist"),
    ("Compression s/l", "sij_comp"),
    ("Gaenslen", "sij_gaenslen"),
    ("ASLR compression", "sij_aslr"),
]


class LumbarPassiveTables(OPPAIVMTable):
    def __init__(self) -> None:
        super().__init__(_OP_ROWS, _PAIVM_LEVELS, "pm", "pm_op_notes", "pm_paivm_notes")


class LumbarMuscleTables(Gtk.Box):
    """Hip strength grid (Wagner FPX kg) + SIJ provocation signs."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.hip_table = StrengthGridTable("Strength — Hip", _HIP_ROWS, unit="Wagner FPX kg")
        self.append(self.hip_table)

        self.append(make_subsection_header("SIJ Provocation Signs"))
        self._checks: dict[str, CheckButton] = {}
        sij_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for label, sid in _SIJ_ITEMS:
            btn = CheckButton(label, sid, compact=True)
            self._checks[sid] = btn
            sij_row.append(btn)
        self.append(sij_row)

    def connect_changed(self, callback) -> None:
        self.hip_table.connect_changed(callback)
        for btn in self._checks.values():
            btn.connect("changed", lambda *_a: callback())

    def collect(self) -> dict:
        data = self.hip_table.collect()
        for sid, btn in self._checks.items():
            data[sid] = btn.value
        return data

    def load(self, data: dict) -> None:
        self.hip_table.load(data)
        for sid, btn in self._checks.items():
            btn.set_value(data.get(sid))
