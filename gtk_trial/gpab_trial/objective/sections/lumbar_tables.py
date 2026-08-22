"""Lumbar Python table widgets — GTK4 port of
pab_assessment.objective.sections.lumbar_tables.

LumbarPassiveTables — Overpressure Normal-toggle+text table + PAIVM grid
LumbarMuscleTables  — Hip strength (Wagner FPX) + SIJ provocation signs

Field ids match the TUI exactly. Both widgets expose collect()/load() and
a connect_changed(callback) hook (RegionContainer's expected extras API,
mirroring the TUI's LumbarTables.Changed message the region container
catches for autosave).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import CheckButton, CycleField, TouchEntry, AutoTextView, make_subsection_header

_NORM_STATE = [("Norm", "success")]

# (label, prefix, bilateral) — bilateral rows show L | R columns in one row
_OP_ROWS: list[tuple[str, str, bool]] = [
    ("Tx Flexion", "op_tx_flex", False),
    ("Tx Extension", "op_tx_ext", False),
    ("Tx Rotation", "op_tx_rot", True),
    ("Lx Flexion", "op_lx_flex", False),
    ("Lx Extension", "op_lx_ext", False),
    ("Lx Lat Flex", "op_lx_lf", True),
]

_PAIVM_LEVELS: list[str] = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]

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


class LumbarPassiveTables(Gtk.Box):
    """Overpressure Normal+text table + PAIVM grid for Lumbar passive tab."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._cycles: dict[str, CycleField] = {}
        self._entries: dict[str, TouchEntry] = {}
        self._grid: list[list[str]] = []
        self._grid_pos: dict[str, tuple[int, int]] = {}

        self.append(make_subsection_header("Overpressure"))
        for label, prefix, bilateral in _OP_ROWS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(110, -1)
            row.append(lbl)
            row_ids: list[str] = []
            if bilateral:
                sides = [("L", f"{prefix}_l"), ("R", f"{prefix}_r")]
            else:
                sides = [(None, prefix)]
            for side_label, side_prefix in sides:
                if side_label:
                    slbl = Gtk.Label(label=side_label)
                    slbl.set_size_request(16, -1)
                    row.append(slbl)
                norm_id = f"{side_prefix}_norm"
                cf = CycleField("", norm_id, options=_NORM_STATE)
                self._cycles[norm_id] = cf
                row.append(cf)
                row_ids.append(norm_id)
                txt_id = f"{side_prefix}_txt"
                entry = TouchEntry(txt_id, placeholder="findings / reassessment")
                entry.set_hexpand(True)
                self._entries[txt_id] = entry
                row.append(entry)
                row_ids.append(txt_id)
            self._add_grid_row(row_ids)
            self.append(row)

        self.append(Gtk.Label(label="OP notes:", halign=Gtk.Align.START))
        self.op_notes = AutoTextView("pm_op_notes", min_lines=2)
        self._add_grid_row(["pm_op_notes"])
        self.append(self.op_notes)

        self.append(make_subsection_header("PAIVMs"))
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spacer = Gtk.Label(label="")
        spacer.set_size_request(30, -1)
        hdr.append(spacer)
        for side in ("L", "C", "R"):
            slbl = Gtk.Label(label=side)
            slbl.set_size_request(48, -1)
            hdr.append(slbl)
        hdr.append(Gtk.Label(label="Notes"))
        self.append(hdr)
        for level in _PAIVM_LEVELS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=level)
            lbl.set_size_request(30, -1)
            row.append(lbl)
            row_ids = []
            for side in ("l", "c", "r"):
                norm_id = f"pm_{level}_{side}_norm"
                cf = CycleField("", norm_id, options=_NORM_STATE)
                self._cycles[norm_id] = cf
                row.append(cf)
                row_ids.append(norm_id)
            txt_id = f"pm_{level}_txt"
            entry = TouchEntry(txt_id, placeholder="grade / findings")
            entry.set_hexpand(True)
            self._entries[txt_id] = entry
            row.append(entry)
            row_ids.append(txt_id)
            self._add_grid_row(row_ids)
            self.append(row)

        self.append(Gtk.Label(label="PAIVM notes:", halign=Gtk.Align.START))
        self.paivm_notes = AutoTextView("pm_paivm_notes", min_lines=2)
        self._add_grid_row(["pm_paivm_notes"])
        self.append(self.paivm_notes)

        self._wire_nav()

    def _add_grid_row(self, ids: list[str]) -> None:
        row_idx = len(self._grid)
        self._grid.append(ids)
        for col_idx, fid in enumerate(ids):
            self._grid_pos[fid] = (row_idx, col_idx)

    def _widget_for(self, fid: str):
        return self._cycles.get(fid) or self._entries.get(fid) or (
            self.op_notes if fid == "pm_op_notes" else
            self.paivm_notes if fid == "pm_paivm_notes" else None
        )

    def _on_navigate(self, widget, direction: str) -> None:
        fid = getattr(widget, "field_id", None)
        if fid is None or fid not in self._grid_pos:
            return
        row, col = self._grid_pos[fid]
        grid = self._grid
        target_id = None
        if direction == "up" and row > 0:
            tc = min(col, len(grid[row - 1]) - 1)
            target_id = grid[row - 1][tc]
        elif direction == "down" and row < len(grid) - 1:
            tc = min(col, len(grid[row + 1]) - 1)
            target_id = grid[row + 1][tc]
        elif direction == "left" and col > 0:
            target_id = grid[row][col - 1]
        elif direction == "right" and col < len(grid[row]) - 1:
            target_id = grid[row][col + 1]
        if target_id is not None:
            w = self._widget_for(target_id)
            if w is not None:
                w.grab_focus()

    def _wire_nav(self) -> None:
        for cf in self._cycles.values():
            cf.connect("navigate", self._on_navigate)
        for e in self._entries.values():
            e.connect("navigate", self._on_navigate)
        self.op_notes.connect("navigate", self._on_navigate)
        self.paivm_notes.connect("navigate", self._on_navigate)

    def connect_changed(self, callback) -> None:
        for cf in self._cycles.values():
            cf.connect("changed", lambda *_a: callback())
        for e in self._entries.values():
            e.connect("changed", lambda *_a: callback())
        self.op_notes.textview.get_buffer().connect("changed", lambda *_a: callback())
        self.paivm_notes.textview.get_buffer().connect("changed", lambda *_a: callback())

    def collect(self) -> dict:
        data: dict = {}
        for fid, cf in self._cycles.items():
            data[fid] = cf.value
        for fid, e in self._entries.items():
            data[fid] = e.text.strip()
        data["pm_op_notes"] = self.op_notes.text
        data["pm_paivm_notes"] = self.paivm_notes.text
        return data

    def load(self, data: dict) -> None:
        for fid, cf in self._cycles.items():
            cf.set_value(data.get(fid))
        for fid, e in self._entries.items():
            e.text = data.get(fid, "")
        self.op_notes.text = data.get("pm_op_notes", "")
        self.paivm_notes.text = data.get("pm_paivm_notes", "")


