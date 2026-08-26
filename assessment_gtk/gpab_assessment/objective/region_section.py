"""YAML-driven region block renderer — GTK4 port of
pab_assessment.objective.sections.region_section.

RegionContainer  — collapsible per-region block for one objective tab.
                   Renders YAML-defined flat fields + optional Python extras.
RegionTabContent — the full tab: one RegionContainer per active region.

Supported YAML field group types (see sections/yaml/lumbar.yaml, the same
YAML files the TUI reads — unmodified, read directly from the read-only
../assessment clone):
  active_movement  -> ROMGroupWidget  (rom_widgets.ROMRow tables)
  muscle_testing   -> GradeGroupWidget (bilateral/unilateral RadioGroup rows)
                    + TrunkStrengthWidget (numeric TouchEntry rows)
  special_tests    -> SpecialTestsWidget (RadioGroup rows) or
                       BilateralGridSpecialTestsWidget (paired CycleField rows,
                       used by regions whose YAML special_tests has a "groups"
                       key instead of a flat "rows" list, e.g. shoulder)

Python extras (OP/PAIVM, hip/SIJ, etc. — whatever can't be expressed as
flat YAML) are registered per (region_id, section_key) in REGION_EXTRAS at
the bottom of this file, exactly like the TUI's registry. Only lumbar is
populated so far (Phase 2's first region, per CONVERSION_PLAN.md); the
other five regions' *_tables.py equivalents are follow-up work.

Field ids and collect()/load() keys match the TUI exactly so a session
this app writes round-trips byte-for-byte with pab_assessment.storage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Type

import yaml
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject  # noqa: E402

from ..widgets import RadioGroup, CycleField, AutoTextView, TouchEntry, make_subsection_header
from .grid_widgets import bilateral_header_row
from .grid_drag_select import GridDragSelect
from .rom_widgets import ROMRow
from .sections.ankle_tables import AnkleMuscleTables, AnklePassiveTables
from .sections.cervical_tables import CervicalMuscleTables, CervicalPassiveTables
from .sections.hip_tables import HipMuscleTables, HipPassiveTables
from .sections.knee_tables import KneeMuscleTables, KneePassiveTables
from .sections.lumbar_tables import LumbarMuscleTables, LumbarPassiveTables, LumbarSpecialTables
from .sections.shoulder_tables import ShoulderMuscleTables, ShoulderPassiveTables

# Reads the same YAML the TUI uses, from the read-only reference clone —
# never write to this path.
_YAML_DIR = Path(__file__).resolve().parents[3] / "assessment" / "pab_assessment" / "objective" / "sections" / "yaml"

# Maps section_key ("active", "muscle", "special") -> yaml top-level key.
# ("passive" has no YAML content anywhere — every region's passive tab is
# 100% Python extras, same as the TUI.)
_YAML_KEY: dict[str, str] = {
    "active": "active_movement",
    "muscle": "muscle_testing",
    "special": "special_tests",
}


def _load_yaml(region_id: str) -> dict:
    path = _YAML_DIR / f"{region_id}.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _infer_variant(idx: int, total: int) -> str:
    if idx == 0:
        return "success"
    if total == 2 or idx == total - 1:
        return "error"
    return "warning"


def _build_gang(options: list[str]) -> list[tuple[str, str]]:
    total = len(options)
    return [(label, _infer_variant(i, total)) for i, label in enumerate(options)]


# YAML group label -> grid_overview anchor_id, for the two group loops below
# (active_movement / muscle_testing) whose subsection labels come straight
# from YAML rather than a fixed string. Only labels that actually appear as
# a heading in OBJ_GRID_DATA's "03_passive"/"02_active"/"06_muscle" rows are
# listed — every other region-specific group (Ankle ROM, Cervical Endurance,
# etc.) has no corresponding grid heading and falls back to plain
# _show_section() navigation (see app.py's _open_grid_overview), same as
# before this anchor-tagging was added. "Thoracic ROM" legitimately appears
# in three regions' YAML (lumbar/cervical/shoulder) — find_by_anchor_id is
# first-match-in-tree-order, which is fine here.
_ACTIVE_GROUP_ANCHOR: dict[str, str] = {
    "Lumbar ROM": "am_lumbar",
    "Thoracic ROM": "am_thoracic",
}
_MUSCLE_GROUP_ANCHOR: dict[str, str] = {
    "Muscle Length": "ml_length",
    "Muscle Activation": "ml_activation",
    "Trunk Strength": "ml_strength_trunk",
}


# ---------------------------------------------------------------------------
# ROM group widget
# ---------------------------------------------------------------------------

class ROMGroupWidget(Gtk.Box):
    """One named group of ROM rows (Ax L/R) from YAML active_movement.groups."""

    def __init__(self, group_def: dict) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._group = group_def
        self._notes_id: str | None = group_def.get("notes_id")
        self._rows: list[ROMRow] = []

        _label = group_def.get("label", "")
        self.append(make_subsection_header(_label, _ACTIVE_GROUP_ANCHOR.get(_label)))
        self.append(bilateral_header_row())
        for row in group_def.get("rows", []):
            rr = ROMRow(row["label"], row["id"], bilateral=row.get("bilateral", False))
            self._rows.append(rr)
            self.append(rr)

        self.notes: AutoTextView | None = None
        if self._notes_id:
            self.append(Gtk.Label(label="Comment:", halign=Gtk.Align.START))
            self.notes = AutoTextView(self._notes_id, min_lines=2)
            self.append(self.notes)

    def grid_rows(self) -> list[list[str]]:
        """Row field-id lists for RegionContainer's cross-group nav grid,
        in DOM order — mirrors the TUI's ROMGroupWidget.grid_rows()."""
        rows = [rr.field_ids() for rr in self._rows]
        if self.notes is not None:
            rows.append([self._notes_id])
        return rows

    def entries_by_id(self) -> dict:
        widgets = {}
        for rr in self._rows:
            widgets.update(rr.entries)
        if self.notes is not None:
            widgets[self._notes_id] = self.notes
        return widgets

    def collect(self) -> dict:
        data: dict = {}
        for rr in self._rows:
            data.update(rr.collect())
        if self.notes is not None:
            data[self._notes_id] = self.notes.text
        return data

    def load(self, data: dict) -> None:
        for rr in self._rows:
            rr.load(data)
        if self.notes is not None:
            self.notes.text = data.get(self._notes_id, "")


