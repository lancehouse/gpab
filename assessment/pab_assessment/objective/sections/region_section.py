"""YAML-driven region block renderer for Objective TUI.

RegionContainer  — collapsible per-region block for one objective tab.
                   Renders YAML-defined flat fields + optional Python extras.
RegionTabContent — the full tab container; manages one RegionContainer per
                   active region, stacked vertically.

Supported YAML field group types (in lumbar.yaml):
  active_movement  → ROMGroupWidget (RangeCell/ROMRow tables)
  muscle_testing   → GradeGroupWidget (bilateral/unilateral RadioGroup rows)
                   + TrunkStrengthWidget (numeric GridInput rows)
  special_tests    → SpecialTestsWidget (RadioGroup rows)

Python extras (OP/PAIVM/hip/SIJ) registered per (region_id, section_key)
in REGION_EXTRAS at the bottom of this file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Type

import yaml

from textual.app import ComposeResult, on
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widgets import Label, Static, TextArea

from ...widgets import CycleButton, GridInput, GridTextArea, RadioGroup
from .active_movement import RangeCell, ROMRow
from .ankle_tables import AnkleMuscleTables, AnklePassiveTables, AnkleTables
from .cervical_tables import CervicalMuscleTables, CervicalPassiveTables, CervicalTables
from .hip_tables import HipMuscleTables, HipPassiveTables, HipTables
from .knee_tables import KneeMuscleTables, KneePassiveTables, KneeTables
from .lumbar_tables import LumbarMuscleTables, LumbarPassiveTables, LumbarTables
from .shoulder_tables import ShoulderMuscleTables, ShoulderPassiveTables, ShoulderTables


_YAML_DIR = Path(__file__).parent / "yaml"

# Maps section_key ("active", "passive", "muscle", "special") → yaml top-level key
_YAML_KEY: dict[str, str] = {
    "active":  "active_movement",
    "muscle":  "muscle_testing",
    "special": "special_tests",
}


def _load_yaml(region_id: str) -> dict:
    path = _YAML_DIR / f"{region_id}.yaml"
    return yaml.safe_load(path.read_text()) if path.exists() else {}


def _infer_variant(idx: int, total: int) -> str:
    if idx == 0:
        return "success"
    if total == 2 or idx == total - 1:
        return "error"
    return "warning"


def _build_gang(options: list[str]) -> list[tuple[str, str]]:
    total = len(options)
    return [(label, _infer_variant(i, total)) for i, label in enumerate(options)]


# ── ROM group widget ──────────────────────────────────────────────────────────

class ROMGroupWidget(Static):
    """One named group of ROM rows (Ax L/R) from YAML active_movement.groups."""

    DEFAULT_CSS = """
    ROMGroupWidget { width: 100%; height: auto; }
    ROMGroupWidget .hdr_major  { layout: horizontal; height: 1; width: 100%; color: $text-muted; }
    ROMGroupWidget .hdr_spacer { width: 12; }
    ROMGroupWidget .hdr_group  { width: 1fr; text-align: center; text-style: bold; }
    ROMGroupWidget .hdr_sub    { layout: horizontal; height: 1; width: 100%; color: $text-muted; }
    ROMGroupWidget .hdr_lr     { width: 1fr; text-align: center; }
    ROMGroupWidget TextArea    { height: auto; min-height: 2; padding: 0 1; }
    ROMGroupWidget Label       { height: auto; margin-top: 0; }
    """

    def __init__(self, group_def: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._group = group_def
        self._notes_id: str | None = group_def.get("notes_id")
        self._row_ids: list[str] = [r["id"] for r in group_def.get("rows", [])]

    def compose(self) -> ComposeResult:
        label = self._group.get("label", "")
        yield Label(label, classes="subsection_header")
        with Horizontal(classes="hdr_major"):
            yield Static("",   classes="hdr_spacer")
            yield Static("Ax", classes="hdr_group")
        with Horizontal(classes="hdr_sub"):
            yield Static("",      classes="hdr_spacer")
            yield Static("Left",  classes="hdr_lr")
            yield Static("Right", classes="hdr_lr")
        for row in self._group.get("rows", []):
            yield ROMRow(
                row["label"],
                row["id"],
                bilateral=row.get("bilateral", False),
                id=f"romrow_{row['id']}",
            )
        if self._notes_id:
            yield Label("Comment:")
            yield GridTextArea(id=self._notes_id, language="plain")

    def grid_rows(self) -> list[list[str]]:
        """Row ids for RegionContainer's cross-group nav grid, in DOM order."""
        rows: list[list[str]] = []
        for row in self._group.get("rows", []):
            prefix = row["id"]
            bilateral = row.get("bilateral", False)
            cols = [f"{prefix}_ax_l_range"]
            if not bilateral:
                cols.append(f"{prefix}_ax_r_range")
            rows.append(cols)
        if self._notes_id:
            rows.append([self._notes_id])
        return rows

    def collect(self) -> dict:
        data: dict = {}
        for rid in self._row_ids:
            try:
                data.update(self.query_one(f"#romrow_{rid}", ROMRow).collect())
            except Exception:
                pass
        if self._notes_id:
            try:
                data[self._notes_id] = self.query_one(f"#{self._notes_id}", TextArea).text
            except Exception:
                data[self._notes_id] = ""
        return data

    def load(self, data: dict) -> None:
        for rid in self._row_ids:
            try:
                self.query_one(f"#romrow_{rid}", ROMRow).load(data)
            except Exception:
                pass
        if self._notes_id:
            try:
                self.query_one(f"#{self._notes_id}", TextArea).text = data.get(self._notes_id, "")
            except Exception:
                pass


