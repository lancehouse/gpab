"""Ctrl+T grid overview — full heading map for rapid section/subsection
navigation. GTK4 port of pab_assessment.grid_overview.

Rebound from the TUI's original Ctrl+G to Ctrl+T ("Overview") — confirmed
straight from the reference TUI source (`assessment/pab_assessment/tui.py`'s
own BINDINGS table: `Binding("ctrl+t", "toggle_grid", "Overview", ...)`,
`Binding("ctrl+g", "import_gonio", "Import ROM", ...)`), not a guess: Ctrl+G
was freed for the goniometer-import wizard (its own separate, not-yet-ported
feature — `goniometer_import/`), and Ctrl+G isn't one of the reserved
termios special characters the old Ctrl+O binding collided with. This app's
Ctrl+T mirrors that rebind exactly.

`SUBJ_GRID_DATA`/`OBJ_GRID_DATA` (the heading tables) and `section_to_cursor`/
`_section_has_data` (pure logic) are lifted verbatim — every (section_id,
anchor_id) pair in them already matches this port's own section ids
one-to-one, including the special "04_objective" row whose "headings" are
themselves objective section ids (e.g. "02_active") rather than anchors
within a "04_objective" section — that row doesn't need the TUI's special
mode-switch handling here, since `app.py::_show_section` already treats any
objective section id as directly showable regardless of current mode.

Selecting a heading jumps precisely: `widgets.make_subsection_header()`
tags each subsection's header Label with the same anchor_id used here
(`app.py::_scroll_section_to_anchor`, via `search.find_by_anchor_id`),
scrolling that header to the top of the section's viewport rather than
just focusing the section's first field (which could leave the header
itself cut off above the visible area). Region rows (Active/Passive/
Muscle) and the Special Tests region-list row are handled specially —
see app.py's `on_selected` for the "08_special" case, which mounts an
inactive region before jumping to it.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

# ── Heading data — lifted verbatim ──────────────────────────────────────────
# Each entry: (section_id, display_label, [(heading_label, anchor_id), ...])

SUBJ_GRID_DATA: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("01_consent", "01 Consent", [
        ("Consent",  "cs_consent"),
        ("Framing",  "cs_framing"),
        ("ICE+",     "cs_ice"),
        ("Goals",    "consent_goals"),
        ("Beliefs",  "cs_beliefs"),
    ]),
    ("02_subjective", "02 Subjective", [
        ("Symptoms",     "subj_symptoms"),
        ("History",      "subj_history"),
        ("Behaviour",    "subj_behaviour"),
        ("Mgmt",         "subj_management"),
        ("Activity",     "subj_activity"),
        ("Work",         "subj_work"),
        ("Sleep",        "subj_sleep"),
        ("24Hr",         "subj_24hr"),
        ("Psychosocial", "subj_psychosocial"),
        ("Goals",        "subj_goals"),
        ("Risk",         "subj_suicide"),
    ]),
    ("03_medical", "03 Medical", [
        ("Comorbid",     "med_comorbidities"),
        ("CVD Risk",     "med_cardiovascular"),
        ("Red Flags",    "med_red_flags"),
        ("Differential", "med_differential"),
        ("Medications",  "med_medications"),
    ]),
    ("04_objective", "04 Objective →", [
        ("General Obs",  "01_general"),
        ("Active",       "02_active"),
        ("Passive",      "03_passive"),
        ("Neurological", "04_neurological"),
        ("Sensory",      "05_sensory"),
        ("Muscle",       "06_muscle"),
        ("Functional",   "07_functional"),
        ("Special",      "08_special"),
    ]),
    ("04_pain_classification", "04 Pain Class", [
        ("Inflamm",      "pc_inflammatory"),
        ("Nociceptive",  "pc_nociceptive"),
        ("Neuropathic",  "pc_neuropathic"),
        ("Nociplastic",  "pc_nociplastic"),
        ("Central",      "pc_central"),
        ("Fibro",        "pc_fibromyalgia"),
        ("BACPAP",       "pc_bacpap"),
        ("Summary",      "pc_summary"),
    ]),
    ("05_outcome_measures", "05 Outcomes", [
        ("PSFS",       "om_psfs"),
        ("BPI",        "om_bpi"),
        ("DASS",       "om_dass"),
        ("PCS",        "om_pcs"),
        ("PSEQ/PCL",   "om_pseq"),
        ("Sleep",      "om_sleep"),
        ("Additional", "om_additional"),
        ("Hypothesis", "om_hypothesis"),
    ]),
    ("06_diagnosis", "06 Diagnosis", [
        ("Overview",    "dx_overview"),
        ("Primary",     "dx_primary"),
        ("Post-Surg",   "dx_surgical"),
        ("Post-Trauma", "dx_traumatic"),
        ("MSK",         "dx_msk"),
        ("Neuro",       "dx_neuropathic"),
        ("Mixed",       "dx_mixed"),
    ]),
    ("07_barriers", "07 Barriers", [
        ("Physical",  "br_physical"),
        ("Neuro",     "br_neuro"),
        ("Nocip",     "br_nocip"),
        ("Psych",     "br_psych"),
        ("Sleep/Soc", "br_sleep"),
        ("Medical",   "br_medical"),
        ("Custom",    "br_custom"),
    ]),
    ("08_rx_plan", "08 Rx Plan", [
        ("Treatment", "rp_treatment"),
        ("Session 1", "rp_session1"),
        ("Day 1",     "rp_day1"),
        ("Follow-Up", "rp_followup"),
    ]),
]

OBJ_GRID_DATA: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("01_general", "01 General", [
        ("Physical",   "go_physical"),
        ("Posture",    "go_posture"),
    ]),
    ("07_functional", "02 Functional", [
        ("Goals",          "fn_goals"),
        ("Functional Mvt", "fn_movement"),
        ("Balance",        "fn_balance"),
        ("Timed",          "fn_timed"),
    ]),
    ("02_active", "03 Active Mvt", [
        ("Lumbar",   "am_lumbar"),
        ("Thoracic", "am_thoracic"),
    ]),
    ("03_passive", "04 Passive/OP", [
        ("Overpressure", "pm_overpressure"),
        ("PAIVMs",       "pm_paivms"),
    ]),
    ("04_neurological", "05 Neurology", [
        ("UL Reflex",       "nr_ul_reflexes"),
        ("UL Myotomes",     "nr_ul_myotomes"),
        ("UL Dermatomes",   "nr_ul_dermatomes"),
        ("UL Neurodynamics","nr_ul_neurodynamics"),
        ("LL Reflex",       "nr_reflexes"),
        ("LL Myotomes",     "nr_myotomes"),
        ("LL Dermatomes",   "nr_dermatomes"),
        ("LL Neurodynamics","nr_neurodynamics"),
        ("UMN",             "nr_umn"),
    ]),
    ("05_sensory", "06 Sensory", [
        ("Hyposensitivity",  "sn_hyposensitivity"),
        ("Hypersensitivity", "sn_hypersensitivity"),
    ]),
    ("06_muscle", "07 Muscle", [
        ("Length",       "ml_length"),
        ("Activation",   "ml_activation"),
        ("Trunk Str",    "ml_strength_trunk"),
        ("Hip Str",      "ml_strength_hip"),
        # SIJ Provocation Signs moved to Special Tests 2026-08-24 (was
        # misfiled under Muscle here and in the reference TUI — see
        # lumbar_tables.py's module docstring). No longer listed here.
    ]),
    # The TUI's own grid_overview.py has no "08 Special Tests" row at all
    # (OBJ_GRID_DATA jumps straight from Muscle to CRPS there too) — a
    # real, pre-existing TUI gap, not something lost in this port. Left
    # as-is there, it also misaligns the TUI's own grid against its own
    # ObjectiveSidebar by one row from Special Tests down through CRPS
    # (confirmed: same bug, same cause, in both apps). Fixed here per
    # direct feedback rather than reproducing it: a region-list row, since
    # Special Tests has no fixed heading set of its own (unlike every other
    # objective tab) — it shows whichever regions are currently toggled
    # active via RegionTopbar, so "headings" here are the region choices
    # themselves rather than subsection anchors within one fixed layout.
    ("08_special", "08 Special Tests", [
        ("Lumbar",   "st_lumbar"),
        ("Cervical", "st_cervical"),
        ("Shoulder", "st_shoulder"),
        ("Hip",      "st_hip"),
        ("Knee",     "st_knee"),
        ("Ankle",    "st_ankle"),
    ]),
    ("09_crps", "09 CRPS", [
        ("Disp Pain",  "crps_disp"),
        ("Symptoms",   "crps_sx"),
        ("Signs",      "crps_sg"),
        ("No Alt Dx",  "crps_no_dx"),
        ("Summary",    "crps_summary_hdr"),
        ("Subtype",    "crps_subtype_hdr"),
        ("2Pt Discrim","crps_tpd"),
        ("Visualis",   "crps_vis"),
        ("Laterality", "crps_lat"),
    ]),
]


# ── Cursor / tick helpers — lifted verbatim ─────────────────────────────────

def section_to_cursor(section_id: str, grid_data: list) -> tuple[int, int]:
    """Return (row, 0) for the first grid row matching section_id, else (0, 0)."""
    for row_idx, (sid, _, headings) in enumerate(grid_data):
        if sid == section_id and headings:
            return (row_idx, 0)
    return (0, 0)


def _section_has_data(data: dict) -> bool:
    """True if any field in collected section data has a meaningful value."""
    for v in data.values():
        if v is True:
            return True
        if isinstance(v, str) and v.strip():
            return True
        if isinstance(v, dict) and _section_has_data(v):
            return True
    return False


# ── Grid overview page ───────────────────────────────────────────────────────

class GridOverviewPage(Gtk.Box):
    """Heading map — an in-place page swapped into app.py's main Gtk.Stack
    (named "grid_overview"), not a separate popup window.

    A first version of this used a transient Gtk.Window (matching the
    Ctrl+F/Ctrl+D popups). Per direct feedback, that was wrong for this
    specific feature: unlike a search box, the TUI's own Ctrl+G/Ctrl+T grid
    replaces #section_content IN PLACE — same content area, same sidebar
    still visible and still responsive, no new window size to mentally
    recalibrate around. This rebuild matches that: app.py adds this page to
    the same Gtk.Stack every other section lives in and just switches to
    it, exactly like switching to any other tab.
    """

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._grid_data: list[tuple[str, str, list[tuple[str, str]]]] = []
        self._on_selected = None
        self._buttons: list[list[Gtk.Button]] = []
        self._cursor: tuple[int, int] = (0, 0)

        # margin_top=4 + spacing=2 between rows deliberately match
        # nav.py's SectionNav / objective_nav.py's ObjectiveNav exactly
        # (same values there) — each grid row lines up with its own
        # section's sidebar tab at the same y position (see _build_row's
        # matching .nav-button/.grid-overview-btn min-height too). No
        # in-content row label either: the sidebar tab directly alongside
        # IS the row label now, not repeated here — this only works because
        # SUBJ_GRID_DATA/OBJ_GRID_DATA already list rows in the exact same
        # order as SectionNav.SECTION_LABELS/ObjectiveNav.SECTION_LABELS.
        self._rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._rows_box.set_margin_top(4)
        self._rows_box.set_margin_bottom(4)
        self._rows_box.set_margin_start(10)
        self._rows_box.set_margin_end(10)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self._rows_box)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        self.append(scroll)

    # ------------------------------------------------------------------
    # Public API — driven by app.py's _open_grid_overview/_toggle_grid_overview
    # ------------------------------------------------------------------

    def open(
        self,
        grid_data: list[tuple[str, str, list[tuple[str, str]]]],
        has_data: dict[str, bool],
        cursor: tuple[int, int],
        on_selected,
    ) -> None:
        """(Re)build the grid for grid_data (SUBJ_GRID_DATA or OBJ_GRID_DATA
        depending on assessment/objective mode) and focus the given cursor
        cell. Rebuilt every open() rather than kept as two permanently-live
        widgets (unlike the TUI's own subj/obj GridOverview, both always
        mounted) — simpler, and this page is never open during normal typing
        so rebuild cost is irrelevant."""
        self._grid_data = grid_data
        self._on_selected = on_selected
        self._cursor = cursor

        child = self._rows_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._rows_box.remove(child)
            child = nxt
        self._buttons = []

        for row_idx, (section_id, row_label, headings) in enumerate(grid_data):
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row_box.set_valign(Gtk.Align.CENTER)

            btn_row: list[Gtk.Button] = []
            for col_idx, (h_label, _anchor_id) in enumerate(headings):
                btn = Gtk.Button()
                btn.add_css_class("grid-overview-btn")
                btn.row = row_idx
                btn.col = col_idx
                btn.base_label = h_label
                btn.connect("clicked", self._on_button_clicked, row_idx, col_idx)
                row_box.append(btn)
                btn_row.append(btn)
            self._buttons.append(btn_row)
            self._rows_box.append(row_box)

        self._refresh_ticks(has_data)
        self._focus_cursor()

    def current_cursor(self) -> tuple[int, int]:
        return self._cursor

    def move_cursor(self, direction: str) -> None:
        """Called by app.py's global key handler (Up/Down/Left/Right) while
        this page is the visible stack child."""
        row, col = self._cursor
        if direction == "Up":
            new_row = self._next_non_empty(row, -1)
            self._move_cursor(new_row, min(col, len(self._buttons[new_row]) - 1))
        elif direction == "Down":
            new_row = self._next_non_empty(row, +1)
            self._move_cursor(new_row, min(col, len(self._buttons[new_row]) - 1))
        elif direction == "Left":
            self._move_cursor(row, max(0, col - 1))
        elif direction == "Right":
            self._move_cursor(row, min(len(self._buttons[row]) - 1, col + 1))

    # ------------------------------------------------------------------

    def _refresh_ticks(self, has_data: dict[str, bool]) -> None:
        for row_idx, (section_id, _, _) in enumerate(self._grid_data):
            tick = has_data.get(section_id, False)
            for btn in self._buttons[row_idx]:
                btn.set_label(f"✓ {btn.base_label}" if tick else btn.base_label)

    def _focus_cursor(self) -> None:
        row, col = self._cursor
        for r in range(row, len(self._buttons)):
            if self._buttons[r]:
                c = min(col, len(self._buttons[r]) - 1)
                self._buttons[r][c].grab_focus()
                return
        for row_btns in self._buttons:
            if row_btns:
                row_btns[0].grab_focus()
                return

    def _move_cursor(self, row: int, col: int) -> None:
        self._cursor = (row, col)
        try:
            self._buttons[row][col].grab_focus()
        except IndexError:
            pass

    def _next_non_empty(self, start: int, direction: int) -> int:
        r = start + direction
        while 0 <= r < len(self._buttons):
            if self._buttons[r]:
                return r
            r += direction
        return start

    def _on_button_clicked(self, _btn, row: int, col: int) -> None:
        self._cursor = (row, col)
        section_id, _, headings = self._grid_data[row]
        _, anchor_id = headings[col]
        if self._on_selected is not None:
            self._on_selected(section_id, anchor_id)
