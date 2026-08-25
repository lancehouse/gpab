"""Outcome Measures — GTK4 port of pab_assessment/sections/outcome_measures.py.

Field ids and collect()/load() keys are 1:1 with the TUI section. Two
deliberate simplifications from the TUI version, neither changing the data
schema:

- The TUI's accordion blocks lazily mount their body widgets only on first
  expand (a real perf concern under Textual's rendering model at the time).
  GTK's Gtk.Expander natively shows/hides a pre-built child with no such
  cost at this widget count, so every block's fields are built once, up
  front — no _mounted/_pending_data/drain_pending bookkeeping needed.
- Per-field cross-reference badges (the small "◀ Subj: ..." hints next to
  specific fields) aren't rendered yet — update_cross_refs() still computes
  the same data the TUI does (called from app.py on switching to this tab,
  same in-memory pattern as pain_classification.py), it's just not wired to
  a badge widget per field yet. Same scope choice as pain_classification.py.

Note re: pab-intake (a separate, not-yet-clinic-used patient-facing PROM
collector living in ~/Projects/pab-intake) — that project's own CLAUDE.md
explicitly defers any TUI/PAB import integration ("No changes to
~/Projects/pab/ until this is explicitly requested"). This port matches the
TUI's outcome_measures.py exactly as it stands today: manual entry only, no
_intake.json import path. Not built here for the same reason it isn't built
in the real TUI yet.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..section_base import SectionBase
from ..widgets import (
    CheckButton, AutoTextView, TouchEntry, CycleField,
    make_subsection_header as _header,
)

# measure_id -> grid_overview anchor_id (SUBJ_GRID_DATA "05_outcome_measures"
# row). phq4/pcl5 have no distinct grid heading — PCL-5 shares "PSEQ/PCL"
# (om_pseq) with PSEQ since the grid only lists one combined heading for
# both; PHQ-4 has no heading at all, so it falls back to plain _show_section.
_OM_BLOCK_ANCHOR: dict[str, str | None] = {
    "psfs": "om_psfs", "bpi": "om_bpi", "dass": "om_dass", "phq4": None,
    "pcs": "om_pcs", "pseq": "om_pseq", "pcl5": "om_pseq",
    "sleep": "om_sleep", "additional": "om_additional",
}

_DASS_OPTIONS = [
    ("Normal", "success"), ("Mild", "primary"), ("Moderate", "warning"),
    ("Severe", "error"), ("Extremely severe", "error"),
]
_PCS_TOTAL_OPTIONS = [("Mild (<20)", "success"), ("High", "warning"), ("Severe (>30)", "error")]
_PCS_SUB_OPTIONS = [("Normal", "success"), ("Clinical", "error")]
_PCL5_OPTIONS = [("Negative (<33)", "success"), ("Positive — PTSD likely", "error")]
_ISI_OPTIONS = [("No insomnia (<10)", "success"), ("Clinically significant (≥10)", "error")]
_PBAS_OPTIONS = [("Normal", "success"), ("Moderate", "warning"), ("Severe", "error")]
_PSEQ_OPTIONS = [
    ("Severe (<20)", "error"), ("Moderate (20–30)", "warning"),
    ("Mild (31–40)", "primary"), ("Minimal (>40)", "success"),
]
_PSEQ2_OPTIONS = [("Severe (≤5)", "error"), ("Moderate (6–9)", "warning"), ("Adequate (≥10)", "success")]

_HYP_COLS = ["measure", "baseline", "interval", "rationale"]
_HYP_PLACEHOLDERS = ["Measure", "Baseline", "Interval", "Rationale"]


def _interp_dass_dep(s: int) -> str:
    if s < 10: return "Normal"
    if s < 14: return "Mild"
    if s < 21: return "Moderate"
    if s < 28: return "Severe"
    return "Extremely severe"


def _interp_dass_anx(s: int) -> str:
    if s < 8: return "Normal"
    if s < 10: return "Mild"
    if s < 15: return "Moderate"
    if s < 20: return "Severe"
    return "Extremely severe"


def _interp_dass_str(s: int) -> str:
    if s < 15: return "Normal"
    if s < 19: return "Mild"
    if s < 26: return "Moderate"
    if s < 34: return "Severe"
    return "Extremely severe"


def _interp_pcs_total(s: int) -> str:
    if s < 20: return "Mild (<20)"
    if s <= 30: return "High"
    return "Severe (>30)"


def _interp_pcs_rum(s: int) -> str: return "Clinical" if s >= 11 else "Normal"
def _interp_pcs_mag(s: int) -> str: return "Clinical" if s >= 5 else "Normal"
def _interp_pcs_help(s: int) -> str: return "Clinical" if s >= 13 else "Normal"
def _interp_pcl5(s: int) -> str: return "Positive — PTSD likely" if s >= 33 else "Negative (<33)"
def _interp_isi(s: int) -> str: return "Clinically significant (≥10)" if s >= 10 else "No insomnia (<10)"


def _interp_pseq(s: int) -> str:
    if s < 20: return "Severe (<20)"
    if s <= 30: return "Moderate (20–30)"
    if s <= 40: return "Mild (31–40)"
    return "Minimal (>40)"


def _interp_pseq2(s: int) -> str:
    if s <= 5: return "Severe (≤5)"
    if s <= 9: return "Moderate (6–9)"
    return "Adequate (≥10)"


_AUTO_INTERP = [
    ("dass_dep_score", "dass_dep_interp", _interp_dass_dep),
    ("dass_anx_score", "dass_anx_interp", _interp_dass_anx),
    ("dass_str_score", "dass_str_interp", _interp_dass_str),
    ("pcs_rum_score", "pcs_rum_risk", _interp_pcs_rum),
    ("pcs_mag_score", "pcs_mag_risk", _interp_pcs_mag),
    ("pcs_help_score", "pcs_help_risk", _interp_pcs_help),
    ("pcs_total_score", "pcs_total_risk", _interp_pcs_total),
    ("pcl5_score", "pcl5_interp", _interp_pcl5),
    ("isi_score", "isi_interp", _interp_isi),
    ("pseq_score", "pseq_interp", _interp_pseq),
    ("pseq2_score", "pseq2_interp", _interp_pseq2),
]

_ALERT_CHECKS = [
    ("pcs_total_score", 20, "⚠ PCS ≥20 — clinically significant catastrophising: consider psychology referral"),
    ("pcl5_score", 33, "⚠ PCL-5 ≥33 — PTSD likely: document action above"),
    ("isi_score", 10, "⚠ ISI ≥10 — clinically significant insomnia"),
]

_BPI_FIELDS = ["bpi_activity", "bpi_mood", "bpi_walking", "bpi_work",
               "bpi_relations", "bpi_sleep", "bpi_enjoyment"]


class OutcomeMeasuresSection(Gtk.Box, SectionBase):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None

        self._toggles: dict[str, CheckButton] = {}
        self._entries: dict[str, TouchEntry] = {}
        self._texts: dict[str, AutoTextView] = {}
        self._cyclefields: dict[str, CycleField] = {}
        self._hyp_entries: list[list[TouchEntry]] = []
        self._hyp_row_count = 0

        title = Gtk.Label(label="Outcome Measures")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        self.append(self._make_block("psfs", "PSFS — Patient Specific Functional Scale", self._build_psfs))
        self.append(self._make_block("bpi", "BPI — Brief Pain Inventory", self._build_bpi))
        self.append(self._make_block("dass", "DASS-21", self._build_dass))
        self.append(self._make_block("phq4", "PHQ-4 — Patient Health Questionnaire 4", self._build_phq4))
        self.append(self._make_block("pcs", "PCS — Pain Catastrophising Scale", self._build_pcs))
        self.append(self._make_block("pseq", "PSEQ — Pain Self-Efficacy Questionnaire", self._build_pseq))
        self.append(self._make_block("pcl5", "PCL-5 — PTSD Checklist", self._build_pcl5))
        self.append(self._make_block("sleep", "Sleep Outcome Measures", self._build_sleep))
        self.append(self._make_block("additional", "Additional Measures", self._build_additional))

        self.append(_header("Measures Selected for Ongoing Hypothesis Testing", "om_hypothesis"))
        hyp_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for lbl_text in ("Measure", "Baseline", "Interval", "Rationale"):
            lbl = Gtk.Label(label=lbl_text)
            lbl.set_hexpand(True)
            lbl.add_css_class("field-label")
            hyp_header.append(lbl)
        self.append(hyp_header)
        self.hyp_table_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.append(self.hyp_table_box)
        self._add_hyp_row()

        note = Gtk.Label(label="Administer questionnaires same day where possible. Score before next session.")
        note.add_css_class("reference-note")
        note.set_halign(Gtk.Align.START)
        self.append(note)

        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("save-status")
        self.status_label.set_halign(Gtk.Align.START)
        self.append(self.status_label)

        self._refresh_all_computed()

    # ------------------------------------------------------------------
    # Widget-creation helpers
    # ------------------------------------------------------------------

    def _make_block(self, measure_id: str, title: str, build_fn) -> Gtk.Expander:
        expander = Gtk.Expander()
        # om_* anchor_id (grid_overview.py's SUBJ_GRID_DATA "05_outcome_measures"
        # row / search.py's _SUBSECTIONS) — stashed on the Expander itself
        # (not just a child label) since app.py's grid-jump needs to call
        # set_expanded(True) here before scrolling, unlike a plain header bar.
        expander.anchor_id = _OM_BLOCK_ANCHOR.get(measure_id)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        plan_btn = CheckButton("Plan", f"plan_{measure_id}")
        plan_btn.connect("changed", self._field_changed)
        self._toggles[f"plan_{measure_id}"] = plan_btn
        header.append(plan_btn)
        title_lbl = Gtk.Label(label=title)
        title_lbl.add_css_class("field-label")
        header.append(title_lbl)
        expander.set_label_widget(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        body.set_margin_start(12)
        body.set_margin_top(4)
        build_fn(body)
        expander.set_child(body)
        return expander

    def _entry(self, field_id: str, placeholder: str = "", width_chars: int = -1) -> TouchEntry:
        w = TouchEntry(field_id, placeholder=placeholder)
        if width_chars > 0:
            w.set_width_chars(width_chars)
            w.set_hexpand(False)
        w.connect("changed", self._field_changed)
        self._entries[field_id] = w
        return w

    def _text(self, field_id: str, min_lines: int = 2) -> AutoTextView:
        w = AutoTextView(field_id, min_lines=min_lines)
        w.textview.get_buffer().connect("changed", self._field_changed)
        self._texts[field_id] = w
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

    def _reference(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("reference-note")
        lbl.set_halign(Gtk.Align.START)
        return lbl

    def _labeled(self, text: str, widget: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        lbl = Gtk.Label(label=text)
        row.append(lbl)
        row.append(widget)
        return row

    def _alert(self) -> Gtk.Label:
        lbl = Gtk.Label(label="")
        lbl.set_halign(Gtk.Align.START)
        lbl.set_wrap(True)
        lbl.add_css_class("rf-alert-warning")
        lbl.set_visible(False)
        return lbl

    # ------------------------------------------------------------------
    # Block bodies
    # ------------------------------------------------------------------

    def _build_psfs(self, body: Gtk.Box) -> None:
        for i in (1, 2, 3):
            body.append(self._entry(f"psfs_act_{i}", placeholder=f"Activity {i}"))

    def _build_bpi(self, body: Gtk.Box) -> None:
        body.append(self._reference("Scores /10 — higher = greater impairment due to pain"))
        pairs = [
            ("Activity:", "bpi_activity"), ("Mood:", "bpi_mood"),
            ("Walking:", "bpi_walking"), ("Work:", "bpi_work"),
            ("Relations:", "bpi_relations"), ("Sleep:", "bpi_sleep"),
        ]
        for i in range(0, len(pairs), 2):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            for lbl_text, fid in pairs[i:i + 2]:
                row.append(self._labeled(lbl_text, self._entry(fid, placeholder="0–10", width_chars=6)))
            body.append(row)
        last_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        last_row.append(self._labeled("Enjoyment:", self._entry("bpi_enjoyment", placeholder="0–10", width_chars=6)))
        self.bpi_total_label = Gtk.Label(label="—")
        self.bpi_total_label.add_css_class("field-label")
        last_row.append(self._labeled("Avg:", self.bpi_total_label))
        body.append(last_row)

    def _build_dass(self, body: Gtk.Box) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(self._labeled("Dep:", self._entry("dass_dep_score", placeholder="##", width_chars=4)))
        row.append(self._cycle("dass_dep_interp", _DASS_OPTIONS))
        row.append(self._labeled("Anx:", self._entry("dass_anx_score", placeholder="##", width_chars=4)))
        row.append(self._cycle("dass_anx_interp", _DASS_OPTIONS))
        row.append(self._labeled("Str:", self._entry("dass_str_score", placeholder="##", width_chars=4)))
        row.append(self._cycle("dass_str_interp", _DASS_OPTIONS))
        body.append(row)

    def _build_phq4(self, body: Gtk.Box) -> None:
        body.append(self._reference("Items 0 (never) – 3 (nearly every day)  |  Subscale ≥ 3 = positive screen"))
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row1.append(self._labeled("Nervous:", self._entry("phq4_nervous", placeholder="0–3", width_chars=4)))
        row1.append(self._labeled("+  Worry:", self._entry("phq4_worry", placeholder="0–3", width_chars=4)))
        self.phq4_anx_sum_label = Gtk.Label(label="—")
        self.phq4_anx_sum_label.add_css_class("field-label")
        row1.append(self._labeled("= Anxiety", self.phq4_anx_sum_label))
        body.append(row1)
        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row2.append(self._labeled("No Interest:", self._entry("phq4_noint", placeholder="0–3", width_chars=4)))
        row2.append(self._labeled("+  Depressed:", self._entry("phq4_depressed", placeholder="0–3", width_chars=4)))
        self.phq4_dep_sum_label = Gtk.Label(label="—")
        self.phq4_dep_sum_label.add_css_class("field-label")
        row2.append(self._labeled("= Depression", self.phq4_dep_sum_label))
        body.append(row2)

    def _build_pcs(self, body: Gtk.Box) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(self._labeled("Rum:", self._entry("pcs_rum_score", placeholder="##", width_chars=4)))
        row.append(self._cycle("pcs_rum_risk", _PCS_SUB_OPTIONS))
        row.append(self._labeled("Mag:", self._entry("pcs_mag_score", placeholder="##", width_chars=4)))
        row.append(self._cycle("pcs_mag_risk", _PCS_SUB_OPTIONS))
        row.append(self._labeled("Help:", self._entry("pcs_help_score", placeholder="##", width_chars=4)))
        row.append(self._cycle("pcs_help_risk", _PCS_SUB_OPTIONS))
        row.append(self._labeled("Total:", self._entry("pcs_total_score", placeholder="##", width_chars=4)))
        row.append(self._cycle("pcs_total_risk", _PCS_TOTAL_OPTIONS))
        body.append(row)
        self.pcs_alert_label = self._alert()
        body.append(self.pcs_alert_label)

    def _build_pseq(self, body: Gtk.Box) -> None:
        body.append(self._reference("PSEQ — Score /60 — higher = stronger self-efficacy"))
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row1.append(self._entry("pseq_score", placeholder="/60", width_chars=6))
        row1.append(self._cycle("pseq_interp", _PSEQ_OPTIONS))
        body.append(row1)
        body.append(self._reference("PSEQ-2 — 2-item screen  /12  (cutoff ≤5 = at risk)"))
        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row2.append(self._entry("pseq2_score", placeholder="/12", width_chars=6))
        row2.append(self._cycle("pseq2_interp", _PSEQ2_OPTIONS))
        body.append(row2)

    def _build_pcl5(self, body: Gtk.Box) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(self._labeled("Score /80:", self._entry("pcl5_score", placeholder="/80", width_chars=6)))
        row.append(self._cycle("pcl5_interp", _PCL5_OPTIONS))
        body.append(row)
        self.pcl5_alert_label = self._alert()
        body.append(self.pcl5_alert_label)
        body.append(self._labeled("Action if positive:", self._text("pcl5_action")))

    def _build_sleep(self, body: Gtk.Box) -> None:
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row1.append(self._labeled(
            "Insomnia Severity Index (ISI) — score /28:",
            self._entry("isi_score", placeholder="/28", width_chars=6),
        ))
        row1.append(self._cycle("isi_interp", _ISI_OPTIONS))
        body.append(row1)
        self.isi_alert_label = self._alert()
        body.append(self.isi_alert_label)
        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row2.append(self._labeled(
            "Pain-Related Beliefs and Attitudes About Sleep (PBAS) — score /10:",
            self._entry("pbas_score", placeholder="/10", width_chars=6),
        ))
        row2.append(self._cycle("pbas_interp", _PBAS_OPTIONS))
        body.append(row2)

    def _build_additional(self, body: Gtk.Box) -> None:
        body.append(self._check("AUDIT (alcohol use) — administered?", "add_audit"))
        body.append(self._check("DUDIT (drug use) — administered?", "add_dudit"))
        body.append(self._labeled("ePPOC components (specify):", self._text("add_epoc")))
        body.append(self._labeled("Other:", self._text("add_other")))

    # ------------------------------------------------------------------
    # Hypothesis-testing table — grows whenever the last row gets content
    # in any column, mirroring the TUI's _maybe_add_hyp_row (triggered on
    # every field-changed event, not just Tab, since these plain Inputs have
    # no natural "last cell" boundary the way the medications table does).
    # ------------------------------------------------------------------

    def _make_hyp_row(self, row_idx: int) -> tuple[Gtk.Box, list[TouchEntry]]:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        entries = []
        for col, placeholder in zip(_HYP_COLS, _HYP_PLACEHOLDERS):
            e = TouchEntry(f"hyp_{row_idx}_{col}", placeholder=placeholder)
            e.set_hexpand(True)
            e.connect("changed", self._on_hyp_entry_changed, row_idx)
            entries.append(e)
            row.append(e)
        return row, entries

    def _on_hyp_entry_changed(self, _entry, row_idx: int) -> None:
        self._field_changed()
        if not self._loading and row_idx == self._hyp_row_count - 1:
            self._maybe_add_hyp_row()

    def _maybe_add_hyp_row(self) -> None:
        last = self._hyp_entries[-1]
        if any(e.text.strip() for e in last):
            self._add_hyp_row()

    def _add_hyp_row(self) -> None:
        idx = self._hyp_row_count
        row, entries = self._make_hyp_row(idx)
        self.hyp_table_box.append(row)
        self._hyp_entries.append(entries)
        self._hyp_row_count += 1

    # ------------------------------------------------------------------
    # Auto-interpretation and alerts — mirrors _update_auto_interp etc.
    # ------------------------------------------------------------------

    def _update_auto_interp(self) -> None:
        for score_id, interp_id, fn in _AUTO_INTERP:
            raw = self._entries[score_id].text.strip()
            if raw.lstrip("-").isdigit():
                self._cyclefields[interp_id].set_value(fn(int(raw)))
        self._update_bpi_total()
        self._update_phq4_sums()

    def _update_bpi_total(self) -> None:
        values = []
        for fid in _BPI_FIELDS:
            raw = self._entries[fid].text.strip()
            if raw.replace(".", "", 1).lstrip("-").isdigit():
                values.append(float(raw))
        if values:
            avg = sum(values) / len(values)
            suffix = f"({len(values)}/7)" if len(values) < 7 else ""
            self.bpi_total_label.set_label(f"{avg:.1f}/10 {suffix}".strip())
        else:
            self.bpi_total_label.set_label("—")

    def _update_phq4_sums(self) -> None:
        for item_ids, label in (
            (["phq4_nervous", "phq4_worry"], self.phq4_anx_sum_label),
            (["phq4_noint", "phq4_depressed"], self.phq4_dep_sum_label),
        ):
            raw_vals = [self._entries[fid].text.strip() for fid in item_ids]
            vals = [int(v) for v in raw_vals if v.isdigit()]
            if len(vals) == 2:
                label.set_label(f"{sum(vals)}/6")
            elif vals:
                label.set_label(f"{sum(vals)}+?")
            else:
                label.set_label("—")

    def _update_alerts(self) -> None:
        for score_id, threshold, msg in _ALERT_CHECKS:
            raw = self._entries[score_id].text.strip()
            alert = {"pcs_total_score": self.pcs_alert_label,
                     "pcl5_score": self.pcl5_alert_label,
                     "isi_score": self.isi_alert_label}[score_id]
            if raw.lstrip("-").isdigit() and int(raw) >= threshold:
                alert.set_label(msg)
                alert.set_visible(True)
            else:
                alert.set_visible(False)

    def _refresh_all_computed(self) -> None:
        self._update_auto_interp()
        self._update_alerts()

    # ------------------------------------------------------------------
    # Cross-reference badges — computed, not yet rendered per-field
    # (see module docstring, same scope choice as pain_classification.py).
    # ------------------------------------------------------------------

    def update_cross_refs(self, assessment: dict | None = None) -> dict[str, list[str]]:
        assessment = assessment or {}
        med = assessment.get("medical") or {}
        subj = assessment.get("subjective") or {}
        refs: dict[str, list[str]] = {}

        lines = []
        if med.get("comorbid_mental_health") is True:
            lines.append("Med: mental health condition (comorbidity)")
        if (subj.get("psychological_distress") or "").strip():
            lines.append("Subj: psychological distress recorded")
        if subj.get("mood_influences") is True:
            lines.append("Subj: mood influences pain")
        if (subj.get("screening_tool") or "").strip():
            lines.append("Subj: screening tool recorded")
        refs["xref_om_dass"] = lines

        lines = []
        if (subj.get("psychological_distress") or "").strip():
            lines.append("Subj: psychological distress recorded")
        refs["xref_om_pcs"] = lines

        lines = []
        conf = (subj.get("confidence_score") or "").strip()
        if conf:
            lines.append(f"Subj: confidence score = {conf}/10")
        refs["xref_om_pseq"] = lines

        lines = []
        if subj.get("self_harm_risk") is True:
            lines.append("Subj: self-harm/suicide risk — POSITIVE")
        elif subj.get("self_harm_risk") is False:
            lines.append("Subj: self-harm/suicide risk — cleared")
        if (subj.get("harm_plan") or "").strip():
            lines.append("Subj: harm plan documented")
        refs["xref_om_pcl5"] = lines

        lines = []
        if subj.get("sleep_difficulty") is True:
            lines.append("Subj: sleep difficulty")
        if subj.get("night_waking") is True:
            lines.append("Subj: night waking")
        total_sleep = (subj.get("total_sleep_hours") or "").strip()
        if total_sleep:
            lines.append(f"Subj: {total_sleep} hrs/night")
        refs["xref_om_sleep"] = lines

        lines = []
        if med.get("comorbid_drug_alcohol") is True:
            lines.append("Med: drug/alcohol issues (comorbidity)")
        refs["xref_om_audit"] = lines

        return refs

    # ------------------------------------------------------------------
    # Change events
    # ------------------------------------------------------------------

    def _field_changed(self, *_args) -> None:
        if self._loading:
            return
        self._update_auto_interp()
        self._update_alerts()
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
        for fid, w in self._entries.items():
            data[fid] = w.text
        for fid, w in self._texts.items():
            data[fid] = w.text
        for fid, w in self._cyclefields.items():
            data[fid] = w.value
        for entries in self._hyp_entries:
            for col, e in zip(_HYP_COLS, entries):
                data[e.field_id] = e.text
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            om = data if isinstance(data, dict) else {}
            for fid, w in self._toggles.items():
                w.set_value(om.get(fid))
            for fid, w in self._entries.items():
                w.text = om.get(fid, "")
            for fid, w in self._texts.items():
                w.text = om.get(fid, "")
            for fid, w in self._cyclefields.items():
                w.set_value(om.get(fid))

            max_hyp = -1
            for k in om:
                if k.startswith("hyp_"):
                    parts = k.split("_")
                    if len(parts) >= 3 and parts[1].isdigit():
                        max_hyp = max(max_hyp, int(parts[1]))
            while self._hyp_row_count <= max_hyp:
                self._add_hyp_row()
            for entries in self._hyp_entries:
                for col, e in zip(_HYP_COLS, entries):
                    e.text = om.get(e.field_id, "")
        finally:
            self._loading = False
            self._refresh_all_computed()

    def is_complete(self) -> bool:
        indicators = ["psfs_act_1", "bpi_activity", "dass_dep_score",
                      "pcs_total_score", "pseq_score", "pcl5_score", "isi_score"]
        return any(self._entries[fid].text.strip() for fid in indicators)

    def focus_first_field(self) -> None:
        self._entries["psfs_act_1"].grab_focus()