# ── Grade group widget (bilateral / unilateral RadioGroup rows) ───────────────

class GradeGroupWidget(Static):
    """One group of RadioGroup rows — bilateral (L/R) or unilateral (single)."""

    DEFAULT_CSS = """
    GradeGroupWidget { width: 100%; height: auto; }
    GradeGroupWidget .hdr  { layout: horizontal; height: 1; width: 100%; color: $text-muted; }
    GradeGroupWidget .hlbl { width: 18; }
    GradeGroupWidget .hcol { width: 24; text-align: center; }
    GradeGroupWidget .hgap { width: 2; }
    GradeGroupWidget .row  { layout: horizontal; height: 3; width: 100%; margin-bottom: 0; }
    GradeGroupWidget .rlbl { width: 18; height: 3; content-align: left middle; }
    GradeGroupWidget .rgap { width: 2; height: 3; }
    GradeGroupWidget Label { height: auto; margin-top: 0; }
    """

    def __init__(self, group_def: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._group = group_def
        self._bilateral = (group_def.get("type", "bilateral") == "bilateral")
        self._gang = _build_gang(group_def.get("options", []))
        self._rows: list[dict] = group_def.get("rows", [])
        self._grid: list[list[str]] = []
        self._grid_pos: dict[str, tuple[int, int]] = {}

    def _rg_id(self, row_id: str, side: str = "") -> str:
        return f"{row_id}_{side}" if side else row_id

    def compose(self) -> ComposeResult:
        label = self._group.get("label", "")
        yield Label(label, classes="subsection_header")
        if self._bilateral:
            with Horizontal(classes="hdr"):
                yield Static("",      classes="hlbl")
                yield Static("Left",  classes="hcol")
                yield Static("",      classes="hgap")
                yield Static("Right", classes="hcol")
        for row in self._rows:
            with Horizontal(classes="row"):
                yield Static(row["label"], classes="rlbl")
                if self._bilateral:
                    yield RadioGroup(self._gang, id=self._rg_id(row["id"], "l"))
                    yield Static("", classes="rgap")
                    yield RadioGroup(self._gang, id=self._rg_id(row["id"], "r"))
                else:
                    yield RadioGroup(self._gang, id=self._rg_id(row["id"]))

    def on_mount(self) -> None:
        for row_idx, row in enumerate(self._rows):
            if self._bilateral:
                ids = [self._rg_id(row["id"], "l"), self._rg_id(row["id"], "r")]
            else:
                ids = [self._rg_id(row["id"])]
            self._grid.append(ids)
            for col_idx, rg_id in enumerate(ids):
                self._grid_pos[rg_id] = (row_idx, col_idx)

    def on_key(self, event) -> None:
        focused = self.app.focused
        if not isinstance(focused, RadioGroup):
            return
        fid = focused.id or ""
        if fid not in self._grid_pos:
            return
        if event.key not in ("up", "down"):
            return
        row, col = self._grid_pos[fid]
        target = row - 1 if event.key == "up" else row + 1
        if 0 <= target < len(self._grid):
            try:
                self.query_one(f"#{self._grid[target][col]}", RadioGroup).focus()
                event.stop()
            except Exception:
                pass

    def collect(self) -> dict:
        data: dict = {}
        for rg in self.query(RadioGroup):
            data[rg.id] = rg.value
        return data

    def load(self, data: dict) -> None:
        for rg in self.query(RadioGroup):
            rg.set_value(data.get(rg.id))


# ── Trunk strength widget (numeric GridInput rows) ────────────────────────────

class TrunkStrengthWidget(Static):
    """Numeric GridInput rows for trunk strength (reps, raises, etc.)."""

    DEFAULT_CSS = """
    TrunkStrengthWidget { width: 100%; height: auto; }
    TrunkStrengthWidget .row { layout: horizontal; height: 3; width: 100%; margin-bottom: 0; }
    TrunkStrengthWidget .lbl { width: 18; height: 3; content-align: left middle; }
    TrunkStrengthWidget .inp { width: 1fr; height: 3; padding: 0 1; }
    TrunkStrengthWidget Label { height: auto; margin-top: 0; }
    """

    def __init__(self, group_def: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: list[dict] = group_def.get("rows", [])
        label = group_def.get("label", "Trunk Strength")
        self._label = label

    def compose(self) -> ComposeResult:
        yield Label(self._label, classes="subsection_header")
        for row in self._rows:
            with Horizontal(classes="row"):
                yield Static(row["label"], classes="lbl")
                yield GridInput(
                    placeholder=row.get("placeholder", ""),
                    id=row["id"],
                    classes="inp",
                )

    def collect(self) -> dict:
        data: dict = {}
        for row in self._rows:
            try:
                data[row["id"]] = self.query_one(f"#{row['id']}", GridInput).value.strip()
            except Exception:
                data[row["id"]] = ""
        return data

    def load(self, data: dict) -> None:
        for row in self._rows:
            try:
                self.query_one(f"#{row['id']}", GridInput).value = data.get(row["id"], "")
            except Exception:
                pass


# ── Special tests widget ──────────────────────────────────────────────────────

class SpecialTestsWidget(Static):
    """RadioGroup rows for special tests from YAML special_tests section."""

    DEFAULT_CSS = """
    SpecialTestsWidget { width: 100%; height: auto; }
    SpecialTestsWidget .row  { layout: horizontal; height: 3; width: 100%; margin-bottom: 0; }
    SpecialTestsWidget .rlbl { width: 18; height: 3; content-align: left middle; }
    SpecialTestsWidget TextArea { height: auto; min-height: 2; padding: 0 1; }
    SpecialTestsWidget Label    { height: auto; margin-top: 0; }
    """

    def __init__(self, section_def: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: list[dict] = section_def.get("rows", [])
        self._notes_id: str | None = section_def.get("notes_id")
        self._grid: list[str] = []
        self._grid_pos: dict[str, int] = {}

    def _rg_id(self, row_id: str) -> str:
        return f"st_{row_id}"

    def compose(self) -> ComposeResult:
        for row in self._rows:
            gang = _build_gang(row.get("options", ["Negative", "Positive"]))
            with Horizontal(classes="row"):
                yield Static(row["label"], classes="rlbl")
                yield RadioGroup(gang, id=self._rg_id(row["id"]))
        if self._notes_id:
            yield Label("Notes:")
            yield GridTextArea(id=self._notes_id, language="plain")

    def on_mount(self) -> None:
        for idx, row in enumerate(self._rows):
            rg_id = self._rg_id(row["id"])
            self._grid.append(rg_id)
            self._grid_pos[rg_id] = idx
        if self._notes_id:
            self._grid_pos[self._notes_id] = len(self._grid)
            self._grid.append(self._notes_id)

    def _focus_by_index(self, direction: str, fid: str) -> bool:
        if fid not in self._grid_pos:
            return False
        idx = self._grid_pos[fid]
        target = idx - 1 if direction == "up" else idx + 1
        if 0 <= target < len(self._grid):
            try:
                self.query_one(f"#{self._grid[target]}").focus()
                return True
            except Exception:
                return False
        return False

    def on_key(self, event) -> None:
        focused = self.app.focused
        if not isinstance(focused, RadioGroup):
            return
        if event.key not in ("up", "down"):
            return
        fid = focused.id or ""
        if fid in self._grid_pos and self._focus_by_index(event.key, fid):
            event.stop()

    @on(GridInput.Navigate)
    def _on_grid_navigate(self, event: GridInput.Navigate) -> None:
        if event.direction not in ("up", "down"):
            return
        focused = self.app.focused
        fid = focused.id if focused else ""
        if fid in self._grid_pos:
            self._focus_by_index(event.direction, fid)
        event.stop()

    def collect(self) -> dict:
        data: dict = {}
        for rg in self.query(RadioGroup):
            data[rg.id] = rg.value
        if self._notes_id:
            try:
                data[self._notes_id] = self.query_one(f"#{self._notes_id}", TextArea).text
            except Exception:
                data[self._notes_id] = ""
        return data

    def load(self, data: dict) -> None:
        for rg in self.query(RadioGroup):
            rg.set_value(data.get(rg.id))
        if self._notes_id:
            try:
                self.query_one(f"#{self._notes_id}", TextArea).text = data.get(self._notes_id, "")
            except Exception:
                pass


# ── Bilateral grid special tests widget ──────────────────────────────────────

class BilateralGridSpecialTestsWidget(Static):
    """Two-column bilateral special tests: pairs of tests per row, L/R CycleButtons.

    YAML format (special_tests with groups key):
        groups:
          - label: "Impingement"
            cluster_id: sh_impingement   # reserved for Phase 3 DDx — not used at runtime
            rows:
              - {id: hawkins, label: "Hawkins"}
              - {id: neer,    label: "Neer"}

    CycleButton outer IDs: st_{stem}_l / st_{stem}_r  (data keys, KB-resolver compatible).
    Inner button IDs: st_{stem}_l_btn / st_{stem}_r_btn (handled by focus resolver patch).
    Cycle states: blank (·) → Yes (red/error) → No (green/success).
    """

    DEFAULT_CSS = """
    BilateralGridSpecialTestsWidget { width: 100%; height: auto; }
    BilateralGridSpecialTestsWidget CycleButton        { width: 6; height: 3; }
    BilateralGridSpecialTestsWidget CycleButton Button { width: 100%; height: 3; min-width: 0; }
    BilateralGridSpecialTestsWidget .bg_grp_hdr {
        height: auto; margin-top: 1; text-style: bold;
    }
    BilateralGridSpecialTestsWidget .bg_colhdr {
        layout: horizontal; height: 1; width: 100%; color: $text-muted;
    }
    BilateralGridSpecialTestsWidget .bg_hentry { layout: horizontal; width: 1fr; height: 1; }
    BilateralGridSpecialTestsWidget .bg_hspc   { width: 12; }
    BilateralGridSpecialTestsWidget .bg_hcol   { width: 6; text-align: center; }
    BilateralGridSpecialTestsWidget .bg_hgap   { width: 1; }
    BilateralGridSpecialTestsWidget .bg_row    {
        layout: horizontal; height: 3; width: 100%; margin-bottom: 0;
    }
    BilateralGridSpecialTestsWidget .bg_entry  { layout: horizontal; width: 1fr; height: 3; }
    BilateralGridSpecialTestsWidget .bg_lbl    { width: 12; height: 3; content-align: left middle; }
    BilateralGridSpecialTestsWidget .bg_gap    { width: 1; height: 3; }
    BilateralGridSpecialTestsWidget TextArea   { height: auto; min-height: 2; padding: 0 1; }
    BilateralGridSpecialTestsWidget Label      { height: auto; margin-top: 0; }
    """

    _STATES = [("Yes", "error"), ("No", "success")]

    def __init__(self, section_def: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._groups: list[dict] = section_def.get("groups", [])
        self._notes_id: str | None = section_def.get("notes_id")
        self._grid: list[str] = []       # inner button IDs in tab order
        self._grid_pos: dict[str, int] = {}

    def compose(self) -> ComposeResult:
        for group in self._groups:
            yield Label(group["label"], classes="bg_grp_hdr")
            with Horizontal(classes="bg_colhdr"):
                for _ in range(2):
                    with Horizontal(classes="bg_hentry"):
                        yield Static("",  classes="bg_hspc")
                        yield Static("L", classes="bg_hcol")
                        yield Static("",  classes="bg_hgap")
                        yield Static("R", classes="bg_hcol")
            rows = group.get("rows", [])
            for i in range(0, len(rows), 2):
                left = rows[i]
                right = rows[i + 1] if i + 1 < len(rows) else None
                with Horizontal(classes="bg_row"):
                    with Horizontal(classes="bg_entry"):
                        yield Static(left["label"], classes="bg_lbl")
                        yield CycleButton(self._STATES, id=f"st_{left['id']}_l")
                        yield Static("", classes="bg_gap")
                        yield CycleButton(self._STATES, id=f"st_{left['id']}_r")
                    with Horizontal(classes="bg_entry"):
                        if right:
                            yield Static(right["label"], classes="bg_lbl")
                            yield CycleButton(self._STATES, id=f"st_{right['id']}_l")
                            yield Static("", classes="bg_gap")
                            yield CycleButton(self._STATES, id=f"st_{right['id']}_r")
            group_notes_id = group.get("notes_id")
            if group_notes_id:
                yield Label(group.get("notes_label", "Notes:"))
                yield GridTextArea(id=group_notes_id, language="plain")
        if self._notes_id:
            yield Label("Notes:")
            yield GridTextArea(id=self._notes_id, language="plain")

    def on_mount(self) -> None:
        for group in self._groups:
            rows = group.get("rows", [])
            for i in range(0, len(rows), 2):
                left = rows[i]
                right = rows[i + 1] if i + 1 < len(rows) else None
                btn_ids = [f"st_{left['id']}_l_btn", f"st_{left['id']}_r_btn"]
                if right:
                    btn_ids += [f"st_{right['id']}_l_btn", f"st_{right['id']}_r_btn"]
                for btn_id in btn_ids:
                    self._grid_pos[btn_id] = len(self._grid)
                    self._grid.append(btn_id)
            group_notes_id = group.get("notes_id")
            if group_notes_id:
                self._grid_pos[group_notes_id] = len(self._grid)
                self._grid.append(group_notes_id)
        if self._notes_id:
            self._grid_pos[self._notes_id] = len(self._grid)
            self._grid.append(self._notes_id)

    def _focus_by_index(self, direction: str, fid: str) -> bool:
        if fid not in self._grid_pos:
            return False
        idx = self._grid_pos[fid]
        target = idx - 1 if direction == "up" else idx + 1
        if 0 <= target < len(self._grid):
            try:
                self.query_one(f"#{self._grid[target]}").focus()
                return True
            except Exception:
                return False
        return False

    def on_key(self, event) -> None:
        focused = self.app.focused
        fid = focused.id if focused else ""
        if not fid or fid not in self._grid_pos:
            return
        if event.key not in ("up", "down"):
            return
        if self._focus_by_index(event.key, fid):
            event.stop()

    @on(GridInput.Navigate)
    def _on_grid_navigate(self, event: GridInput.Navigate) -> None:
        if event.direction not in ("up", "down"):
            return
        focused = self.app.focused
        fid = focused.id if focused else ""
        if fid in self._grid_pos:
            self._focus_by_index(event.direction, fid)
        event.stop()

    def _all_notes_ids(self) -> list[str]:
        ids = [g["notes_id"] for g in self._groups if g.get("notes_id")]
        if self._notes_id:
            ids.append(self._notes_id)
        return ids

    def collect(self) -> dict:
        data: dict = {}
        for cb in self.query(CycleButton):
            data[cb.id] = cb.value
        for notes_id in self._all_notes_ids():
            try:
                data[notes_id] = self.query_one(f"#{notes_id}", TextArea).text
            except Exception:
                data[notes_id] = ""
        return data

    def load(self, data: dict) -> None:
        for cb in self.query(CycleButton):
            cb.set_value(data.get(cb.id))
        for notes_id in self._all_notes_ids():
            try:
                self.query_one(f"#{notes_id}", TextArea).text = data.get(notes_id, "")
            except Exception:
                pass


# ── RegionContainer ───────────────────────────────────────────────────────────

class RegionContainer(Static):
    """Collapsible block for one region's content within one objective tab.

    Renders YAML-driven flat fields (ROMGroupWidget, GradeGroupWidget, etc.)
    and optionally mounts a Python extras widget (LumbarPassiveTables, etc.)
    registered in REGION_EXTRAS.
    """

    class FieldChanged(Message):
        pass

    DEFAULT_CSS = """
    RegionContainer {
        width: 100%;
        height: auto;
        border: solid $border;
        margin-bottom: 1;
    }
    RegionContainer .region_header {
        background: $panel-darken-1;
        color: $text;
        text-style: bold;
        height: 2;
        padding: 0 1;
        content-align: left middle;
        width: 100%;
    }
    RegionContainer .region_body {
        width: 100%;
        height: auto;
        padding: 0 1 1 1;
    }
    """

    def __init__(self, region_id: str, section_key: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._region_id = region_id
        self._section_key = section_key
        self._yaml = _load_yaml(region_id)
        self._extras_class: Type | None = REGION_EXTRAS.get((region_id, section_key))
        self._loading = False
        self._notes_ids: list[str] = []
        self._nav_grid: list[list[str]] = []
        self._nav_grid_pos: dict[str, tuple[int, int]] = {}

    def compose(self) -> ComposeResult:
        label = self._yaml.get("label", self._region_id.upper())
        yield Static(f"▼ {label}", classes="region_header")
        with Vertical(classes="region_body"):
            yield from self._compose_yaml_widgets()
            if self._extras_class is not None:
                yield self._extras_class(
                    id=f"extras_{self._region_id}_{self._section_key}"
                )

    def _compose_yaml_widgets(self) -> ComposeResult:
        yaml_key = _YAML_KEY.get(self._section_key, "")
        if not yaml_key:
            return
        section_def = self._yaml.get(yaml_key, {})
        if not section_def:
            return

        if self._section_key == "active":
            for group in section_def.get("groups", []):
                notes_id = group.get("notes_id", "")
                yield ROMGroupWidget(group, id=f"romgrp_{self._region_id}_{notes_id}")

        elif self._section_key == "muscle":
            for group in section_def.get("groups", []):
                gtype = group.get("type", "bilateral")
                slug = group["label"].lower().replace(" ", "_")
                if gtype in ("bilateral", "unilateral"):
                    yield GradeGroupWidget(group, id=f"grade_{self._region_id}_{slug}")
                elif gtype == "numeric":
                    yield TrunkStrengthWidget(group, id=f"trunk_{self._region_id}_{slug}")
            notes_id = section_def.get("notes_id")
            if notes_id:
                self._notes_ids.append(notes_id)
                yield Label("Notes:")
                yield TextArea(id=notes_id, language="plain")

        elif self._section_key == "special":
            if "groups" in section_def:
                yield BilateralGridSpecialTestsWidget(
                    section_def, id=f"sptests_{self._region_id}"
                )
            else:
                yield SpecialTestsWidget(
                    section_def, id=f"sptests_{self._region_id}"
                )

    # ── Cross-widget arrow-key nav (Active Movement only for now) ──────────────

    def on_mount(self) -> None:
        if self._section_key != "active":
            return
        for widget in self.query(ROMGroupWidget):
            for row in widget.grid_rows():
                row_idx = len(self._nav_grid)
                self._nav_grid.append(row)
                for col_idx, wid in enumerate(row):
                    self._nav_grid_pos[wid] = (row_idx, col_idx)

    def _nav(self, fid: str, direction: str) -> bool:
        if fid not in self._nav_grid_pos:
            return False
        row, col = self._nav_grid_pos[fid]
        grid = self._nav_grid
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
        if target_id is None:
            return False
        try:
            self.query_one(f"#{target_id}").focus()
            return True
        except Exception:
            return False

    @on(GridInput.Navigate)
    def _on_grid_navigate(self, event: GridInput.Navigate) -> None:
        if not self._nav_grid_pos:
            return
        focused = self.app.focused
        fid = focused.id if focused else ""
        if fid in self._nav_grid_pos:
            self._nav(fid, event.direction)
            event.stop()

    # ── Event handlers ────────────────────────────────────────────────────────

    @on(RadioGroup.Changed)
    @on(CycleButton.Changed)
    @on(TextArea.Changed)
    @on(GridInput.Changed)
    @on(AnkleTables.Changed)
    @on(CervicalTables.Changed)
    @on(HipTables.Changed)
    @on(KneeTables.Changed)
    @on(LumbarTables.Changed)
    @on(ShoulderTables.Changed)
    def _on_any_field_changed(self) -> None:
        if not self._loading:
            self.post_message(self.FieldChanged())

    # ── collect / load ────────────────────────────────────────────────────────

    def collect(self) -> dict:
        data: dict = {}
        for cls in (ROMGroupWidget, GradeGroupWidget, TrunkStrengthWidget, SpecialTestsWidget, BilateralGridSpecialTestsWidget):
            for w in self.query(cls):
                data.update(w.collect())
        for nid in self._notes_ids:
            try:
                data[nid] = self.query_one(f"#{nid}", TextArea).text
            except Exception:
                data[nid] = ""
        if self._extras_class is not None:
            extras_id = f"#extras_{self._region_id}_{self._section_key}"
            try:
                extras = self.query_one(extras_id, self._extras_class)
                data.update(extras.collect())
            except Exception:
                pass
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            for cls in (ROMGroupWidget, GradeGroupWidget, TrunkStrengthWidget, SpecialTestsWidget, BilateralGridSpecialTestsWidget):
                for w in self.query(cls):
                    w.load(data)
            for nid in self._notes_ids:
                try:
                    self.query_one(f"#{nid}", TextArea).text = data.get(nid, "")
                except Exception:
                    pass
            if self._extras_class is not None:
                extras_id = f"#extras_{self._region_id}_{self._section_key}"
                try:
                    extras = self.query_one(extras_id, self._extras_class)
                    extras.load(data)
                except Exception:
                    pass
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        return bool(self.collect())


# ── RegionTabContent ──────────────────────────────────────────────────────────

class RegionTabContent(Container):
    """Variable objective tab — shows one collapsible RegionContainer per active region."""

    class FieldChanged(Message):
        pass

    DEFAULT_CSS = """
    RegionTabContent {
        width: 100%;
        height: auto;
        padding: 0 1 2 1;
    }
    RegionTabContent .tab_title { text-style: bold; margin-bottom: 1; }
    RegionTabContent .no_region {
        color: $text-muted;
        margin: 2 1;
    }
    """

    def __init__(self, section_key: str, tab_label: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._section_key = section_key
        self._tab_label = tab_label
        self._containers: dict[str, RegionContainer] = {}
        self.session_file = ""
        self._loading = False

    def compose(self) -> ComposeResult:
        yield Label(self._tab_label, classes="tab_title")
        yield Static("No region selected. Enable a region from the topbar.",
                     id="no_region_msg", classes="no_region")

    def _update_empty_msg(self) -> None:
        try:
            msg = self.query_one("#no_region_msg", Static)
            msg.display = len(self._containers) == 0
        except Exception:
            pass

    def mount_region(self, region_id: str) -> None:
        if region_id in self._containers:
            return
        container = RegionContainer(
            region_id,
            self._section_key,
            id=f"rc_{region_id}_{self._section_key}",
        )
        self._containers[region_id] = container
        self.mount(container)
        self._update_empty_msg()

    def unmount_region(self, region_id: str) -> None:
        container = self._containers.pop(region_id, None)
        if container:
            container.remove()
        self._update_empty_msg()

    def get_container(self, region_id: str) -> RegionContainer | None:
        return self._containers.get(region_id)

    @on(RegionContainer.FieldChanged)
    def _on_region_changed(self) -> None:
        if not self._loading:
            self.post_message(self.FieldChanged())

    def collect(self) -> dict:
        return {rid: c.collect() for rid, c in self._containers.items()}

    def load(self, data: dict) -> None:
        for rid, container in self._containers.items():
            container.load(data.get(rid, {}))

    def is_complete(self) -> bool:
        return any(c.is_complete() for c in self._containers.values())


# ── Region extras registry ────────────────────────────────────────────────────
# Add entries here when new region Python table widgets are created.
# Key: (region_id, section_key)  Value: widget class

REGION_EXTRAS: dict[tuple[str, str], Type] = {
    ("ankle",    "passive"): AnklePassiveTables,
    ("ankle",    "muscle"):  AnkleMuscleTables,
    ("cervical", "passive"): CervicalPassiveTables,
    ("cervical", "muscle"):  CervicalMuscleTables,
    ("hip",      "passive"): HipPassiveTables,
    ("hip",      "muscle"):  HipMuscleTables,
    ("knee",     "passive"): KneePassiveTables,
    ("knee",     "muscle"):  KneeMuscleTables,
    ("lumbar",   "passive"): LumbarPassiveTables,
    ("lumbar",   "muscle"):  LumbarMuscleTables,
    ("shoulder", "passive"): ShoulderPassiveTables,
    ("shoulder", "muscle"):  ShoulderMuscleTables,
}
