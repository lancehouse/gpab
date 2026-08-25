"""ROM (Range of Motion) row widget — GTK4 port of
pab_assessment.objective.sections.active_movement's RangeCell + ROMRow.

The TUI splits these into two classes (RangeCell = one degree cell,
ROMRow = label + up to 2 RangeCells) because Textual widgets are heavier
and RangeCell posts its own Changed message. GTK doesn't need that extra
layer — one Gtk.Box row with 1-2 TouchEntry cells covers both, and field
ids stay byte-identical to the TUI's (`{prefix}_ax_l_range` /
`{prefix}_ax_r_range`) so collect()/load() round-trip against real
_objective.json data.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..widgets import TouchEntry


class ROMRow(Gtk.Box):
    """label | Ax-Left [| Ax-Right] — bilateral rows omit the right cell
    entirely (mirrors the TUI leaving it an empty placeholder column)."""

    def __init__(self, label: str, prefix: str, bilateral: bool = False) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.add_css_class("grid-row")
        self._prefix = prefix
        self._bilateral = bilateral

        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_size_request(120, -1)
        self.append(lbl)

        self.entries: dict[str, TouchEntry] = {}
        self._add_cell(f"{prefix}_ax_l", "°")
        if not bilateral:
            self._add_cell(f"{prefix}_ax_r", "°")

    def _add_cell(self, prefix: str, placeholder: str) -> None:
        fid = f"{prefix}_range"
        entry = TouchEntry(fid, placeholder=placeholder)
        entry.set_hexpand(True)
        self.entries[fid] = entry
        self.append(entry)

    def field_ids(self) -> list[str]:
        return list(self.entries.keys())

    def collect(self) -> dict:
        return {fid: e.text.strip() for fid, e in self.entries.items()}

    def load(self, data: dict) -> None:
        for fid, e in self.entries.items():
            e.text = data.get(fid, "")
