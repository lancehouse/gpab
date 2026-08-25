"""Search window for the Ctrl+F jump-search feature — GTK4 port of
pab_assessment.search_widget.SearchModal.

Same UX as the Ctrl+D KB browser's own search window
(objective/kb_db_screen.py's _KBSearchWindow): a small transient window
with a search entry and a live-filtered result list, Up/Down to move
selection, Enter to confirm, Escape to cancel. Kept as a separate small
class here (rather than sharing code with _KBSearchWindow) since the two
operate on differently-shaped entries (SearchEntry vs KBSearchEntry) with
no real logic in common beyond "a filtered list in a popup" — extracting a
shared base would only save a few dozen lines at the cost of an extra
layer of indirection for something this small.

Keyboard nav is wired via Gtk.SearchEntry's own signals
(next-match/previous-match/stop-search/activate), NOT a window-level
Gtk.EventControllerKey. GtkSearchEntry has built-in class key bindings for
exactly Down/Up/Escape/Enter (it's purpose-built for this "type to filter a
list" pattern) that consume those keys at the entry itself before they'd
ever bubble to an ancestor controller — a first version of this window used
a window-level key controller for Up/Down/Enter/Escape and none of the four
ever fired, for this reason. Connecting the entry's own signals is both the
fix and the idiomatic approach.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .search import SearchEntry, filter_entries


class SearchModal(Gtk.Window):
    """Ctrl+F jump-search. Escape cancels; Enter or clicking a result
    confirms and closes."""

    def __init__(self, parent: Gtk.Window, index: list[SearchEntry], on_selected) -> None:
        super().__init__(transient_for=parent, modal=True, decorated=False)
        self.set_default_size(560, 360)
        self._index = index
        self._entries: list[SearchEntry] = []
        self._selected_idx = -1
        self._on_selected = on_selected

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text("⌕ type to search…")
        self.entry.connect("search-changed", self._on_changed)
        self.entry.connect("next-match", self._on_next_match)
        self.entry.connect("previous-match", self._on_previous_match)
        self.entry.connect("stop-search", self._on_stop_search)
        self.entry.connect("activate", self._on_activate)
        box.append(self.entry)

        self.results_box = Gtk.ListBox()
        self.results_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.results_box.connect("row-activated", self._on_row_activated)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(300)
        scroll.set_child(self.results_box)
        box.append(scroll)

        self.set_child(box)

        self.connect("show", lambda *_a: self.entry.grab_focus())

    def _on_changed(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text()
        results = filter_entries(query, self._index) if query.strip() else []
        self._entries = results
        row = self.results_box.get_row_at_index(0)
        while row is not None:
            self.results_box.remove(row)
            row = self.results_box.get_row_at_index(0)
        for e in results:
            lbl = Gtk.Label(label=e.display)
            lbl.set_xalign(0.0)
            lbl.set_wrap(True)
            lbl.set_margin_start(6)
            lbl.set_margin_end(6)
            lbl.set_margin_top(3)
            lbl.set_margin_bottom(3)
            self.results_box.append(lbl)
        self._selected_idx = 0 if results else -1
        if results:
            self.results_box.select_row(self.results_box.get_row_at_index(0))

    def _on_next_match(self, _entry: Gtk.SearchEntry) -> None:
        if self._selected_idx < len(self._entries) - 1:
            self._selected_idx += 1
            self.results_box.select_row(self.results_box.get_row_at_index(self._selected_idx))

    def _on_previous_match(self, _entry: Gtk.SearchEntry) -> None:
        if self._selected_idx > 0:
            self._selected_idx -= 1
            self.results_box.select_row(self.results_box.get_row_at_index(self._selected_idx))

    def _on_activate(self, _entry: Gtk.SearchEntry) -> None:
        if 0 <= self._selected_idx < len(self._entries):
            self._finish(self._entries[self._selected_idx])

    def _on_stop_search(self, _entry: Gtk.SearchEntry) -> None:
        self._finish(None)

    def _on_row_activated(self, _box, row: Gtk.ListBoxRow) -> None:
        idx = row.get_index()
        if 0 <= idx < len(self._entries):
            self._finish(self._entries[idx])

    def _finish(self, result: SearchEntry | None) -> None:
        self._on_selected(result)
        self.close()
