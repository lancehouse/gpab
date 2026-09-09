"""Fast review-and-apply screen for goniometer ROM import — GTK4 port of
pab_assessment.goniometer_import.wizard_screen.

Design goal (from the user, carried over unchanged): if reviewing takes
longer than doing it by hand, the feature has failed. So: everything that
resolved unambiguously is shown pre-accepted at the top, needing zero
interaction. Only genuinely ambiguous rows (no field match, or a side that
was never stated anywhere in the batch) need one click — a candidate
button, or type an override and hit Enter.

GTK port notes:
- Textual's ModalScreen[T] (dismiss with a typed return value, awaited by
  the caller) has no GTK equivalent — both windows here are plain
  Gtk.Window and take an `on_result`/`on_picked` callback instead, called
  once right before the window closes itself. Same pattern as
  search_widget.SearchModal / objective/kb_db_screen.py's _KBSearchWindow.
- DataTable -> a Gtk.ListBox of plain row widgets (rebuilt on every change,
  same as the reference's own table.clear()+add_row() refresh). Selection
  IS preserved across a refresh (by index) — small deliberate improvement
  over relying on the widget default, since fixing several ambiguous rows
  in sequence would otherwise jump back to the top of the list each time.
- Enter-to-fix is wired via Gtk.ListBox's own built-in "row-activated"
  signal (fires on Enter for the focused row, or double-click) rather than
  a window-level key controller — GtkListBox already consumes Enter itself
  for exactly this, so a second window-level handler for the same key would
  either never fire or double-fire. Escape and 'a' (apply) don't collide
  with anything ListBox handles, so those stay on the window-level
  controller, matching FieldPickerModal's digit-hotkey approach below.
- Digit hotkeys (1-9) in the candidate picker are ignored while the
  override entry has focus — identical reasoning and identical mechanism
  to the reference (nothing is auto-focused on show, so a Button gets
  initial focus and digits work immediately; grabbing the entry via
  Tab/click is what switches digits back to being typed instead of
  picking).

GonioPatientPickerWindow (below) has NO reference equivalent — added
2026-08-23 per direct user feedback: the reference TUI's exact-patient-code
match has no fallback at all, so a typo'd or mismatched code was a silent
dead end. See importer.available_patient_codes()'s docstring for the
matching app.py-side change.
"""

from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, Pango  # noqa: E402

from .field_dictionary_active import ROM_FIELDS
from .field_dictionary_passive import ROM_FIELDS as PASSIVE_ROM_FIELDS
from .importer import InboxPatientSummary
from .matcher import GroupedValue, MatchResult, format_measurement_value, group_resolved
from .rom_field import RomField

_SIDE_LABEL = {"l": "L", "r": "R", None: ""}


@dataclass
class _Row:
    result: MatchResult
    included: bool  # whether this row's value will be written on Apply
    field: RomField | None
    side: str | None

    @property
    def resolved(self) -> bool:
        return self.field is not None and (not self.field.bilateral or self.side in ("l", "r"))


class FieldPickerWindow(Gtk.Window):
    """Candidate picker for fixing one unresolved row. Calls on_picked with
    either a (field, side) tuple, a raw field-id override string, or None
    (cancelled), then closes itself.

    Bilateral candidates are expanded into two options up front — "Movement
    — Left" / "Movement — Right" — so picking one is a single tap or
    keypress, never a second side-picking step.
    """

    def __init__(self, parent: Gtk.Window, label: str, candidates: list[RomField], on_picked) -> None:
        super().__init__(transient_for=parent, modal=True, title="Pick a field", decorated=True)
        self.set_default_size(420, -1)
        self._on_picked = on_picked
        self._finished = False

        self._options: list[tuple[RomField, str | None]] = []
        for f in candidates:
            if f.bilateral:
                self._options.append((f, "l"))
                self._options.append((f, "r"))
            else:
                self._options.append((f, None))

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        prompt = Gtk.Label(label=f'"{label}" — pick a field, or type an override below:')
        prompt.set_wrap(True)
        prompt.set_halign(Gtk.Align.START)
        box.append(prompt)

        self._first_button: Gtk.Button | None = None
        for i, (f, side) in enumerate(self._options):
            side_label = " — Left" if side == "l" else " — Right" if side == "r" else ""
            btn = Gtk.Button(label=f"{i + 1} · {f.region.capitalize()} {f.movement}{side_label}")
            btn.connect("clicked", lambda _b, idx=i: self._pick(idx))
            box.append(btn)
            if self._first_button is None:
                self._first_button = btn

        self.override_entry = Gtk.Entry()
        self.override_entry.set_placeholder_text("or type a field id override, then Enter")
        self.override_entry.connect("activate", self._on_override)
        box.append(self.override_entry)

        self.set_child(box)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        # Nothing auto-focused except the first candidate button — matches
        # the reference's own reasoning: leaves digit hotkeys live
        # immediately without an override-Input default focus swallowing
        # them first.
        if self._first_button is not None:
            self.connect("show", lambda *_a: self._first_button.grab_focus())

    def _pick(self, i: int) -> None:
        field, side = self._options[i]
        self._finish((field, side))

    def _on_override(self, entry: Gtk.Entry) -> None:
        text = entry.get_text().strip()
        if text:
            self._finish(text)

    def _on_key(self, _ctrl, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval)
        if name == "Escape":
            self._finish(None)
            return True
        if self.get_focus() is self.override_entry:
            return False  # let digits be typed, not picked — see class docstring
        if name and len(name) == 1 and name.isdigit():
            i = int(name) - 1
            if 0 <= i < len(self._options):
                self._pick(i)
                return True
        return False

    def _finish(self, result) -> None:
        if self._finished:
            return
        self._finished = True
        self._on_picked(result)
        self.close()