# ---------------------------------------------------------------------------
# Grade group widget (bilateral / unilateral RadioGroup rows)
# ---------------------------------------------------------------------------

class GradeGroupWidget(Gtk.Box, GridDragSelect):
    """One group of RadioGroup rows - bilateral (L/R) or unilateral (single).

    Owns its own up/down arrow-key nav internally (the TUI never chains
    this into a cross-widget grid either — only the "active" ROM tab gets
    that treatment).

    Drag-gesture bulk-select (grid_drag_select.py) mixed in 2026-08-24,
    porting the mechanism built+confirmed on Neurological the day before —
    this is the ONE shared, YAML-driven widget every region's Muscle Testing
    tab uses for its RadioGroup grade grids (Muscle Length/Activation), so
    fixing it here covers all six regions (lumbar/cervical/shoulder/hip/
    knee/ankle) in one change; the per-region "Muscle" extras
    (StrengthGridTable-based, or Lumbar's bespoke hip-strength+SIJ box) use
    numeric entries/checkboxes, not RadioGroup, so there was nothing to port
    there. Left/Right columns drag independently, same as Neurological;
    unilateral groups get one column.
    """

    def __init__(self, group_def: dict) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._bilateral = group_def.get("type", "bilateral") == "bilateral"
        gang = _build_gang(group_def.get("options", []))
        self._rows: list[dict] = group_def.get("rows", [])
        self._groups: dict[str, RadioGroup] = {}
        self._grid: list[list[str]] = []
        self._grid_pos: dict[str, tuple[int, int]] = {}
        self._init_drag_select()

        _label = group_def.get("label", "")
        self.append(make_subsection_header(_label, _MUSCLE_GROUP_ANCHOR.get(_label)))
        if self._bilateral:
            self.append(bilateral_header_row())
        drag_columns: list[list[RadioGroup]] = []
        for row in self._rows:
            hrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            hrow.add_css_class("grid-row")
            lbl = Gtk.Label(label=row["label"])
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(160, -1)
            hrow.append(lbl)
            if self._bilateral:
                ids = [f"{row['id']}_l", f"{row['id']}_r"]
            else:
                ids = [row["id"]]
            row_ids = []
            for col_idx, fid in enumerate(ids):
                rg = RadioGroup(gang, fid)
                rg.set_hexpand(True)
                rg.connect("navigate", self._on_navigate)
                self._groups[fid] = rg
                hrow.append(rg)
                row_ids.append(fid)
                if col_idx >= len(drag_columns):
                    drag_columns.append([])
                drag_columns[col_idx].append(rg)
            row_idx = len(self._grid)
            self._grid.append(row_ids)
            for col_idx, fid in enumerate(row_ids):
                self._grid_pos[fid] = (row_idx, col_idx)
            self.append(hrow)
        for column in drag_columns:
            self._register_drag_column(column)

    def connect_changed(self, callback) -> None:
        for rg in self._groups.values():
            rg.connect("changed", lambda *_a: callback())

    def _on_navigate(self, widget: RadioGroup, direction: str) -> None:
        if direction not in ("up", "down"):
            return
        fid = widget.field_id
        if fid not in self._grid_pos:
            return
        row, col = self._grid_pos[fid]
        target = row - 1 if direction == "up" else row + 1
        if 0 <= target < len(self._grid):
            self._groups[self._grid[target][col]].grab_focus()

    def collect(self) -> dict:
        return {fid: rg.value for fid, rg in self._groups.items()}

    def load(self, data: dict) -> None:
        for fid, rg in self._groups.items():
            rg.set_value(data.get(fid))


