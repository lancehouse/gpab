"""Floating "reminder to self" sticky note — gpab's half of a feature shared
with bodychart (see bodychart/src/sticky_note.c's module docstring for the
full picture). This is a physio-wide preference, not per-patient data: one
piece of text plus three independent show/position "locations"
(bodychart/subjective/objective), set once from bodychart's launch dialog
and persisted at ~/.local/share/pab/sticky_note.json — the *same* file both
apps read/write, kept in sync by convention (matching JSON shape), not by a
shared source.

gpab only ever renders the "subjective" and "objective" locations (one
widget instance, repositioned/shown depending on which is currently active
— see app.py's _update_sticky_note, called from _show_section). The
"bodychart" location is bodychart's own to draw.

Text is fixed for the life of this process — the only way to change it is
the launch dialog, which runs before gpab starts — so it's loaded once at
widget construction and never re-read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GObject  # noqa: E402

_STICKY_NOTE_PATH = Path.home() / ".local" / "share" / "pab" / "sticky_note.json"

NOTE_W = 190
NOTE_H = 190
_MAX_FONT = 26.0
_MIN_FONT = 9.0
_MAX_LINES = 8

_LOCATIONS = ("bodychart", "subjective", "objective")


def load_sticky_note() -> dict:
    """Returns {"text": str, "bodychart": {...}, "subjective": {...},
    "objective": {...}}, each location {"show": bool, "x": float, "y": float}.
    Defaults (blank text, all off, x=y=40) if the file is missing/corrupt —
    mirrors bodychart/src/sticky_note.c's sticky_note_load()."""
    data = {
        "text": "",
        "bodychart":  {"show": False, "x": 40.0, "y": 40.0},
        "subjective": {"show": False, "x": 40.0, "y": 40.0},
        "objective":  {"show": False, "x": 40.0, "y": 40.0},
    }
    try:
        raw = json.loads(_STICKY_NOTE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return data
    if isinstance(raw.get("text"), str):
        data["text"] = raw["text"]
    for loc in _LOCATIONS:
        v = raw.get(loc)
        if not isinstance(v, dict):
            continue
        if isinstance(v.get("show"), bool):
            data[loc]["show"] = v["show"]
        for k in ("x", "y"):
            if isinstance(v.get(k), (int, float)):
                data[loc][k] = float(v[k])
    return data


def save_sticky_note_position(location: str, x: float, y: float) -> bool:
    """Read-modify-write: updates one location's x/y only, preserving text
    and every show flag — the gpab-side counterpart to bodychart's own
    sticky_note_save_position() (called after a drag ends here too). Text
    and the show flags are only ever edited from bodychart's launch
    dialog — gpab never writes those, only position."""
    if location not in _LOCATIONS:
        return False
    data = load_sticky_note()
    data[location]["x"] = x
    data[location]["y"] = y
    try:
        _STICKY_NOTE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STICKY_NOTE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(_STICKY_NOTE_PATH)
    except Exception:
        return False
    return True


def _wrap_and_fits(cr, text: str, font_size: float, max_w: float, max_h: float):
    """Greedy word-wrap at the given font size. Returns (lines, True) if it
    fits within max_w/max_h, else (partial_lines, False) so the caller can
    retry smaller. Mirrors bodychart/src/sticky_note.c's sticky_text_fits()
    — reimplemented here (Cairo is available directly via PyGObject's
    DrawingArea draw_func), not shared, same as the C/Python quality-word
    tables elsewhere in this project."""
    cr.select_font_face("Sans", 0, 1)  # normal slant, bold weight
    cr.set_font_size(font_size)

    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}" if cur else word
        te = cr.text_extents(trial)
        if (te.width - te.x_bearing) <= max_w or not cur:
            cur = trial
        else:
            if len(lines) >= _MAX_LINES:
                return lines, False
            lines.append(cur)
            cur = word
            te = cr.text_extents(cur)
            if (te.width - te.x_bearing) > max_w:
                return lines, False  # one word too wide even alone
    if cur:
        if len(lines) >= _MAX_LINES:
            return lines, False
        lines.append(cur)

    fe = cr.font_extents()
    line_h = fe[2]  # (ascent, descent, height, max_x_advance, max_y_advance)
    if line_h * len(lines) > max_h:
        return lines, False
    return lines, True


