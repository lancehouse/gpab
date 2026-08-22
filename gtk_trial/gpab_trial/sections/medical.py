"""Medical Screening — GTK4 port of pab_assessment/sections/medical.py.

Field ids and collect()/load() keys are 1:1 with the TUI section so the
saved dict is schema-compatible with pab_assessment.storage. One dynamic
piece ported as-is: the medications table starts with 4 rows and grows by
one every time Tab is pressed in the last column of the last row, mirroring
the TUI's on_key handler.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

from ..section_base import SectionBase
from ..widgets import (
    CheckButton, FlagButton, AutoTextView, TouchEntry, LikelihoodField,
    make_subsection_header as _header,
    make_subgroup_header as _subheader,
    field_row as _field_row,
    field_row_pair as _field_row_pair,
)

_MED_COLS = ["name", "dose", "timing", "comments"]
_MED_COL_LABELS = ["Name / brand", "Dose", "Frequency", "Comments"]

# Red flag groups driving the alert banner (see _update_rf_alert).
_RF_URGENT_CAUDA = ["rf_saddle_anaesthesia", "rf_bladder_disturbance", "rf_bowel_disturbance"]
_RF_URGENT_CORD = ["rf_bilateral_paraesthesia", "rf_gait_disturbance"]
_RF_GENERAL = [
    "rf_weight_loss", "rf_cancer_history", "rf_age_50_spinal", "rf_failed_conservative",
    "rf_trauma", "rf_corticosteroids_fracture", "rf_osteoporosis_fracture",
    "rf_fever", "rf_immunosuppressed", "rf_spinal_procedure",
]

_IMAGING_FIELDS = [
    ("Xray", "img_xray", "img_xray_detail"),
    ("U/S", "img_us", "img_us_detail"),
    ("CT", "img_ct", "img_ct_detail"),
    ("MRI", "img_mri", "img_mri_detail"),
    ("NCS", "img_ncs", "img_ncs_detail"),
    ("Other", "img_other", "img_other_detail"),
]


class MedicalSection(Gtk.Box, SectionBase):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None

        self._toggles: dict[str, CheckButton] = {}
        self._likelihoods: dict[str, LikelihoodField] = {}
        self._texts: dict[str, AutoTextView] = {}
        self._med_entries: list[list[TouchEntry]] = []
        self._med_row_count = 0

        title = Gtk.Label(label="Medical Screening")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        self._build_comorbidities()
        self._build_cardiovascular()
        self._build_red_flags()
        self._build_differential()
        self._build_medications()
        self._build_imaging()

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

    def _btn_row(self, *widgets: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for w in widgets:
            row.append(w)
        return row

    # ------------------------------------------------------------------
    # Comorbidities / PMH
    # ------------------------------------------------------------------

    def _build_comorbidities(self) -> None:
        self.append(_header("Comorbidities / PMH", "med_comorbidities"))
        self.append(self._check(
            "No previous injuries or general health issues: Confirmed", "no_previous_injuries",
        ))
        self.append(_field_row("Previous injuries:", self._text("previous_injuries")))

        lbl = Gtk.Label(label="Comorbidities:")
        lbl.set_halign(Gtk.Align.START)
        self.append(lbl)
        self.append(self._btn_row(
            self._flag("Cancer (hx or current)", "comorbid_cancer"),
            self._flag("Mental health", "comorbid_mental_health"),
            self._flag("Osteoporosis", "comorbid_osteoporosis"),
            self._flag("Inflammatory condition", "comorbid_inflammatory"),
            self._flag("Fibromyalgia", "comorbid_fibromyalgia"),
        ))
        self.append(self._btn_row(
            self._flag("Chronic fatigue (CFS)", "comorbid_cfs"),
            self._flag("Irritable bowel (IBS)", "comorbid_ibs"),
            self._flag("Chronic whiplash", "comorbid_whiplash"),
            self._flag("Painful skin rash", "comorbid_skin_rash"),
            self._flag("Drug / alcohol issues", "comorbid_drug_alcohol"),
        ))
        self.append(self._flag("Fatigue / memory / cognition issues", "comorbid_fatigue_memory"))
        self.append(_field_row("Other comorbidities:", self._text("comorbid_other")))

    # ------------------------------------------------------------------
    # Cardiovascular Risk Factors
    # ------------------------------------------------------------------

    def _build_cardiovascular(self) -> None:
        self.append(_header("Cardiovascular Risk Factors", "med_cardiovascular"))
        self.append(self._btn_row(
            self._flag("Hypercholesterolaemia", "cvd_hypercholesterolaemia"),
            self._flag("Cardiac disease", "cvd_cardiac"),
            self._flag("Vascular disease", "cvd_vascular"),
            self._flag("Stroke / TIA", "cvd_stroke_tia"),
            self._flag("Diabetes", "cvd_diabetes"),
        ))
        self.append(self._btn_row(
            self._flag("Prolonged corticosteroids", "cvd_corticosteroids"),
            self._flag("Clotting disorder", "cvd_clotting"),
            self._flag("Oral contraceptive", "cvd_ocp"),
            self._flag("Smoker", "cvd_smoker"),
            self._flag("Post-partum", "cvd_postpartum"),
        ))
        self.append(self._flag("Familial history of presenting condition", "cvd_familial_history"))

    # ------------------------------------------------------------------
    # Red Flags
    # ------------------------------------------------------------------

    def _build_red_flags(self) -> None:
        self.append(_header("Red Flags", "med_red_flags"))
        self.rf_alert = Gtk.Label(label="")
        self.rf_alert.set_halign(Gtk.Align.START)
        self.rf_alert.set_visible(False)
        self.append(self.rf_alert)

        self.append(_subheader("Malignancy:"))
        self.append(self._btn_row(
            self._flag("Unexplained weight loss", "rf_weight_loss"),
            self._flag("Cancer history", "rf_cancer_history"),
            self._flag("Age >50 + new spinal pain", "rf_age_50_spinal"),
            self._flag("Failed conservative Rx", "rf_failed_conservative"),
        ))
        self.append(_field_row("Comment:", self._text("rf_malignancy_comment")))

        self.append(_subheader("Fracture:"))
        self.append(self._btn_row(
            self._flag("Significant trauma", "rf_trauma"),
            self._flag("Prolonged corticosteroids", "rf_corticosteroids_fracture"),
            self._flag("Confirmed osteoporosis", "rf_osteoporosis_fracture"),
        ))
        self.append(_field_row("Comment:", self._text("rf_fracture_comment")))

        self.append(_subheader("Infection:"))
        self.append(self._btn_row(
            self._flag("Fever", "rf_fever"),
            self._flag("Immunosuppressed", "rf_immunosuppressed"),
            self._flag("Recent spinal procedure", "rf_spinal_procedure"),
        ))
        self.append(_field_row("Comment:", self._text("rf_infection_comment")))

        self.append(_subheader("Cauda Equina Compression (URGENT):"))
        self.append(self._btn_row(
            self._flag("Saddle / perineal anaesthesia", "rf_saddle_anaesthesia"),
            self._flag("Bladder disturbance", "rf_bladder_disturbance"),
            self._flag("Bowel disturbance", "rf_bowel_disturbance"),
        ))
        self.append(_field_row("Action taken:", self._text("cauda_equina_action")))

        self.append(_subheader("Spinal Cord Compression (URGENT):"))
        self.append(self._btn_row(
            self._flag("Bilateral paraesthesia / weakness", "rf_bilateral_paraesthesia"),
            self._flag("Gait / balance disturbance", "rf_gait_disturbance"),
        ))
        self.append(_field_row("Action taken:", self._text("spinal_cord_action")))

    # ------------------------------------------------------------------
    # Differential Screening
    # ------------------------------------------------------------------

    def _build_differential(self) -> None:
        self.append(_header("Differential Screening", "med_differential"))

        self.append(_subheader("Ankylosing Spondylitis:"))
        self.append(self._btn_row(
            self._flag("Insidious onset", "diff_as_insidious"),
            self._flag("Lumbar / SIJ spreading", "diff_as_lumbar_sij"),
            self._flag("Inflammatory pattern", "diff_as_inflammatory"),
            self._flag("Breathing difficulties", "diff_as_breathing"),
            self._flag("Fever / weight loss", "diff_as_fever_weight_loss"),
        ))
        self.append(self._likelihood("Likelihood:", "diff_as_likelihood"))
        self.append(_field_row("Action:", self._text("diff_as_action")))

        self.append(_subheader("Abdominal Aortic Aneurysm:"))
        self.append(self._btn_row(
            self._flag("Pulsating lumbar / groin pain", "diff_aaa_pulsating"),
            self._flag("Age >50", "diff_aaa_age_50"),
            self._flag("CVD risk factors present", "diff_aaa_cvd_risk"),
            self._flag("Sudden onset + low BP (ruptured)", "diff_aaa_ruptured"),
        ))
        self.append(self._likelihood("Likelihood:", "diff_aaa_likelihood"))
        self.append(_field_row("Action:", self._text("diff_aaa_action")))

        self.append(_subheader("Vascular Claudication:"))
        self.append(self._btn_row(
            self._flag("Non-dermatomal leg symptoms", "diff_vc_non_dermatomal"),
            self._flag("Age >50", "diff_vc_age_50"),
            self._flag("CVD risk factors", "diff_vc_cvd_risk"),
            self._flag("Pain / fatigue with walking", "diff_vc_walking_pain"),
            self._flag("PVD signs (cold / blotchy / hairless)", "diff_vc_pvd_signs"),
        ))
        self.append(self._btn_row(
            self._flag("Impotence (men)", "diff_vc_impotence"),
            self._flag("Leg pain at night", "diff_vc_night_pain"),
        ))
        self.append(self._likelihood("Likelihood:", "diff_vc_likelihood"))
        self.append(_field_row("Action:", self._text("diff_vc_action")))

    # ------------------------------------------------------------------
    # Medications — dynamic table, grows via Tab in the last cell
    # ------------------------------------------------------------------

    def _build_medications(self) -> None:
        self.append(_header("Medications", "med_medications"))
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for lbl in _MED_COL_LABELS:
            col_lbl = Gtk.Label(label=lbl)
            col_lbl.set_hexpand(True)
            col_lbl.add_css_class("field-label")
            header_row.append(col_lbl)
        self.append(header_row)

        self.med_table_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.append(self.med_table_box)
        for _ in range(4):
            self._add_medication_row(focus_new=False)

    def _make_med_row(self, row_idx: int) -> tuple[Gtk.Box, list[TouchEntry]]:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        entries: list[TouchEntry] = []
        for col in _MED_COLS:
            e = TouchEntry(f"med_{row_idx}_{col}")
            e.set_hexpand(True)
            e.connect("changed", self._field_changed)
            entries.append(e)
            row.append(e)
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_med_last_cell_key, row_idx)
        entries[-1].add_controller(key_ctrl)
        return row, entries

    def _on_med_last_cell_key(self, _ctrl, keyval, _keycode, state, row_idx: int) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        shift_held = bool(state & Gdk.ModifierType.SHIFT_MASK)
        if name == "Tab" and not shift_held and row_idx == self._med_row_count - 1:
            self._add_medication_row(focus_new=True)
            return True
        return False

    def _add_medication_row(self, focus_new: bool) -> None:
        idx = self._med_row_count
        row, entries = self._make_med_row(idx)
        self.med_table_box.append(row)
        self._med_entries.append(entries)
        self._med_row_count += 1
        if focus_new:
            GLib.idle_add(lambda w=entries[0]: (w.grab_focus(), False)[1])

    # ------------------------------------------------------------------
    # Imaging
    # ------------------------------------------------------------------

    def _build_imaging(self) -> None:
        self.append(_header("Imaging"))
        for label, btn_id, detail_id in _IMAGING_FIELDS:
            self.append(_field_row_pair(self._check(label, btn_id), self._text(detail_id, min_lines=1)))

    # ------------------------------------------------------------------
    # Red flag alert banner — mirrors medical.py's _update_rf_alert
    # ------------------------------------------------------------------

    def _update_rf_alert(self) -> None:
        def _any_true(ids: list[str]) -> bool:
            return any(self._toggles[fid].value is True for fid in ids)

        if _any_true(_RF_URGENT_CAUDA):
            self.rf_alert.set_label("⚠ URGENT: Cauda equina symptoms — document action below")
            self.rf_alert.remove_css_class("rf-alert-warning")
            self.rf_alert.add_css_class("rf-alert-urgent")
            self.rf_alert.set_visible(True)
        elif _any_true(_RF_URGENT_CORD):
            self.rf_alert.set_label("⚠ URGENT: Spinal cord compression signs — document action below")
            self.rf_alert.remove_css_class("rf-alert-warning")
            self.rf_alert.add_css_class("rf-alert-urgent")
            self.rf_alert.set_visible(True)
        elif _any_true(_RF_GENERAL):
            self.rf_alert.set_label("⚠ Red flag(s) positive — clinical judgement required")
            self.rf_alert.remove_css_class("rf-alert-urgent")
            self.rf_alert.add_css_class("rf-alert-warning")
            self.rf_alert.set_visible(True)
        else:
            self.rf_alert.set_visible(False)

    # ------------------------------------------------------------------
    # Change events
    # ------------------------------------------------------------------

    def _field_changed(self, *_args) -> None:
        if self._loading:
            return
        self._update_rf_alert()
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

        medications = []
        for entries in self._med_entries:
            row = {col: e.text for col, e in zip(_MED_COLS, entries)}
            if any(row.values()):
                medications.append(row)
        data["medications"] = medications
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            medical = data if isinstance(data, dict) else {}
            for fid, w in self._toggles.items():
                w.set_value(medical.get(fid))
            for fid, w in self._likelihoods.items():
                w.set_value(medical.get(fid))
            for fid, w in self._texts.items():
                w.text = medical.get(fid, "")

            meds = medical.get("medications", [])
            # Grow the table first if the saved session has more rows than
            # the 4 built at construction — mirrors the TUI's _load_extra_meds.
            while self._med_row_count < len(meds):
                self._add_medication_row(focus_new=False)
            for i, entries in enumerate(self._med_entries):
                med = meds[i] if i < len(meds) else {}
                for col, e in zip(_MED_COLS, entries):
                    e.text = med.get(col, "")
        finally:
            self._loading = False
            self._update_rf_alert()

    def is_complete(self) -> bool:
        urgent = _RF_URGENT_CAUDA + _RF_URGENT_CORD
        return all(self._toggles[fid].value is not None for fid in urgent)

    def focus_first_field(self) -> None:
        self._toggles["no_previous_injuries"].grab_focus()
