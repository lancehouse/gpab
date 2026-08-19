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
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Static

from .field_dictionary_active import ROM_FIELDS
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
    """Small candidate-list picker for fixing one unresolved row. Dismisses with
    either a (field, side) tuple, a raw field-id override string, or None (cancelled).

    Candidates are real clickable Buttons, not digit-key bindings — an
    earlier digit-binding design conflicted with the override Input (a
    focused Input eats keypresses as typed characters at the raw key-event
    layer, before the binding/action system ever runs, so priority=True
    bindings never fired while it had focus; working around that by starting
    with no widget focused meant the Input silently didn't respond unless you
    already knew to press a special key first — confusing in real use).
    Buttons sidestep the whole conflict: they work by click regardless of
    what has focus, and the Input can just stay normally focusable so typing
    into it works immediately, no extra step needed.
    """

    # Explicit selector, not Textual's default "*" (first focusable widget in
    # document order) — the candidate Buttons come first in compose(), so the
    # default would auto-focus a Button instead of the Input, silently eating
    # typed characters again (same failure shape as the original bug, just
    # relocated). Targeting the Input by id sidesteps composition order entirely.
    AUTO_FOCUS = "#override_input"

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True, priority=True)]

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

    def compose(self) -> ComposeResult:
        with Container(id="picker_box"):
            yield Static(f'"{self._label}" — pick a field, or type an override below:')
            for i, f in enumerate(self._candidates):
                side_hint = " (choose side next)" if f.bilateral else ""
                yield Button(
                    f"{f.region.capitalize()} {f.movement}{side_hint}",
                    id=f"cand_{i}",
                )
            yield Input(placeholder="or type a field id override, then Enter", id="override_input")

    @on(Button.Pressed)
    def _on_candidate_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if not button_id.startswith("cand_"):
            return
        i = int(button_id.removeprefix("cand_"))
        chosen = self._candidates[i]
        # Always dismiss with (field, None) — the caller (GonioImportWizard)
        # chains to SidePickerModal itself when the field turns out to need a
        # side. Keeping that chaining in one place avoids two competing
        # nested-modal paths trying to resolve the same pick.
        self.dismiss((chosen, None))

    @on(Input.Submitted, "#override_input")
    def _on_override(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.dismiss(text)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SidePickerModal(ModalScreen[tuple[RomField, str] | None]):
    """Tiny L/R picker, chained after FieldPickerModal for bilateral fields."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True, priority=True)]

    DEFAULT_CSS = """
    SidePickerModal { align: center middle; background: $background 60%; }
    #side_box { width: 40; height: auto; background: $surface; border: solid $primary; padding: 1 2; }
    #side_box Button { width: 1fr; margin: 0 1; }
    """

    def __init__(self, rom_field: RomField, **kwargs) -> None:
        super().__init__(**kwargs)
        self._field = rom_field

    def compose(self) -> ComposeResult:
        with Container(id="side_box"):
            yield Static(f"{self._field.region.capitalize()} {self._field.movement} — which side?")
            with Horizontal():
                yield Button("Left", id="pick_left")
                yield Button("Right", id="pick_right")

    @on(Button.Pressed, "#pick_left")
    def _pick_left(self) -> None:
        self.dismiss((self._field, "l"))

    @on(Button.Pressed, "#pick_right")
    def _pick_right(self) -> None:
        self.dismiss((self._field, "r"))

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
        table.add_columns("", "Measurement", "→ Field", "Value")
        self._refresh_table()
        table.focus()

    def _refresh_table(self) -> None:
        table = self.query_one("#wizard_table", DataTable)
        table.clear()
        for row in self._rows:
            icon = "✓" if row.resolved else "⚠"
            if row.resolved:
                assert row.field is not None
                side = _SIDE_LABEL[row.side]
                target = f"{row.field.region.capitalize()} {row.field.movement}" + (f" ({side})" if side else "")
            else:
                target = "— needs review —"
            value = f"{round(row.result.measurement.primary_range_deg)}°"
            table.add_row(icon, row.result.measurement.label or "(no label)", target, value)

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
                field, side = picked
                if field.bilateral and side is None:
                    # Needs a follow-up side pick.
                    def _after_side(side_result) -> None:
                        if side_result is not None:
                            f2, s2 = side_result
                            self._set_row_field(idx, f2, s2)
                    self.app.push_screen(SidePickerModal(field), _after_side)
                else:
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
            from .field_dictionary_active import SECTION_KEY
            # Best-effort region guess from the field id prefix's region tables;
            # fall back to "shoulder" only as a last resort — flagged clearly
            # in the display label so a wrong guess is obvious, not silent.
            region_guess = next((f.region for f in ROM_FIELDS if field_id.startswith(f.region[:2])), "unknown")
            grouped.append(GroupedValue(
                field_id=field_id,
                region=region_guess,
                section_key=SECTION_KEY,
                display_label=f"(override) {field_id}",
                joined_value=str(round(row.result.measurement.primary_range_deg)),
                source_indices=[row.result.measurement.index],
            ))

        self.dismiss(grouped)

    def action_cancel(self) -> None:
        self.dismiss(None)
