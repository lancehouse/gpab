"""Fast review-and-apply screen for goniometer ROM import.

Design goal (from the user): if reviewing takes longer than doing it by hand,
the feature has failed. So: everything that resolved unambiguously is shown
pre-accepted at the top, needing zero interaction. Only genuinely ambiguous
rows (no field match, or a side that was never stated anywhere in the batch)
need one click — a candidate button, or type an override and hit Enter.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Static

from .field_dictionary_active import ROM_FIELDS
from .field_dictionary_passive import ROM_FIELDS as PASSIVE_ROM_FIELDS
from .matcher import GroupedValue, MatchResult, group_resolved
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


class FieldPickerModal(ModalScreen[tuple[RomField, str | None] | str | None]):
    """Candidate picker for fixing one unresolved row. Dismisses with either a
    (field, side) tuple, a raw field-id override string, or None (cancelled).

    Bilateral candidates are expanded into two options up front — "Movement —
    Left" / "Movement — Right" — so picking one is a single tap or keypress,
    never a second side-picking step. (Older design chained into a separate
    SidePickerModal for the side; removed once every bilateral option here
    already carries its side.)

    Options are real clickable Buttons AND have digit hotkeys (1-9, matching
    on-screen order). An earlier digit-binding attempt was confusing because
    #override_input had default focus and Input widgets consume every
    keystroke — including digits — before any Screen-level binding runs, so
    the bindings silently never fired. Fix: nothing is auto-focused here
    (Textual falls back to the first focusable widget, one of the option
    Buttons), so digit bindings fire immediately; Tab/click into the override
    Input still works for typing an override, and once it has focus digits
    correctly resume being typed instead of picking — you're no longer
    picking a candidate at that point. Buttons remain fully clickable
    regardless, so mouse/touch is an unconditional fallback either way.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True, priority=True),
        *[Binding(str(n), f"pick_hotkey({n})", show=False, priority=True) for n in range(1, 10)],
    ]

    DEFAULT_CSS = """
    FieldPickerModal { align: center middle; background: $background 60%; }
    #picker_box {
        width: 64; height: auto; max-height: 24;
        background: $surface; border: solid $primary; padding: 1 2;
    }
    #picker_box Static { margin-bottom: 1; }
    #picker_box Button { width: 100%; margin-bottom: 1; }
    #picker_box Input { margin-top: 1; }
    """

    def __init__(self, label: str, candidates: list[RomField], **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._candidates = candidates
        # Flat, ordered (field, side) options as rendered — index+1 is the
        # option's digit hotkey; button ids are just its position ("opt_0", …).
        self._options: list[tuple[RomField, str | None]] = []
        for f in candidates:
            if f.bilateral:
                self._options.append((f, "l"))
                self._options.append((f, "r"))
            else:
                self._options.append((f, None))

    def compose(self) -> ComposeResult:
        with Container(id="picker_box"):
            yield Static(f'"{self._label}" — pick a field (1-{len(self._options)}), or type an override below:')
            for i, (f, side) in enumerate(self._options):
                side_label = " — Left" if side == "l" else " — Right" if side == "r" else ""
                yield Button(f"{i + 1} · {f.region.capitalize()} {f.movement}{side_label}", id=f"opt_{i}")
            yield Input(placeholder="or type a field id override, then Enter", id="override_input")

    @on(Button.Pressed)
    def _on_option_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if not button_id.startswith("opt_"):
            return
        self._pick(int(button_id.removeprefix("opt_")))

    def action_pick_hotkey(self, n: int) -> None:
        # Ignored while the override Input has focus — see class docstring.
        if self.focused is not None and self.focused.id == "override_input":
            return
        i = n - 1
        if 0 <= i < len(self._options):
            self._pick(i)

    def _pick(self, i: int) -> None:
        field, side = self._options[i]
        self.dismiss((field, side))

    @on(Input.Submitted, "#override_input")
    def _on_override(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.dismiss(text)

    def action_cancel(self) -> None:
        self.dismiss(None)


class GonioImportWizard(ModalScreen[list[GroupedValue] | None]):
    """Reviews every measurement across one or more .gonio.json files for this
    patient, lets you fix anything ambiguous, and dismisses with the final
    list of GroupedValue writes to apply — or None if cancelled."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True, priority=True),
        Binding("a", "apply", "Apply all", show=True, priority=True),
        # priority=True: DataTable (focused) would otherwise consume Enter itself.
        Binding("enter", "fix_row", "Fix", show=True, priority=True),
    ]

    DEFAULT_CSS = """
    GonioImportWizard { align: center middle; background: $background 70%; }
    #wizard_box {
        width: 90%; height: 90%;
        background: $surface; border: solid $primary; padding: 1 2;
    }
    #wizard_title { margin-bottom: 1; text-style: bold; }
    #wizard_table { height: 1fr; }
    #wizard_help { margin-top: 1; color: $text-muted; }
    """

    def __init__(self, results: list[MatchResult], **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: list[_Row] = [
            _Row(result=r, included=r.resolved, field=r.field, side=r.side)
            for r in results
        ]

    def compose(self) -> ComposeResult:
        with Vertical(id="wizard_box"):
            n_resolved = sum(1 for r in self._rows if r.resolved)
            yield Static(
                f"Import ROM — {len(self._rows)} measurement(s), {n_resolved} auto-matched",
                id="wizard_title",
            )
            yield DataTable(id="wizard_table", cursor_type="row", zebra_stripes=True)
            yield Static(
                "↑↓ move · Enter fix a flagged row · a apply everything included · Esc cancel",
                id="wizard_help",
            )

    def on_mount(self) -> None:
        table = self.query_one("#wizard_table", DataTable)
        table.add_columns("", "Mode", "Measurement", "→ Field", "Value")
        self._refresh_table()
        table.focus()

    def _refresh_table(self) -> None:
        table = self.query_one("#wizard_table", DataTable)
        table.clear()
        for row in self._rows:
            icon = "✓" if row.resolved else "⚠"
            mode = row.result.measurement.rom_type
            if row.resolved:
                assert row.field is not None
                side = _SIDE_LABEL[row.side]
                target = f"{row.field.region.capitalize()} {row.field.movement}" + (f" ({side})" if side else "")
            else:
                target = "— needs review —"
            value = f"{round(row.result.measurement.primary_range_deg)}°"
            table.add_row(icon, mode, row.result.measurement.label or "(no label)", target, value)

    def action_fix_row(self) -> None:
        table = self.query_one("#wizard_table", DataTable)
        idx = table.cursor_row
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.resolved:
            return  # nothing to fix — already matched

        def _after_pick(picked) -> None:
            if picked is None:
                return
            if isinstance(picked, str):
                # Free-text override: treat as a literal field id, bypass the dictionary.
                self._apply_override(idx, picked)
            elif isinstance(picked, tuple) and len(picked) == 2:
                # FieldPickerModal already expands bilateral candidates into
                # separate Left/Right options, so side is always resolved here.
                field, side = picked
                self._set_row_field(idx, field, side)

        self.app.push_screen(
            FieldPickerModal(row.result.measurement.label, [c.field for c in row.result.candidates]),
            _after_pick,
        )

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
        self._refresh_table()

    def _apply_override(self, idx: int, field_id_override: str) -> None:
        # A manually-typed field id bypasses RomField entirely — store it as a
        # pseudo-field so group_resolved's normal path still works, by faking
        # a unilateral RomField-like wrapper is overkill here; instead we
        # short-circuit: mark included with a raw override string kept on the row.
        self._rows[idx].field = None
        self._rows[idx].side = None
        self._rows[idx].included = True
        self._raw_overrides = getattr(self, "_raw_overrides", {})
        self._raw_overrides[idx] = field_id_override
        self._refresh_table()

    def action_apply(self) -> None:
        included_results = [r.result for r in self._rows if r.included and r.resolved]
        grouped = group_resolved(included_results)

        # Fold in any raw text overrides as their own single-value groups.
        raw_overrides: dict[int, str] = getattr(self, "_raw_overrides", {})
        for idx, field_id in raw_overrides.items():
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
                # The row's own AROM/PROM section — an override on a PROM
                # measurement should land in "passive", not always "active".
                section_key=row.result.section_key,
                display_label=f"(override) {field_id}",
                joined_value=str(round(row.result.measurement.primary_range_deg)),
                source_indices=[row.result.measurement.index],
            ))

        self.dismiss(grouped)

    def action_cancel(self) -> None:
        self.dismiss(None)