class GonioImportWizard(Gtk.Window):
    """Reviews every measurement across one or more .gonio.json files for this
    patient, lets you fix anything ambiguous, and calls on_result with the
    final list of GroupedValue writes to apply — or None if cancelled."""

    def __init__(self, parent: Gtk.Window, results: list[MatchResult], on_result) -> None:
        super().__init__(transient_for=parent, modal=True, title="Import ROM")
        self.set_default_size(900, 640)
        self._on_result = on_result
        self._finished = False
        self._rows: list[_Row] = [
            _Row(result=r, included=r.resolved, field=r.field, side=r.side)
            for r in results
        ]
        self._raw_overrides: dict[int, str] = {}
        self._selected_idx = 0 if self._rows else -1

        header = Gtk.HeaderBar()
        apply_btn = Gtk.Button(label="Apply all (a)")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", lambda *_a: self._apply())
        header.pack_start(apply_btn)
        cancel_btn = Gtk.Button(label="Cancel (Esc)")
        cancel_btn.connect("clicked", lambda *_a: self._cancel())
        header.pack_end(cancel_btn)
        self.set_titlebar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        n_resolved = sum(1 for r in self._rows if r.resolved)
        self._title_label = Gtk.Label(
            label=f"Import ROM — {len(self._rows)} measurement(s), {n_resolved} auto-matched"
        )
        self._title_label.set_halign(Gtk.Align.START)
        box.append(self._title_label)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("row-activated", lambda _b, row: self._fix_row(row.get_index()))
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(self.list_box)
        box.append(scroll)

        help_label = Gtk.Label(
            label="↑↓ move · Enter fix a flagged row · a apply everything included · Esc cancel"
        )
        help_label.set_halign(Gtk.Align.START)
        help_label.add_css_class("dim-label")
        box.append(help_label)

        self.set_child(box)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        self._refresh_list()
        self.connect("show", lambda *_a: self.list_box.grab_focus())

    def _refresh_list(self) -> None:
        row = self.list_box.get_row_at_index(0)
        while row is not None:
            self.list_box.remove(row)
            row = self.list_box.get_row_at_index(0)
        for row_data in self._rows:
            self.list_box.append(self._build_row_widget(row_data))
        n_resolved = sum(1 for r in self._rows if r.resolved)
        self._title_label.set_label(
            f"Import ROM — {len(self._rows)} measurement(s), {n_resolved} auto-matched"
        )
        if 0 <= self._selected_idx < len(self._rows):
            target = self.list_box.get_row_at_index(self._selected_idx)
            if target is not None:
                self.list_box.select_row(target)

    def _build_row_widget(self, row: _Row) -> Gtk.Widget:
        icon = "✓" if row.resolved else "⚠"
        mode = row.result.measurement.rom_type
        if row.resolved:
            assert row.field is not None
            side = _SIDE_LABEL[row.side]
            target = f"{row.field.region.capitalize()} {row.field.movement}" + (f" ({side})" if side else "")
        else:
            target = "— needs review —"
        # Preview EXACTLY what Apply will write for this one measurement
        # (repeats still get ' // '-joined downstream) — same helper, so the
        # review row and the stored value can never disagree.
        value = format_measurement_value(row.result.measurement)
        label_text = row.result.measurement.label or "(no label)"

        hrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hrow.set_margin_top(4)
        hrow.set_margin_bottom(4)
        hrow.set_margin_start(6)
        hrow.set_margin_end(6)

        icon_lbl = Gtk.Label(label=icon)
        icon_lbl.set_size_request(24, -1)
        hrow.append(icon_lbl)

        mode_lbl = Gtk.Label(label=mode)
        mode_lbl.set_size_request(56, -1)
        hrow.append(mode_lbl)

        meas_lbl = Gtk.Label(label=label_text)
        meas_lbl.set_hexpand(True)
        meas_lbl.set_halign(Gtk.Align.START)
        meas_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        hrow.append(meas_lbl)

        target_lbl = Gtk.Label(label=target)
        target_lbl.set_hexpand(True)
        target_lbl.set_halign(Gtk.Align.START)
        hrow.append(target_lbl)

        value_lbl = Gtk.Label(label=value)
        value_lbl.set_size_request(200, -1)  # wide enough for "110 (-8->102) ; 43 ; 98"
        value_lbl.set_halign(Gtk.Align.START)
        value_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        hrow.append(value_lbl)

        return hrow

    def _on_key(self, _ctrl, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval)
        if name == "Escape":
            self._cancel()
            return True
        if name and name.lower() == "a":
            self._apply()
            return True
        return False

    def _fix_row(self, idx: int) -> None:
        if idx is None or idx >= len(self._rows):
            return
        self._selected_idx = idx
        row = self._rows[idx]
        if row.resolved:
            return  # nothing to fix — already matched

        def _after_pick(picked) -> None:
            if picked is None:
                return
            if isinstance(picked, str):
                self._apply_override(idx, picked)
            elif isinstance(picked, tuple) and len(picked) == 2:
                field, side = picked
                self._set_row_field(idx, field, side)

        FieldPickerWindow(self, row.result.measurement.label,
                           [c.field for c in row.result.candidates], _after_pick).present()

    def _set_row_field(self, idx: int, field: RomField, side: str | None) -> None:
        # group_resolved() reads MatchResult.field/.side, not the _Row wrapper —
        # both must be updated in lockstep or the fix silently doesn't apply.
        row = self._rows[idx]
        row.field = field
        row.side = side
        row.included = True
        row.result.field = field
        row.result.side = side
        row.result.side_inferred = False  # explicitly chosen now, not inferred
        self._refresh_list()

    def _apply_override(self, idx: int, field_id_override: str) -> None:
        self._rows[idx].field = None
        self._rows[idx].side = None
        self._rows[idx].included = True
        self._raw_overrides[idx] = field_id_override
        self._refresh_list()

    def _apply(self) -> None:
        included_results = [r.result for r in self._rows if r.included and r.resolved]
        grouped = group_resolved(included_results)

        for idx, field_id in self._raw_overrides.items():
            row = self._rows[idx]
            if not row.included:
                continue
            # Best-effort region guess from the field id prefix's region tables
            # (both dictionaries — an override on a PROM row should still
            # guess correctly); falls back to "unknown" as a last resort,
            # flagged clearly in the display label so a wrong guess is
            # obvious, not silent.
            region_guess = next(
                (f.region for f in ROM_FIELDS + PASSIVE_ROM_FIELDS if field_id.startswith(f.region[:2])),
                "unknown",
            )
            grouped.append(GroupedValue(
                field_id=field_id,
                region=region_guess,
                section_key=row.result.section_key,
                display_label=f"(override) {field_id}",
                joined_value=format_measurement_value(row.result.measurement),
                source_indices=[row.result.measurement.index],
            ))

        self._finish(grouped)

    def _cancel(self) -> None:
        self._finish(None)

    def _finish(self, result) -> None:
        if self._finished:
            return
        self._finished = True
        self._on_result(result)
        self.close()


