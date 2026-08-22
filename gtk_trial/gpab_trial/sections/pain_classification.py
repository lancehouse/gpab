"""Pain Type Classification — GTK4 port of pab_assessment/sections/pain_classification.py.

Field ids and collect()/load() keys are 1:1 with the TUI section. Two pieces
of the TUI section are deliberately NOT ported here, flagged rather than
faked:

- The embedded RegionalDifferentialPanel (regional_differential.py) — a
  clinical-KB-backed panel (reads clinical_kb.db via objective/kb_db.py,
  objective/kb_loader.py) that mounts/unmounts based on which body regions
  are active. That's Phase 4 (KB integration) territory per
  CONVERSION_PLAN.md, and regional_differential.py itself is still a
  separate, not-yet-ported Phase 1 file. The container this section would
  mount panels into is present (self.diff_region_box) but stays empty, with
  a visible note explaining why, rather than stubbing in fake KB content.
- The individual xref_* cross-reference badges next to specific fields
  (e.g. "Subj: morning stiffness recorded" beside Inflammatory's morning-pain
  toggle) — update_cross_refs() still runs (see below) and computes the same
  data the TUI does, but isn't wired to a per-field badge widget yet; this
  is a rendering-only gap, not a missing capability.

update_cross_refs() mirrors the TUI's actual behaviour (assessment_view.py's
_show_section): called with an in-memory dict of {"medical": ..., "subjective":
...} collected live from the sibling sections' widgets, not read from disk —
see app.py's _show_section, which calls this on switching to this tab.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..section_base import SectionBase
from ..widgets import (
    FlagButton, AutoTextView, TouchEntry, LikelihoodField, PainTypeSelector,
    make_subsection_header as _header,
    make_subgroup_header as _subheader,
    field_row as _field_row,
)

_INFL_FIELDS = ["infl_constant", "infl_morning", "infl_sleep", "infl_activity"]

_TEXT_FIELDS = [
    "noci_interpretation", "neuro_interpretation",
    "nocip_interpretation", "summary_contributing", "summary_reasoning",
    "bacpap_notes",
]

_BACPAP_STEP5 = ("bacpap_static", "bacpap_dynamic", "bacpap_thermal", "bacpap_after")
_BACPAP_HYPER = ("bacpap_hyper_touch", "bacpap_hyper_movement", "bacpap_hyper_pressure",
                 "bacpap_hyper_heat", "bacpap_hyper_cold")
_BACPAP_COMO = ("bacpap_como_sensory", "bacpap_como_sleep", "bacpap_como_fatigue",
                "bacpap_como_cognitive")


def _alert_label() -> Gtk.Label:
    lbl = Gtk.Label(label="")
    lbl.set_halign(Gtk.Align.START)
    lbl.set_wrap(True)
    lbl.add_css_class("rf-alert-warning")
    lbl.set_visible(False)
    return lbl


class PainClassificationSection(Gtk.Box, SectionBase):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None

        self._toggles: dict[str, FlagButton] = {}
        self._likelihoods: dict[str, LikelihoodField] = {}
        self._texts: dict[str, AutoTextView] = {}

        title = Gtk.Label(label="Pain Type Classification")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        self.append(_header("Regional Differential (deferred)"))
        deferred_note = Gtk.Label(
            label="Not built yet — depends on regional_differential.py + clinical "
                  "KB integration (Phase 4). See this file's module docstring.",
        )
        deferred_note.add_css_class("reference-note")
        deferred_note.set_halign(Gtk.Align.START)
        deferred_note.set_wrap(True)
        self.append(deferred_note)
        self.diff_region_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.append(self.diff_region_box)

        self._build_inflammatory()
        self._build_nociceptive()
        self._build_neuropathic()
        self._build_nociplastic()
        self._build_central_sensitisation()
        self._build_fibromyalgia()
        self._build_bacpap()
        self._build_summary()

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

    def _text(self, field_id: str, min_lines: int = 2) -> AutoTextView:
        w = AutoTextView(field_id, min_lines=min_lines)
        w.textview.get_buffer().connect("changed", self._field_changed)
        self._texts[field_id] = w
        return w

    def _likelihood(self, label: str, field_id: str) -> LikelihoodField:
        w = LikelihoodField(label, field_id)
        w.connect("changed", self._field_changed)
        self._likelihoods[field_id] = w
        return w

    def _reference(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("reference-note")
        lbl.set_halign(Gtk.Align.START)
        return lbl

    def _btn_row(self, *widgets: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for w in widgets:
            row.append(w)
        return row

    # ------------------------------------------------------------------
    # Inflammatory
    # ------------------------------------------------------------------

    def _build_inflammatory(self) -> None:
        self.append(_header("Inflammatory Pain"))
        self.append(self._reference("Walker & Williamson 2008"))
        self.append(self._btn_row(
            self._flag("Constant symptoms", "infl_constant"),
            self._flag("Morning pain/stiffness >30 min", "infl_morning"),
        ))
        self.append(self._btn_row(
            self._flag("Sleep disturbance (moderate+)", "infl_sleep"),
            self._flag("Better with activity", "infl_activity"),
        ))
        self.infl_score_label = Gtk.Label(label="Score: 0/4")
        self.infl_score_label.set_halign(Gtk.Align.START)
        self.append(self.infl_score_label)
        self.infl_alert_label = _alert_label()
        self.append(self.infl_alert_label)
        self.append(self._likelihood("Inflammatory likelihood:", "infl_likelihood"))

    # ------------------------------------------------------------------
    # Nociceptive
    # ------------------------------------------------------------------

    def _build_nociceptive(self) -> None:
        self.append(_header("Nociceptive Pain"))
        self.append(self._reference(
            "Smart et al 2010 — pain from actual or threatened non-neural tissue damage"
        ))
        self.append(_subheader("Subjective:"))
        self.append(self._btn_row(
            self._flag("Mechanical agg/ease factors", "noci_subj_mechanical"),
            self._flag("Proportionate to trauma/pathology", "noci_subj_trauma"),
            self._flag("Localised ±somatic referral", "noci_subj_localised"),
        ))
        self.append(self._btn_row(
            self._flag("Resolves in healing timeframes", "noci_subj_resolving"),
            self._flag("Responsive to analgesia/NSAIDs", "noci_subj_analgesia"),
            self._flag("No constant/unremitting pain", "noci_subj_no_constant"),
        ))
        self.append(self._btn_row(
            self._flag("Associated with inflammation", "noci_subj_inflammation"),
            self._flag("Recent onset", "noci_subj_recent"),
        ))
        self.append(_subheader("Examination:"))
        self.append(self._btn_row(
            self._flag("Mechanical pattern on testing", "noci_exam_mechanical"),
            self._flag("Localised on palpation", "noci_exam_palpation"),
            self._flag("Proportionate hyperalgesia", "noci_exam_hyperalgesia"),
            self._flag("Antalgic posture/movement", "noci_exam_antalgic"),
        ))
        self.append(self._likelihood("Nociceptive likelihood:", "noci_likelihood"))
        self.append(_field_row("Interpretation:", self._text("noci_interpretation")))

    # ------------------------------------------------------------------
    # Neuropathic
    # ------------------------------------------------------------------

    def _build_neuropathic(self) -> None:
        self.append(_header("Neuropathic Pain"))
        self.append(self._reference(
            "Smart et al 2010 — pain from somatosensory nervous system lesion/disease"
        ))
        self.append(_subheader("Subjective:"))
        self.append(self._btn_row(
            self._flag("Burning/shooting/electric quality", "neuro_subj_quality"),
            self._flag("Hx of nerve injury", "neuro_subj_nerve_injury"),
            self._flag("Neurological Sx/paraesthesia", "neuro_subj_neurological"),
        ))
        self.append(self._btn_row(
            self._flag("Dermatomal distribution", "neuro_subj_dermatomal"),
            self._flag("Anti-epileptic/AD responsive", "neuro_subj_medication"),
            self._flag("High severity/irritability", "neuro_subj_severity"),
        ))
        self.append(self._btn_row(
            self._flag("Neural tissue loading pattern", "neuro_subj_neural_loading"),
            self._flag("Dysaesthesias (burn/cold/crawl)", "neuro_subj_dysaesthesia"),
            self._flag("Spontaneous/paroxysmal pain", "neuro_subj_spontaneous"),
        ))
        self.append(_subheader("Examination:"))
        self.append(self._btn_row(
            self._flag("Provoc neurodynamic tests", "neuro_exam_neurodynamic"),
            self._flag("Neural tissue palpation +", "neuro_exam_neural_palpation"),
            self._flag("Positive neurological findings", "neuro_exam_neurology"),
            self._flag("Antalgic limb posture", "neuro_exam_antalgic"),
        ))
        self.append(self._flag("Hyperalgesia/allodynia in distribution", "neuro_exam_hyperalgesia"))
        self.append(self._likelihood("Neuropathic likelihood:", "neuro_likelihood"))
        self.append(_field_row("Interpretation:", self._text("neuro_interpretation")))

    # ------------------------------------------------------------------
    # Nociplastic
    # ------------------------------------------------------------------

    def _build_nociplastic(self) -> None:
        self.append(_header("Nociplastic Pain"))
        self.append(self._reference(
            "IASP — pain from altered nociception, no clear nociceptive/neuropathic cause"
        ))
        self.append(_subheader("Subjective:"))
        self.append(self._btn_row(
            self._flag("Disproportionate/unpredictable", "nocip_subj_disproportionate"),
            self._flag("Beyond healing timeframes", "nocip_subj_persistent"),
            self._flag("Disproportionate to pathology", "nocip_subj_disproportionate2"),
        ))
        self.append(self._btn_row(
            self._flag("Widespread/non-anatomical", "nocip_subj_widespread"),
            self._flag("Failed interventions", "nocip_subj_failed"),
            self._flag("Psychosocial association", "nocip_subj_psychosocial"),
        ))
        self.append(self._btn_row(
            self._flag("Anti-epileptic/AD responsive", "nocip_subj_medication"),
            self._flag("Spontaneous/paroxysmal pain", "nocip_subj_spontaneous"),
            self._flag("High functional disability", "nocip_subj_disability"),
        ))
        self.append(self._btn_row(
            self._flag("Constant/unremitting pain", "nocip_subj_constant"),
            self._flag("Night pain/disturbed sleep", "nocip_subj_night_pain"),
            self._flag("Dysaesthesias (burn/cold/crawl)", "nocip_subj_dysaesthesia"),
        ))
        self.append(self._flag("High severity/irritability", "nocip_subj_severity"))
        self.append(_subheader("Examination:"))
        self.append(self._btn_row(
            self._flag("Disproportionate provocation", "nocip_exam_disproportionate"),
            self._flag("Hyperalgesia/allodynia", "nocip_exam_hyperalgesia"),
            self._flag("Diffuse non-anatomic tenderness", "nocip_exam_diffuse"),
            self._flag("Psychosocial (catastroph/FA)", "nocip_exam_psychosocial"),
        ))
        self.append(self._likelihood("Nociplastic likelihood:", "nocip_likelihood"))
        self.append(_field_row("Interpretation:", self._text("nocip_interpretation")))

    # ------------------------------------------------------------------
    # Central Sensitisation
    # ------------------------------------------------------------------

    def _build_central_sensitisation(self) -> None:
        self.append(_header("Central Sensitisation"))
        self.append(self._reference("Nijs et al 2010, Neblett et al 2013"))
        self.append(_field_row("CSI score (0–100):", self._make_csi_entry()))
        self.csi_alert_label = _alert_label()
        self.append(self.csi_alert_label)
        self.append(_subheader("Additional CS features:"))
        self.append(self._btn_row(
            self._flag("Light sensitivity", "cs_light"),
            self._flag("Touch sensitivity", "cs_touch"),
            self._flag("Noise sensitivity", "cs_noise"),
            self._flag("Chemical sensitivity", "cs_pesticides"),
        ))
        self.append(self._btn_row(
            self._flag("Temperature sensitivity", "cs_temperature"),
            self._flag("Fatigue", "cs_fatigue"),
            self._flag("Sleep disturbance", "cs_sleep"),
            self._flag("Concentration difficulty", "cs_concentration"),
        ))
        self.append(self._btn_row(
            self._flag("Limb swelling sensation", "cs_swelling"),
            self._flag("Tingling/numbness", "cs_tingling"),
        ))

    def _make_csi_entry(self) -> TouchEntry:
        self.csi_score = TouchEntry("csi_score", placeholder="0–100")
        self.csi_score.connect("changed", self._field_changed)
        return self.csi_score

    # ------------------------------------------------------------------
    # Fibromyalgia
    # ------------------------------------------------------------------

    def _build_fibromyalgia(self) -> None:
        self.append(_header("Fibromyalgia"))
        self.append(self._reference("Wolfe et al 2016"))
        self.append(self._reference(
            "Criteria A: WPI > 7 and SS > 5  |  Criteria B: WPI 3–6 and SS > 9"
        ))

        score_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.fm_wpi = TouchEntry("fm_wpi", placeholder="0–19")
        self.fm_fatigue = TouchEntry("fm_fatigue", placeholder="0–3")
        self.fm_waking = TouchEntry("fm_waking", placeholder="0–3")
        self.fm_cognitive = TouchEntry("fm_cognitive", placeholder="0–3")
        for entry in (self.fm_wpi, self.fm_fatigue, self.fm_waking, self.fm_cognitive):
            entry.set_size_request(60, -1)
            entry.set_hexpand(False)
            entry.connect("changed", self._field_changed)
        for lbl_text, entry in (
            ("WPI (0–19):", self.fm_wpi), ("Fatigue:", self.fm_fatigue),
            ("Waking:", self.fm_waking), ("Cognition:", self.fm_cognitive),
        ):
            lbl = Gtk.Label(label=lbl_text)
            score_row.append(lbl)
            score_row.append(entry)
        self.fm_ss_label = Gtk.Label(label="SS: —")
        score_row.append(self.fm_ss_label)
        self.append(score_row)

        self.append(_subheader("Additional SS symptoms (1 pt each):"))
        self.append(self._btn_row(
            self._flag("Headaches", "fm_headaches"),
            self._flag("IBS", "fm_ibs"),
            self._flag("Depression", "fm_depression"),
        ))
        self.append(_subheader("Diagnostic criteria:"))
        self.append(self._btn_row(
            self._flag("Symptoms ≥ 3 months", "fm_duration"),
            self._flag("No alternative explanation", "fm_exclusion"),
        ))
        self.fm_alert_label = _alert_label()
        self.append(self.fm_alert_label)

    # ------------------------------------------------------------------
    # BACPAP
    # ------------------------------------------------------------------

    def _build_bacpap(self) -> None:
        self.append(_header("BACPAP LBP Phenotyping"))
        self.append(self._reference(
            "Nijs et al. 2024 — 7-step consensus decision tree for LBP pain phenotyping"
        ))

        self.append(_subheader("Chronicity & distribution:"))
        self.append(self._btn_row(
            self._flag("LBP ≥ 3 months (or half-days in 6 months)", "bacpap_chronic"),
            self._flag("Regional / multifocal / widespread distribution", "bacpap_distribution"),
        ))
        self.append(_subheader("Dominant mechanism:"))
        self.append(self._btn_row(
            self._flag("Nociceptive pain mainly responsible", "bacpap_nociceptive"),
            self._flag("Neuropathic pain mainly responsible", "bacpap_neuropathic"),
        ))
        self.append(_subheader("Evoked hypersensitivity in LBP region — any one of:"))
        self.append(self._btn_row(
            self._flag("Static mechanical allodynia", "bacpap_static"),
            self._flag("Dynamic mechanical allodynia", "bacpap_dynamic"),
        ))
        self.append(self._btn_row(
            self._flag("Heat or cold allodynia", "bacpap_thermal"),
            self._flag("Painful after-sensations", "bacpap_after"),
        ))
        self.append(_subheader("Nociplastic features:"))
        self.append(_subheader("Subjective hypersensitivity to:"))
        self.append(self._btn_row(
            self._flag("Touch", "bacpap_hyper_touch"),
            self._flag("Movement", "bacpap_hyper_movement"),
            self._flag("Pressure", "bacpap_hyper_pressure"),
            self._flag("Heat", "bacpap_hyper_heat"),
            self._flag("Cold", "bacpap_hyper_cold"),
        ))
        self.append(_subheader("Comorbid symptoms:"))
        self.append(self._btn_row(
            self._flag("Sensitive to light, sound, or odours", "bacpap_como_sensory"),
            self._flag("Sleep disturbance", "bacpap_como_sleep"),
            self._flag("Fatigue", "bacpap_como_fatigue"),
            self._flag("Cognitive problems", "bacpap_como_cognitive"),
        ))
        self.bacpap_result_label = _alert_label()
        self.append(self.bacpap_result_label)
        self.append(_field_row("Notes:", self._text("bacpap_notes")))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary(self) -> None:
        self.append(_header("Pain Type Summary"))
        self.summary_dominant = PainTypeSelector("Dominant pain type:", "summary_dominant")
        self.summary_dominant.connect("changed", self._field_changed)
        self.append(self.summary_dominant)
        self.mixed_reminder_label = _alert_label()
        self.append(self.mixed_reminder_label)
        self.append(_field_row("Contributing pain type(s):", self._text("summary_contributing")))
        self.append(_field_row("Clinical reasoning:", self._text("summary_reasoning")))

    # ------------------------------------------------------------------
    # Regional differential panel management — stubbed, see module docstring
    # ------------------------------------------------------------------

    def set_active_regions(self, regions: list[str]) -> None:
        pass

    def set_region_test_data(self, region_id: str, tests: dict) -> None:
        pass

    # ------------------------------------------------------------------
    # Cross-reference badges — computed, not yet rendered per-field
    # (see module docstring). Kept as a real method, not a no-op stub, so
    # app.py's _show_section can call it exactly like the TUI does and the
    # data is ready for badge widgets once those are built.
    # ------------------------------------------------------------------

    def update_cross_refs(self, assessment: dict | None = None) -> dict[str, list[str]]:
        assessment = assessment or {}
        med = assessment.get("medical") or {}
        subj = assessment.get("subjective") or {}
        refs: dict[str, list[str]] = {}

        lines = []
        if (subj.get("morning_stiffness") or "").strip():
            lines.append("Subj: morning stiffness recorded")
        refs["xref_infl_morning"] = lines

        lines = []
        if subj.get("sleep_difficulty") is True:
            lines.append("Subj: sleep difficulty")
        if subj.get("night_waking") is True:
            lines.append("Subj: night waking")
        refs["xref_infl_sleep"] = lines

        lines = []
        if med.get("comorbid_inflammatory") is True:
            lines.append("Med: systemic inflammatory condition")
        if med.get("diff_as_inflammatory") is True:
            lines.append("Med: inflammatory pattern (diff. AS)")
        refs["xref_infl_dx"] = lines

        lines = []
        if subj.get("course_improving") is True:
            lines.append("Subj: course improving")
        if subj.get("course_worsening") is True:
            lines.append("Subj: course worsening")
        refs["xref_noci_resolving"] = lines

        lines = []
        if med.get("rf_bilateral_paraesthesia") is True:
            lines.append("Med: bilateral paraesthesia (red flag +ve)")
        if med.get("rf_saddle_anaesthesia") is True:
            lines.append("Med: saddle anaesthesia (red flag +ve)")
        refs["xref_neuro_neurological"] = lines

        lines = []
        if (subj.get("previous_treatment") or "").strip():
            lines.append("Subj: previous treatment recorded")
        refs["xref_nocip_failed"] = lines

        lines = []
        if subj.get("mood_influences") is True:
            lines.append("Subj: mood influences pain")
        refs["xref_nocip_psych"] = lines

        lines = []
        if subj.get("night_waking") is True:
            lines.append("Subj: night waking")
        refs["xref_nocip_night"] = lines

        lines = []
        if med.get("comorbid_fibromyalgia") is True:
            lines.append("Med: fibromyalgia")
        if med.get("comorbid_whiplash") is True:
            lines.append("Med: chronic whiplash")
        refs["xref_nocip_dx"] = lines

        lines = []
        if med.get("comorbid_cfs") is True:
            lines.append("Med: chronic fatigue syndrome")
        if med.get("comorbid_fatigue_memory") is True:
            lines.append("Med: fatigue/concentration/memory issues")
        refs["xref_cs_fatigue"] = lines

        lines = []
        if subj.get("sleep_difficulty") is True:
            lines.append("Subj: sleep difficulty")
        if subj.get("night_waking") is True:
            lines.append("Subj: night waking")
        if med.get("comorbid_cfs") is True:
            lines.append("Med: CFS")
        refs["xref_cs_sleep"] = lines

        lines = []
        if med.get("comorbid_fatigue_memory") is True:
            lines.append("Med: fatigue/concentration/memory issues")
        if med.get("comorbid_cfs") is True:
            lines.append("Med: CFS")
        refs["xref_cs_concentration"] = lines

        lines = []
        if med.get("rf_bilateral_paraesthesia") is True:
            lines.append("Med: bilateral paraesthesia (red flag +ve)")
        refs["xref_cs_tingling"] = lines

        return refs

    # ------------------------------------------------------------------
    # Auto-update display widgets — mirrors medical.py's scoring methods
    # ------------------------------------------------------------------

    def _update_infl_score(self) -> None:
        score = sum(1 for fid in _INFL_FIELDS if self._toggles[fid].value is True)
        self.infl_score_label.set_label(f"Score: {score}/4")
        if score >= 2:
            self.infl_alert_label.set_label(
                "⚠ Score ≥2 — moderate likelihood of inflammatory processes "
                "as significant barrier to recovery"
            )
            self.infl_alert_label.set_visible(True)
        else:
            self.infl_alert_label.set_visible(False)

    def _update_csi_alert(self) -> None:
        score_str = self.csi_score.text.strip()
        if score_str.isdigit() and int(score_str) >= 40:
            self.csi_alert_label.set_label(
                f"⚠ CSI score {score_str} ≥ 40 — suggestive of central sensitisation"
            )
            self.csi_alert_label.set_visible(True)
        else:
            self.csi_alert_label.set_visible(False)

    def _update_fm_score(self) -> None:
        def _int(entry: TouchEntry) -> int | None:
            v = entry.text.strip()
            return int(v) if v.isdigit() else None

        wpi = _int(self.fm_wpi)
        fatigue = _int(self.fm_fatigue)
        waking = _int(self.fm_waking)
        cognitive = _int(self.fm_cognitive)

        def _yn(fid: str) -> int:
            return 1 if self._toggles[fid].value is True else 0

        additional = _yn("fm_headaches") + _yn("fm_ibs") + _yn("fm_depression")

        ss = None
        if all(v is not None for v in (fatigue, waking, cognitive)):
            ss = fatigue + waking + cognitive + additional
            self.fm_ss_label.set_label(f"SS: {ss}/12")
        else:
            self.fm_ss_label.set_label("SS: —")

        if wpi is not None and ss is not None:
            crit_a = wpi > 7 and ss > 5
            crit_b = 3 <= wpi <= 6 and ss > 9
            duration = self._toggles["fm_duration"].value is True
            exclusion = self._toggles["fm_exclusion"].value is True
            if (crit_a or crit_b) and duration and exclusion:
                label = "A" if crit_a else "B"
                self.fm_alert_label.set_label(f"⚠ Fibromyalgia criteria met — Condition {label}")
                self.fm_alert_label.set_visible(True)
            elif crit_a or crit_b:
                self.fm_alert_label.set_label("Scoring criteria met — confirm duration and exclusion")
                self.fm_alert_label.set_visible(True)
            else:
                self.fm_alert_label.set_visible(False)
        else:
            self.fm_alert_label.set_visible(False)

    def _update_bacpap(self) -> None:
        def val(fid: str):
            return self._toggles[fid].value

        alert = self.bacpap_result_label

        chronic = val("bacpap_chronic")
        if chronic is False:
            alert.set_label("Acute / subacute LBP — BACPAP criteria not applicable")
            alert.set_visible(True)
            return
        if chronic is None:
            alert.set_visible(False)
            return

        distribution = val("bacpap_distribution")
        if distribution is False:
            alert.set_label("Exclude nociplastic — consider nociceptive / neuropathic LBP")
            alert.set_visible(True)
            return
        if distribution is None:
            alert.set_visible(False)
            return

        noci = val("bacpap_nociceptive") is True
        neuro = val("bacpap_neuropathic") is True

        step5_vals = [val(f) for f in _BACPAP_STEP5]
        step5_any_yes = any(v is True for v in step5_vals)
        step5_all_answered = all(v is not None for v in step5_vals)

        if not step5_any_yes:
            if step5_all_answered:
                if noci and not neuro:
                    alert.set_label("Nociceptive LBP — nociplastic excluded")
                elif neuro and not noci:
                    alert.set_label("Neuropathic LBP — nociplastic excluded")
                elif noci and neuro:
                    alert.set_label("Mixed nociceptive + neuropathic LBP — nociplastic excluded")
                else:
                    alert.set_label("Exclude nociplastic LBP")
                alert.set_visible(True)
            else:
                alert.set_visible(False)
            return

        hyper_vals = [val(f) for f in _BACPAP_HYPER]
        hyper_any_yes = any(v is True for v in hyper_vals)
        hyper_all_answered = all(v is not None for v in hyper_vals)
        hx = True if hyper_any_yes else (False if hyper_all_answered else None)

        como_vals = [val(f) for f in _BACPAP_COMO]
        como_any_yes = any(v is True for v in como_vals)
        como_all_answered = all(v is not None for v in como_vals)
        comorbid = True if como_any_yes else (False if como_all_answered else None)

        if hx is None or comorbid is None:
            alert.set_visible(False)
            return

        if noci and neuro:
            mix = " (mixed: nociplastic + nociceptive + neuropathic)"
        elif noci:
            mix = " (mixed: nociplastic + nociceptive)"
        elif neuro:
            mix = " (mixed: nociplastic + neuropathic)"
        else:
            mix = ""

        if hx is True and comorbid is True:
            alert.set_label(f"⚠ Probable nociplastic LBP{mix}")
        else:
            alert.set_label(f"Possible nociplastic LBP{mix}")
        alert.set_visible(True)

    def _update_mixed_reminder(self) -> None:
        if self.summary_dominant.value == "Mixed — unable to determine":
            self.mixed_reminder_label.set_label(
                "Reminder: document plan to determine dominant pain type "
                "during the preparation phase"
            )
            self.mixed_reminder_label.set_visible(True)
        else:
            self.mixed_reminder_label.set_visible(False)

    def _refresh_all_computed(self) -> None:
        self._update_infl_score()
        self._update_csi_alert()
        self._update_fm_score()
        self._update_bacpap()
        self._update_mixed_reminder()

    # ------------------------------------------------------------------
    # Change events
    # ------------------------------------------------------------------

    def _field_changed(self, *_args) -> None:
        if self._loading:
            return
        self._refresh_all_computed()
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
        for fid, w in self._likelihoods.items():
            data[fid] = w.value
        for fid, w in self._texts.items():
            data[fid] = w.text
        data["csi_score"] = self.csi_score.text
        data["fm_wpi"] = self.fm_wpi.text
        data["fm_fatigue"] = self.fm_fatigue.text
        data["fm_waking"] = self.fm_waking.text
        data["fm_cognitive"] = self.fm_cognitive.text
        data["summary_dominant"] = self.summary_dominant.value
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            pain = data if isinstance(data, dict) else {}
            for fid, w in self._toggles.items():
                w.set_value(pain.get(fid))
            for fid, w in self._likelihoods.items():
                w.set_value(pain.get(fid))
            for fid, w in self._texts.items():
                w.text = pain.get(fid, "")
            self.csi_score.text = pain.get("csi_score", "")
            self.fm_wpi.text = pain.get("fm_wpi", "")
            self.fm_fatigue.text = pain.get("fm_fatigue", "")
            self.fm_waking.text = pain.get("fm_waking", "")
            self.fm_cognitive.text = pain.get("fm_cognitive", "")
            self.summary_dominant.set_value(pain.get("summary_dominant"))
        finally:
            self._loading = False
            self._refresh_all_computed()

    def is_complete(self) -> bool:
        return self.summary_dominant.value is not None

    def focus_first_field(self) -> None:
        self._toggles["infl_constant"].grab_focus()
