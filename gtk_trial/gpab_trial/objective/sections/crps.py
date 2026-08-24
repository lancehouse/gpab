"""CRPS — Objective 09, GTK4 port of pab_assessment.objective.sections.crps.

Budapest / Valencia diagnostic criteria (IASP 2004/2021) + clinical
measures. Field ids and collect()/load() keys are 1:1 with the TUI (JSON
key "crps" in _objective.json), including the three derived fields
(`crps_sx_domains_triggered`, `crps_sg_domains_triggered`,
`crps_criteria_met`) the TUI computes into collect() for report rendering.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import FlagButton, RadioGroup, TouchEntry, AutoTextView, make_subsection_header
from ...section_base import SectionBase

# (prefix, display_label, indicator placeholder attr, [(field_id, label), ...])
_SX_DOMAINS: list[tuple[str, str, list]] = [
    ("Sensory", [
        ("crps_sx_hyperesth", "Hyperesthesia"),
        ("crps_sx_hyperalg", "Hyperalgesia"),
        ("crps_sx_allodynia", "Allodynia"),
    ]),
    ("Vasomotor", [
        ("crps_sx_temp_asymm", "Temperature asymmetry"),
        ("crps_sx_skin_colour", "Skin colour change"),
        ("crps_sx_colour_asymm", "Colour asymmetry"),
    ]),
    ("Sudomotor/Oedema", [
        ("crps_sx_oedema", "Oedema"),
        ("crps_sx_sweat_chng", "Sweating change"),
        ("crps_sx_sweat_asymm", "Sweating asymmetry"),
    ]),
    ("Motor/Trophic", [
        ("crps_sx_rom_dec", "Decreased range of motion"),
        ("crps_sx_weakness", "Weakness"),
        ("crps_sx_tremor", "Tremor"),
        ("crps_sx_dystonia", "Dystonia"),
        ("crps_sx_trophic", "Trophic changes"),
    ]),
]

_SG_DOMAINS: list[tuple[str, list]] = [
    ("Sensory", [
        ("crps_sg_hyperalg_pp", "Hyperalgesia (pinprick)"),
        ("crps_sg_allod_lt", "Allodynia (light touch)"),
        ("crps_sg_allod_press", "Allodynia (pressure)"),
        ("crps_sg_allod_jt", "Allodynia (joint movement)"),
    ]),
    ("Vasomotor", [
        ("crps_sg_temp_asymm", "Temperature asymmetry"),
        ("crps_sg_skin_colour", "Skin colour change"),
        ("crps_sg_colour_asymm", "Colour asymmetry"),
    ]),
    ("Sudomotor/Oedema", [
        ("crps_sg_oedema", "Oedema"),
        ("crps_sg_sweat_chng", "Sweating change"),
        ("crps_sg_sweat_asymm", "Sweating asymmetry"),
    ]),
    ("Motor/Trophic", [
        ("crps_sg_rom_dec", "Decreased range of motion"),
        ("crps_sg_weakness", "Weakness"),
        ("crps_sg_tremor", "Tremor"),
        ("crps_sg_dystonia", "Dystonia"),
        ("crps_sg_trophic", "Trophic changes"),
    ]),
]

_ALL_SX_IDS = [fid for _, items in _SX_DOMAINS for fid, _ in items]
_ALL_SG_IDS = [fid for _, items in _SG_DOMAINS for fid, _ in items]
_ALL_FLAG_IDS = ["crps_disp_pain"] + _ALL_SX_IDS + _ALL_SG_IDS + ["crps_no_alt_dx"]

_LAT_ROWS: list[tuple[str, str]] = [
    ("quick", "Quick"), ("vanilla", "Vanilla"), ("context", "Context"), ("abstract", "Abstract"),
]
_LAT_COLS: list[tuple[str, str, str]] = [
    ("l_acc", "L acc", "%"), ("l_speed", "L speed", "s"),
    ("r_acc", "R acc", "%"), ("r_speed", "R speed", "s"),
]
_LAT_IDS = [f"crps_lat_{row}_{col}" for row, _ in _LAT_ROWS for col, _, _ in _LAT_COLS]

_ALL_TA_IDS = [
    "crps_disp_pain_notes", "crps_sx_notes", "crps_sg_notes",
    "crps_no_alt_dx_notes", "crps_subtype_notes", "crps_notes",
    "crps_tpd_notes", "crps_vis_notes", "crps_lat_notes",
]

_SUBTYPE = [("T-I", "success"), ("T-II", "warning"), ("Remit", "primary"), ("NOS", "default")]


class CRPSSection(Gtk.Box, SectionBase):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None

        self._flags: dict[str, FlagButton] = {}
        self._domain_indicators: dict[str, Gtk.Label] = {}
        self._notes: dict[str, AutoTextView] = {}
        self._lat_entries: dict[str, TouchEntry] = {}
        self._lat_grid: list[list[str]] = []
        self._lat_grid_pos: dict[str, tuple[int, int]] = {}

        title = Gtk.Label(label="09 CRPS Assessment")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)
        subtitle = Gtk.Label(label="Budapest / Valencia Clinical Criteria (IASP 2004 / 2021)")
        subtitle.add_css_class("reference-note")
        subtitle.set_halign(Gtk.Align.START)
        self.append(subtitle)

        # ── 1 · Disproportionate Pain ────────────────────────────────────────
        self.append(make_subsection_header("1 · Disproportionate Pain", "crps_disp"))
        self.append(self._rule_row("Continuing pain disproportionate to inciting event", "crps_disp_pain"))
        self._notes["crps_disp_pain_notes"] = self._add_notes("crps_disp_pain_notes")

        # ── 2 · Symptoms ──────────────────────────────────────────────────────
        self.append(make_subsection_header("2 · Symptoms  (Patient Reported)", "crps_sx"))
        self._add_rule_desc("Rule 2: ≥ 1 symptom reported in 3 or more of the 4 domains")
        for domain_lbl, items in _SX_DOMAINS:
            self._add_domain(f"sx_{domain_lbl}", domain_lbl, items)
        self._notes["crps_sx_notes"] = self._add_notes("crps_sx_notes")

        # ── 3 · Signs ─────────────────────────────────────────────────────────
        self.append(make_subsection_header("3 · Signs  (Clinician Observed)", "crps_sg"))
        self._add_rule_desc("Rule 3: ≥ 1 sign observed in 2 or more of the 4 domains")
        for domain_lbl, items in _SG_DOMAINS:
            self._add_domain(f"sg_{domain_lbl}", domain_lbl, items)
        self._notes["crps_sg_notes"] = self._add_notes("crps_sg_notes")

        # ── 4 · No Other Diagnosis ────────────────────────────────────────────
        self.append(make_subsection_header("4 · No Other Diagnosis", "crps_no_dx"))
        self.append(self._rule_row("No better diagnosis explains this presentation", "crps_no_alt_dx"))
        self._notes["crps_no_alt_dx_notes"] = self._add_notes("crps_no_alt_dx_notes")

        # ── Criteria Summary ──────────────────────────────────────────────────
        self.append(make_subsection_header("Criteria Summary", "crps_summary_hdr"))
        self.summary_label = Gtk.Label(label="")
        self.summary_label.set_halign(Gtk.Align.START)
        self.summary_label.set_justify(Gtk.Justification.LEFT)
        self.summary_label.set_wrap(True)
        self.summary_label.add_css_class("region-container")
        self.append(self.summary_label)

        # ── Subtype Classification ───────────────────────────────────────────
        self.append(make_subsection_header("Subtype Classification", "crps_subtype_hdr"))
        self._add_rule_desc(
            "T-I = Type I · T-II = Type II · Remit = Remission of Some Features · NOS = Not Otherwise Specified"
        )
        self.subtype = RadioGroup(_SUBTYPE, "crps_subtype")
        self.subtype.connect("changed", self._field_changed)
        self.append(self.subtype)
        self._notes["crps_subtype_notes"] = self._add_notes("crps_subtype_notes")

        self.append(Gtk.Label(label="General Notes:", halign=Gtk.Align.START))
        self._notes["crps_notes"] = self._add_notes("crps_notes")

        # ── 5 · Two-Point Discrimination ─────────────────────────────────────
        self.append(make_subsection_header("5 · Two-Point Discrimination", "crps_tpd"))
        self._notes["crps_tpd_notes"] = self._add_notes("crps_tpd_notes")

        # ── 6 · Visualisation ─────────────────────────────────────────────────
        self.append(make_subsection_header("6 · Visualisation", "crps_vis"))
        self._notes["crps_vis_notes"] = self._add_notes("crps_vis_notes")

        # ── 7 · Laterality ────────────────────────────────────────────────────
        self.append(make_subsection_header("7 · Laterality", "crps_lat"))
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spacer = Gtk.Label(label="")
        spacer.set_size_request(90, -1)
        hdr.append(spacer)
        for _, hdr_lbl, _unit in _LAT_COLS:
            l = Gtk.Label(label=hdr_lbl)
            l.set_hexpand(True)
            hdr.append(l)
        self.append(hdr)
        for row_key, row_label in _LAT_ROWS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=row_label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(90, -1)
            row.append(lbl)
            row_ids = []
            for col_key, _hdr_lbl, unit in _LAT_COLS:
                fid = f"crps_lat_{row_key}_{col_key}"
                entry = TouchEntry(fid, placeholder=unit)
                entry.set_hexpand(True)
                entry.connect("changed", self._field_changed)
                entry.connect("navigate", self._on_lat_navigate)
                self._lat_entries[fid] = entry
                row.append(entry)
                row_ids.append(fid)
            row_idx = len(self._lat_grid)
            self._lat_grid.append(row_ids)
            for col_idx, fid in enumerate(row_ids):
                self._lat_grid_pos[fid] = (row_idx, col_idx)
            self.append(row)
        self._notes["crps_lat_notes"] = self._add_notes("crps_lat_notes")

        self._update_indicators_and_summary()

    # ------------------------------------------------------------------
    # Row builders
    # ------------------------------------------------------------------

    def _rule_row(self, label: str, fid: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("grid-row")
        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        lbl.set_wrap(True)
        row.append(lbl)
        btn = FlagButton("Confirmed", fid)
        btn.connect("changed", self._field_changed)
        self._flags[fid] = btn
        row.append(btn)
        return row

    def _add_rule_desc(self, text: str) -> None:
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("reference-note")
        lbl.set_halign(Gtk.Align.START)
        self.append(lbl)

    def _add_domain(self, ind_key: str, domain_lbl: str, items: list[tuple[str, str]]) -> None:
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_lbl = Gtk.Label(label=domain_lbl)
        name_lbl.set_hexpand(True)
        name_lbl.set_halign(Gtk.Align.START)
        hdr.append(name_lbl)
        ind_lbl = Gtk.Label(label="○ –")
        self._domain_indicators[ind_key] = ind_lbl
        hdr.append(ind_lbl)
        self.append(hdr)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, homogeneous=True)
        for fid, flabel in items:
            btn = FlagButton(flabel, fid)
            btn.connect("changed", self._field_changed)
            self._flags[fid] = btn
            row.append(btn)
        self.append(row)

    def _add_notes(self, notes_id: str) -> AutoTextView:
        ta = AutoTextView(notes_id, min_lines=2)
        ta.textview.get_buffer().connect("changed", self._field_changed)
        self.append(ta)
        return ta

    # ------------------------------------------------------------------
    # Laterality grid nav
    # ------------------------------------------------------------------

    def _on_lat_navigate(self, widget: TouchEntry, direction: str) -> None:
        fid = widget.field_id
        if fid not in self._lat_grid_pos:
            return
        row, col = self._lat_grid_pos[fid]
        grid = self._lat_grid
        target = None
        if direction == "up" and row > 0:
            target = grid[row - 1][col]
        elif direction == "down" and row < len(grid) - 1:
            target = grid[row + 1][col]
        elif direction == "left" and col > 0:
            target = grid[row][col - 1]
        elif direction == "right" and col < len(grid[row]) - 1:
            target = grid[row][col + 1]
        if target is not None:
            self._lat_entries[target].grab_focus()

    # ------------------------------------------------------------------
    # Reactive indicators + summary
    # ------------------------------------------------------------------

    def _domain_triggered(self, items: list[tuple[str, str]]) -> bool:
        return any(self._flags[fid].value is True for fid, _ in items)

    def _update_indicators_and_summary(self) -> None:
        for prefix, domains in (("sx_", _SX_DOMAINS), ("sg_", _SG_DOMAINS)):
            for domain_lbl, items in domains:
                triggered = self._domain_triggered(items)
                ind = self._domain_indicators[f"{prefix}{domain_lbl}"]
                ind.set_label("■ triggered" if triggered else "○ –")

        sx_t = sum(1 for _, items in _SX_DOMAINS if self._domain_triggered(items))
        sg_t = sum(1 for _, items in _SG_DOMAINS if self._domain_triggered(items))
        disp = self._flags["crps_disp_pain"].value
        no_dx = self._flags["crps_no_alt_dx"].value

        r2_met = sx_t >= 3
        r3_met = sg_t >= 2
        all_met = disp is True and r2_met and r3_met and no_dx is True

        def _s(v) -> str:
            return "✓" if v is True else "✗" if v is False else "–"

        summary = (
            f"Rule 1 · Disproportionate pain  :  {_s(disp)}\n"
            f"Rule 2 · Symptom domains        :  {sx_t} / 4  (need ≥ 3)  {'✓' if r2_met else '✗'}\n"
            f"Rule 3 · Sign domains           :  {sg_t} / 4  (need ≥ 2)  {'✓' if r3_met else '✗'}\n"
            f"Rule 4 · No other diagnosis     :  {_s(no_dx)}\n\n"
            f"Clinical Criteria:  {'CRITERIA MET' if all_met else 'CRITERIA NOT MET'}"
        )
        self.summary_label.set_label(summary)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _field_changed(self, *_args) -> None:
        if self._loading:
            return
        self._update_indicators_and_summary()
        if self._on_changed:
            self._on_changed()

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    def focus_first_field(self) -> None:
        self._flags["crps_disp_pain"].grab_focus()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def collect(self) -> dict:
        data: dict = {}
        for fid in _ALL_FLAG_IDS:
            data[fid] = self._flags[fid].value
        data["crps_subtype"] = self.subtype.value
        for tid, ta in self._notes.items():
            data[tid] = ta.text
        for lid, entry in self._lat_entries.items():
            data[lid] = entry.text.strip()

        sx_t = sum(1 for _, items in _SX_DOMAINS if self._domain_triggered(items))
        sg_t = sum(1 for _, items in _SG_DOMAINS if self._domain_triggered(items))
        disp = data.get("crps_disp_pain")
        no_dx = data.get("crps_no_alt_dx")
        data["crps_sx_domains_triggered"] = sx_t
        data["crps_sg_domains_triggered"] = sg_t
        data["crps_criteria_met"] = disp is True and sx_t >= 3 and sg_t >= 2 and no_dx is True
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            for fid in _ALL_FLAG_IDS:
                self._flags[fid].set_value(data.get(fid))
            self.subtype.set_value(data.get("crps_subtype"))
            for tid, ta in self._notes.items():
                ta.text = data.get(tid, "")
            for lid, entry in self._lat_entries.items():
                entry.text = data.get(lid, "")
        finally:
            self._loading = False
        self._update_indicators_and_summary()

    def is_complete(self) -> bool:
        return self._flags["crps_disp_pain"].value is not None
