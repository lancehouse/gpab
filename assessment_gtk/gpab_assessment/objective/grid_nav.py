"""Shared spatial grid navigation for objective tab sections.

Mirrors pab_assessment.objective.sections.neurological's _grid/_grid_pos/_nav
pattern exactly: rows are lists of field ids in left-to-right visual order;
moving up/down keeps the same column (clamped to the target row's length,
never wrapping); moving left/right stays within the current row (no wrap,
no cross-row jump). Additionally supports a "next" direction — used by
RadioGroup/CheckButton's Enter/Space commit — which flattens the grid in
row-major order to advance to the next cell, one Enter at a time.

Any future dense grid tab (Sensory, Muscle, ROM) should mix in GridNav
rather than reimplementing this, so a fix or refinement here benefits every
tab built on top of it — same centralization principle as field_left_slot()
and make_subsection_header() in widgets.py.
"""

from __future__ import annotations


class GridNav:
    """Mixin: call _init_grid() once, then _add_grid_row(ids) per visual
    row as widgets are built, then route each widget's "navigate" signal
    to _grid_nav(field_id, direction, widgets_by_id).
    """

    def _init_grid(self) -> None:
        self._grid: list[list[str]] = []
        self._grid_pos: dict[str, tuple[int, int]] = {}

    def _add_grid_row(self, field_ids: list[str]) -> None:
        row = len(self._grid)
        self._grid.append(list(field_ids))
        for col, fid in enumerate(field_ids):
            self._grid_pos[fid] = (row, col)

    def _grid_nav(self, fid: str, direction: str, widgets_by_id: dict) -> None:
        if fid not in self._grid_pos:
            return
        if direction == "next":
            self._grid_focus_next(fid, widgets_by_id)
            return

        row, col = self._grid_pos[fid]
        if direction == "left":
            if col > 0:
                widgets_by_id[self._grid[row][col - 1]].grab_focus()
            return
        if direction == "right":
            if col < len(self._grid[row]) - 1:
                widgets_by_id[self._grid[row][col + 1]].grab_focus()
            return

        if direction == "up":
            target_row = row - 1
        elif direction == "down":
            target_row = row + 1
        else:
            return
        if 0 <= target_row < len(self._grid):
            target_ids = self._grid[target_row]
            tc = min(col, len(target_ids) - 1)
            widgets_by_id[target_ids[tc]].grab_focus()

    def _grid_focus_next(self, fid: str, widgets_by_id: dict) -> None:
        row, col = self._grid_pos[fid]
        if col + 1 < len(self._grid[row]):
            target = self._grid[row][col + 1]
        elif row + 1 < len(self._grid):
            target = self._grid[row + 1][0]
        else:
            return
        widgets_by_id[target].grab_focus()