# ---------------------------------------------------------------------------
# Trunk strength widget (numeric TouchEntry rows)
# ---------------------------------------------------------------------------

class TrunkStrengthWidget(Gtk.Box):
    """Numeric TouchEntry rows for trunk strength (reps, raises, etc.)."""

    def __init__(self, group_def: dict) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._entries: dict[str, TouchEntry] = {}

        _label = group_def.get("label", "Trunk Strength")
        self.append(make_subsection_header(_label, _MUSCLE_GROUP_ANCHOR.get(_label)))
        for row in group_def.get("rows", []):
            hrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            hrow.add_css_class("grid-row")
            lbl = Gtk.Label(label=row["label"])
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(160, -1)
            hrow.append(lbl)
            entry = TouchEntry(row["id"], placeholder=row.get("placeholder", ""))
            entry.set_hexpand(True)
            self._entries[row["id"]] = entry
            hrow.append(entry)
            self.append(hrow)

    def connect_changed(self, callback) -> None:
        for e in self._entries.values():
            e.connect("changed", lambda *_a: callback())

    def collect(self) -> dict:
        return {fid: e.text.strip() for fid, e in self._entries.items()}

    def load(self, data: dict) -> None:
        for fid, e in self._entries.items():
            e.text = data.get(fid, "")


# ---------------------------------------------------------------------------
# Special tests widget (flat RadioGroup rows)
# ---------------------------------------------------------------------------

class SpecialTestsWidget(Gtk.Box):
    """RadioGroup rows for special tests from YAML special_tests.rows (flat
    form — no "groups" key). Row field id is st_{row_id}."""

    def __init__(self, section_def: dict) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._notes_id: str | None = section_def.get("notes_id")
        self._groups: dict[str, RadioGroup] = {}
        self._grid: list[str] = []
        self._grid_pos: dict[str, int] = {}

        rows = section_def.get("rows")
        groups = section_def.get("groups")
        if groups:
            for grp in groups:
                self.append(make_subsection_header(grp.get("label", "")))
                self._append_rows(grp.get("rows", []))
        elif rows:
            self._append_rows(rows)

        if self._notes_id:
            self.append(Gtk.Label(label="Notes:", halign=Gtk.Align.START))
            self.notes = AutoTextView(self._notes_id, min_lines=2)
            self._grid_pos[self._notes_id] = len(self._grid)
            self._grid.append(self._notes_id)
            self.append(self.notes)
        else:
            self.notes = None

    def _append_rows(self, rows: list[dict]) -> None:
        for row in rows:
            gang = _build_gang(row.get("options", ["Negative", "Positive"]))
            fid = f"st_{row['id']}"
            hrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            hrow.add_css_class("grid-row")
            lbl = Gtk.Label(label=row["label"])
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(160, -1)
            hrow.append(lbl)
            rg = RadioGroup(gang, fid)
            rg.set_hexpand(True)
            rg.connect("navigate", self._on_navigate)
            self._groups[fid] = rg
            hrow.append(rg)
            self._grid_pos[fid] = len(self._grid)
            self._grid.append(fid)
            self.append(hrow)

    def connect_changed(self, callback) -> None:
        for rg in self._groups.values():
            rg.connect("changed", lambda *_a: callback())
        if self.notes is not None:
            self.notes.textview.get_buffer().connect("changed", lambda *_a: callback())

    def _widget_for(self, fid: str):
        if fid == self._notes_id:
            return self.notes
        return self._groups.get(fid)

    def _on_navigate(self, widget: RadioGroup, direction: str) -> None:
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

    def collect(self) -> dict:
        data = {fid: rg.value for fid, rg in self._groups.items()}
        if self._notes_id and self.notes is not None:
            data[self._notes_id] = self.notes.text
        return data

    def load(self, data: dict) -> None:
        for fid, rg in self._groups.items():
            rg.set_value(data.get(fid))
        if self._notes_id and self.notes is not None:
            self.notes.text = data.get(self._notes_id, "")


