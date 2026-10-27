"""AD block-form tab — Objective 10 "AD Lx/SIJ" (test run, 2026-10-22).

AD's position-ordered Lx/SIJ examination form (Standing → Sitting → Supine
→ Side lying → Prone → Neurological → Other), rendered from the shared
spec pab_assessment/objective/ad_forms/ad_lx_sij.yaml — the same file
storage.py's "10 AD Lx/SIJ" report section is built from, so this tab and
its report can't disagree about labels, order or wording.

Two kinds of cell (see the YAML header):
  - linked: a mirror of an existing gpab field (field_link.py) — editing
    it edits that real field, which keeps saving exactly where it always
    did. Re-read via refresh_links() whenever this tab is shown or the
    session reloads, since the real field may have been edited elsewhere.
  - AD-only: this tab's own fields for gaps in gpab (bridging, per-level
    sensation, ...), saved under _objective.json assessment["ad_lx_sij"].

Front end only: layout comes from objective/block_layout.py, data meaning
from the spec + pab_assessment.objective.ad_forms. Swapping either the
layout or the spec doesn't require touching the other.
"""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ...widgets import AutoTextView, CheckButton, CycleField, FlagButton, RadioGroup, TouchEntry
from ...section_base import SectionBase
from ..block_layout import BlockCard, PositionSection
from ..field_link import (
    LinkResolver, clone_field_widget, connect_changed, set_widget_value, widget_value,
)
from ... import pab_path_bootstrap  # noqa: F401  (sys.path side effect)
from pab_assessment.objective.ad_forms import (  # noqa: E402
    TOUCHED_KEY, Block, Cell, load_form, path_value, tally_text,
)

logger = logging.getLogger(__name__)


