"""Rx & Treatment Plan — GTK4 port of pab_assessment/sections/rx_plan.py.

Field ids and collect()/load() keys are 1:1 with the TUI section. No
cross-reference badges in the TUI version of this section, so none here.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..section_base import SectionBase
from ..widgets import (
    CheckButton, AutoTextView, TouchEntry, CycleField,
    make_subsection_header as _header,
    field_row as _field_row,
)

_PAIN_TYPE_OPTIONS = [("1 — Nociceptive / Neuropathic", "primary"), ("2 — Nociplastic", "warning")]
_DEBUNK_OPTIONS = [("Yes", "success"), ("No", "error"), ("N/A", "default")]

_CONSENT_ITEMS = [
    ("Consent to discuss explanation", "tx_consent_explanation"),
    ("Consent to discuss content", "s1_consent_content"),
    ("Email obtained for resources", "tx_email_obtained"),
    ("Patient display book provided", "tx_display_book"),
]
_HW_ITEMS = [
    ("Online module — questions / reflections", "hw_online_module"),
    ("Mindfulness / experiential practice", "hw_mindfulness"),
    ("Goal sheet", "hw_goal_sheet"),
    ("Activity diary", "hw_activity_diary"),
    ("Sleep diary", "hw_sleep_diary"),
]
_D1_ITEMS = [
    ("Clear and simple explanation delivered", "d1_explanation"),
    ("Importance of Session 2 communicated", "d1_session2"),
    ("Complexity and hypothesis testing articulated", "d1_hypothesis"),
    ("Diagnosis and formulation provided (implies pain type)", "d1_diagnosis"),
    ("Patient values / preferences / goals articulated", "d1_values"),
    ("Evidence discussed (ePPOC and RCTs referenced)", "d1_evidence"),
    ("Short and long term plan provided", "d1_plan"),
    ("Prognosis and prevention discussed", "d1_prognosis"),
    ("Other stakeholders identified", "d1_stakeholders"),
    ("Confidence / understanding tested", "d1_confidence_tested"),
    ("Questionnaires administered (individualised set)", "d1_questionnaires"),
]
_PS_ITEMS = [
    ("Questionnaires scored", "ps_questionnaires"),
    ("ePPOC components completed", "ps_eppoc"),
    ("PTSD screen scored (if administered)", "ps_ptsd_scored"),
    ("ISI and PBAS scored (if sleep primary problem)", "ps_isi_pbas"),
    ("CSI scored", "ps_csi"),
    ("AUDIT / DUDIT scored (if administered)", "ps_audit_dudit"),
]


class RxPlanSection(Gtk.Box, SectionBase):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None

        self._toggles: dict[str, CheckButton] = {}
        self._notes: dict[str, TouchEntry] = {}
        self._cyclefields: dict[str, CycleField] = {}
        self._entries: dict[str, TouchEntry] = {}
        self._texts: dict[str, AutoTextView] = {}

        title = Gtk.Label(label="09 Rx & Plan")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        self._build_treatment_plan()
        self._build_session1()
        self._build_day1()
        self._build_followup()

        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("save-status")
        self.status_label.set_halign(Gtk.Align.START)
        self.append(self.status_label)

    # ------------------------------------------------------------------
    # Widget-creation helpers
    # ------------------------------------------------------------------

    def _check(self, label: str, field_id: str) -> CheckButton:
        w = CheckButton(label, field_id)
        w.connect("changed", self._field_changed)
        self._toggles[field_id] = w
        return w

    def _cycle(self, field_id: str, options: list[tuple[str, str]]) -> CycleField:
        w = CycleField("", field_id, options=options)
        w.connect("changed", self._field_changed)
        self._cyclefields[field_id] = w
        return w

    def _entry(self, field_id: str, placeholder: str = "") -> TouchEntry:
        w = TouchEntry(field_id, placeholder=placeholder)
        w.set_hexpand(True)
        w.connect("changed", self._field_changed)
        self._entries[field_id] = w
        return w

    def _text(self, field_id: str, min_lines: int = 2) -> AutoTextView:
        w = AutoTextView(field_id, min_lines=min_lines)
        w.textview.get_buffer().connect("changed", self._field_changed)
        self._texts[field_id] = w
        return w

    def _stmt_row(self, label: str, field_id: str) -> Gtk.Box:
        """CheckButton statement + a notes entry alongside it — the TUI's
        stmt_row pattern used throughout consent/homework/day-1/post-session
        checklists."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(self._check(label, field_id))
        note = TouchEntry(f"{field_id}_note", placeholder="notes")
        note.set_hexpand(True)
        note.connect("changed", self._field_changed)
        self._notes[f"{field_id}_note"] = note
        row.append(note)
        return row

    # ------------------------------------------------------------------
    # Treatment Plan Summary
    # ------------------------------------------------------------------

    def _build_treatment_plan(self) -> None:
        self.append(_header("Treatment Plan Summary"))
        self.append(_field_row("Education — pain type:", self._cycle("tx_pain_type", _PAIN_TYPE_OPTIONS)))
        self.append(_field_row("Debunk radiology (nociplastic):", self._cycle("tx_debunk_radiology", _DEBUNK_OPTIONS)))
        self.append(_field_row("Goal orientation:", self._text("tx_goal_orientation")))
        self.append(_field_row("Formulation:", self._text("tx_formulation")))
        self.append(_field_row("Exercise / Rehab program:", self._text("tx_program")))
        self.append(_field_row("Home program:", self._text("tx_home_program")))
        self.append(_field_row("Psychosocial strategies:", self._text("tx_psychosocial")))
        self.append(_field_row("Medical / Referral:", self._text("tx_medical")))
        self.append(_field_row("RTW plan:", self._text("tx_rtw")))

        for label, fid in _CONSENT_ITEMS[:2]:
            self.append(self._stmt_row(label, fid))

    # ------------------------------------------------------------------
    # Session 1 Treatment
    # ------------------------------------------------------------------

    def _build_session1(self) -> None:
        self.append(_header("Session 1 Treatment"))
        note = Gtk.Label(label="(Consider: (1) Specialist treatment; (2) Monitor by others; (3) Referral)")
        note.add_css_class("reference-note")
        note.set_halign(Gtk.Align.START)
        self.append(note)

        self.append(_field_row("Education provided:", self._text("s1_education")))
        self.append(_field_row("Experiential treatment:", self._text("s1_experiential")))
        self.append(_field_row("Confidence NRS (0–10):", self._entry("s1_confidence_nrs", placeholder="0–10")))

        hw_label = Gtk.Label(label="Homework set:")
        hw_label.set_halign(Gtk.Align.START)
        self.append(hw_label)
        for label, fid in _HW_ITEMS:
            self.append(self._stmt_row(label, fid))
        self.append(_field_row("Other homework:", self._text("s1_hw_other")))

        for label, fid in _CONSENT_ITEMS[2:]:
            self.append(self._stmt_row(label, fid))

    # ------------------------------------------------------------------
    # Day 1 Checklist
    # ------------------------------------------------------------------

    def _build_day1(self) -> None:
        self.append(_header("Day 1 Checklist"))
        for label, fid in _D1_ITEMS:
            self.append(self._stmt_row(label, fid))

    # ------------------------------------------------------------------
    # Follow-Up Plan
    # ------------------------------------------------------------------

    def _build_followup(self) -> None:
        self.append(_header("Follow-Up Plan"))
        self.append(_field_row("Next session focus:", self._text("fu_next_focus")))
        self.append(_field_row("Monitoring:", self._text("fu_monitoring")))
        self.append(_field_row("OM re-testing schedule:", self._entry("fu_om_schedule", placeholder="schedule")))

        ps_label = Gtk.Label(label="Post-Session Admin:")
        ps_label.set_halign(Gtk.Align.START)
        self.append(ps_label)
        for label, fid in _PS_ITEMS:
            self.append(self._stmt_row(label, fid))

    # ------------------------------------------------------------------
    # Change events
    # ------------------------------------------------------------------

    def _field_changed(self, *_args) -> None:
        if self._loading:
            return
        if self._on_changed:
            self._on_changed()

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def collect(self) -> dict:
        data: dict = {}
        for fid, w in self._toggles.items():
            data[fid] = w.value
        for fid, w in self._notes.items():
            data[fid] = w.text
        for fid, w in self._cyclefields.items():
            data[fid] = w.value
        for fid, w in self._entries.items():
            data[fid] = w.text
        for fid, w in self._texts.items():
            data[fid] = w.text
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            rp = data if isinstance(data, dict) else {}
            for fid, w in self._toggles.items():
                w.set_value(rp.get(fid))
            for fid, w in self._notes.items():
                w.text = rp.get(fid, "")
            for fid, w in self._cyclefields.items():
                w.set_value(rp.get(fid))
            for fid, w in self._entries.items():
                w.text = rp.get(fid, "")
            for fid, w in self._texts.items():
                w.text = rp.get(fid, "")
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        return self._cyclefields["tx_pain_type"].value is not None

    def focus_first_field(self) -> None:
        self._cyclefields["tx_pain_type"].grab_focus()