class StickyNoteWidget(Gtk.Box):
    """One floating note, shown for whichever of "subjective"/"objective"
    is currently active (see set_context()). Position and show-state are
    tracked per location; a corner X hides it in-memory for the rest of
    this run only (does not touch the persisted show flag — matches
    bodychart's own close-button behaviour, see sticky_note.c)."""

    def __init__(self, overlay: Gtk.Overlay) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("sticky-note")
        self.set_size_request(NOTE_W, NOTE_H)
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)
        self.set_visible(False)

        self._data = load_sticky_note()
        self._overlay = overlay
        self._dismissed: set[str] = set()   # locations closed via X this run
        self._current_location: str | None = None
        self._x = 0.0
        self._y = 0.0
        self._drag_start_x = 0.0
        self._drag_start_y = 0.0

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        close_btn = Gtk.Button(label="×")
        close_btn.add_css_class("sticky-note-close")
        close_btn.set_halign(Gtk.Align.END)
        close_btn.set_hexpand(True)
        close_btn.connect("clicked", self._on_close_clicked)
        top.append(close_btn)
        self.append(top)

        self._area = Gtk.DrawingArea()
        self._area.set_hexpand(True)
        self._area.set_vexpand(True)
        self._area.set_draw_func(self._draw_text)
        self.append(self._area)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        overlay.connect("get-child-position", self._on_get_child_position)
        overlay.add_overlay(self)

    # ------------------------------------------------------------------
    # Drawing — auto-shrinking font so the text always fits the fixed box
    # ------------------------------------------------------------------

    def _draw_text(self, _area, cr, width, height) -> None:
        text = self._data.get("text", "")
        if not text:
            return
        pad = 10.0
        max_w = width - 2 * pad
        max_h = height - 2 * pad

        font_size = _MAX_FONT
        lines: list[str] = []
        fitted = False
        while font_size >= _MIN_FONT:
            lines, fitted = _wrap_and_fits(cr, text, font_size, max_w, max_h)
            if fitted:
                break
            font_size -= 1.0
        if not fitted:
            font_size = _MIN_FONT
            lines, _ = _wrap_and_fits(cr, text, font_size, max_w, max_h)
            if not lines:
                return

        cr.set_font_size(font_size)
        fe = cr.font_extents()
        ascent, _descent, line_h = fe[0], fe[1], fe[2]
        total_h = line_h * len(lines)
        start_y = (height - total_h) / 2.0 + ascent

        cr.set_source_rgba(0.30, 0.24, 0.04, 1.0)
        for i, line in enumerate(lines):
            te = cr.text_extents(line)
            x = (width - (te.width - te.x_bearing)) / 2.0
            cr.move_to(x, start_y + line_h * i)
            cr.show_text(line)

    # ------------------------------------------------------------------
    # Positioning — GtkOverlay's get-child-position gives pixel-perfect
    # free placement, same technique as bodychart/src/sticky_note.c.
    # ------------------------------------------------------------------

    def _on_get_child_position(self, _overlay, widget, allocation) -> bool:
        if widget is not self:
            return False
        allocation.x = int(self._x)
        allocation.y = int(self._y)
        allocation.width = NOTE_W
        allocation.height = NOTE_H
        return True

    def _on_drag_begin(self, _gesture, _start_x, _start_y) -> None:
        self._drag_start_x = self._x
        self._drag_start_y = self._y

    def _on_drag_update(self, _gesture, dx, dy) -> None:
        nx = self._drag_start_x + dx
        ny = self._drag_start_y + dy
        win_w = self._overlay.get_width()
        win_h = self._overlay.get_height()
        if win_w > NOTE_W:
            nx = max(0.0, min(nx, win_w - NOTE_W))
        if win_h > NOTE_H:
            ny = max(0.0, min(ny, win_h - NOTE_H))
        self._x, self._y = nx, ny
        self._overlay.queue_allocate()

    def _on_drag_end(self, _gesture, _dx, _dy) -> None:
        if self._current_location:
            save_sticky_note_position(self._current_location, self._x, self._y)

    def _on_close_clicked(self, _btn) -> None:
        if self._current_location:
            self._dismissed.add(self._current_location)
        self.set_visible(False)

    # ------------------------------------------------------------------
    # Context switching — called by app.py whenever the active
    # section/mode changes (see app.py's _update_sticky_note).
    # ------------------------------------------------------------------

    def set_context(self, location: str | None) -> None:
        """location is "subjective", "objective", or None (neither —
        hides the note without affecting either location's dismissed
        state)."""
        self._current_location = location
        if location is None:
            self.set_visible(False)
            return
        loc_data = self._data.get(location, {})
        if (
            not self._data.get("text")
            or not loc_data.get("show")
            or location in self._dismissed
        ):
            self.set_visible(False)
            return
        self._x = float(loc_data.get("x", 40.0))
        self._y = float(loc_data.get("y", 40.0))
        self._overlay.queue_allocate()
        self.set_visible(True)
