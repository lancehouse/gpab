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

        for f in defn.fields:
            if f.id in consumed:
                continue
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

    @classmethod
    def from_yaml(cls, path: Path | str) -> "YamlSubsectionGtk":
        return cls(load_subsection_yaml(path))

    # ------------------------------------------------------------------

    def _row(self, label_text: str, widget: Gtk.Widget, container: Gtk.Box | None = None) -> None:
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
