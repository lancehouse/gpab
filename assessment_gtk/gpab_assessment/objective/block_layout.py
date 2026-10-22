"""Block-form layout — position sections of self-contained cards, for
AD-style forms (objective/sections/ad_form.py).

Every other objective tab is one long column of full-width rows. A block
form is instead a sequence of position sections (Standing, Sitting,
Supine, ...), each holding cards that reflow side by side as width allows
(Gtk.FlowBox), so related tests sit together the way they do on a paper
form. A card marked wide always takes a full line (e.g. a dense L/R
myotome grid that would be unreadable at card width).

Inside a card, rows sit on one Gtk.Grid — label | L | R, or one column per
cell for blocks with explicit columns — so cells line up within the card
regardless of label length. Keyboard nav is per card (GridNav), keyed on
each row's widget order, so Up/Down/Left/Right/Enter behave like every other
grid tab without one card's field ids colliding with another's.

Content-agnostic: knows nothing about AD, links or field semantics.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango  # noqa: E402

from ..widgets import make_subsection_header
from .grid_nav import GridNav

CARD_MIN_WIDTH_PX = 440
CARD_LABEL_COL_PX = 150


class BlockCard(Gtk.Box, GridNav):
    def __init__(self, title: str, note: str = "", wide: bool = False) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("block-card")
        self.wide = wide
        self.set_size_request(CARD_MIN_WIDTH_PX, -1)
        self.set_hexpand(True)
        self._init_grid()
        self._nav_widgets: dict[str, Gtk.Widget] = {}

        heading = Gtk.Label(label=title)
        heading.add_css_class("block-card-title")
        heading.set_halign(Gtk.Align.START)
        heading.set_xalign(0.0)
        heading.set_wrap(True)
        self.append(heading)
        if note:
            self.append(self._note_label(note))

        self.grid = Gtk.Grid(column_spacing=6, row_spacing=4)
        self.grid.set_hexpand(True)
        self.append(self.grid)
        self._row = 0

    @staticmethod
    def _note_label(text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("reference-note")
        lbl.set_halign(Gtk.Align.START)
        lbl.set_xalign(0.0)
        lbl.set_wrap(True)
        return lbl

    def _label(self, text: str, hint: str = "") -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_size_request(CARD_LABEL_COL_PX, -1)
        box.set_valign(Gtk.Align.CENTER)
        lbl = Gtk.Label(label=text)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_xalign(0.0)
        lbl.set_wrap(True)
        box.append(lbl)
        if hint:
            h = Gtk.Label(label=f"({hint})")
            h.add_css_class("reference-note")
            h.set_halign(Gtk.Align.START)
            h.set_xalign(0.0)
            h.set_wrap(True)
            box.append(h)
        return box

    def add_column_headers(self, headers: list[str]) -> None:
        """headers[0] sits over the label column, the rest over cell columns."""
        for col, text in enumerate(headers):
            lbl = Gtk.Label(label=text)
            lbl.add_css_class("grid-col-header")
            lbl.set_hexpand(col > 0)
            # Wrap, so a long header (e.g. "Temperature — cold (Aδ & C)")
            # never sets the card's minimum width — see the GTK sizing
            # notes in CONVERSION_PLAN/memory: one wide card widens the tab.
            lbl.set_wrap(True)
            lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            lbl.set_justify(Gtk.Justification.CENTER)
            self.grid.attach(lbl, col, self._row, 1, 1)
        self._row += 1

    def add_row(self, label: str, groups: list[list[Gtk.Widget]], hint: str = "",
                nav_keys: list[str] | None = None,
                group_labels: list[str] | None = None) -> None:
        """One grid row: label, then one grid column per group (a group is a
        list of widgets sharing that column, e.g. a radio + its comment).
        A single group spans every cell column; an empty label lets the
        group span the label column too (a free-text block body).
        nav_keys: one key per widget across all groups, in visual order,
        for this card's arrow-key nav — omitted widgets aren't navigable.
        group_labels: an inline caption per group (e.g. "L"/"R"), for a
        card whose rows don't all share one column-header row."""
        start_col = 0 if not label and len(groups) == 1 else 1
        if start_col:
            self.grid.attach(self._label(label, hint), 0, self._row, 1, 1)
        span_all = len(groups) == 1
        for i, widgets in enumerate(groups):
            cell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            cell.set_hexpand(True)
            if group_labels:
                cap = Gtk.Label(label=group_labels[i])
                cap.add_css_class("grid-col-header")
                cell.append(cap)
            for w in widgets:
                cell.append(w)
            width = (3 - start_col) if span_all else 1
            self.grid.attach(cell, start_col + i, self._row, width, 1)
        self._row += 1
        if nav_keys:
            flat = [w for widgets in groups for w in widgets]
            for key, w in zip(nav_keys, flat):
                self._nav_widgets[key] = w
                w.connect("navigate", self._on_navigate, key)
            self._add_grid_row(nav_keys)

    def add_full(self, widget: Gtk.Widget) -> None:
        self.grid.attach(widget, 0, self._row, 3, 1)
        self._row += 1

    def _on_navigate(self, _widget, direction: str, key: str) -> None:
        self._grid_nav(key, direction, self._nav_widgets)


class PositionSection(Gtk.Box):
    """A position heading ("Standing", ...) over its cards: normal cards
    reflow in a FlowBox, wide cards take a full line each, original order
    preserved (consecutive normal cards share one FlowBox)."""

    def __init__(self, label: str, anchor_id: str | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(make_subsection_header(label, anchor_id))
        self._flow: Gtk.FlowBox | None = None

    def add_card(self, card: BlockCard) -> None:
        if card.wide:
            self._flow = None
            self.append(card)
            return
        if self._flow is None:
            self._flow = Gtk.FlowBox()
            self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
            self._flow.set_homogeneous(False)
            self._flow.set_min_children_per_line(1)
            self._flow.set_max_children_per_line(3)
            self._flow.set_column_spacing(8)
            self._flow.set_row_spacing(8)
            self._flow.set_valign(Gtk.Align.START)
            self.append(self._flow)
        self._flow.append(card)
        # The FlowBoxChild wrapper is focusable by default — it would add a
        # dead Tab stop (and a selection highlight) in front of every card.
        child = card.get_parent()
        if child is not None:
            child.set_focusable(False)
            child.set_valign(Gtk.Align.START)
