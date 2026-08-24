"""Drag-gesture bulk-select for grading grids (RadioGroup columns).

New feature (no TUI equivalent), scoped for this first phase to ONLY
NeurologicalSection — confirmed with the user 2026-08-24 ("my test tab for
this"). Written as its own shared mixin module, not inlined into
neurological.py, so a later phase can mix it into Muscle Testing/Sensory the
same way GridNav already generalizes across sections — see
CONVERSION_PLAN.md's "Flagged for future work" section for the three UX
decisions this implements, all confirmed with the user 2026-08-24:
  1. Same column-position replicated down every row the drag passes over —
     NOT raw spatial/pixel hit-testing. Dragging down the "3/5" chip in a
     myotome column sets "3/5" on every row's RadioGroup the drag crosses,
     regardless of exactly where the finger drifts horizontally.
  2. Live highlight while dragging; the actual bulk-set only commits on
     release (drag-end) — matches this project's standing "never lose data
     silently" rule.
  3. The drag only ever activates if it starts directly on a settable chip
     inside a RadioGroup. This falls out of the design rather than needing
     an explicit check: the Gtk.GestureDrag is attached to each RadioGroup
     individually (not once on the whole tab/ScrolledWindow), so a touch
     that starts on a row label, margin, or a notes field never reaches
     this code at all — the tab's own scroll handles it exactly as it did
     before this feature existed.

DRAG-VS-TAP DISAMBIGUATION
---------------------------
Gtk.GestureDrag's own "drag-begin" signal fires on every initial press, not
just genuine drags — claiming the gesture there would swallow ordinary
single-tap chip selection. So this deliberately does NOT claim the gesture
in drag-begin: it only claims (Gtk.EventSequenceState.CLAIMED) once the
drag's offset exceeds _DRAG_THRESHOLD_PX in drag-update. Below that
threshold, the touched Gtk.ToggleButton's own click handling is left
completely alone, so a plain tap still selects that one chip exactly as
before this feature existed. Once the threshold is crossed and the gesture
claims the sequence, GTK cancels the chip's own pending click for that same
touch — so a genuine drag never also fires an accidental single-select on
the chip it started on.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gtk, Graphene  # noqa: E402

from ..widgets import RadioGroup

_DRAG_HOVER_CSS = "grid-drag-hover"
_DRAG_THRESHOLD_PX = 5  # below this, treat as a plain tap — see module docstring.
# Lowered from 12 2026-08-24 per live touchscreen feedback ("needs about 1s
# to activate") — the perceived delay was this distance threshold needing
# that much finger movement before drag-update claims the gesture, not an
# actual timer anywhere in this code.


class GridDragSelect:
    """Mixin: gives a section drag-to-bulk-set across one or more vertical
    "columns" of same-shape RadioGroups. Call `_init_drag_select()` once in
    __init__, then `_register_drag_column(groups)` once per top-to-bottom
    run of RadioGroups that should drag together (e.g. all the Left-side
    myotome gangs in one block)."""

    def _init_drag_select(self) -> None:
        self._drag_group_to_column: dict[RadioGroup, list[RadioGroup]] = {}
        self._drag_active_column: list[RadioGroup] | None = None
        self._drag_start_group: RadioGroup | None = None
        self._drag_start_idx: int | None = None
        self._drag_start_x = 0.0
        self._drag_start_y = 0.0
        self._drag_claimed = False
        self._drag_hovered: list[RadioGroup] = []

    def _register_drag_column(self, groups: list[RadioGroup]) -> None:
        for g in groups:
            self._drag_group_to_column[g] = groups
            self._wire_drag(g)

    def _wire_drag(self, group: RadioGroup) -> None:
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin, group)
        drag.connect("drag-update", self._on_drag_update, group)
        drag.connect("drag-end", self._on_drag_end, group)
        drag.connect("cancel", self._on_drag_cancel)
        group.add_controller(drag)

    # ------------------------------------------------------------------

    def _on_drag_begin(self, gesture: Gtk.GestureDrag, x: float, y: float, group: RadioGroup) -> None:
        idx = group.chip_index_at(x, y)
        if idx is None:
            # Landed in a gap between chips, not on a settable cell — deny
            # immediately so nothing about this touch is claimed here.
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        self._drag_active_column = self._drag_group_to_column.get(group)
        self._drag_start_group = group
        self._drag_start_idx = idx
        self._drag_start_x = x
        self._drag_start_y = y
        self._drag_claimed = False
        self._drag_hovered = []
        # Deliberately NOT claiming yet — see module docstring. A plain tap
        # that never crosses _DRAG_THRESHOLD_PX leaves this gesture unclaimed
        # and the chip's own click fires normally.

    def _on_drag_update(self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float, group: RadioGroup) -> None:
        if self._drag_active_column is None or self._drag_start_idx is None:
            return
        if not self._drag_claimed:
            if (offset_x * offset_x + offset_y * offset_y) < (_DRAG_THRESHOLD_PX ** 2):
                return
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self._drag_claimed = True

        hit_group = self._resolve_hit_column_group(group, offset_x, offset_y)
        if hit_group is None:
            return

        column = self._drag_active_column
        start_pos = column.index(self._drag_start_group)
        hit_pos = column.index(hit_group)
        lo, hi = sorted((start_pos, hit_pos))
        newly_hovered = column[lo:hi + 1]
        for g in self._drag_hovered:
            if g not in newly_hovered:
                _set_hover(g, False)
        for g in newly_hovered:
            _set_hover(g, True)
        self._drag_hovered = newly_hovered

    def _on_drag_end(self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float, group: RadioGroup) -> None:
        if self._drag_claimed and self._drag_start_idx is not None:
            for g in self._drag_hovered:
                g.select_by_index(self._drag_start_idx)
        self._clear_drag_state()

    def _on_drag_cancel(self, gesture: Gtk.GestureDrag, sequence) -> None:
        self._clear_drag_state()

    def _clear_drag_state(self) -> None:
        for g in self._drag_hovered:
            _set_hover(g, False)
        self._drag_hovered = []
        self._drag_active_column = None
        self._drag_start_group = None
        self._drag_start_idx = None
        self._drag_claimed = False

    def _resolve_hit_column_group(self, start_group: RadioGroup, offset_x: float, offset_y: float) -> RadioGroup | None:
        """Translate the current drag point from start_group's own
        coordinate space into the window's, pick() the widget under it
        there, then walk up to find which (if any) RadioGroup in the active
        column that widget belongs to."""
        point = Graphene.Point()
        point.x = self._drag_start_x + offset_x
        point.y = self._drag_start_y + offset_y
        root = start_group.get_root()
        if root is None:
            return None
        success, root_point = start_group.compute_point(root, point)
        if not success:
            return None
        target = root.pick(root_point.x, root_point.y, Gtk.PickFlags.DEFAULT)
        w = target
        while w is not None:
            if isinstance(w, RadioGroup) and w in self._drag_active_column:
                return w
            w = w.get_parent()
        return None


def _set_hover(group: RadioGroup, on: bool) -> None:
    if on:
        group.add_css_class(_DRAG_HOVER_CSS)
    else:
        group.remove_css_class(_DRAG_HOVER_CSS)
