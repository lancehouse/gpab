"""Shared Overpressure + PAIVM passive-movement table — GTK4 port of the
repeated OP/PAIVM widget shape found in every region's *_tables.py
(LumbarPassiveTables, CervicalPassiveTables, and so on for the remaining
regions). The TUI duplicates this widget once per region file with only
the row/level lists and a couple of id prefixes differing; centralizing it
here means a fix or refinement benefits every region at once instead of
needing to be copied five more times, per this project's "centralize,
don't repeat" rule.

Every region's Passive tab is: an Overpressure table (label + optional L/R
split + Norm-toggle CycleField + findings TouchEntry per row) followed by
a PAIVM table (level rows, three Norm-toggle CycleFields for L/C/R plus a
findings TouchEntry), each with its own notes field below it.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..widgets import CycleField, TouchEntry, AutoTextView, make_subsection_header

_NORM_STATE = [("Norm", "success")]


class OPPAIVMTable(Gtk.Box):
    """op_rows: list[(label, field_prefix, bilateral)] — field_prefix already
    includes the region's own prefix (e.g. "op_lx_flex", "cx_op_flex").

    paivm_levels: list[(display_label, id_key)] — id_key must be id-safe
    (e.g. cervical's "C0/1" -> "C0_1"); lumbar's plain level strings (e.g.
    "L4") are id-safe already, so display == id_key there.

    paivm_prefix: field id prefix for PAIVM rows (e.g. "pm" for lumbar,
    "cx_pm" for cervical) — PAIVM row ids are f"{paivm_prefix}_{id_key}_l_norm"
    etc., matching each region's own TUI field-id convention exactly.

    op_notes_id / paivm_notes_id: the two notes field ids for this region.
    """

    def __init__(
        self,
        op_rows: list[tuple[str, str, bool]],
        paivm_levels: list[tuple[str, str]],
        paivm_prefix: str,
        op_notes_id: str,
        paivm_notes_id: str,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._cycles: dict[str, CycleField] = {}
        self._entries: dict[str, TouchEntry] = {}
        self._grid: list[list[str]] = []
        self._grid_pos: dict[str, tuple[int, int]] = {}

        self.append(make_subsection_header("Overpressure"))
        for label, prefix, bilateral in op_rows:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(110, -1)
            row.append(lbl)
            row_ids: list[str] = []
            sides = [("L", f"{prefix}_l"), ("R", f"{prefix}_r")] if bilateral else [(None, prefix)]
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
        self.op_notes = AutoTextView(op_notes_id, min_lines=2)
        self._op_notes_id = op_notes_id
        self._add_grid_row([op_notes_id])
        self.append(self.op_notes)

        self.append(make_subsection_header("PAIVMs"))
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spacer = Gtk.Label(label="")
        spacer.set_size_request(50, -1)
        hdr.append(spacer)
        for side in ("L", "C", "R"):
            slbl = Gtk.Label(label=side)
            slbl.set_size_request(48, -1)
            hdr.append(slbl)
        hdr.append(Gtk.Label(label="Notes"))
        self.append(hdr)
        for display, id_key in paivm_levels:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=display)
            lbl.set_size_request(50, -1)
            row.append(lbl)
            row_ids = []
            for side in ("l", "c", "r"):
                norm_id = f"{paivm_prefix}_{id_key}_{side}_norm"
                cf = CycleField("", norm_id, options=_NORM_STATE)
                self._cycles[norm_id] = cf
                row.append(cf)
                row_ids.append(norm_id)
            txt_id = f"{paivm_prefix}_{id_key}_txt"
            entry = TouchEntry(txt_id, placeholder="grade / findings")
            entry.set_hexpand(True)
            self._entries[txt_id] = entry
            row.append(entry)
            row_ids.append(txt_id)
            self._add_grid_row(row_ids)
            self.append(row)

        self.append(Gtk.Label(label="PAIVM notes:", halign=Gtk.Align.START))
        self.paivm_notes = AutoTextView(paivm_notes_id, min_lines=2)
        self._paivm_notes_id = paivm_notes_id
        self._add_grid_row([paivm_notes_id])
        self.append(self.paivm_notes)

        self._wire_nav()

    def _add_grid_row(self, ids: list[str]) -> None:
        row_idx = len(self._grid)
        self._grid.append(ids)
        for col_idx, fid in enumerate(ids):
            self._grid_pos[fid] = (row_idx, col_idx)

    def _widget_for(self, fid: str):
        return (
            self._cycles.get(fid)
            or self._entries.get(fid)
            or (self.op_notes if fid == self._op_notes_id else
                self.paivm_notes if fid == self._paivm_notes_id else None)
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
        data[self._op_notes_id] = self.op_notes.text
        data[self._paivm_notes_id] = self.paivm_notes.text
        return data

    def load(self, data: dict) -> None:
        for fid, cf in self._cycles.items():
            cf.set_value(data.get(fid))
        for fid, e in self._entries.items():
            e.text = data.get(fid, "")
        self.op_notes.text = data.get(self._op_notes_id, "")
        self.paivm_notes.text = data.get(self._paivm_notes_id, "")


class BilateralNormTable(Gtk.Box):
    """label | L: Norm-toggle + findings | R: Norm-toggle + findings — a
    standalone bilateral table with no paired PAIVM section (unlike
    OPPAIVMTable above). Used where a region's Passive tab has more than
    one such table stacked (e.g. Shoulder's Overpressure + GH Accessory
    Glides + AC/SC Joint, each its own instance of this shape).

    notes_id: pass None to omit a notes field entirely (Shoulder's AC/SC
    table has none in the TUI)."""

    def __init__(
        self,
        title: str,
        rows: list[tuple[str, str]],
        notes_id: str | None = None,
        txt_placeholder: str = "findings",
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._cycles: dict[str, CycleField] = {}
        self._entries: dict[str, TouchEntry] = {}
        self._grid: list[list[str]] = []
        self._grid_pos: dict[str, tuple[int, int]] = {}
        self._notes_id = notes_id

        self.append(make_subsection_header(title))
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spacer = Gtk.Label(label="")
        spacer.set_size_request(110, -1)
        hdr.append(spacer)
        for side in ("Left", "Right"):
            slbl = Gtk.Label(label=side)
            slbl.set_hexpand(True)
            hdr.append(slbl)
        self.append(hdr)

        for label, prefix in rows:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(110, -1)
            row.append(lbl)
            row_ids = []
            for side in ("l", "r"):
                norm_id = f"{prefix}_{side}_norm"
                cf = CycleField("", norm_id, options=_NORM_STATE)
                cf.connect("navigate", self._on_navigate)
                self._cycles[norm_id] = cf
                row.append(cf)
                row_ids.append(norm_id)
                txt_id = f"{prefix}_{side}_txt"
                entry = TouchEntry(txt_id, placeholder=txt_placeholder)
                entry.set_hexpand(True)
                entry.connect("navigate", self._on_navigate)
                self._entries[txt_id] = entry
                row.append(entry)
                row_ids.append(txt_id)
            row_idx = len(self._grid)
            self._grid.append(row_ids)
            for col_idx, fid in enumerate(row_ids):
                self._grid_pos[fid] = (row_idx, col_idx)
            self.append(row)

        self.notes: AutoTextView | None = None
        if notes_id:
            self.append(Gtk.Label(label="Notes:", halign=Gtk.Align.START))
            self.notes = AutoTextView(notes_id, min_lines=2)
            self.notes.connect("navigate", self._on_navigate)
            self._grid_pos[notes_id] = (len(self._grid), 0)
            self._grid.append([notes_id])
            self.append(self.notes)

    def _widget_for(self, fid: str):
        if fid == self._notes_id:
            return self.notes
        return self._cycles.get(fid) or self._entries.get(fid)

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

    def connect_changed(self, callback) -> None:
        for cf in self._cycles.values():
            cf.connect("changed", lambda *_a: callback())
        for e in self._entries.values():
            e.connect("changed", lambda *_a: callback())
        if self.notes is not None:
            self.notes.textview.get_buffer().connect("changed", lambda *_a: callback())

    def collect(self) -> dict:
        data: dict = {}
        for fid, cf in self._cycles.items():
            data[fid] = cf.value
        for fid, e in self._entries.items():
            data[fid] = e.text.strip()
        if self._notes_id and self.notes is not None:
            data[self._notes_id] = self.notes.text
        return data

    def load(self, data: dict) -> None:
        for fid, cf in self._cycles.items():
            cf.set_value(data.get(fid))
        for fid, e in self._entries.items():
            e.text = data.get(fid, "")
        if self._notes_id and self.notes is not None:
            self.notes.text = data.get(self._notes_id, "")


class StrengthGridTable(Gtk.Box):
    """Bilateral numeric strength grid (kg or similar unit) — the second
    common shape found in every region's *MuscleTables (Lumbar's hip
    strength, Cervical's neck strength, and so on)."""

    def __init__(
        self,
        title: str,
        rows: list[tuple[str, str]],
        unit: str = "kg",
        notes_id: str | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._entries: dict[str, TouchEntry] = {}
        self._grid: list[list[str]] = []
        self._grid_pos: dict[str, tuple[int, int]] = {}
        self._notes_id = notes_id

        self.append(make_subsection_header(f"{title}  ({unit})"))
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spacer = Gtk.Label(label="")
        spacer.set_size_request(140, -1)
        hdr.append(spacer)
        for side in ("Left", "Right"):
            slbl = Gtk.Label(label=side)
            slbl.set_hexpand(True)
            hdr.append(slbl)
        self.append(hdr)

        for label, prefix in rows:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(140, -1)
            row.append(lbl)
            row_ids = []
            for side in ("l", "r"):
                fid = f"{prefix}_{side}"
                entry = TouchEntry(fid, placeholder=unit)
                entry.set_hexpand(True)
                entry.connect("navigate", self._on_navigate)
                self._entries[fid] = entry
                row.append(entry)
                row_ids.append(fid)
            row_idx = len(self._grid)
            self._grid.append(row_ids)
            for col_idx, fid in enumerate(row_ids):
                self._grid_pos[fid] = (row_idx, col_idx)
            self.append(row)

        self.notes: AutoTextView | None = None
        if notes_id:
            self.append(Gtk.Label(label="Notes:", halign=Gtk.Align.START))
            self.notes = AutoTextView(notes_id, min_lines=2)
            self.notes.connect("navigate", self._on_navigate)
            self._grid_pos[notes_id] = (len(self._grid), 0)
            self._grid.append([notes_id])
            self.append(self.notes)

    def _widget_for(self, fid: str):
        if fid == self._notes_id:
            return self.notes
        return self._entries.get(fid)

    def _on_navigate(self, widget, direction: str) -> None:
        if direction not in ("up", "down"):
            return
        fid = getattr(widget, "field_id", None)
        if fid is None or fid not in self._grid_pos:
            return
        row, col = self._grid_pos[fid]
        target = row - 1 if direction == "up" else row + 1
        if 0 <= target < len(self._grid):
            w = self._widget_for(self._grid[target][min(col, len(self._grid[target]) - 1)])
            if w is not None:
                w.grab_focus()

    def connect_changed(self, callback) -> None:
        for e in self._entries.values():
            e.connect("changed", lambda *_a: callback())
        if self.notes is not None:
            self.notes.textview.get_buffer().connect("changed", lambda *_a: callback())

    def collect(self) -> dict:
        data = {fid: e.text.strip() for fid, e in self._entries.items()}
        if self._notes_id and self.notes is not None:
            data[self._notes_id] = self.notes.text
        return data

    def load(self, data: dict) -> None:
        for fid, e in self._entries.items():
            e.text = data.get(fid, "")
        if self._notes_id and self.notes is not None:
            self.notes.text = data.get(self._notes_id, "")