# ---------------------------------------------------------------------------
# Bilateral grid special tests widget (paired CycleField rows)
# ---------------------------------------------------------------------------

class BilateralGridSpecialTestsWidget(Gtk.Box):
    """Two-column bilateral special tests: pairs of tests per row, L/R
    CycleField (blank -> Yes/error -> No/success). YAML shape (special_tests
    with a "groups" key) — used by regions like shoulder, not lumbar."""

    _STATES = [("Yes", "error"), ("No", "success")]

    def __init__(self, section_def: dict) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._notes_id: str | None = section_def.get("notes_id")
        self._cycles: dict[str, CycleField] = {}
        self._group_notes: dict[str, AutoTextView] = {}
        self._grid: list[str] = []
        self._grid_pos: dict[str, int] = {}

        for group in section_def.get("groups", []):
            self.append(make_subsection_header(group.get("label", "")))
            rows = group.get("rows", [])
            for i in range(0, len(rows), 2):
                pair = rows[i:i + 2]
                hrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
                hrow.add_css_class("grid-row")
                for row in pair:
                    entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                    entry_box.set_hexpand(True)
                    lbl = Gtk.Label(label=row["label"])
                    lbl.set_halign(Gtk.Align.START)
                    lbl.set_size_request(110, -1)
                    entry_box.append(lbl)
                    for side in ("l", "r"):
                        fid = f"st_{row['id']}_{side}"
                        cf = CycleField("", fid, options=self._STATES)
                        cf.connect("navigate", self._on_navigate)
                        self._cycles[fid] = cf
                        self._grid_pos[fid] = len(self._grid)
                        self._grid.append(fid)
                        entry_box.append(cf)
                    hrow.append(entry_box)
                self.append(hrow)
            group_notes_id = group.get("notes_id")
            if group_notes_id:
                self.append(Gtk.Label(label=group.get("notes_label", "Notes:"), halign=Gtk.Align.START))
                ta = AutoTextView(group_notes_id, min_lines=2)
                self._group_notes[group_notes_id] = ta
                self._grid_pos[group_notes_id] = len(self._grid)
                self._grid.append(group_notes_id)
                self.append(ta)

        self.notes: AutoTextView | None = None
        if self._notes_id:
            self.append(Gtk.Label(label="Notes:", halign=Gtk.Align.START))
            self.notes = AutoTextView(self._notes_id, min_lines=2)
            self._grid_pos[self._notes_id] = len(self._grid)
            self._grid.append(self._notes_id)
            self.append(self.notes)

    def _all_notes_ids(self) -> list[str]:
        ids = list(self._group_notes.keys())
        if self._notes_id:
            ids.append(self._notes_id)
        return ids

    def connect_changed(self, callback) -> None:
        for cf in self._cycles.values():
            cf.connect("changed", lambda *_a: callback())
        for ta in self._group_notes.values():
            ta.textview.get_buffer().connect("changed", lambda *_a: callback())
        if self.notes is not None:
            self.notes.textview.get_buffer().connect("changed", lambda *_a: callback())

    def _widget_for(self, fid: str):
        if fid in self._cycles:
            return self._cycles[fid]
        if fid in self._group_notes:
            return self._group_notes[fid]
        if fid == self._notes_id:
            return self.notes
        return None

    def _on_navigate(self, widget: CycleField, direction: str) -> None:
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

    def collect(self) -> dict:
        data = {fid: cf.value for fid, cf in self._cycles.items()}
        for nid in self._all_notes_ids():
            w = self._group_notes.get(nid) or self.notes
            data[nid] = w.text if w is not None else ""
        return data

    def load(self, data: dict) -> None:
        for fid, cf in self._cycles.items():
            cf.set_value(data.get(fid))
        for nid in self._all_notes_ids():
            w = self._group_notes.get(nid) or self.notes
            if w is not None:
                w.text = data.get(nid, "")


# ---------------------------------------------------------------------------
# RegionContainer
# ---------------------------------------------------------------------------

