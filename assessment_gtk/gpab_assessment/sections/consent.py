"""Consent & Session Setup — GTK4 port of pab_assessment/sections/consent.py.

Field ids and collect()/load() keys are 1:1 with the TUI section so the
saved dict is schema-compatible with pab_assessment.storage.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..section_base import SectionBase
from ..widgets import (
    CheckButton, FlagButton, AutoTextView, TouchEntry,
    make_subsection_header as _header,
    field_row as _field_row,
)


class ConsentSection(Gtk.Box, SectionBase):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None  # set by app.py: callable(), fired on any field change
        self._on_below_framing_changed = None  # set by app.py: callable(), fired only on
        # fields from "Session Framing" onward (starts the session timer —
        # deliberately narrower than _on_changed, which also covers
        # preferred_name/consent checkboxes above the Session Framing
        # header and shouldn't start the clock)

        title = Gtk.Label(label="Consent & Session Setup")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        # -- Consent -----------------------------------------------------
        self.append(_header("Consent", "cs_consent"))
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, homogeneous=True)
        self.consent_to_proceed = CheckButton("Consent to proceed", "consent_to_proceed")
        self.consent_sensitive_topics = CheckButton("Consent to sensitive topics", "consent_sensitive_topics")
        btn_row.append(self.consent_to_proceed)
        btn_row.append(self.consent_sensitive_topics)
        self.append(btn_row)

        self.preferred_name = TouchEntry("preferred_name", placeholder="patient's preferred name")
        self.append(_field_row("Preferred name (required):", self.preferred_name))

        # -- Session Framing ----------------------------------------------
        self.append(_header("Session Framing", "cs_framing"))
        btn_row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, homogeneous=True)
        self.framing_pain_multifactorial = CheckButton("Pain multifactorial explained", "pain_multifactorial_explained")
        self.framing_education_treatment = CheckButton("Education as treatment explained", "education_as_treatment_explained")
        btn_row2.append(self.framing_pain_multifactorial)
        btn_row2.append(self.framing_education_treatment)
        self.append(btn_row2)

        # -- Patient Perspective (ICE+) -------------------------------------
        self.append(_header("Patient Perspective (ICE+)", "cs_ice"))

        self.reason_for_attending = AutoTextView("reason_for_attending")
        self.append(_field_row("Reason for attending (patient's own words):", self.reason_for_attending))

        self.cause_understanding = CheckButton("Has understanding of cause", "cause_understanding")
        self.append(self.cause_understanding)

        self.cause_understanding_detail = AutoTextView("cause_understanding_detail")
        self.append(_field_row("Patient's understanding of cause:", self.cause_understanding_detail))

        self.prognosis_expectations = AutoTextView("prognosis_expectations")
        self.append(_field_row("Prognosis expectations (timeline & hope):", self.prognosis_expectations))

        self.treatment_preference = AutoTextView("treatment_preference")
        self.append(_field_row("Treatment preference (what will help them):", self.treatment_preference))

        # -- SMART Goals (mirror only — not part of collect(), synced from Subjective) --
        self.append(_header("SMART Goals", "consent_goals"))
        note = Gtk.Label(label="Shared with Subjective section — enter in either place:")
        note.add_css_class("reference-note")
        note.set_halign(Gtk.Align.START)
        self.append(note)
        self.consent_goals: list[AutoTextView] = []
        for i in range(1, 5):
            ta = AutoTextView(f"consent_goal_{i}", min_lines=1)
            self.append(_field_row(f"{i}.", ta))
            self.consent_goals.append(ta)
        # app.py's _sync_goals(source_goals, *dest_sections) reads dest.goals
        # uniformly on every destination section (subjective.py and
        # functional.py both name their own list .goals) — this section is
        # the one place that list is called .consent_goals instead (its own
        # field ids are consent_goal_N, unrelated to the shared dict key),
        # so it needs the same name available under both, or
        # _on_subjective_changed's _sync_goals(..., self.consent, ...) call
        # raises AttributeError on every Subjective edit. Found via chart-
        # watcher verification testing (2026-08-23), pre-existing bug, not
        # something the chart watcher itself touches.
        self.goals = self.consent_goals

        # -- Beliefs --------------------------------------------------------
        self.append(_header("Beliefs", "cs_beliefs"))
        belief_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, homogeneous=True)
        self.belief_hurt_harm = FlagButton("Hurt=Harm", "belief_hurt_harm")
        self.belief_unsafe = FlagButton("Unsafe", "belief_unsafe")
        self.belief_passive = FlagButton("Passive", "belief_passive")
        self.belief_rehab = CheckButton("Rehab", "belief_rehab")
        self.belief_high_se = CheckButton("High SE", "belief_high_se")
        self.belief_internal_locus = CheckButton("Internal locus", "belief_internal_locus")
        for w in (
            self.belief_hurt_harm, self.belief_unsafe, self.belief_passive,
            self.belief_rehab, self.belief_high_se, self.belief_internal_locus,
        ):
            belief_row.append(w)
        self.append(belief_row)

        self.belief_notes = AutoTextView("belief_notes")
        self.append(self.belief_notes)

        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("save-status")
        self.status_label.set_halign(Gtk.Align.START)
        self.append(self.status_label)

        # -- wire change events ----------------------------------------------
        self._checkbuttons = [
            self.consent_to_proceed, self.consent_sensitive_topics,
            self.framing_pain_multifactorial, self.framing_education_treatment,
            self.cause_understanding,
            self.belief_hurt_harm, self.belief_unsafe, self.belief_passive,
            self.belief_rehab, self.belief_high_se, self.belief_internal_locus,
        ]
        for cb in self._checkbuttons:
            cb.connect("changed", self._field_changed)

        self.preferred_name.connect("changed", self._field_changed)

        # consent_goals (SMART Goals, goal_1..4) were previously left
        # unwired entirely — editing them here triggered neither autosave
        # nor the live mirror to Subjective/Functional (_sync_goals, only
        # ever ran off the OTHER sections' own edits) until fixed 2026-08-24.
        for ta in (
            self.reason_for_attending,
            self.cause_understanding_detail, self.prognosis_expectations,
            self.treatment_preference, self.belief_notes,
            *self.consent_goals,
        ):
            ta.textview.get_buffer().connect("changed", self._field_changed)

        # Second, narrower wiring for the session-timer trigger: every field
        # from "Session Framing" onward, EXCLUDING preferred_name and the two
        # Consent checkboxes above it (see _on_below_framing_changed above).
        below_framing_checkbuttons = (
            self.framing_pain_multifactorial, self.framing_education_treatment,
            self.cause_understanding,
            self.belief_hurt_harm, self.belief_unsafe, self.belief_passive,
            self.belief_rehab, self.belief_high_se, self.belief_internal_locus,
        )
        for cb in below_framing_checkbuttons:
            cb.connect("changed", self._below_framing_field_changed)

        for ta in (
            self.reason_for_attending,
            self.cause_understanding_detail, self.prognosis_expectations,
            self.treatment_preference, self.belief_notes,
            *self.consent_goals,
        ):
            ta.textview.get_buffer().connect("changed", self._below_framing_field_changed)

    # ------------------------------------------------------------------

    def _field_changed(self, *_args) -> None:
        if self._loading:
            return
        self._update_status()
        if self._on_changed:
            self._on_changed()

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    def _below_framing_field_changed(self, *_args) -> None:
        if self._loading:
            return
        if self._on_below_framing_changed:
            self._on_below_framing_changed()

    def set_on_below_framing_changed(self, callback) -> None:
        self._on_below_framing_changed = callback

    # ------------------------------------------------------------------
    # Data — keys match pab_assessment.sections.consent.ConsentSection exactly
    # ------------------------------------------------------------------

    def collect(self) -> dict:
        return {
            "consent_to_proceed": self.consent_to_proceed.value,
            "consent_sensitive_topics": self.consent_sensitive_topics.value,
            "preferred_name": self.preferred_name.text,
            "pain_multifactorial_explained": self.framing_pain_multifactorial.value,
            "education_as_treatment_explained": self.framing_education_treatment.value,
            "reason_for_attending": self.reason_for_attending.text,
            "cause_understanding": self.cause_understanding.value,
            "cause_understanding_detail": self.cause_understanding_detail.text,
            "prognosis_expectations": self.prognosis_expectations.text,
            "treatment_preference": self.treatment_preference.text,
            "belief_hurt_harm": self.belief_hurt_harm.value,
            "belief_unsafe": self.belief_unsafe.value,
            "belief_passive": self.belief_passive.value,
            "belief_rehab": self.belief_rehab.value,
            "belief_high_se": self.belief_high_se.value,
            "belief_internal_locus": self.belief_internal_locus.value,
            "belief_notes": self.belief_notes.text,
        }

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            consent = data if isinstance(data, dict) else {}
            self.consent_to_proceed.set_value(consent.get("consent_to_proceed"))
            self.consent_sensitive_topics.set_value(consent.get("consent_sensitive_topics"))
            self.preferred_name.text = consent.get("preferred_name", "")
            self.framing_pain_multifactorial.set_value(consent.get("pain_multifactorial_explained"))
            self.framing_education_treatment.set_value(consent.get("education_as_treatment_explained"))
            self.reason_for_attending.text = consent.get("reason_for_attending", "")
            self.cause_understanding.set_value(consent.get("cause_understanding"))
            self.cause_understanding_detail.text = consent.get("cause_understanding_detail", "")
            self.prognosis_expectations.text = consent.get("prognosis_expectations", "")
            self.treatment_preference.text = consent.get("treatment_preference", "")
            self.belief_hurt_harm.set_value(consent.get("belief_hurt_harm"))
            self.belief_unsafe.set_value(consent.get("belief_unsafe"))
            self.belief_passive.set_value(consent.get("belief_passive"))
            self.belief_rehab.set_value(consent.get("belief_rehab"))
            self.belief_high_se.set_value(consent.get("belief_high_se"))
            self.belief_internal_locus.set_value(consent.get("belief_internal_locus"))
            self.belief_notes.text = consent.get("belief_notes", "")
        finally:
            self._loading = False
            self._update_status()

    def load_goals(self, subjective_data: dict) -> None:
        """Mirror goal_1..4 from the Subjective section's data (display only)."""
        self._loading = True
        try:
            for i, ta in enumerate(self.consent_goals, start=1):
                ta.text = subjective_data.get(f"goal_{i}", "")
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        data = self.collect()
        return bool(data.get("consent_to_proceed") is True and data.get("preferred_name", "").strip())

    def focus_first_field(self) -> None:
        self.consent_to_proceed.grab_focus()

    def _update_status(self) -> None:
        self.status_label.set_label("Consent section complete" if self.is_complete() else "")
