"""Lumbar Python table widgets — GTK4 port of
pab_assessment.objective.sections.lumbar_tables.

LumbarPassiveTables — Overpressure Normal-toggle+text table + PAIVM grid,
                      built directly on the shared OPPAIVMTable
                      (objective/passive_widgets.py) since this is exactly
                      that common shape with no region-specific extras.
LumbarMuscleTables  — Hip strength (Wagner FPX kg, via the shared
                      StrengthGridTable).
LumbarSpecialTables — SIJ provocation signs (bespoke — not expressible in
                      lumbar.yaml's special_tests shape, same reason the
                      other extras classes exist).

Field ids match the TUI exactly. All widgets expose collect()/load() and
a connect_changed(callback) hook (RegionContainer's expected extras API).

DELIBERATE DIVERGENCE FROM THE REFERENCE TUI (2026-08-24): the real
PhysioChart TUI (~/Projects/pab/assessment/pab_assessment/objective/
sections/lumbar_tables.py, confirmed by reading it directly) has always put
SIJ Provocation Signs under Muscle Testing, not Special Tests — flagged by
the user as a longstanding misclassification they'd simply never bothered to
raise before gpab existed to fix it in. Per this project's "never edit
assessment/" rule, ~/Projects/pab's own copy is untouched and still has SIJ
under Muscle; gpab now intentionally diverges. Confirmed with the user this
is expected/desired now that gpab is live-clinical-use, not just a port
project.

SIJ REWORK, SAME DAY: originally 6 unilateral CheckButtons (Yes/No/blank,
one value each). Reworked per user feedback to (a) visually match every
other Special Tests row (CycleField "?"/Yes/No, same as
BilateralGridSpecialTestsWidget/SpecialTestsWidget use elsewhere — see
widgets.CycleField), (b) give Left/Right columns to the tests that are
clinically performed per-side, and (c) add a notes field. Confirmed with the
user (2026-08-24) via the KB source text (~/Projects/kb/source/
msk_clusters_pab.csv, Laslett et al. 2005/2003): Thigh Thrust and Gaenslen's
are unambiguously per-side (Gaenslen's is even split into two separate CSV
rows with distinct Sn/Sp per side); Sacral Thrust and Distraction are
single bilateral-simultaneous procedures per the KB text ("both hands",
"bilateral ASIS simultaneously") and stay single-value; Compression and
ASLR compression the user chose to make L/R despite the KB text not being
explicit for Compression, and ASLR having no KB entry at all yet.

REPORT-GENERATOR COMPATIBILITY, IMPORTANT — read before touching
`sij_report_compat` or _SIJ_ITEMS' new field ids: storage.py (reused
unchanged, never edited — see repo CLAUDE.md) hardcodes reading these six
tests as ONE plain boolean value each from the region's "muscle" dict
(search assessment/pab_assessment/storage.py for "sij_sacral" — two call
sites, both `mus.get(sid)` with no L/R concept at all). Forking that report
logic into gpab was considered and explicitly declined by the user in
favour of a simpler compromise: `sij_report_compat()` below derives an
old-shape summary dict (True if EITHER side is "Yes", False if answered and
neither is "Yes", else None) purely for storage.py's report text to keep
consuming — app.py's `_do_save_obj` merges this into the region's "muscle"
dict alongside (not instead of) the real new-field-id data, which is what
gpab's own UI actually reloads from. This means the generated report text
will say "Yes"/"No" for a bilateral SIJ test without saying which side —
a deliberate, accepted loss of granularity in report TEXT only; the full
L/R answer is always present and correct in the underlying JSON.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import AutoTextView, CycleField, make_subsection_header
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

# (label, new field-id prefix, bilateral?) — bilateral rows get "_l"/"_r"
# suffixes (e.g. "st_sij_ptt_l"); single rows use the prefix as-is
# ("st_sij_sacral"). See this file's module docstring for the clinical
# basis of which tests are bilateral.
_SIJ_ITEMS: list[tuple[str, str, bool]] = [
    ("Sacral thrust", "st_sij_sacral", False),
    ("Post thigh thrust", "st_sij_ptt", True),
    ("Distraction supine", "st_sij_dist", False),
    ("Compression s/l", "st_sij_comp", True),
    ("Gaenslen", "st_sij_gaenslen", True),
    ("ASLR compression", "st_sij_aslr", True),
]

# New field id -> the OLD single-value field id storage.py's report
# generator (reused unchanged) still expects under the region's "muscle"
# dict. See sij_report_compat() and this file's module docstring.
_OLD_SID_FOR: dict[str, str] = {
    "st_sij_sacral": "sij_sacral",
    "st_sij_ptt": "sij_ptt",
    "st_sij_dist": "sij_dist",
    "st_sij_comp": "sij_comp",
    "st_sij_gaenslen": "sij_gaenslen",
    "st_sij_aslr": "sij_aslr",
}

_SIJ_NOTES_ID = "st_sij_notes"

_SIJ_STATES = [("Yes", "error"), ("No", "success")]


def sij_report_compat(collected: dict) -> dict:
    """Derive the OLD boolean-per-test dict storage.py's report generator
    expects from LumbarSpecialTables.collect()'s output (new field ids,
    "Yes"/"No"/None values). For the two single-procedure tests this is a
    direct type conversion; for the four bilateral tests it's a deliberate,
    accepted summary — True if EITHER side is "Yes", False if at least one
    side is answered and neither is "Yes", else None (unanswered) — see this
    file's module docstring for why. Called from app.py's _do_save_obj,
    ONLY for region_id == "lumbar" (every other region's collected dict
    simply has none of these keys, so this would be a no-op there anyway,
    but there's no reason to run it)."""
    result: dict = {}
    for _label, new_id, bilateral in _SIJ_ITEMS:
        old_sid = _OLD_SID_FOR[new_id]
        if not bilateral:
            v = collected.get(new_id)
        else:
            left, right = collected.get(f"{new_id}_l"), collected.get(f"{new_id}_r")
            if left == "Yes" or right == "Yes":
                result[old_sid] = True
                continue
            v = "No" if (left == "No" or right == "No") else None
        result[old_sid] = True if v == "Yes" else False if v == "No" else None
    return result


class LumbarPassiveTables(OPPAIVMTable):
    def __init__(self) -> None:
        super().__init__(_OP_ROWS, _PAIVM_LEVELS, "pm", "pm_op_notes", "pm_paivm_notes")


class LumbarMuscleTables(Gtk.Box):
    """Hip strength grid (Wagner FPX kg)."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.hip_table = StrengthGridTable("Strength — Hip", _HIP_ROWS, unit="Wagner FPX kg", anchor_id="ml_strength_hip")
        self.append(self.hip_table)

    def connect_changed(self, callback) -> None:
        self.hip_table.connect_changed(callback)

    def collect(self) -> dict:
        return self.hip_table.collect()

    def load(self, data: dict) -> None:
        self.hip_table.load(data)


class LumbarSpecialTables(Gtk.Box):
    """SIJ Provocation Signs — moved here from Muscle Testing 2026-08-24 per
    user feedback (a longstanding misclassification inherited from the
    reference TUI, which still has it under Muscle — see this file's module
    docstring), and restyled to match every other Special Tests row
    (CycleField "?"/Yes/No chips, "grid-row" layout) with real L/R columns
    on the tests that are clinically per-side. Field ids are new
    (st_sij_* — see _SIJ_ITEMS); storage.py's report generator still reads
    the OLD field ids from the region's "muscle" dict, which app.py's
    _do_save_obj populates via sij_report_compat() — see this file's module
    docstring for why, and don't remove that call without reading it."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.append(make_subsection_header("SIJ Provocation Signs", "st_sij"))
        self._fields: dict[str, CycleField] = {}
        self._grid: list[str] = []
        self._grid_pos: dict[str, int] = {}

        for label, new_id, bilateral in _SIJ_ITEMS:
            hrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            hrow.add_css_class("grid-row")
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(160, -1)
            hrow.append(lbl)
            ids = [f"{new_id}_l", f"{new_id}_r"] if bilateral else [new_id]
            for fid in ids:
                cf = CycleField("", fid, options=_SIJ_STATES)
                cf.connect("navigate", self._on_navigate)
                self._fields[fid] = cf
                hrow.append(cf)
                self._grid_pos[fid] = len(self._grid)
                self._grid.append(fid)
            self.append(hrow)

        self.append(Gtk.Label(label="Notes:", halign=Gtk.Align.START))
        self.notes = AutoTextView(_SIJ_NOTES_ID, min_lines=2)
        self.notes.connect("navigate", self._on_navigate)
        self._grid_pos[_SIJ_NOTES_ID] = len(self._grid)
        self._grid.append(_SIJ_NOTES_ID)
        self.append(self.notes)

    def _widget_for(self, fid: str):
        if fid == _SIJ_NOTES_ID:
            return self.notes
        return self._fields.get(fid)

    def _on_navigate(self, widget, direction: str) -> None:
        if direction not in ("up", "down"):
            return
        fid = widget.field_id
        if fid not in self._grid_pos:
            return
        idx = self._grid_pos[fid]
        target = idx - 1 if direction == "up" else idx + 1
        if 0 <= target < len(self._grid):
            w = self._widget_for(self._grid[target])
            if w is not None:
                w.grab_focus()

    def connect_changed(self, callback) -> None:
        for cf in self._fields.values():
            cf.connect("changed", lambda *_a: callback())
        self.notes.textview.get_buffer().connect("changed", lambda *_a: callback())

    def collect(self) -> dict:
        data = {fid: cf.value for fid, cf in self._fields.items()}
        data[_SIJ_NOTES_ID] = self.notes.text
        return data

    def load(self, data: dict) -> None:
        for fid, cf in self._fields.items():
            cf.set_value(data.get(fid))
        self.notes.text = data.get(_SIJ_NOTES_ID, "")
