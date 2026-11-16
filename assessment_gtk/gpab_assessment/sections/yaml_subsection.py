"""GTK4 renderer for pab_assessment.form_schema.SubsectionDef.

This is a SECOND renderer of the exact same declarative YAML format the TUI's
yaml_subsection.py already consumes (pab_assessment/sections/yaml/*.yaml).
Nothing about form_schema.py or the YAML file changes — only the widget
construction differs. If this works, the other TUI sections can migrate to
GTK by writing more YAML rather than hand-porting Python widget trees.
"""

from __future__ import annotations
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject  # noqa: E402

from ..storage_bridge import pab_path_bootstrap  # noqa: F401  (sys.path side effect)
from pab_assessment.form_schema import SubsectionDef, FieldDef, load_subsection_yaml  # noqa: E402
from pab_assessment.logic import calc_sleep_efficiency  # noqa: E402
from pab_assessment.sleep_screen import (  # noqa: E402
    sleep_screen_step1, sleep_screen_step2, sleep_screen_step3,
)

from ..widgets import RadioGroup, AutoTextView, TouchEntry, field_left_slot, make_subsection_header

_FORMULA_REGISTRY: dict[str, Callable] = {
    "calc_sleep_efficiency": calc_sleep_efficiency,
}

# Sleep diary time fields laid out as two columns (left: the "when" timeline,
# right: wake-after-sleep-onset / time-awake durations), with the calculated
# Sleep Efficiency field as a full-width footer row underneath both — see
# YamlSubsectionGtk.__init__/_build_time_grid. Field ids only; order here is
# the on-screen order within each column.
_TIME_GRID_LEFT = [
    "sleep_time_to_bed",
    "sleep_time_attempt",
    "sleep_onset_time",
    "sleep_final_wakeup",
    "sleep_time_out_of_bed",
]
_TIME_GRID_RIGHT = [
    "sleep_waso_clock",
    "sleep_waso_duration",
    "sleep_awake_in_bed",
    "sleep_awake_out_bed",
]
_TIME_GRID_FOOTER = "sleep_efficiency"

# Sleep dysfunction screen (2026-11-16) — the 3-step flowchart of Shepherd,
# Neilson & Siengsukon 2026 (JOSPT Open 4(1):12-22, Fig 1). Step headings go
# in front of the field with that id; each step's live result line goes after
# the field with that id. The rules themselves are sleep_screen.sleep_screen_step*().
_STEP_HEADERS = {
    "sleep_hours_typical": ("Step 1: General sleep screening",
                            "Move to Step 2 if <7 h sleep, OR not well rested, OR sleep rated fairly/very bad."),
    "sleep_pain_impacts": ("Step 2: Sleep dysfunction vs. pain condition?",
                           "Verify Step 1 and ask whether the pain condition is impacting sleep. "
                           "\u201cNo\u201d, OR \u201cYes\u201d but sleep issues started BEFORE the pain, OR pain "
                           "does not appear to be contributing \u2192 Step 3."),
    "sleep_s3_insomnia": ("Step 3: Screening for the \u201cbig three\u201d sleep conditions",
                          "Insomnia: Yes to Q1 and Q2 \u2192 ISI.  Restless legs: Yes to Q4 \u2192 RLS-DI.  "
                          "Sleep apnea: Yes to Q1\u20133 \u2192 STOP-BANG.  (Tools in Outcome Measures.)"),
    "sleep_time_to_bed": ("Sleep diary", ""),
}
_STEP_RESULT_AFTER = {
    "sleep_quality_4pt": "step1",
    "sleep_pain_contributing": "step2",
    "sleep_s3_rls": "step3",
}
# Questions longer than this get their label on its own full-width line above
# the buttons, rather than wrapping down the narrow left label column.
_STACK_LABEL_CHARS = 60