class LumbarMuscleTables(Gtk.Box):
    """Hip strength grid (Wagner FPX kg) + SIJ provocation signs for Lumbar
    muscle tab."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._entries: dict[str, TouchEntry] = {}
        self._checks: dict[str, CheckButton] = {}
        self._grid: list[list[str]] = []
        self._grid_pos: dict[str, tuple[int, int]] = {}

        self.append(make_subsection_header("Strength — Hip  (Wagner FPX kg)"))
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spacer = Gtk.Label(label="")
        spacer.set_size_request(140, -1)
        hdr.append(spacer)
        for side in ("Left", "Right"):
            slbl = Gtk.Label(label=side)
            slbl.set_hexpand(True)
            hdr.append(slbl)
        self.append(hdr)

        for label, prefix in _HIP_ROWS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(140, -1)
            row.append(lbl)
            row_ids = []
            for side in ("l", "r"):
                fid = f"{prefix}_{side}"
                entry = TouchEntry(fid, placeholder="kg")
                entry.set_hexpand(True)
                self._entries[fid] = entry
                entry.connect("navigate", self._on_navigate)
                row.append(entry)
                row_ids.append(fid)
            row_idx = len(self._grid)
            self._grid.append(row_ids)
            for col_idx, fid in enumerate(row_ids):
                self._grid_pos[fid] = (row_idx, col_idx)
            self.append(row)

        self.append(make_subsection_header("SIJ Provocation Signs"))
        sij_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for label, sid in _SIJ_ITEMS:
            btn = CheckButton(label, sid, compact=True)
            self._checks[sid] = btn
            sij_row.append(btn)
        self.append(sij_row)

    def _on_navigate(self, widget: TouchEntry, direction: str) -> None:
        if direction not in ("up", "down"):
            return
        fid = widget.field_id
        if fid not in self._grid_pos:
            return
        row, col = self._grid_pos[fid]
        target = row - 1 if direction == "up" else row + 1
        if 0 <= target < len(self._grid):
            self._entries[self._grid[target][col]].grab_focus()

    def connect_changed(self, callback) -> None:
        for e in self._entries.values():
            e.connect("changed", lambda *_a: callback())
        for btn in self._checks.values():
            btn.connect("changed", lambda *_a: callback())

    def collect(self) -> dict:
        data: dict = {}
        for fid, e in self._entries.items():
            data[fid] = e.text.strip()
        for sid, btn in self._checks.items():
            data[sid] = btn.value
        return data

    def load(self, data: dict) -> None:
        for fid, e in self._entries.items():
            e.text = data.get(fid, "")
        for sid, btn in self._checks.items():
            btn.set_value(data.get(sid))
