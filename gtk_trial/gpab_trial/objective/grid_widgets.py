"""Bilateral L/R grid-row kit — shared by every Objective tab with a
reflex/myotome/dermatome-style table (Neurological now; Sensory, Muscle,
and the ROM tables later). Centralizing this here means those later tabs
reuse the same row shape instead of re-deriving column widths by feel —
the same principle as widgets.field_left_slot()/make_subsection_header()
for the assessment sections.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

# Label column width for a compact grid row (e.g. "Biceps   C5/6"). Deliberately
# narrower than widgets.FIELD_LEFT_COLUMN_PX (230px) — that constant is for
# question-style field rows with wrapping labels; a grid row's label is a
# single short line, so a wide column would just waste width from the two
# L/R gangs it sits beside. Every grid row in every section uses this same
# constant so label columns line up down the whole tab.
GRID_LABEL_COL_PX = 170


def grid_label(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text)
    lbl.set_halign(Gtk.Align.START)
    lbl.set_size_request(GRID_LABEL_COL_PX, -1)
    lbl.set_hexpand(False)
    return lbl


def bilateral_header_row() -> Gtk.Box:
    """Blank label-width spacer + centered "Left" / "Right" column headers."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    spacer = Gtk.Box()
    spacer.set_size_request(GRID_LABEL_COL_PX, -1)
    row.append(spacer)
    for side in ("Left", "Right"):
        lbl = Gtk.Label(label=side)
        lbl.add_css_class("grid-col-header")
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.CENTER)
        row.append(lbl)
    return row


def bilateral_radio_row(label_text: str, left: Gtk.Widget, right: Gtk.Widget) -> Gtk.Box:
    """label | left gang | right gang — the reflex/myotome/dermatome row shape."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.add_css_class("grid-row")
    row.append(grid_label(label_text))
    left.set_hexpand(True)
    left.set_halign(Gtk.Align.CENTER)
    row.append(left)
    right.set_hexpand(True)
    right.set_halign(Gtk.Align.CENTER)
    row.append(right)
    return row


def bilateral_field_row(label_text: str, left_widgets: list[Gtk.Widget], right_widgets: list[Gtk.Widget]) -> Gtk.Box:
    """label | [left widgets...] | [right widgets...] — for neurodynamics rows
    (an optional degree Entry followed by a response Entry, per side)."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.add_css_class("grid-row")
    row.append(grid_label(label_text))
    for widgets in (left_widgets, right_widgets):
        side_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        side_box.set_hexpand(True)
        for w in widgets:
            side_box.append(w)
        row.append(side_box)
    return row
