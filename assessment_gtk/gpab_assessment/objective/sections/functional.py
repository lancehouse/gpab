"""Functional Assessment — Objective 07, GTK4 port of
pab_assessment.objective.sections.functional.

Field ids and collect()/load() keys are 1:1 with the TUI (JSON key
"functional" in _objective.json). The SMART Goals block (ft_goal_1..4) is a
live mirror of Consent/Subjective's goals — wired 3-way in app.py, same
pattern as the existing Consent<->Subjective mirror.

Balance + Timed Capability rows get arrow-key grid nav via the shared
GridNav mixin (up/down between rows in the same column); the Functional
Movement rows above them don't (matches the TUI, which only builds
_grid/_grid_pos for the balance/capability tables).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import RadioGroup, TouchEntry, AutoTextView, make_subsection_header
from ...section_base import SectionBase
from ..grid_nav import GridNav

_GAIT2 = [("Norm", "success"), ("Antlgc", "warning")]
_STS3 = [("Norm", "success"), ("Hands", "warning"), ("Asymm", "default")]
_SQ3 = [("Norm", "success"), ("Antlgc", "warning"), ("Asymm", "default")]
_CARRY2 = [("Norm", "success"), ("Antlgc", "warning")]
_REACH2 = [("Norm", "success"), ("Antlgc", "warning")]

# (display label, radio id, radio options, input id)
_FM_ROWS: list[tuple[str, str, list, str]] = [
    ("Gait", "ft_gait", _GAIT2, "ft_gait_obs"),
    ("Sit-to-stand", "ft_sts_q", _STS3, "ft_sts_obs"),
    ("Squat", "ft_squat", _SQ3, "ft_squat_obs"),
    ("Lunge", "ft_lunge", _SQ3, "ft_lunge_obs"),
    ("Lifting", "ft_lift", _SQ3, "ft_lift_obs"),
    ("Carrying", "ft_carry", _CARRY2, "ft_carry_obs"),
    ("Reaching", "ft_reach", _REACH2, "ft_reach_obs"),
]

# (label, [input ids]) — one or two columns
_BAL_ROWS: list[tuple[str, list]] = [
    ("Both legs", ["ft_bal_both"]),
    ("Feet together", ["ft_bal_feet"]),
    ("Tandem", ["ft_bal_tandem"]),
    ("SLS eyes open", ["ft_sls_eo_l", "ft_sls_eo_r"]),
    ("SLS eyes closed", ["ft_sls_ec_l", "ft_sls_ec_r"]),
    ("SLS foam 10cm", ["ft_sls_foam_l", "ft_sls_foam_r"]),
]

# (label, id, unit)
_CAP_ROWS: list[tuple[str, str, str]] = [
    ("TUG  (3m chair→chair)", "ft_tug", "s"),
    ("5x Sit-to-Stand", "ft_sts5", "s"),
    ("10m walk comfortable", "ft_10m_e", "m/s"),
    ("10m walk fast", "ft_10m_f", "m/s"),
    ("2 min walk", "ft_2mw", "m"),
]


class FunctionalSection(Gtk.Box, GridNav, SectionBase):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None
        self._on_goals_changed = None
        self._init_grid()

        self._radio_groups: dict[str, RadioGroup] = {}
        self._fm_inputs: dict[str, TouchEntry] = {}
        self._bal_inputs: dict[str, TouchEntry] = {}
        self._cap_inputs: dict[str, TouchEntry] = {}
        self._widgets_by_id: dict[str, Gtk.Widget] = {}

        title = Gtk.Label(label="02 Functional")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        # ── SMART Goals mirror ──────────────────────────────────────────────
        self.append(make_subsection_header("— SMART Goals —", "fn_goals"))
        ref = Gtk.Label(label="Shared with 01 Consent and 02 Subjective — edit in any section:")
        ref.add_css_class("reference-note")
        ref.set_halign(Gtk.Align.START)
        self.append(ref)
        self.goals: list = []
        for i in range(1, 5):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lbl = Gtk.Label(label=f"{i}.")
            lbl.set_size_request(24, -1)
            lbl.set_valign(Gtk.Align.START)
            row.append(lbl)
            ta = AutoTextView(f"ft_goal_{i}", min_lines=2)
            ta.textview.get_buffer().connect("changed", self._on_goal_changed)
            self.goals.append(ta)
            row.append(ta)
            self.append(row)

        # ── Functional Movement ──────────────────────────────────────────────
        self.append(make_subsection_header("Functional Movement", "fn_movement"))
        for label, rid, opts, iid in _FM_ROWS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(110, -1)
            row.append(lbl)
            rg = RadioGroup(opts, rid)
            rg.connect("changed", self._field_changed)
            self._radio_groups[rid] = rg
            row.append(rg)
            entry = TouchEntry(iid, placeholder="…")
            entry.set_hexpand(True)
            entry.connect("changed", self._field_changed)
            self._fm_inputs[iid] = entry
            row.append(entry)
            self.append(row)

        fm_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fm_lbl = Gtk.Label(label="Functional obs")
        fm_lbl.set_halign(Gtk.Align.START)
        fm_lbl.set_size_request(150, -1)
        fm_row.append(fm_lbl)
        self.fm_obs = AutoTextView("ft_fm_obs", min_lines=2)
        self.fm_obs.textview.get_buffer().connect("changed", self._field_changed)
        fm_row.append(self.fm_obs)
        self.append(fm_row)

        custom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        custom_lbl = Gtk.Label(label="Custom Functional test")
        custom_lbl.set_halign(Gtk.Align.START)
        custom_lbl.set_size_request(150, -1)
        custom_row.append(custom_lbl)
        self.fm_custom = AutoTextView("ft_fm_custom", min_lines=2)
        self.fm_custom.textview.get_buffer().connect("changed", self._field_changed)
        custom_row.append(self.fm_custom)
        self.append(custom_row)

        # ── Balance (Steffen 2002) ───────────────────────────────────────────
        self.append(make_subsection_header("Balance  (Steffen 2002)", "fn_balance"))
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spacer = Gtk.Label(label="")
        spacer.set_size_request(150, -1)
        hdr.append(spacer)
        for side in ("Left  s", "Right  s"):
            slbl = Gtk.Label(label=side)
            slbl.set_hexpand(True)
            hdr.append(slbl)
        self.append(hdr)
        for label, ids in _BAL_ROWS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(150, -1)
            row.append(lbl)
            for fid in ids:
                entry = TouchEntry(fid, placeholder="s")
                entry.set_hexpand(True)
                entry.connect("changed", self._field_changed)
                entry.connect("navigate", self._on_navigate)
                self._bal_inputs[fid] = entry
                row.append(entry)
            if len(ids) == 1:
                row.append(Gtk.Box(hexpand=True))
            self._add_grid_row(ids if len(ids) == 2 else [ids[0]])
            self.append(row)

        # ── Timed Capability Measures ────────────────────────────────────────
        self.append(make_subsection_header("Timed Capability Measures", "fn_timed"))
        for label, fid, unit in _CAP_ROWS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("grid-row")
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(150, -1)
            row.append(lbl)
            entry = TouchEntry(fid, placeholder=unit)
            entry.set_hexpand(True)
            entry.connect("changed", self._field_changed)
            entry.connect("navigate", self._on_navigate)
            self._cap_inputs[fid] = entry
            row.append(entry)
            row.append(Gtk.Box(hexpand=True))
            self._add_grid_row([fid])
            self.append(row)

        self._widgets_by_id = {**self._bal_inputs, **self._cap_inputs}

        self.append(Gtk.Label(label="Special tests / notes:", halign=Gtk.Align.START))
        self.notes = AutoTextView("ft_notes", min_lines=2)
        self.notes.textview.get_buffer().connect("changed", self._field_changed)
        self.append(self.notes)

    # ------------------------------------------------------------------
    # Grid navigation — see objective/grid_nav.py
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

    def _on_goal_changed(self, *_args) -> None:
        if self._loading:
            return
        if self._on_goals_changed:
            self._on_goals_changed()
        self._field_changed()

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    def set_on_goals_changed(self, callback) -> None:
        """Called (in addition to set_on_changed's callback) whenever a goal
        text buffer changes — app.py uses this to keep Consent/Subjective's
        goal mirrors in sync live, same as the existing Consent<->Subjective
        wiring."""
        self._on_goals_changed = callback

    def focus_first_field(self) -> None:
        self.goals[0].grab_focus()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def collect(self) -> dict:
        # ft_goal_1..4 are deliberately NOT included here — the TUI's own
        # FunctionalSection.collect() excludes them too: they're a read-only
        # mirror of Consent/Subjective's goals (populated via load_goals()
        # only), and Consent/Subjective already own saving that data into
        # assessment.json. Including them here would just add unused keys
        # to _objective.json's "functional" block, breaking schema parity.
        data: dict = {}
        for rid, rg in self._radio_groups.items():
            data[rid] = rg.value
        for iid, e in self._fm_inputs.items():
            data[iid] = e.text.strip()
        for fid, e in self._bal_inputs.items():
            data[fid] = e.text.strip()
        for fid, e in self._cap_inputs.items():
            data[fid] = e.text.strip()
        data["ft_fm_obs"] = self.fm_obs.text
        data["ft_fm_custom"] = self.fm_custom.text
        data["ft_notes"] = self.notes.text
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            for rid, rg in self._radio_groups.items():
                rg.set_value(data.get(rid))
            for iid, e in self._fm_inputs.items():
                e.text = data.get(iid, "")
            for fid, e in self._bal_inputs.items():
                e.text = data.get(fid, "")
            for fid, e in self._cap_inputs.items():
                e.text = data.get(fid, "")
            self.fm_obs.text = data.get("ft_fm_obs", "")
            self.fm_custom.text = data.get("ft_fm_custom", "")
            self.notes.text = data.get("ft_notes", "")
        finally:
            self._loading = False

    def load_goals(self, data: dict) -> None:
        """Populate the SMART Goals mirror from subjective data (goal_1..4)."""
        self._loading = True
        try:
            for i, ta in enumerate(self.goals, start=1):
                ta.text = data.get(f"goal_{i}", "")
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        return bool(self._cap_inputs.get("ft_tug") and self._cap_inputs["ft_tug"].text.strip())
