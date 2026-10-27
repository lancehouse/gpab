"""Pain Type Classification — GTK4 port of pab_assessment/sections/pain_classification.py,
reworked 2026-10-10 against Shraim et al. 2026 (Pain 167:1669-1682), the IASP Terminology
Task Force's weighted feature ranking for nociceptive/neuropathic/nociplastic pain.

See assessment_gtk/docs/pain_classification_rework.md for the full field-by-field decision
table this rebuild implements, and assessment_gtk/gpab_assessment/sections/kb/
pain_classification.yaml for the weight/rank/criterion/reference KB content behind every
ranked item (loaded by objective/kb_loader.py's _ASSESSMENT_KB_FILES and shown on focus
via app.py's _on_widget_focused while Ctrl+K is open — nothing here needs to know).

Structural changes from the pre-2026-10-10 version:
  - Inflammatory is no longer an independent pain type. Its 4 flags are nested, starred,
    inside Nociceptive (item 4, "Signs of inflammation") as an acknowledged expansion of
    that single paper item — the paper itself notes the item "might require expansion".
  - Nociceptive/Neuropathic/Nociplastic are each reordered to match the paper's ranked
    weight (highest first), with new fields added for paper items that had no prior
    equivalent, and fields with no paper equivalent demoted into a starred "legacy/
    supplementary" subgroup per pain type rather than deleted outright.
  - Central Sensitisation is no longer an independent subsection. csi_score (with its
    existing >=40 alert) and every cs_* flag have moved into Nociplastic, several of them
    folded into fields that are now SHARED with BACPAP (see _shared_flag() below) rather
    than kept as separate fields — BACPAP is the canonical widget tree for comorbid-
    symptom and evoked-hypersensitivity items; Nociplastic renders a second, live-linked
    instance of the same field ids at the same granularity BACPAP already uses.
  - Fibromyalgia and BACPAP are otherwise unchanged.

One piece of the TUI section is deliberately NOT ported here, flagged rather than
faked:

- The individual xref_* cross-reference badges next to specific fields
  (e.g. "Subj: morning stiffness recorded" beside the nested Inflammatory morning-pain
  toggle) — update_cross_refs() still runs (see below) and computes the same kind of
  data the TUI did, but isn't wired to a per-field badge widget yet; this is a
  rendering-only gap, not a missing capability.

The embedded RegionalDifferentialPanel (sections/regional_differential.py)
IS ported (Phase 4, pre-2026-10-10) — set_active_regions()/set_region_test_data() below
mount/unmount one panel per active body region into self.diff_region_box and push live
test results into it, mirroring the TUI's own set_active_regions/set_region_test_data
exactly. app.py wires the mount timing (after region toggle, after load, after every
objective autosave) and the click-to-KB callback (set_on_request_kb) the same way it
wires set_on_changed elsewhere.

update_cross_refs() mirrors the TUI's actual behaviour (assessment_view.py's
_show_section): called with an in-memory dict of {"medical": ..., "subjective":
...} collected live from the sibling sections' widgets, not read from disk —
see app.py's _show_section, which calls this on switching to this tab.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .. import pab_path_bootstrap  # noqa: F401  (sys.path side effect)
from ..section_base import SectionBase
from ..widgets import (
    FlagButton, AutoTextView, TouchEntry, LikelihoodField, PainTypeSelector,
    make_subsection_header as _header,
    make_subgroup_header as _subheader,
    FieldGrid,
)
from .regional_differential import RegionalDifferentialPanel, RequestKBCallback
from pab_assessment.storage import _PAIN_RETIRED_KEYS  # noqa: E402

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
        self._on_request_kb: RequestKBCallback | None = None
        # Fields the 2026-10-10 rework removed from the tab, as loaded.
        # collect() writes them back unchanged so a save (which replaces the
        # whole section) never erases what a pre-rework session recorded —
        # user decision 2026-10-27. The report shows them under "Retired
        # fields" (storage.py's _PAIN_RETIRED_KEYS).
        self._retired: dict = {}
        self._diff_panels: dict[str, RegionalDifferentialPanel] = {}

        self._toggles: dict[str, FlagButton] = {}
        self._likelihoods: dict[str, LikelihoodField] = {}
        self._texts: dict[str, AutoTextView] = {}
        # field_id -> every FlagButton instance for that field (BACPAP <-> Nociplastic
        # shared fields have 2; everything else has exactly 1, same list as a trivial
        # case so load()/collect() can treat shared and non-shared fields uniformly).
        self._shared_widgets: dict[str, list[FlagButton]] = {}

        title = Gtk.Label(label="Pain Type Classification")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        self.append(_header("Regional Differential"))
        self.diff_region_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self.diff_region_box)

        self._build_nociceptive()
        self._build_neuropathic()
        self._build_nociplastic()
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
        self._shared_widgets.setdefault(field_id, []).append(w)
        return w

    def _shared_flag(self, label: str, field_id: str) -> FlagButton:
        """A FlagButton for a field_id that may be rendered more than once
        (currently: BACPAP <-> Nociplastic's items 4/8/9/10/15 — see module
        docstring and assessment_gtk/docs/pain_classification_rework.md Q3).
        Every instance of the same field_id stays in lockstep: toggling any
        one of them updates every other instance and the stored value alike.
        The first instance built becomes collect()/load()'s canonical entry
        in self._toggles; which one that is doesn't matter functionally,
        only build order (Nociplastic builds before BACPAP, so Nociplastic's
        copy is canonical here)."""
        w = FlagButton(label, field_id)
        self._shared_widgets.setdefault(field_id, []).append(w)
        if field_id not in self._toggles:
            self._toggles[field_id] = w
        w.connect("changed", lambda _w, fid=field_id: self._on_shared_flag_changed(fid, _w))
        return w

    def _on_shared_flag_changed(self, field_id: str, changed_widget: FlagButton) -> None:
        if self._loading:
            return
        value = changed_widget.value
        for w in self._shared_widgets.get(field_id, []):
            if w is not changed_widget and w.value != value:
                w.set_value(value)
        self._refresh_all_computed()
        if self._on_changed:
            self._on_changed()

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
        lbl.set_xalign(0.0)
        lbl.set_wrap(True)
        return lbl

    def _grid(self) -> FieldGrid:
        """One FieldGrid per subsection, so every flag/score/text row in the
        tab lines up on the same 3 equal-width columns (see widgets.py)."""
        g = FieldGrid()
        self.append(g)
        return g

    def _add_likelihood(self, g: FieldGrid, label: str, field_id: str) -> None:
        w = self._likelihood("", field_id)
        w.button.set_hexpand(True)
        g.add_score(label, w)

    # ------------------------------------------------------------------
    # Nociceptive — ranked by relative weight, Shraim et al. 2026 Table 6.
    # No published IASP clinical criteria exist for nociceptive pain (the
    # paper's own framing); Inflammatory (Walker & Williamson 2008) is
    # nested here as item 4's expansion, not an independent pain type.
    # ------------------------------------------------------------------

    def _build_nociceptive(self) -> None:
        self.append(_header("Nociceptive Pain", "pc_nociceptive"))
        g = self._grid()
        g.add_full(self._reference(
            "Ranked by relative weight — Shraim et al. 2026 (Pain 167:1669-1682)"
        ))
        g.add_flags(
            self._flag("1. Provoked by movement, proportionally", "noci_subj_mechanical"),
            self._flag("2. Consistent pattern on exam/movement testing", "noci_exam_mechanical"),
            self._flag("3. Localised distribution", "noci_subj_localised"),
            self._flag("4. Signs of inflammation", "noci_subj_inflammation"),
        )
        g.add_full(_subheader("Inflammatory features (expansion of item 4) *:"))
        g.add_flags(
            self._flag("Constant symptoms *", "infl_constant"),
            self._flag("Morning pain/stiffness >30 min *", "infl_morning"),
            self._flag("Sleep disturbance (moderate+) *", "infl_sleep"),
            self._flag("Better with activity *", "infl_activity"),
        )
        self.infl_score_label = Gtk.Label(label="Inflammatory sub-score: 0/4")
        self.infl_score_label.set_halign(Gtk.Align.START)
        g.add_full(self.infl_score_label)
        self.infl_alert_label = _alert_label()
        g.add_full(self.infl_alert_label)

        g.add_flags(
            self._flag("5. No generalised hypersensitivity", "noci_subj_no_gen_hypersensitivity"),
            self._flag("7. No autonomic symptoms/signs", "noci_subj_no_autonomic"),
            self._flag("8. Imaging findings of potential relevance", "noci_imaging"),
        )
        g.add_score(
            "6. PainDETECT score (cut-off ≤ 12):",
            self._make_touch_entry("noci_painDETECT_score", "0–38"),
        )

        g.add_full(_subheader("Legacy/supplementary features (pre-2026) *:"))
        g.add_flags(
            self._flag("Proportionate to trauma/pathology *", "noci_subj_trauma"),
            self._flag("Resolves in healing timeframes *", "noci_subj_resolving"),
            self._flag("No constant/unremitting pain *", "noci_subj_no_constant"),
            self._flag("Localised on palpation *", "noci_exam_palpation"),
            self._flag("Proportionate hyperalgesia *", "noci_exam_hyperalgesia"),
            self._flag("Antalgic posture/movement *", "noci_exam_antalgic"),
        )

        self._add_likelihood(g, "Nociceptive likelihood:", "noci_likelihood")
        g.add_text("Interpretation:", self._text("noci_interpretation"))

    # ------------------------------------------------------------------
    # Neuropathic — ranked, Shraim et al. 2026 Table 7, mapped to
    # Finnerup et al. 2016 grading criteria.
    # ------------------------------------------------------------------

    def _build_neuropathic(self) -> None:
        self.append(_header("Neuropathic Pain", "pc_neuropathic"))
        g = self._grid()
        g.add_full(self._reference(
            "Ranked by relative weight — Shraim et al. 2026; criteria: Finnerup et al. 2016"
        ))
        g.add_flags(
            self._flag("1. Diagnostic test confirms lesion/disease", "neuro_diagnostic_test"),
            self._flag("2. Sensory signs on exam, plausible distribution", "neuro_exam_neurology"),
            self._flag("3. Electric/shooting/stinging/flashing quality", "neuro_subj_quality"),
            self._flag("4. Dermatomal/plausible distribution", "neuro_subj_dermatomal"),
            self._flag("5. Nonpainful sensory symptoms", "neuro_subj_neurological"),
            self._flag("6. Heat-related sensory symptoms", "neuro_heat_sensory"),
            self._flag("7. Cold-related sensory symptoms", "neuro_cold_sensory"),
            self._flag("9. Motor symptoms/signs", "neuro_exam_motor"),
            self._flag("11. Neural tissue loading pattern", "neuro_subj_neural_loading"),
            self._flag("12. Phantom pain", "neuro_phantom"),
            self._flag("13. Muscle spasticity, plausible distribution", "neuro_spasticity"),
        )
        g.add_score(
            "8. DN4 score (cut-off ≥ 4):",
            self._make_touch_entry("neuro_dn4_score", "0–4"),
        )
        g.add_score(
            "10. Neuropathic Pain Questionnaire score:",
            self._make_touch_entry("neuro_npq_score", "score"),
        )

        g.add_full(_subheader("Legacy/supplementary features (pre-2026) *:"))
        g.add_flags(
            self._flag("Hx of nerve injury *", "neuro_subj_nerve_injury"),
            self._flag("High severity/irritability *", "neuro_subj_severity"),
            self._flag("Spontaneous/paroxysmal pain *", "neuro_subj_spontaneous"),
            self._flag("Provoc neurodynamic tests *", "neuro_exam_neurodynamic"),
            self._flag("Neural tissue palpation + *", "neuro_exam_neural_palpation"),
            self._flag("Antalgic limb posture *", "neuro_exam_antalgic"),
            self._flag("Hyperalgesia/allodynia in distribution *", "neuro_exam_hyperalgesia"),
        )

        self._add_likelihood(g, "Neuropathic likelihood:", "neuro_likelihood")
        g.add_text("Interpretation:", self._text("neuro_interpretation"))

    # ------------------------------------------------------------------
    # Nociplastic — ranked, Shraim et al. 2026 Table 8, mapped to Kosek
    # et al. 2016 criteria. Central Sensitisation (csi_score + cs_* flags)
    # is dissolved in here; items 4/8/9/10/15 are rendered as SHARED
    # instances of BACPAP's own fields (_shared_flag), not duplicates.
    # ------------------------------------------------------------------

    def _build_nociplastic(self) -> None:
        self.append(_header("Nociplastic Pain", "pc_nociplastic"))
        g = self._grid()
        g.add_full(self._reference(
            "Ranked by relative weight — Shraim et al. 2026; criteria: Kosek et al. 2016"
        ))
        g.add_flags(
            self._flag("1. Diffuse/widespread/regional distribution", "nocip_subj_widespread"),
            self._flag("2. Generalised hypersensitivity", "nocip_generalised_hypersensitivity"),
            self._flag("3. Multisite pain (3+ regions)", "nocip_multisite"),
            self._flag("5. Disproportionate exam pattern", "nocip_exam_disproportionate"),
            self._flag("6. Nonneuroanatomical distribution", "nocip_nonneuroanatomical"),
            self._flag("13. Inconsistent/ambiguous test responses", "nocip_inconsistent_responses"),
            self._flag("14. Absent/inconsistent neuro signs", "nocip_absent_inconsistent_signs"),
            self._flag("16. Variable pain-quality descriptors", "nocip_variable_descriptors"),
            self._flag("17. No imaging findings", "nocip_no_imaging"),
            self._flag("18. Pain present >3 months", "nocip_subj_persistent"),
        )

        g.add_full(_subheader("4. Comorbid symptoms (shared with BACPAP):"))
        g.add_flags(
            self._shared_flag("Sleep disturbance", "bacpap_como_sleep"),
            self._shared_flag("Fatigue", "bacpap_como_fatigue"),
            self._shared_flag("Cognitive problems", "bacpap_como_cognitive"),
        )
        g.add_full(_subheader("8. Hypersensitivity in region of pain (shared with BACPAP):"))
        g.add_flags(
            self._shared_flag("Touch", "bacpap_hyper_touch"),
            self._shared_flag("Movement", "bacpap_hyper_movement"),
            self._shared_flag("Pressure", "bacpap_hyper_pressure"),
            self._shared_flag("Heat", "bacpap_hyper_heat"),
            self._shared_flag("Cold", "bacpap_hyper_cold"),
        )
        g.add_full(_subheader(
            "9. Sound/light/odour  ·  10. Evoked touch/pressure allodynia  ·  "
            "15. Evoked heat/cold allodynia (shared with BACPAP):"
        ))
        g.add_flags(
            self._shared_flag("9. Sound/light/odour sensitivity", "bacpap_como_sensory"),
            self._shared_flag("10. Static mechanical allodynia", "bacpap_static"),
            self._shared_flag("10. Dynamic mechanical allodynia", "bacpap_dynamic"),
            self._shared_flag("15. Heat or cold allodynia", "bacpap_thermal"),
        )

        self.csi_alert_label = _alert_label()
        g.add_score("7. CSI score (cut-off ≥ 40):", self._make_csi_entry(), self.csi_alert_label)
        g.add_score(
            "11. RFIQ score (no cut-off proposed):",
            self._make_touch_entry("nocip_rfiq_score", "score"),
        )
        g.add_score(
            "12. FCSS score (no cut-off proposed):",
            self._make_touch_entry("nocip_fcss_score", "score"),
        )

        g.add_full(_subheader("Legacy/supplementary features (pre-2026) *:"))
        g.add_flags(
            self._flag("Disproportionate to stimulus *", "nocip_subj_disproportionate2"),
            self._flag("Spontaneous/paroxysmal pain *", "nocip_subj_spontaneous"),
            self._flag("High functional disability *", "nocip_subj_disability"),
            self._flag("Constant/unremitting pain *", "nocip_subj_constant"),
            self._flag("Night pain/disturbed sleep *", "nocip_subj_night_pain"),
            self._flag("Dysaesthesias (burn/cold/crawl) *", "nocip_subj_dysaesthesia"),
            self._flag("High severity/irritability *", "nocip_subj_severity"),
            self._flag("Hyperalgesia/allodynia (general) *", "nocip_exam_hyperalgesia"),
            self._flag("Limb swelling sensation *", "cs_swelling"),
            self._flag("Tingling/numbness *", "cs_tingling"),
        )

        self._add_likelihood(g, "Nociplastic likelihood:", "nocip_likelihood")
        g.add_text("Interpretation:", self._text("nocip_interpretation"))

    def _make_touch_entry(self, field_id: str, placeholder: str) -> TouchEntry:
        w = TouchEntry(field_id, placeholder=placeholder)
        w.connect("changed", self._field_changed)
        setattr(self, f"_entry_{field_id}", w)
        return w

    def _make_csi_entry(self) -> TouchEntry:
        self.csi_score = TouchEntry("csi_score", placeholder="0–100")
        self.csi_score.connect("changed", self._field_changed)
        return self.csi_score

    # ------------------------------------------------------------------
    # Fibromyalgia — unchanged. RFIQ/FCSS (above) are new, separate
    # nociplastic items, not assumed equivalent to this subscale —
    # flagged for a manual compare-and-report, see pain_classification.yaml.
    # ------------------------------------------------------------------

    def _build_fibromyalgia(self) -> None:
        self.append(_header("Fibromyalgia", "pc_fibromyalgia"))
        g = self._grid()
        g.add_full(self._reference("Wolfe et al 2016"))
        g.add_full(self._reference(
            "Criteria A: WPI > 7 and SS > 5  |  Criteria B: WPI 3–6 and SS > 9"
        ))

        self.fm_wpi = TouchEntry("fm_wpi", placeholder="0–19")
        self.fm_fatigue = TouchEntry("fm_fatigue", placeholder="0–3")
        self.fm_waking = TouchEntry("fm_waking", placeholder="0–3")
        self.fm_cognitive = TouchEntry("fm_cognitive", placeholder="0–3")
        for entry in (self.fm_wpi, self.fm_fatigue, self.fm_waking, self.fm_cognitive):
            entry.connect("changed", self._field_changed)
        self.fm_ss_label = Gtk.Label(label="SS: —")
        self.fm_ss_label.set_halign(Gtk.Align.START)
        g.add_score("WPI (0–19):", self.fm_wpi)
        g.add_score("Fatigue (0–3):", self.fm_fatigue)
        g.add_score("Waking (0–3):", self.fm_waking)
        g.add_score("Cognition (0–3):", self.fm_cognitive, self.fm_ss_label)

        g.add_full(_subheader("Additional SS symptoms (1 pt each):"))
        g.add_flags(
            self._flag("Headaches", "fm_headaches"),
            self._flag("IBS", "fm_ibs"),
            self._flag("Depression", "fm_depression"),
        )
        g.add_full(_subheader("Diagnostic criteria:"))
        g.add_flags(
            self._flag("Symptoms ≥ 3 months", "fm_duration"),
            self._flag("No alternative explanation", "fm_exclusion"),
        )
        self.fm_alert_label = _alert_label()
        g.add_full(self.fm_alert_label)

    # ------------------------------------------------------------------
    # BACPAP — unchanged, and now the canonical widget tree for every
    # field it shares with Nociplastic (see _shared_flag() above).
    # ------------------------------------------------------------------

    def _build_bacpap(self) -> None:
        self.append(_header("BACPAP LBP Phenotyping", "pc_bacpap"))
        g = self._grid()
        g.add_full(self._reference(
            "Nijs et al. 2024 — 7-step consensus decision tree for LBP pain phenotyping"
        ))

        g.add_full(_subheader("Chronicity & distribution  /  Dominant mechanism:"))
        g.add_flags(
            self._flag("LBP ≥ 3 months (or half-days in 6 months)", "bacpap_chronic"),
            self._flag("Regional / multifocal / widespread distribution", "bacpap_distribution"),
            self._flag("Nociceptive pain mainly responsible", "bacpap_nociceptive"),
            self._flag("Neuropathic pain mainly responsible", "bacpap_neuropathic"),
        )
        g.add_full(_subheader("Evoked hypersensitivity in LBP region — any one of:"))
        g.add_flags(
            self._shared_flag("Static mechanical allodynia", "bacpap_static"),
            self._shared_flag("Dynamic mechanical allodynia", "bacpap_dynamic"),
            self._shared_flag("Heat or cold allodynia", "bacpap_thermal"),
            self._flag("Painful after-sensations", "bacpap_after"),
        )
        g.add_full(_subheader("Nociplastic features — subjective hypersensitivity to:"))
        g.add_flags(
            self._shared_flag("Touch", "bacpap_hyper_touch"),
            self._shared_flag("Movement", "bacpap_hyper_movement"),
            self._shared_flag("Pressure", "bacpap_hyper_pressure"),
            self._shared_flag("Heat", "bacpap_hyper_heat"),
            self._shared_flag("Cold", "bacpap_hyper_cold"),
        )
        g.add_full(_subheader("Comorbid symptoms:"))
        g.add_flags(
            self._shared_flag("Sensitive to light, sound, or odours", "bacpap_como_sensory"),
            self._shared_flag("Sleep disturbance", "bacpap_como_sleep"),
            self._shared_flag("Fatigue", "bacpap_como_fatigue"),
            self._shared_flag("Cognitive problems", "bacpap_como_cognitive"),
        )
        self.bacpap_result_label = _alert_label()
        g.add_full(self.bacpap_result_label)
        g.add_text("Notes:", self._text("bacpap_notes"))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary(self) -> None:
        self.append(_header("Pain Type Summary", "pc_summary"))
        g = self._grid()
        self.summary_dominant = PainTypeSelector("", "summary_dominant")
        self.summary_dominant.button.set_hexpand(True)
        self.summary_dominant.connect("changed", self._field_changed)
        self.mixed_reminder_label = _alert_label()
        g.add_score("Dominant pain type:", self.summary_dominant, self.mixed_reminder_label)
        g.add_text("Contributing pain type(s):", self._text("summary_contributing"))
        g.add_text("Clinical reasoning:", self._text("summary_reasoning"))

    # ------------------------------------------------------------------
    # Regional differential panel management
    # ------------------------------------------------------------------

    def set_on_request_kb(self, callback: RequestKBCallback) -> None:
        """Called by app.py to wire click-on-test-row -> Ctrl+K panel, the
        same way set_on_changed wires field edits -> autosave."""
        self._on_request_kb = callback

    def set_active_regions(self, regions: list[str]) -> None:
        """Mount/unmount regional differential panels to match active regions."""
        current = set(self._diff_panels.keys())
        for rid in current - set(regions):
            panel = self._diff_panels.pop(rid)
            self.diff_region_box.remove(panel)
        for rid in set(regions) - current:
            panel = RegionalDifferentialPanel(rid, self._on_request_kb)
            self._diff_panels[rid] = panel
            self.diff_region_box.append(panel)

    def set_region_test_data(self, region_id: str, tests: dict) -> None:
        """Push latest special test results to the matching regional panel."""
        panel = self._diff_panels.get(region_id)
        if panel:
            panel.set_tests(tests)

    # ------------------------------------------------------------------
    # Cross-reference badges — computed, not yet rendered per-field
    # (see module docstring). Kept as a real method, not a no-op stub, so
    # app.py's _show_section can call it exactly like the TUI does and the
    # data is ready for badge widgets once those are built.
    #
    # Re-pointed 2026-10-10: xref_cs_fatigue/sleep/concentration now
    # anchor to bacpap_como_fatigue/sleep/cognitive (the fields that
    # absorbed cs_fatigue/cs_sleep/cs_concentration — see
    # docs/pain_classification_rework.md). xref_nocip_failed and
    # xref_nocip_psych are retired: nocip_subj_failed and
    # nocip_subj_psychosocial were removed in the same rework.
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
        if subj.get("mood_influences") is True:
            lines.append("Subj: mood influences pain")
        refs["xref_nocip_psych"] = lines  # retained for mood-influences data only;
        # NOT shown next to nocip_subj_psychosocial, which was removed — no field to
        # anchor this badge to yet.

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
        refs["xref_bacpap_como_fatigue"] = lines

        lines = []
        if subj.get("sleep_difficulty") is True:
            lines.append("Subj: sleep difficulty")
        if subj.get("night_waking") is True:
            lines.append("Subj: night waking")
        if med.get("comorbid_cfs") is True:
            lines.append("Med: CFS")
        refs["xref_bacpap_como_sleep"] = lines

        lines = []
        if med.get("comorbid_fatigue_memory") is True:
            lines.append("Med: fatigue/concentration/memory issues")
        if med.get("comorbid_cfs") is True:
            lines.append("Med: CFS")
        refs["xref_bacpap_como_cognitive"] = lines

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
        self.infl_score_label.set_label(f"Inflammatory sub-score: {score}/4")
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
                f"⚠ CSI score {score_str} ≥ 40 — suggestive of nociplastic/"
                "central-sensitisation features (Nociplastic item 7)"
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
        data["noci_painDETECT_score"] = self._entry_noci_painDETECT_score.text
        data["neuro_dn4_score"] = self._entry_neuro_dn4_score.text
        data["neuro_npq_score"] = self._entry_neuro_npq_score.text
        data["nocip_rfiq_score"] = self._entry_nocip_rfiq_score.text
        data["nocip_fcss_score"] = self._entry_nocip_fcss_score.text
        data["fm_wpi"] = self.fm_wpi.text
        data["fm_fatigue"] = self.fm_fatigue.text
        data["fm_waking"] = self.fm_waking.text
        data["fm_cognitive"] = self.fm_cognitive.text
        data["summary_dominant"] = self.summary_dominant.value
        data.update(self._retired)
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            pain = data if isinstance(data, dict) else {}
            self._retired = {k: pain[k] for k in _PAIN_RETIRED_KEYS if k in pain}
            for fid, w in self._toggles.items():
                w.set_value(pain.get(fid))
            # Shared fields (BACPAP <-> Nociplastic): propagate the canonical
            # value (just set above, from self._toggles) to every other
            # rendered instance of the same field_id.
            for fid, widgets in self._shared_widgets.items():
                canonical_value = self._toggles[fid].value
                for w in widgets:
                    if w is not self._toggles[fid]:
                        w.set_value(canonical_value)
            for fid, w in self._likelihoods.items():
                w.set_value(pain.get(fid))
            for fid, w in self._texts.items():
                w.text = pain.get(fid, "")
            self.csi_score.text = pain.get("csi_score", "")
            self._entry_noci_painDETECT_score.text = pain.get("noci_painDETECT_score", "")
            self._entry_neuro_dn4_score.text = pain.get("neuro_dn4_score", "")
            self._entry_neuro_npq_score.text = pain.get("neuro_npq_score", "")
            self._entry_nocip_rfiq_score.text = pain.get("nocip_rfiq_score", "")
            self._entry_nocip_fcss_score.text = pain.get("nocip_fcss_score", "")
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
        self._toggles["noci_subj_mechanical"].grab_focus()
