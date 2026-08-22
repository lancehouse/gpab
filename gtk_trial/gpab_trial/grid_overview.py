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

One scope cut carried over from search.py's `_execute_jump`: selecting a
heading switches to the right section (which already focuses that
section's first field) rather than scrolling to the exact subsection
anchor — same reasoning, same missing ~80-anchor infrastructure. Every
other piece of the TUI's grid — the 2-D keyboard nav (skip-empty-row aware),
the ✓ data-completion ticks, remembering cursor position across opens — is
real, not simplified.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk  # noqa: E402

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
        ("SIJ",          "ml_sij"),
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


# ── Grid overview window ─────────────────────────────────────────────────────

class GridOverviewWindow(Gtk.Window):
    """Heading map popup. Click, or arrow keys + Enter, or Escape to close.

    A separate transient window (like the Ctrl+F/Ctrl+D search popups)
    rather than an in-place content swap — this app's per-tab content
    already lives in a Gtk.Stack, and a window keeps the overlay/dismiss
    mechanics identical to every other popup in this app rather than
    teaching app.py's stack-swap logic a second, grid-specific mode.
    """

    def __init__(
        self,
        parent: Gtk.Window,
        grid_data: list[tuple[str, str, list[tuple[str, str]]]],
        has_data: dict[str, bool],
        cursor: tuple[int, int],
        on_selected,
    ) -> None:
        super().__init__(transient_for=parent, modal=True, title="Overview")
        self.set_default_size(900, 650)
        self._grid_data = grid_data
        self._on_selected = on_selected
        self._buttons: list[list[Gtk.Button]] = []
        self._cursor = cursor

        header = Gtk.HeaderBar()
        close_btn = Gtk.Button(label="Close (Esc)")
        close_btn.connect("clicked", lambda _b: self.close())
        header.pack_end(close_btn)
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_margin_top(10)
        outer.set_margin_bottom(10)
        outer.set_margin_start(10)
        outer.set_margin_end(10)

        for row_idx, (section_id, row_label, headings) in enumerate(grid_data):
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row_title = Gtk.Label(label=row_label)
            row_title.set_size_request(140, -1)
            row_title.set_xalign(0.0)
            row_title.add_css_class("grid-overview-row-label")
            row_box.append(row_title)

            btn_row: list[Gtk.Button] = []
            for col_idx, (h_label, _anchor_id) in enumerate(headings):
                btn = Gtk.Button()
                btn.add_css_class("grid-overview-btn")
                btn.row = row_idx
                btn.col = col_idx
                btn.base_label = h_label
                btn.set_label(h_label)
                btn.connect("clicked", self._on_button_clicked, row_idx, col_idx)
                row_box.append(btn)
                btn_row.append(btn)
            self._buttons.append(btn_row)
            outer.append(row_box)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(outer)
        scroll.set_vexpand(True)
        self.set_child(scroll)

        self._refresh_ticks(has_data)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        self.connect("show", lambda *_a: self._focus_cursor())

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

    # ------------------------------------------------------------------

    def _on_key(self, _ctrl, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name == "Escape":
            self.close()
            return True
        if name == "Up":
            row, col = self._cursor
            new_row = self._next_non_empty(row, -1)
            self._move_cursor(new_row, min(col, len(self._buttons[new_row]) - 1))
            return True
        if name == "Down":
            row, col = self._cursor
            new_row = self._next_non_empty(row, +1)
            self._move_cursor(new_row, min(col, len(self._buttons[new_row]) - 1))
            return True
        if name == "Left":
            row, col = self._cursor
            self._move_cursor(row, max(0, col - 1))
            return True
        if name == "Right":
            row, col = self._cursor
            self._move_cursor(row, min(len(self._buttons[row]) - 1, col + 1))
            return True
        return False

    def _on_button_clicked(self, _btn, row: int, col: int) -> None:
        self._cursor = (row, col)
        section_id, _, headings = self._grid_data[row]
        _, anchor_id = headings[col]
        self._on_selected(section_id, anchor_id)
        self.close()