class GonioPatientPickerWindow(Gtk.Window):
    """Shown when the open session's own patient code has no exact-match
    goniometer data waiting — lists every OTHER patient code that does have
    something in the inbox (pending and/or already-imported), so a mismatched
    or typo'd code isn't a dead end. Calls on_picked with the chosen code, or
    None if cancelled. No reference equivalent — see module docstring."""

    def __init__(self, parent: Gtk.Window, requested_code: str,
                 available: list[InboxPatientSummary], on_picked) -> None:
        super().__init__(transient_for=parent, modal=True, title="Import ROM — pick a patient")
        self.set_default_size(420, -1)
        self._on_picked = on_picked
        self._finished = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        if requested_code:
            header_text = f'No goniometer data for "{requested_code}" — pick from what\'s waiting:'
        else:
            header_text = "No patient code on this session — pick which patient's data to import:"
        prompt = Gtk.Label(label=header_text)
        prompt.set_wrap(True)
        prompt.set_halign(Gtk.Align.START)
        box.append(prompt)

        self._first_button: Gtk.Button | None = None
        for s in available:
            parts = []
            if s.pending:
                parts.append(f"{s.pending} new")
            if s.imported:
                parts.append(f"{s.imported} already imported")
            detail = ", ".join(parts) if parts else "no files"
            btn = Gtk.Button(label=f"{s.code}  ({detail})")
            btn.connect("clicked", lambda _b, code=s.code: self._pick(code))
            box.append(btn)
            if self._first_button is None:
                self._first_button = btn

        self.set_child(box)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        if self._first_button is not None:
            self.connect("show", lambda *_a: self._first_button.grab_focus())

    def _pick(self, code: str) -> None:
        self._finish(code)

    def _on_key(self, _ctrl, keyval, _keycode, _state) -> bool:
        if Gdk.keyval_name(keyval) == "Escape":
            self._finish(None)
            return True
        return False

    def _finish(self, result) -> None:
        if self._finished:
            return
        self._finished = True
        self._on_picked(result)
        self.close()