class YamlSubsectionGtk(Gtk.Box):
    """Renders one SubsectionDef (header + fields) as native GTK4 widgets."""

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, defn: SubsectionDef) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._def = defn
        self._loading = False
        self._widgets: dict[str, Gtk.Widget] = {}

        # value<->label translation for radio fields (same as TUI's YamlSubsection)
        self._v2l: dict[str, dict[str, str]] = {}
        self._l2v: dict[str, dict[str, str]] = {}
        for f in defn.fields:
            if f.type == "radio" and f.options:
                self._v2l[f.id] = {o.value: o.label for o in f.options}
                self._l2v[f.id] = {o.label: o.value for o in f.options}

        # This renderer is only ever used for the Sleep subsection (see
        # subjective.py) — subj_sleep is the one anchor_id it will ever need.
        self.append(make_subsection_header(defn.label, "subj_sleep"))

        fields_by_id = {f.id: f for f in defn.fields}
        consumed: set[str] = set()
        self._step_results: dict[str, Gtk.Label] = {}

        for f in defn.fields:
            if f.id in consumed:
                continue
            if f.id in _STEP_HEADERS:
                self._build_step_header(*_STEP_HEADERS[f.id])
            if (
                f.id == _TIME_GRID_LEFT[0]
                and all(fid in fields_by_id for fid in _TIME_GRID_LEFT + _TIME_GRID_RIGHT)
            ):
                self._build_time_grid(fields_by_id)
                consumed.update(_TIME_GRID_LEFT)
                consumed.update(_TIME_GRID_RIGHT)
                consumed.add(_TIME_GRID_FOOTER)
                continue
            self._build_field(f)
            if f.id in _STEP_RESULT_AFTER:
                self._build_step_result(_STEP_RESULT_AFTER[f.id])
        self._refresh_step_results()

    @classmethod
    def from_yaml(cls, path: Path | str) -> "YamlSubsectionGtk":
        return cls(load_subsection_yaml(path))

    # ------------------------------------------------------------------

    def _build_step_header(self, title: str, hint: str) -> None:
        lbl = Gtk.Label(label=title)
        lbl.add_css_class("sleep-step-header")
        lbl.set_xalign(0.0)
        lbl.set_halign(Gtk.Align.FILL)
        self.append(lbl)
        if hint:
            h = Gtk.Label(label=hint)
            h.add_css_class("reference-note")
            h.set_xalign(0.0)
            h.set_wrap(True)
            self.append(h)

    def _build_step_result(self, key: str) -> None:
        # Always visible with fixed padding (rf-alert-slot) so answering a
        # question never reflows the rows below it — only the colour changes.
        lbl = Gtk.Label(label="")
        lbl.add_css_class("rf-alert-slot")
        lbl.set_xalign(0.0)
        lbl.set_wrap(True)
        self._step_results[key] = lbl
        self.append(lbl)

    def _refresh_step_results(self) -> None:
        if not self._step_results:
            return
        data = self.collect()
        texts = {
            "step1": sleep_screen_step1(data),
            "step2": sleep_screen_step2(data),
            "step3": "\n".join(sleep_screen_step3(data)),
        }
        names = {"step1": "Step 1", "step2": "Step 2", "step3": "Step 3"}
        for key, lbl in self._step_results.items():
            text = texts.get(key, "")
            lbl.set_label(f"{names[key]}: {text}" if text else f"{names[key]}: —")
            # Highlight when the step points onward (next step / a tool).
            onward = ("\u2192" in text or "administer" in text)
            if onward:
                lbl.add_css_class("rf-alert-warning")
            else:
                lbl.remove_css_class("rf-alert-warning")

    def _row(self, label_text: str, widget: Gtk.Widget, container: Gtk.Box | None = None) -> None:
        # Callers append ":" — drop it after a question mark / existing colon
        # (the sleep screen's questions end in "?" or "is:").
        if label_text.endswith(("?:", "::")):
            label_text = label_text[:-1]
        if len(label_text) > _STACK_LABEL_CHARS:
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl = Gtk.Label(label=label_text)
            lbl.set_xalign(0.0)
            lbl.set_wrap(True)
            lbl.add_css_class("field-label")
            col.append(lbl)
            widget.set_halign(Gtk.Align.START)
            col.append(widget)
            (container if container is not None else self).append(col)
            return
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl = Gtk.Label(label=label_text)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_valign(Gtk.Align.START)
        lbl.set_wrap(True)
        lbl.add_css_class("field-label")
        field_left_slot(lbl)
        row.append(lbl)
        row.append(widget)
        (container if container is not None else self).append(row)

    def _build_field(self, f: FieldDef, container: Gtk.Box | None = None) -> None:
        if f.type == "text_area":
            ta = AutoTextView(f.id)
            ta.textview.get_buffer().connect("changed", self._on_changed_field, f.id)
            self._widgets[f.id] = ta
            self._row(f"{f.label}:", ta, container)

        elif f.type == "input":
            label = f.label + (" (duration)" if f.time_kind == "duration" else "")
            entry = TouchEntry(f.id, placeholder=f.placeholder)
            entry.connect("changed", self._on_changed_field, f.id)
            self._widgets[f.id] = entry
            self._row(f"{label}:", entry, container)

        elif f.type == "radio":
            opts = [(o.label, o.variant) for o in f.options]
            rg = RadioGroup(opts, f.id)
            rg.connect("changed", self._on_changed_field, f.id)
            self._widgets[f.id] = rg
            self._row(f"{f.label}:", rg, container)

        elif f.type == "calculated":
            entry = TouchEntry(f.id, placeholder=f"— {f.unit}" if f.unit else "—")
            entry.set_sensitive(False)
            self._widgets[f.id] = entry
            self._row(f"{f.label}:", entry, container)

    def _build_time_grid(self, fields_by_id: dict[str, FieldDef]) -> None:
        """Sleep diary time fields as two side-by-side columns, with the
        calculated Sleep Efficiency field as a full-width footer row below
        both — the numeric data-entry block the user asked for, distinct
        from the ratings/free-text fields above and below it."""
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24, homogeneous=True)
        left_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for fid in _TIME_GRID_LEFT:
            self._build_field(fields_by_id[fid], container=left_col)
        for fid in _TIME_GRID_RIGHT:
            self._build_field(fields_by_id[fid], container=right_col)
        outer.append(left_col)
        outer.append(right_col)
        self.append(outer)

        footer_f = fields_by_id.get(_TIME_GRID_FOOTER)
        if footer_f is not None:
            self._build_field(footer_f)

    # ------------------------------------------------------------------
    # Calculated fields — identical recompute logic to the TUI's YamlSubsection
    # ------------------------------------------------------------------

    def _on_changed_field(self, _widget, fid: str) -> None:
        if self._loading:
            return
        is_calc = any(f.id == fid and f.type == "calculated" for f in self._def.fields)
        if not is_calc:
            self._recompute_calculated()
            self._refresh_step_results()
        self.emit("changed")

    def _recompute_calculated(self) -> None:
        for f in self._def.fields:
            if f.type != "calculated" or not f.formula_fn:
                continue
            fn = _FORMULA_REGISTRY.get(f.formula_fn)
            if fn is None:
                continue
            kwargs: dict[str, str] = {}
            for inp_id in f.inputs:
                inp_f = next((x for x in self._def.fields if x.id == inp_id), None)
                if inp_f is None:
                    continue
                w = self._widgets.get(inp_id)
                try:
                    if inp_f.type in ("input",):
                        kwargs[inp_id] = w.text
                    elif inp_f.type == "text_area":
                        kwargs[inp_id] = w.text
                    elif inp_f.type == "radio":
                        lbl = w.value
                        kwargs[inp_id] = self._l2v[inp_id].get(lbl, "") if lbl else ""
                except Exception:
                    kwargs[inp_id] = ""
            try:
                result = fn(**kwargs)
                self._widgets[f.id].text = result
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def collect(self) -> dict:
        data: dict = {}
        for f in self._def.fields:
            w = self._widgets.get(f.id)
            try:
                if f.type in ("text_area", "input", "calculated"):
                    data[f.id] = w.text
                elif f.type == "radio":
                    lbl = w.value
                    data[f.id] = self._l2v[f.id].get(lbl) if lbl else None
            except Exception:
                data[f.id] = None if f.type == "radio" else ""
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            for f in self._def.fields:
                if f.type == "calculated":
                    continue
                val = data.get(f.id)
                w = self._widgets.get(f.id)
                try:
                    if f.type in ("text_area", "input"):
                        w.text = val or ""
                    elif f.type == "radio":
                        lbl = self._v2l[f.id].get(val) if val else None
                        w.set_value(lbl)
                except Exception:
                    pass
        finally:
            self._loading = False
            self._recompute_calculated()
            self._refresh_step_results()
