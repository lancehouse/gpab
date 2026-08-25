"""Neurological — Objective 04, GTK4 port of
pab_assessment/objective/sections/neurological.py.

Field ids and collect()/load() keys are 1:1 with the TUI section (JSON key
"neurological" in _objective.json), so the saved dict is schema-compatible.

This is deliberately the densest tab: reflex/myotome/dermatome bilateral
grids (~54 RadioGroups), 6 neurodynamics rows, a 9-button UMN row, and 10
notes fields — the TUI section this most directly stresses touch/scroll
performance, which is the whole point of testing it here.

Arrow-key grid navigation (Up/Down move between rows in the same column,
Left/Right cycle a gang's own selection, Enter/Space commit-and-advance to
the next cell) mirrors pab_assessment.objective.sections.neurological's
_grid/_grid_pos/_nav exactly, via the shared GridNav mixin in
objective/grid_nav.py — see that file's docstring, and RadioGroup's in
widgets.py, for the full key semantics.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import RadioGroup, FlagButton, AutoTextView, TouchEntry, make_subsection_header
from ..grid_widgets import bilateral_header_row, bilateral_radio_row, bilateral_field_row
from ..grid_nav import GridNav
from ..grid_drag_select import GridDragSelect
from ...section_base import SectionBase

# Block title -> grid_overview anchor_id (search.py's _SUBSECTIONS /
# grid_overview.py's OBJ_GRID_DATA "04_neurological" row vocabulary).
_NEURO_BLOCK_ANCHOR: dict[str, str] = {
    "Upper Limb — Reflexes": "nr_ul_reflexes",
    "Upper Limb — Myotomes": "nr_ul_myotomes",
    "Upper Limb — Dermatomes": "nr_ul_dermatomes",
    "Upper Limb — Neurodynamics": "nr_ul_neurodynamics",
    "Lower Limb — Reflexes": "nr_reflexes",
    "Lower Limb — Myotomes": "nr_myotomes",
    "Lower Limb — Dermatomes": "nr_dermatomes",
    "Lower Limb — Neurodynamics": "nr_neurodynamics",
}

# ---------------------------------------------------------------------------
# Gang option sets — identical to the TUI's (labels, variants, cycle order)
# ---------------------------------------------------------------------------

_REFLEX = [("0 Absnt", "error"), ("1+ Redu", "warning"), ("2+ Norm", "success"),
           ("3+ Hypr", "warning"), ("4+Clons", "error")]
_MYOTOME = [("5/5", "success"), ("4/5", "warning"), ("3/5", "warning"),
            ("2/5", "error"), ("1/5", "error"), ("0/5", "error")]
_DERM = [("Absent", "error"), ("↓Hypo", "warning"),
         ("Normal", "success"), ("↑Hyper", "error")]

# ---------------------------------------------------------------------------
# Row definitions — Upper Limb
# ---------------------------------------------------------------------------

_UL_REFLEX_ROWS = [
    ("Biceps   C5/6", "nr_biceps"),
    ("Brachiorad  C6", "nr_brad"),
    ("Triceps  C7", "nr_triceps"),
]
_UL_MYOTOME_ROWS = [
    ("C5  Shldr abd", "nr_c5"),
    ("C6  Wrist ext", "nr_c6"),
    ("C7  Elbow ext", "nr_c7"),
    ("C8  Finger flx", "nr_c8"),
    ("T1  Finger abd", "nr_t1"),
]
_UL_DERM_ROWS = [
    ("C5  Lat arm/delt", "sn_c5"),
    ("C6  Thumb & index", "sn_c6"),
    ("C7  Middle finger", "sn_c7"),
    ("C8  Little/ulnar", "sn_c8"),
    ("T1  Med forearm", "sn_t1"),
]
_UL_ND_ROWS = [
    ("ULNT1", "nr_ulnt1", False),
    ("ULNT2a", "nr_ulnt2a", False),
    ("ULNT3", "nr_ulnt3", False),
]

# ---------------------------------------------------------------------------
# Row definitions — Lower Limb
# ---------------------------------------------------------------------------

_REFLEX_ROWS = [
    ("Knee jerk  L3/4", "nr_knee"),
    ("Ankle jerk  S1", "nr_ankle"),
]
_MYOTOME_ROWS = [
    ("L2  Hip flex", "nr_l2"),
    ("L3  Knee ext", "nr_l3"),
    ("L4  Ankle DF", "nr_l4"),
    ("L5  GT ext/EHL", "nr_l5"),
    ("S1  PF / evert", "nr_s1"),
    ("S2  Ham / KF", "nr_s2"),
]
_DERM_ROWS = [
    ("L2  Ant thigh", "sn_l2"),
    ("L3  Med knee", "sn_l3"),
    ("L4  Med foot", "sn_l4"),
    ("L5  Dorsum foot", "sn_l5"),
    ("S1  Lat foot", "sn_s1"),
    ("S2  Post thigh", "sn_s2"),
]
_ND_ROWS = [
    ("SLR", "nr_slr", True),
    ("Slump", "nr_slump", False),
    ("PKF", "nr_pkf", True),
]
_UMN_ITEMS = [
    ("Hyperreflexia", "nr_umn_hyper"),
    ("Babinski +", "nr_umn_bab"),
    ("Clonus", "nr_umn_clonus"),
    ("Romberg +", "nr_umn_romberg"),
    ("Coord impaired", "nr_umn_coord"),
    ("Hoffman's", "nr_umn_hoffman"),
    ("Tromner", "nr_umn_tromner"),
    ("Lhermitte's", "nr_umn_lhermitte"),
    ("Inv Supinator", "nr_umn_inv_sup"),
]

_ND_ALL_ROWS = _UL_ND_ROWS + _ND_ROWS
_NOTES_IDS = [
    "nr_ul_reflex_notes", "nr_ul_myotome_notes", "nr_ul_derm_notes", "nr_ul_nd_notes",
    "nr_ll_reflex_notes", "nr_ll_myotome_notes", "nr_ll_derm_notes", "nr_ll_nd_notes",
    "nr_umn_notes", "nr_notes",
]


class NeurologicalSection(Gtk.Box, GridNav, GridDragSelect, SectionBase):
    """Drag-gesture bulk-select (grid_drag_select.py) was built and first
    wired in HERE (2026-08-24) — the user's chosen test tab for that
    feature — then ported the same day into GradeGroupWidget
    (objective/region_section.py) so it covers Muscle Testing across all six
    regions too. Not yet mixed into Sensory. See CONVERSION_PLAN.md's
    "Flagged for future work" section and grid_drag_select.py's module
    docstring for the full design."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None

        self._radio_groups: dict[str, RadioGroup] = {}
        self._entries: dict[str, TouchEntry] = {}
        self._notes: dict[str, AutoTextView] = {}
        self._umn_buttons: dict[str, FlagButton] = {}
        self._init_grid()
        self._init_drag_select()

        title = Gtk.Label(label="04 Neurological")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        self._build_reflex_myotome_block("Upper Limb — Reflexes", _UL_REFLEX_ROWS, _REFLEX, "nr_ul_reflex_notes")
        self._build_reflex_myotome_block("Upper Limb — Myotomes", _UL_MYOTOME_ROWS, _MYOTOME, "nr_ul_myotome_notes")
        self._build_reflex_myotome_block("Upper Limb — Dermatomes", _UL_DERM_ROWS, _DERM, "nr_ul_derm_notes")
        self._build_nd_block("Upper Limb — Neurodynamics", _UL_ND_ROWS, "nr_ul_nd_notes")

        self._build_reflex_myotome_block("Lower Limb — Reflexes", _REFLEX_ROWS, _REFLEX, "nr_ll_reflex_notes")
        self._build_reflex_myotome_block("Lower Limb — Myotomes", _MYOTOME_ROWS, _MYOTOME, "nr_ll_myotome_notes")
        self._build_reflex_myotome_block("Lower Limb — Dermatomes", _DERM_ROWS, _DERM, "nr_ll_derm_notes")
        self._build_nd_block("Lower Limb — Neurodynamics", _ND_ROWS, "nr_ll_nd_notes")

        self._build_umn_block()

        self.append(Gtk.Label(label="General Notes:", halign=Gtk.Align.START))
        self._add_notes("nr_notes", grid_row=True)

        self._widgets_by_id: dict[str, Gtk.Widget] = {
            **self._radio_groups, **self._entries, **self._notes, **self._umn_buttons,
        }

    # ------------------------------------------------------------------
    # Block builders
    # ------------------------------------------------------------------

    def _build_reflex_myotome_block(self, title: str, rows, states, notes_id: str) -> None:
        self.append(make_subsection_header(title, _NEURO_BLOCK_ANCHOR.get(title)))
        self.append(bilateral_header_row())
        left_column: list[RadioGroup] = []
        right_column: list[RadioGroup] = []
        for label, prefix in rows:
            left = RadioGroup(states, f"{prefix}_l")
            right = RadioGroup(states, f"{prefix}_r")
            self._radio_groups[left.field_id] = left
            self._radio_groups[right.field_id] = right
            left.connect("changed", self._field_changed)
            right.connect("changed", self._field_changed)
            left.connect("navigate", self._on_navigate)
            right.connect("navigate", self._on_navigate)
            self._add_grid_row([left.field_id, right.field_id])
            self.append(bilateral_radio_row(label, left, right))
            left_column.append(left)
            right_column.append(right)
        # Drag-select columns: Left-side gangs drag together top-to-bottom,
        # Right-side gangs separately — a drag never crosses from Left to
        # Right (see grid_drag_select.py; "same column position" per the
        # user's 2026-08-24 decision).
        self._register_drag_column(left_column)
        self._register_drag_column(right_column)
        self._add_notes(notes_id, grid_row=True)

    def _build_nd_block(self, title: str, rows, notes_id: str) -> None:
        self.append(make_subsection_header(title, _NEURO_BLOCK_ANCHOR.get(title)))
        self.append(bilateral_header_row())
        for label, prefix, has_deg in rows:
            left_widgets = self._nd_side_widgets(prefix, "l", has_deg)
            right_widgets = self._nd_side_widgets(prefix, "r", has_deg)
            self._add_grid_row([w.field_id for w in (*left_widgets, *right_widgets)])
            self.append(bilateral_field_row(label, left_widgets, right_widgets))
        self._add_notes(notes_id, grid_row=True)

    def _nd_side_widgets(self, prefix: str, side: str, has_deg: bool) -> list[Gtk.Widget]:
        widgets: list[Gtk.Widget] = []
        if has_deg:
            deg = TouchEntry(f"{prefix}_{side}_deg", placeholder="°")
            deg.set_size_request(64, -1)
            deg.set_hexpand(False)
            deg.connect("changed", self._field_changed)
            deg.connect("navigate", self._on_navigate)
            self._entries[deg.field_id] = deg
            widgets.append(deg)
        resp = TouchEntry(f"{prefix}_{side}_resp", placeholder="Response")
        resp.set_hexpand(True)
        resp.connect("changed", self._field_changed)
        resp.connect("navigate", self._on_navigate)
        self._entries[resp.field_id] = resp
        widgets.append(resp)
        return widgets

    def _build_umn_block(self) -> None:
        self.append(make_subsection_header("UMN Signs", "nr_umn"))
        # NOT homogeneous: this is a single independent row (unlike the
        # reflex/myotome rows, nothing below it needs matching columns), so
        # each button should size to its own label instead of every column
        # being forced to match whichever one is currently answered with the
        # longest text (e.g. "Coord impaired No" would otherwise stretch
        # all 9 buttons to its width).
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, homogeneous=False)
        for label, uid in _UMN_ITEMS:
            btn = FlagButton(label, uid, compact=True)
            btn.connect("changed", self._field_changed)
            btn.connect("navigate", self._on_navigate)
            self._umn_buttons[uid] = btn
            row.append(btn)
        self._add_grid_row([uid for _, uid in _UMN_ITEMS])
        self.append(row)
        self._add_notes("nr_umn_notes", grid_row=True)

    def _add_notes(self, notes_id: str, grid_row: bool = False) -> None:
        ta = AutoTextView(notes_id, min_lines=2)
        ta.textview.get_buffer().connect("changed", self._field_changed)
        ta.connect("navigate", self._on_navigate)
        self._notes[notes_id] = ta
        self.append(ta)
        if grid_row:
            self._add_grid_row([notes_id])

    # ------------------------------------------------------------------
    # Grid navigation — see objective/grid_nav.py for the shared algorithm
    # ------------------------------------------------------------------

    def _on_navigate(self, widget, direction: str) -> None:
        self._grid_nav(widget.field_id, direction, self._widgets_by_id)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _field_changed(self, *_args) -> None:
        if self._loading:
            return
        if self._on_changed:
            self._on_changed()

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    def focus_first_field(self) -> None:
        self._radio_groups["nr_biceps_l"].grab_focus()

    # ------------------------------------------------------------------
    # Data — keys match pab_assessment.objective.sections.neurological exactly
    # ------------------------------------------------------------------

    def collect(self) -> dict:
        data: dict = {}
        for fid, rg in self._radio_groups.items():
            data[fid] = rg.value
        for _, uid in _UMN_ITEMS:
            data[uid] = self._umn_buttons[uid].value
        for _, prefix, has_deg in _ND_ALL_ROWS:
            for side in ("l", "r"):
                if has_deg:
                    fid = f"{prefix}_{side}_deg"
                    data[fid] = self._entries[fid].text.strip()
                fid = f"{prefix}_{side}_resp"
                data[fid] = self._entries[fid].text.strip()
        for nid in _NOTES_IDS:
            data[nid] = self._notes[nid].text
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            for fid, rg in self._radio_groups.items():
                rg.set_value(data.get(fid))
            for _, uid in _UMN_ITEMS:
                self._umn_buttons[uid].set_value(data.get(uid))
            for _, prefix, has_deg in _ND_ALL_ROWS:
                for side in ("l", "r"):
                    if has_deg:
                        fid = f"{prefix}_{side}_deg"
                        self._entries[fid].text = data.get(fid, "")
                    fid = f"{prefix}_{side}_resp"
                    self._entries[fid].text = data.get(fid, "")
            for nid in _NOTES_IDS:
                self._notes[nid].text = data.get(nid, "")
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        rg = self._radio_groups.get("nr_knee_l")
        return rg is not None and rg.value is not None