class ADFormSection(Gtk.Box, SectionBase):
    def __init__(self, form_id: str, tab_label: str, resolver: LinkResolver) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.form = load_form(form_id)
        self._resolver = resolver
        self._loading = False
        self._writing = False
        self._touched = False
        self._on_changed = None
        self._saved_provider = None

        self._own: dict[str, Gtk.Widget] = {}
        self._links: dict[str, list[Gtk.Widget]] = {}
        self._tallies: list[tuple[Block, Gtk.Label]] = []
        self._first_widget: Gtk.Widget | None = None

        title = Gtk.Label(label=tab_label)
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)
        for text in (
            self.form.title,
            "Fields marked 🔗 edit the existing gpab field (same value as its own tab); "
            "unmarked fields belong to this form only.",
        ):
            note = Gtk.Label(label=text)
            note.add_css_class("reference-note")
            note.set_halign(Gtk.Align.START)
            note.set_xalign(0.0)
            note.set_wrap(True)
            self.append(note)

        for pos in self.form.positions:
            section = PositionSection(pos.label, pos.id)
            for block in pos.blocks:
                section.add_card(self._build_card(block), column=block.column)
            self.append(section)

        self._update_tallies()

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _build_card(self, block: Block) -> BlockCard:
        card = BlockCard(block.title, block.note, wide=block.wide)
        if block.tally:
            lbl = Gtk.Label(label="")
            lbl.add_css_class("block-card-tally")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_wrap(True)
            card.add_full(lbl)
            self._tallies.append((block, lbl))

        if block.level_grid:
            self._build_level_grid(card, block)
            return card

        # L/R as a header row only when every row is two-sided; a mixed
        # card (e.g. Squat beside Stand on one leg L/R) captions each side
        # inline instead, so a one-sided row never sits under an "L".
        all_sided = bool(block.rows) and all(r.sides for r in block.rows)
        if block.columns:
            card.add_column_headers(list(block.columns))
        elif all_sided:
            card.add_column_headers(["", "L", "R"])

        for r_idx, row in enumerate(block.rows):
            solo = len(row.cells) == 1
            widgets = [self._cell_widget(c, row.label, solo) for c in row.cells]
            if row.sides:
                half = len(widgets) // len(row.sides)
                groups = [widgets[i * half:(i + 1) * half] for i in range(len(row.sides))]
            elif block.columns:
                groups = [[w] for w in widgets]
            else:
                groups = [widgets]
            # A row that is nothing but one flag/check button carries its
            # label inside the button — no separate label column.
            label = row.label
            if len(widgets) == 1 and isinstance(widgets[0], CheckButton):
                label = ""
            if label and any(c.link for c in row.cells):
                label = f"🔗 {label}"
            keys = [f"{r_idx}:{i}" for i in range(len(widgets))]
            captions = [s.upper() for s in row.sides] if (row.sides and not all_sided) else None
            card.add_row(label, groups, hint=row.hint, nav_keys=keys, group_labels=captions)
        return card

    def _build_level_grid(self, card: BlockCard, block: Block) -> None:
        lg = block.level_grid
        card.add_column_headers([""] + [f"{lbl}\nL · R" for _, lbl in lg["modalities"]])
        for r_idx, (lvl, lvl_lbl) in enumerate(lg["levels"]):
            groups = []
            for mod, _ in lg["modalities"]:
                pair = [self._cell_widget(lg["cells"][(mod, lvl, side)], "", False) for side in ("l", "r")]
                # 10 cycle buttons per row: the compact toggle size (as
                # Neurological's 9-button UMN row uses) keeps the grid
                # within a normal content width.
                for w in pair:
                    w.button.add_css_class("toggle-compact")
                groups.append(pair)
            keys = [f"{r_idx}:{i}" for i in range(2 * len(groups))]
            card.add_row(lvl_lbl, groups, nav_keys=keys)

    def _cell_widget(self, cell: Cell, row_label: str, solo: bool) -> Gtk.Widget:
        # A flag/check button alone in its row IS the row (label inside the
        # button, so a linked one carries the 🔗 itself); beside a detail
        # field it sits under the row label, so it just reads "Finding".
        flag_label = row_label if solo else "Finding"
        if cell.link is not None:
            src = self._resolver.template(cell.link)
            if src is None:
                raise LookupError(f"AD form link target not found: {cell.link}")
            w = clone_field_widget(src, label=f"🔗 {flag_label}" if solo else flag_label)
            # Whole-window walkers that EDIT text (Ctrl+S spellcheck) must
            # skip mirrors: a hidden mirror can be stale, and editing it
            # writes its whole old text through over the real field.
            w.is_link_mirror = True
            self._links.setdefault(cell.link, []).append(w)
            connect_changed(w, lambda widget, path=cell.link: self._on_link_changed(widget, path))
        else:
            w = self._own_widget(cell, flag_label)
            self._own[cell.id] = w
            connect_changed(w, self._on_own_changed)
        if isinstance(w, (TouchEntry, AutoTextView)):
            w.set_hexpand(True)
        if self._first_widget is None:
            self._first_widget = w
        return w

    @staticmethod
    def _own_widget(cell: Cell, row_label: str) -> Gtk.Widget:
        options = [tuple(o) for o in cell.options]
        if cell.type == "radio":
            return RadioGroup(options, cell.id)
        if cell.type == "cycle":
            return CycleField("", cell.id, options=options)
        if cell.type == "entry":
            return TouchEntry(cell.id, placeholder=cell.placeholder)
        if cell.type == "text":
            return AutoTextView(cell.id, min_lines=2)
        if cell.type == "flag":
            return FlagButton(row_label, cell.id)
        raise ValueError(f"unknown AD cell type {cell.type!r} ({cell.id})")

    # ------------------------------------------------------------------
    # Edits
    # ------------------------------------------------------------------

    def _on_own_changed(self, _widget) -> None:
        if self._loading:
            return
        self._touched = True
        self._notify()

    def _on_link_changed(self, widget, path: str) -> None:
        if self._loading:
            return
        value = widget_value(widget)
        self._writing = True
        try:
            # mount=True: a link into a region that's switched off turns it
            # on (which loads its saved data) before the write lands.
            target = self._resolver.widget(path, mount=True)
            if target is None:
                logger.error("AD form: link target %s missing, edit not saved", path)
                return
            set_widget_value(target, value, notify=True)
            self._loading = True
            try:
                for w in self._links.get(path, []):
                    if w is not widget:
                        set_widget_value(w, value)
            finally:
                self._loading = False
        finally:
            self._writing = False
        self._touched = True
        self._update_tallies()
        self._notify()

    def _notify(self) -> None:
        if self._on_changed:
            self._on_changed()

    # ------------------------------------------------------------------
    # Linked-field refresh
    # ------------------------------------------------------------------

    def set_saved_provider(self, provider) -> None:
        """provider() -> the session's saved objective block, used to show
        linked values for regions that are currently switched off."""
        self._saved_provider = provider

    def refresh_links(self) -> None:
        """Re-read every linked mirror from its real field. Skipped while a
        write-through is in flight (a region being turned on by that write
        triggers a refresh mid-edit, which would revert the edited mirror)."""
        if self._writing:
            return
        saved = None
        self._loading = True
        try:
            for path, widgets in self._links.items():
                target = self._resolver.widget(path)
                if target is not None:
                    value = widget_value(target)
                else:
                    if saved is None:
                        saved = self._saved_provider() if self._saved_provider else {}
                    value = path_value(saved, path)
                for w in widgets:
                    set_widget_value(w, value)
        finally:
            self._loading = False
        self._update_tallies()

    def _update_tallies(self) -> None:
        def get(path):
            widgets = self._links.get(path)
            return widget_value(widgets[0]) if widgets else None
        for block, lbl in self._tallies:
            lbl.set_label(f"{block.tally['label']}: {tally_text(block, get)}")

    # ------------------------------------------------------------------
    # SectionBase
    # ------------------------------------------------------------------

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    def focus_first_field(self) -> None:
        if self._first_widget is not None:
            self._first_widget.grab_focus()

    def collect(self) -> dict:
        data = {fid: widget_value(w) for fid, w in self._own.items()}
        data[TOUCHED_KEY] = self._touched
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            for fid, w in self._own.items():
                set_widget_value(w, data.get(fid))
            self._touched = bool(data.get(TOUCHED_KEY, False))
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        return self._touched