# Extras registry — all six regions now have Passive + Muscle extras ported.
REGION_EXTRAS: dict[tuple[str, str], Type] = {
    ("ankle", "passive"): AnklePassiveTables,
    ("ankle", "muscle"): AnkleMuscleTables,
    ("cervical", "passive"): CervicalPassiveTables,
    ("cervical", "muscle"): CervicalMuscleTables,
    ("hip", "passive"): HipPassiveTables,
    ("hip", "muscle"): HipMuscleTables,
    ("knee", "passive"): KneePassiveTables,
    ("knee", "muscle"): KneeMuscleTables,
    ("lumbar", "passive"): LumbarPassiveTables,
    ("lumbar", "muscle"): LumbarMuscleTables,
    ("lumbar", "special"): LumbarSpecialTables,
    ("shoulder", "passive"): ShoulderPassiveTables,
    ("shoulder", "muscle"): ShoulderMuscleTables,
}


class RegionContainer(Gtk.Box):
    """Collapsible block for one region's content within one objective tab."""

    __gsignals__ = {
        "field-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, region_id: str, section_key: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("region-container")
        self._region_id = region_id
        self._section_key = section_key
        self._loading = False
        self._rom_groups: list[ROMGroupWidget] = []
        self._grade_groups: list[GradeGroupWidget] = []
        self._trunk_widgets: list[TrunkStrengthWidget] = []
        self._special_widget = None
        self._notes: dict[str, AutoTextView] = {}
        self._extras = None
        self._nav_grid: list[list[str]] = []
        self._nav_grid_pos: dict[str, tuple[int, int]] = {}

        yaml_data = _load_yaml(region_id)
        label = yaml_data.get("label", region_id.upper())
        header = Gtk.Label(label=f"▼ {label}")
        header.add_css_class("region-header")
        header.set_halign(Gtk.Align.START)
        self.append(header)

        self._compose_yaml_widgets(yaml_data)

        extras_class = REGION_EXTRAS.get((region_id, section_key))
        if extras_class is not None:
            self._extras = extras_class()
            self._extras.connect_changed(self._field_changed)
            self.append(self._extras)

        if section_key == "active":
            self._build_nav_grid()

    def _compose_yaml_widgets(self, yaml_data: dict) -> None:
        yaml_key = _YAML_KEY.get(self._section_key, "")
        if not yaml_key:
            return
        section_def = yaml_data.get(yaml_key, {})
        if not section_def:
            return

        if self._section_key == "active":
            for group in section_def.get("groups", []):
                w = ROMGroupWidget(group)
                self._rom_groups.append(w)
                if w.notes is not None:
                    w.notes.textview.get_buffer().connect("changed", self._field_changed)
                for rr in w._rows:
                    for e in rr.entries.values():
                        e.connect("changed", self._field_changed)
                self.append(w)

        elif self._section_key == "muscle":
            for group in section_def.get("groups", []):
                gtype = group.get("type", "bilateral")
                if gtype in ("bilateral", "unilateral"):
                    gw = GradeGroupWidget(group)
                    gw.connect_changed(self._field_changed)
                    self._grade_groups.append(gw)
                    self.append(gw)
                elif gtype == "numeric":
                    tw = TrunkStrengthWidget(group)
                    tw.connect_changed(self._field_changed)
                    self._trunk_widgets.append(tw)
                    self.append(tw)
            notes_id = section_def.get("notes_id")
            if notes_id:
                self.append(Gtk.Label(label="Notes:", halign=Gtk.Align.START))
                ta = AutoTextView(notes_id, min_lines=2)
                ta.textview.get_buffer().connect("changed", self._field_changed)
                self._notes[notes_id] = ta
                self.append(ta)

        elif self._section_key == "special":
            if "groups" in section_def:
                self._special_widget = BilateralGridSpecialTestsWidget(section_def)
            else:
                self._special_widget = SpecialTestsWidget(section_def)
            self._special_widget.connect_changed(self._field_changed)
            self.append(self._special_widget)

    def _build_nav_grid(self) -> None:
        for w in self._rom_groups:
            for row in w.grid_rows():
                row_idx = len(self._nav_grid)
                self._nav_grid.append(row)
                for col_idx, fid in enumerate(row):
                    self._nav_grid_pos[fid] = (row_idx, col_idx)
        widgets_by_id = {}
        for w in self._rom_groups:
            widgets_by_id.update(w.entries_by_id())
        self._nav_widgets = widgets_by_id
        for w in self._rom_groups:
            for rr in w._rows:
                for e in rr.entries.values():
                    e.connect("navigate", self._on_rom_navigate)
            if w.notes is not None:
                w.notes.connect("navigate", self._on_rom_navigate)

    def _on_rom_navigate(self, widget, direction: str) -> None:
        fid = getattr(widget, "field_id", None)
        if fid is None or fid not in self._nav_grid_pos:
            return
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
        if target_id is not None and target_id in self._nav_widgets:
            self._nav_widgets[target_id].grab_focus()

    def _field_changed(self, *_args) -> None:
        if not self._loading:
            self.emit("field-changed")

    def collect(self) -> dict:
        data: dict = {}
        for w in self._rom_groups:
            data.update(w.collect())
        for w in self._grade_groups:
            data.update(w.collect())
        for w in self._trunk_widgets:
            data.update(w.collect())
        if self._special_widget is not None:
            data.update(self._special_widget.collect())
        for nid, ta in self._notes.items():
            data[nid] = ta.text
        if self._extras is not None:
            data.update(self._extras.collect())
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            for w in self._rom_groups:
                w.load(data)
            for w in self._grade_groups:
                w.load(data)
            for w in self._trunk_widgets:
                w.load(data)
            if self._special_widget is not None:
                self._special_widget.load(data)
            for nid, ta in self._notes.items():
                ta.text = data.get(nid, "")
            if self._extras is not None:
                self._extras.load(data)
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        return bool(self.collect())


# ---------------------------------------------------------------------------
# RegionTabContent
# ---------------------------------------------------------------------------

# Fixed anatomical display order (2026-08-26) — regions used to append in
# whatever order they were toggled active, so e.g. toggling Ankle before
# Cervical put Ankle's block above Cervical's. Requested fix: always show
# mounted regions top-to-bottom in this order regardless of activation
# order, matching how a clinician would expect a chart read top-to-bottom
# (head to foot; Thoracic isn't its own region tab — its content lives
# inside Lumbar's container, see lumbar_tables.py).
_REGION_DISPLAY_ORDER = ["cervical", "shoulder", "lumbar", "hip", "knee", "ankle"]


def _region_order_index(region_id: str) -> int:
    try:
        return _REGION_DISPLAY_ORDER.index(region_id)
    except ValueError:
        return len(_REGION_DISPLAY_ORDER)


class RegionTabContent(Gtk.Box):
    """Variable objective tab - shows one collapsible RegionContainer per
    active region. This app has no live body-chart region sync yet, so
    the active region list is fixed at construction time (see app.py)
    rather than driven by chart selection, same deferral as the KB panel."""

    __gsignals__ = {
        "field-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, section_key: str, tab_label: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._section_key = section_key
        self._containers: dict[str, RegionContainer] = {}

        title = Gtk.Label(label=tab_label)
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

    def mount_region(self, region_id: str) -> None:
        if region_id in self._containers:
            return
        container = RegionContainer(region_id, self._section_key)
        container.connect("field-changed", lambda *_a: self.emit("field-changed"))
        self._containers[region_id] = container

        # Insert in fixed anatomical order (_REGION_DISPLAY_ORDER), not
        # appended at the end — walk the box's ACTUAL current children
        # (skipping the title label) rather than self._containers (a plain
        # dict, whose iteration order doesn't necessarily match the box's
        # child order once regions have been unmounted/remounted).
        idx = _region_order_index(region_id)
        insert_before = None
        child = self.get_first_child()
        if child is not None:
            child = child.get_next_sibling()  # skip the title label
        while child is not None:
            if _region_order_index(child._region_id) > idx:
                insert_before = child
                break
            child = child.get_next_sibling()
        if insert_before is not None:
            self.insert_child_after(container, insert_before.get_prev_sibling())
        else:
            self.append(container)

    def get_container(self, region_id: str) -> RegionContainer | None:
        return self._containers.get(region_id)

    def unmount_region(self, region_id: str) -> None:
        container = self._containers.pop(region_id, None)
        if container is not None:
            self.remove(container)

    def focus_first_field(self) -> None:
        for container in self._containers.values():
            if container.child_focus(Gtk.DirectionType.TAB_FORWARD):
                return

    def collect(self) -> dict:
        return {rid: c.collect() for rid, c in self._containers.items()}

    def load(self, data: dict) -> None:
        for rid, container in self._containers.items():
            container.load(data.get(rid, {}))

    def is_complete(self) -> bool:
        return any(c.is_complete() for c in self._containers.values())
