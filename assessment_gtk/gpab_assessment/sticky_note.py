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
import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gtk, Gdk, Graphene  # noqa: E402

# GPAB_STICKY_NOTE_PATH override exists purely for isolated testing — this
# file is a real, live, cross-session clinician preference (not per-patient
# data), so a test run against any disposable session would otherwise still
# read/write the SAME shared global file a concurrently-running real gpabd/
# bodychart session is using. Added after exactly that nearly clobbered a
# real dragged position during testing — see git history. Unset in normal
# use, so this changes nothing for the real app.
_STICKY_NOTE_PATH = Path(os.environ.get(
    "GPAB_STICKY_NOTE_PATH",
    str(Path.home() / ".local" / "share" / "pab" / "sticky_note.json"),
))

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
        self._grab_dx = 0.0   # press point, offset from this widget's own top-left
        self._grab_dy = 0.0

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
        # GtkGestureSingle handles mouse AND touch by default (touch_only
        # only needs setting when mouse should be EXCLUDED, never for touch
        # to be included) — this app runs on a touchscreen laptop, so made
        # explicit here rather than leaving it an unstated default.
        drag.set_touch_only(False)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        # This widget is a direct GtkOverlay child, sized/positioned only
        # to its own NOTE_W x NOTE_H rect via get-child-position — nothing
        # else in the overlay claims the rest of that plane, so clicks
        # outside the note fall through to whatever's underneath with no
        # extra plumbing needed. (An earlier attempt wrapped this in an
        # always-full-size Gtk.Fixed with can_target(False), meaning to let
        # clicks pass through its empty area — that broke input to the
        # note entirely instead: GTK4 blocks picking for a widget's whole
        # subtree when can_target is False, not just the widget's own
        # empty area, so the note and its close button became unreachable
        # too. Reverted.)
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
    # Positioning
    # ------------------------------------------------------------------

    def _on_get_child_position(self, _overlay, widget, allocation) -> bool:
        # Confirmed via live testing (not guessed): PyGObject marshals this
        # signal's GdkRectangle* out-param as a plain 4th positional arg to
        # mutate in place, same as the C signature — NOT as a return value
        # (a "return a Gdk.Rectangle" version raised a TypeError about a
        # 4th argument being passed where only 3 were expected).
        if widget is not self:
            return False
        allocation.x = int(self._x)
        allocation.y = int(self._y)
        allocation.width = NOTE_W
        allocation.height = NOTE_H
        return True

    def _on_drag_begin(self, _gesture, start_x, start_y) -> None:
        # start_x/y: press point, offset from this widget's own top-left,
        # in this widget's local coordinates — stays valid as a "grab
        # offset" for the rest of the gesture regardless of where this
        # widget later moves to (unlike GTK's own cumulative dx/dy, see
        # drag-update below).
        self._grab_dx = start_x
        self._grab_dy = start_y

    def _on_drag_update(self, gesture, _dx, _dy) -> None:
        # GTK's own cumulative dx/dy (relative to drag-begin, in this
        # widget's LOCAL frame) is unusable here: this widget is the same
        # one being repositioned every update, via get-child-position
        # above. GTK re-derives each event's local coordinates from the
        # widget's CURRENT (already-partway-moved) allocation, so the
        # reported delta under-counts real pointer motion every frame —
        # converges to roughly half the actual drag distance with visible
        # jitter as it oscillates (reported after both the first, naive
        # version of this and a since-reverted "stationary Gtk.Fixed
        # stage" attempt — see __init__'s comment for why that one broke
        # input to the note entirely instead of just fixing the jitter).
        #
        # Fix: recompute this widget's ABSOLUTE position fresh on every
        # event, via a true geometric transform (compute_point, not a
        # cached delta), so there is nothing to accumulate and nothing
        # that can drift.
        ok, cur_x, cur_y = gesture.get_point(None)
        if not ok:
            return
        local_pt = Graphene.Point()
        local_pt.init(cur_x, cur_y)
        ok, overlay_pt = self.compute_point(self._overlay, local_pt)
        if not ok:
            return

        nx = overlay_pt.x - self._grab_dx
        ny = overlay_pt.y - self._grab_dy
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
            # Keep the in-memory copy in sync too — self._data was loaded
            # once at construction and is what set_context() re-reads on
            # every tab/mode switch (subjective <-> objective share this
            # one widget instance). Without this, the position written to
            # disk above was correct, but switching away and back would
            # still reposition from the STALE startup value, snapping the
            # note back to wherever it started — reported as "I can drag it
            # out of the way, but it realigns when I switch tabs."
            self._data[self._current_location]["x"] = self._x
            self._data[self._current_location]["y"] = self._y

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
