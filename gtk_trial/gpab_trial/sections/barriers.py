"""Barriers to Recovery — GTK4 port of pab_assessment/sections/barriers.py.

Field ids and collect()/load() keys are 1:1 with the TUI section. Per-field
cross-reference badges aren't rendered yet (same deliberate scope choice as
pain_classification.py/outcome_measures.py) — update_cross_refs() computes
the same data the TUI does and is called from app.py on switching to this
tab, using live in-memory data from Medical/Subjective/Pain Classification/
Outcome Measures/Diagnosis, matching assessment_view.py's own pattern.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..section_base import SectionBase
from ..widgets import (
    CheckButton, FlagButton, AutoTextView, TouchEntry, CycleField,
    make_subsection_header as _header,
)

_DASS_SEVERITY_OPTIONS = [
    ("Mild", "success"), ("Moderate", "warning"),
    ("Severe", "error"), ("Extremely severe", "error"),
]
_PTSD_MECHANISM_OPTIONS = [
    ("Motor vehicle accident", "default"), ("Traumatic work accident", "default"), ("Other", "default"),
]

_MAIN_BARRIERS = [
    "b_noci_disease", "b_noci_pacing", "b_noci_inflammatory", "b_noci_deconditioning",
    "b_noci_movement", "b_noci_gait", "b_noci_strength", "b_noci_deep_muscle",
    "b_noci_overactivity", "b_noci_nerve_mech", "b_noci_diet",
    "b_neuro_confirmed", "b_neuro_unconfirmed",
    "b_nocip_moderate", "b_nocip_crps", "b_nocip_fnd",
    "b_psych_depression", "b_psych_anxiety", "b_psych_stress",
    "b_psych_catastrophising", "b_psych_self_efficacy", "b_psych_unhelpful_beliefs",
    "b_psych_ptsd", "b_psych_readiness",
    "b_sleep_disturbed",
    "b_social_home", "b_social_rtw",
    "b_med_red_flag", "b_med_substance", "b_med_as", "b_med_aaa",
    "b_med_vascular", "b_med_cervical_ha", "b_med_medico_legal",
]


class BarriersSection(Gtk.Box, SectionBase):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None

        self._toggles: dict[str, CheckButton] = {}
        self._cyclefields: dict[str, CycleField] = {}
        self._entries: dict[str, TouchEntry] = {}
        self._texts: dict[str, AutoTextView] = {}

        title = Gtk.Label(label="08 Barriers to Recovery")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        self._build_physical()
        self._build_neuropathic()
        self._build_nociplastic()
        self._build_psychological()
        self._build_sleep_social()
        self._build_medical()
        self._build_custom()

        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("save-status")
        self.status_label.set_halign(Gtk.Align.START)
        self.append(self.status_label)

    # ------------------------------------------------------------------
    # Widget-creation helpers
    # ------------------------------------------------------------------

    def _flag(self, label: str, field_id: str) -> FlagButton:
        w = FlagButton(label, field_id)
        w.connect("changed", self._field_changed)
        self._toggles[field_id] = w
        return w

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

    def _row(self, *widgets: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for w in widgets:
            row.append(w)
        return row

    def _sub_row(self, *widgets: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row.set_margin_start(16)
        for w in widgets:
            row.append(w)
        return row

    def _xref_badge(self) -> Gtk.Label:
        lbl = Gtk.Label(label="")
        lbl.set_halign(Gtk.Align.START)
        lbl.set_wrap(True)
        lbl.add_css_class("reference-note")
        lbl.set_visible(False)
        return lbl

    # ------------------------------------------------------------------
    # Physical / Nociceptive
    # ------------------------------------------------------------------

    def _build_physical(self) -> None:
        self.append(_header("Physical / Nociceptive Barriers"))
        self.xref_noci = self._xref_badge()
        self.append(self.xref_noci)

        self.append(self._flag("Significant disease / pathology / physical factors — nociceptive", "b_noci_disease"))
        self.append(self._row(
            self._flag("Significant pacing issues — boom-bust pattern", "b_noci_pacing"),
            self._flag("Moderate severity inflammatory features", "b_noci_inflammatory"),
        ))
        self.append(self._row(
            self._flag("Deconditioning (>50% activity reduction >3 months)", "b_noci_deconditioning"),
            self._flag("Relevant diet and / or weight issues", "b_noci_diet"),
        ))

        self.append(self._flag("Significant regional reduction in passive movement / resistance", "b_noci_movement"))
        self.append(self._entry("bi_movement_region", placeholder="region or level"))

        self.append(self._flag("Asymmetrical gait — moderate severity", "b_noci_gait"))

        self.append(self._flag("Significant regional strength deficits", "b_noci_strength"))
        self.append(self._sub_row(
            self._flag("Gluteus maximus", "bx_strength_glute_max"),
            self._flag("Gluteus medius / minimus", "bx_strength_glute_med"),
            self._flag("Iliopsoas", "bx_strength_iliopsoas"),
            self._flag("Quadriceps", "bx_strength_quads"),
        ))
        self.append(self._entry("bi_strength_other", placeholder="other muscle(s)"))

        self.append(self._flag("Reduced functional activation — deep / local / postural muscles", "b_noci_deep_muscle"))
        self.append(self._sub_row(
            self._flag("Lumbar multifidus", "bx_deep_multifidus"),
            self._flag("Transversus abdominis", "bx_deep_ta"),
            self._flag("Thoracic erector spinae", "bx_deep_erector"),
        ))
        self.append(self._entry("bi_deep_other", placeholder="other muscle(s)"))

        self.append(self._flag("Significant overactivity of muscles", "b_noci_overactivity"))
        self.append(self._sub_row(
            self._flag("Erector spinae", "bx_over_erector"),
            self._flag("Quadratus lumborum", "bx_over_ql"),
            self._flag("Rectus abdominis", "bx_over_ra"),
            self._flag("External obliques", "bx_over_obliques"),
        ))
        self.append(self._sub_row(
            self._flag("Piriformis", "bx_over_piriformis"),
            self._flag("Iliopsoas", "bx_over_iliopsoas"),
            self._flag("Hamstrings", "bx_over_hamstrings"),
            self._flag("Short hip adductors", "bx_over_adductors"),
        ))
        self.append(self._entry("bi_over_other", placeholder="other muscle(s)"))

        self.append(self._flag("Moderately increased nerve mechanosensitivity", "b_noci_nerve_mech"))
        self.append(self._entry("bi_nerve_region", placeholder="nerve / region"))

    # ------------------------------------------------------------------
    # Neuropathic
    # ------------------------------------------------------------------

    def _build_neuropathic(self) -> None:
        self.append(_header("Neuropathic Barriers"))
        self.xref_neuro = self._xref_badge()
        self.append(self.xref_neuro)
        self.append(self._row(
            self._flag("Moderate neuropathic pain — confirmed nerve injury on investigations", "b_neuro_confirmed"),
            self._flag("Moderate neuropathic pain — without confirmed nerve injury", "b_neuro_unconfirmed"),
        ))

    # ------------------------------------------------------------------
    # Nociplastic
    # ------------------------------------------------------------------

    def _build_nociplastic(self) -> None:
        self.append(_header("Nociplastic / Central Sensitisation Barriers"))
        self.xref_nocip = self._xref_badge()
        self.append(self.xref_nocip)
        self.append(self._row(
            self._flag("Moderate nociplastic pain including central sensitisation", "b_nocip_moderate"),
            self._flag("Confirmed CRPS (Budapest criteria)", "b_nocip_crps"),
            self._flag("Functional neurological disorder", "b_nocip_fnd"),
        ))

    # ------------------------------------------------------------------
    # Psychological
    # ------------------------------------------------------------------

    def _build_psychological(self) -> None:
        self.append(_header("Psychological Barriers"))

        self.xref_depression = self._xref_badge()
        self.append(self.xref_depression)
        self.xref_anxiety = self._xref_badge()
        self.append(self.xref_anxiety)
        self.xref_stress = self._xref_badge()
        self.append(self.xref_stress)

        self.append(self._row(
            self._flag("Depression", "b_psych_depression"),
            self._cycle("bx_dep_severity", _DASS_SEVERITY_OPTIONS),
            self._check("Psychiatry referral", "bx_dep_psychiatry"),
        ))
        self.append(self._row(
            self._flag("Anxiety", "b_psych_anxiety"),
            self._cycle("bx_anx_severity", _DASS_SEVERITY_OPTIONS),
            self._check("Psychiatry referral", "bx_anx_psychiatry"),
        ))
        self.append(self._row(
            self._flag("Stress", "b_psych_stress"),
            self._cycle("bx_stress_severity", _DASS_SEVERITY_OPTIONS),
            self._check("Psychiatry referral", "bx_stress_psychiatry"),
        ))

        self.append(self._row(
            self._flag("Moderate pain catastrophising (PCS)", "b_psych_catastrophising"),
            self._flag("Reduced pain self-efficacy (PSEQ)", "b_psych_self_efficacy"),
        ))
        self.xref_catastrophising = self._xref_badge()
        self.append(self.xref_catastrophising)
        self.xref_self_efficacy = self._xref_badge()
        self.append(self.xref_self_efficacy)

        self.append(self._flag("Moderate unhelpful beliefs impacting pain management", "b_psych_unhelpful_beliefs"))
        self.append(self._sub_row(
            self._flag("Unrealistic recovery expectations", "bx_belief_expectations"),
            self._flag("Strong symptom focus", "bx_belief_symptom_focus"),
            self._flag("Strong cure focus", "bx_belief_cure_focus"),
            self._flag("Desire for further treatment / investigations", "bx_belief_further_tx"),
        ))

        self.append(self._flag("PTSD-type symptoms (PCL-5)", "b_psych_ptsd"))
        self.xref_ptsd = self._xref_badge()
        self.xref_ptsd.add_css_class("rf-alert-warning")
        self.append(self.xref_ptsd)
        self.append(self._row(
            Gtk.Label(label="Mechanism:"),
            self._cycle("bx_ptsd_mechanism", _PTSD_MECHANISM_OPTIONS),
            self._check("Psychiatry referral", "bx_ptsd_psychiatry"),
        ))

        self.append(self._flag("Unclear readiness for change", "b_psych_readiness"))

    # ------------------------------------------------------------------
    # Sleep & Social
    # ------------------------------------------------------------------

    def _build_sleep_social(self) -> None:
        self.append(_header("Sleep & Social / Contextual Barriers"))

        self.append(self._flag("Moderately disturbed sleep due to pain and / or rumination", "b_sleep_disturbed"))
        self.xref_sleep = self._xref_badge()
        self.append(self.xref_sleep)

        self.append(self._flag("Moderate home / social barriers", "b_social_home"))
        self.append(self._sub_row(
            self._flag("Reduced family support", "bx_soc_family_support"),
            self._flag("Reduced social support", "bx_soc_social_support"),
            self._flag("Relationship issues (immediate family)", "bx_soc_relationship"),
        ))
        self.append(self._sub_row(
            self._flag("Personal relationship issues", "bx_soc_personal_rel"),
            self._flag("Financial difficulties", "bx_soc_financial"),
            self._flag("Residential instability", "bx_soc_residential"),
            self._flag("Distance from program location", "bx_soc_distance"),
        ))

        self.append(self._flag("Moderate return-to-work barriers — physical and psychosocial", "b_social_rtw"))

    # ------------------------------------------------------------------
    # Medical
    # ------------------------------------------------------------------

    def _build_medical(self) -> None:
        self.append(_header("Medical / Systemic Barriers"))
        self.xref_red_flag = self._xref_badge()
        self.append(self.xref_red_flag)

        self.append(self._flag("Red flag — requires further investigation", "b_med_red_flag"))
        self.append(self._text("bi_red_flag_detail"))

        self.append(self._flag("Significant maladaptive use of prescription / non-prescription drugs / alcohol", "b_med_substance"))
        self.xref_substance = self._xref_badge()
        self.append(self.xref_substance)
        self.append(self._text("bi_substance_detail"))

        self.append(self._row(
            self._flag("Possible ankylosing spondylitis", "b_med_as"),
            self._flag("Possible lumbar symptoms due to AAA", "b_med_aaa"),
            self._flag("Possible vascular claudication", "b_med_vascular"),
        ))
        self.append(self._row(
            self._flag("Moderate severity cervical headache", "b_med_cervical_ha"),
            self._flag("Medico-legal / claim issues", "b_med_medico_legal"),
        ))

    # ------------------------------------------------------------------
    # Custom Barriers
    # ------------------------------------------------------------------

    def _build_custom(self) -> None:
        self.append(_header("Custom Barriers"))
        self.append(Gtk.Label(label="1. Barrier:", halign=Gtk.Align.START))
        self.append(self._text("custom_1_barrier"))
        self.append(Gtk.Label(label="   Strategy:", halign=Gtk.Align.START))
        self.append(self._text("custom_1_strategy"))
        self.append(Gtk.Label(label="2. Barrier:", halign=Gtk.Align.START))
        self.append(self._text("custom_2_barrier"))
        self.append(Gtk.Label(label="   Strategy:", halign=Gtk.Align.START))
        self.append(self._text("custom_2_strategy"))

    # ------------------------------------------------------------------
    # Cross-reference badges — mirrors the TUI's update_cross_refs exactly,
    # now actually rendered (unlike pain_classification.py/outcome_measures.py,
    # this section already has the named badge Labels wired above, so there's
    # no reason to leave them as data-only like those two).
    # ------------------------------------------------------------------

    def update_cross_refs(self, assessment: dict | None = None) -> None:
        assessment = assessment or {}

        def _sec(key):
            v = assessment.get(key)
            return v if isinstance(v, dict) else {}

        med = _sec("medical")
        subj = _sec("subjective")
        pc = _sec("pain_classification")
        om = _sec("outcome_measures")
        dx = _sec("diagnosis")

        def _set(label: Gtk.Label, lines: list[str]) -> None:
            if lines:
                label.set_label("  ".join(f"◀ {l}" for l in lines))
                label.set_visible(True)
            else:
                label.set_visible(False)

        dominant = pc.get("summary_dominant")

        lines = []
        if dominant:
            lines.append(f"PC: dominant type = {dominant}")
        mech = dx.get("mechanism")
        if mech:
            lines.append(f"Dx: mechanism = {mech}")
        _set(self.xref_noci, lines)

        lines = []
        if med.get("rf_bilateral_paraesthesia") is True:
            lines.append("Med: bilateral paraesthesia (red flag +ve)")
        if med.get("rf_saddle_anaesthesia") is True:
            lines.append("Med: saddle anaesthesia (red flag +ve)")
        if dominant:
            lines.append(f"PC: dominant type = {dominant}")
        _set(self.xref_neuro, lines)

        lines = []
        if dominant:
            lines.append(f"PC: dominant type = {dominant}")
        if dx.get("primary_subtype") == "CRPS type I":
            lines.append("Dx: CRPS type I selected")
        _set(self.xref_nocip, lines)

        lines = []
        score = (om.get("dass_dep_score") or "").strip()
        interp = om.get("dass_dep_interp")
        if score:
            lines.append(f"OM: DASS depression score = {score}" + (f" ({interp})" if interp else ""))
        _set(self.xref_depression, lines)

        lines = []
        score = (om.get("dass_anx_score") or "").strip()
        interp = om.get("dass_anx_interp")
        if score:
            lines.append(f"OM: DASS anxiety score = {score}" + (f" ({interp})" if interp else ""))
        _set(self.xref_anxiety, lines)

        lines = []
        score = (om.get("dass_str_score") or "").strip()
        interp = om.get("dass_str_interp")
        if score:
            lines.append(f"OM: DASS stress score = {score}" + (f" ({interp})" if interp else ""))
        _set(self.xref_stress, lines)

        lines = []
        score = (om.get("pcs_total_score") or "").strip()
        risk = om.get("pcs_total_risk")
        if score:
            lines.append(f"OM: PCS total = {score}" + (f" ({risk})" if risk else ""))
        _set(self.xref_catastrophising, lines)

        lines = []
        score = (om.get("pseq_score") or "").strip()
        if score:
            lines.append(f"OM: PSEQ score = {score}")
        _set(self.xref_self_efficacy, lines)

        lines = []
        score = (om.get("pcl5_score") or "").strip()
        interp = om.get("pcl5_interp")
        if score:
            lines.append(f"OM: PCL-5 score = {score}" + (f" ({interp})" if interp else ""))
        if subj.get("self_harm_risk") is True:
            lines.append("Subj: self-harm risk flagged")
        _set(self.xref_ptsd, lines)

        lines = []
        score = (om.get("isi_score") or "").strip()
        interp = om.get("isi_interp")
        if score:
            lines.append(f"OM: ISI score = {score}" + (f" ({interp})" if interp else ""))
        if subj.get("sleep_difficulty") is True:
            lines.append("Subj: sleep difficulty reported")
        _set(self.xref_sleep, lines)

        rf_fields = [
            ("rf_saddle_anaesthesia", "saddle anaesthesia"),
            ("rf_bladder_disturbance", "bladder disturbance"),
            ("rf_bowel_disturbance", "bowel disturbance"),
            ("rf_bilateral_paraesthesia", "bilateral paraesthesia"),
            ("rf_gait_disturbance", "gait disturbance"),
        ]
        lines = [f"Med: {label} +ve" for fid, label in rf_fields if med.get(fid) is True]
        _set(self.xref_red_flag, lines)

        lines = []
        if med.get("comorbid_drug_alcohol") is True:
            lines.append("Med: drug / alcohol comorbidity flagged")
        _set(self.xref_substance, lines)

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
            br = data if isinstance(data, dict) else {}
            for fid, w in self._toggles.items():
                w.set_value(br.get(fid))
            for fid, w in self._cyclefields.items():
                w.set_value(br.get(fid))
            for fid, w in self._entries.items():
                w.text = br.get(fid, "")
            for fid, w in self._texts.items():
                w.text = br.get(fid, "")
        finally:
            self._loading = False
            self.update_cross_refs()

    def is_complete(self) -> bool:
        return any(self._toggles[fid].value is not None for fid in _MAIN_BARRIERS)

    def focus_first_field(self) -> None:
        self._toggles["b_noci_disease"].grab_focus()
