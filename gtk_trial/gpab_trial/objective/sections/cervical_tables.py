"""Cervical Python table widgets — GTK4 port of
pab_assessment.objective.sections.cervical_tables.

CervicalPassiveTables — Overpressure + PAIVM grid C0/1-T4, built directly
                        on the shared OPPAIVMTable.
CervicalMuscleTables  — Neck strength bilateral grid (kg), via the shared
                        StrengthGridTable.

Field ids match the TUI exactly.
"""

from __future__ import annotations

from ..passive_widgets import OPPAIVMTable, StrengthGridTable

# (label, prefix, bilateral) — bilateral rows show L | R columns in one row
_CX_OP_ROWS: list[tuple[str, str, bool]] = [
    ("Cx Flexion", "cx_op_flex", False),
    ("Cx Extension", "cx_op_ext", False),
    ("Cx Lat Flex", "cx_op_lf", True),
    ("Cx Rotation", "cx_op_rot", True),
    ("Cx Quadrant", "cx_op_quad", True),
]

# (display_label, id_key) — id_key avoids slashes for use in field ids
_CX_PAIVM_LEVELS: list[tuple[str, str]] = [
    ("C0/1", "C0_1"), ("C1/2", "C1_2"), ("C2", "C2"), ("C3", "C3"),
    ("C4", "C4"), ("C5", "C5"), ("C6", "C6"), ("C7", "C7"),
    ("T1", "T1"), ("T2", "T2"), ("T3", "T3"), ("T4", "T4"),
]

_CX_NECK_ROWS: list[tuple[str, str]] = [
    ("Neck flexion", "cx_neck_flex"),
    ("Neck extension", "cx_neck_ext"),
    ("Neck lat flex", "cx_neck_lf"),
    ("Neck rotation", "cx_neck_rot"),
]


class CervicalPassiveTables(OPPAIVMTable):
    def __init__(self) -> None:
        super().__init__(_CX_OP_ROWS, _CX_PAIVM_LEVELS, "cx_pm", "cx_pm_op_notes", "cx_pm_paivm_notes")


class CervicalMuscleTables(StrengthGridTable):
    def __init__(self) -> None:
        super().__init__("Strength — Neck", _CX_NECK_ROWS, unit="kg")
