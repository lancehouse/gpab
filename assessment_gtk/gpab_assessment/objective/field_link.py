"""Cross-linking one form's widget to another section's existing field.

Used by the AD block-form tab (objective/sections/ad_form.py): a linked
cell there is a *mirror* widget — same class and same options as the real
field's widget, cloned from it so the two can never grade on different
scales — and the real field stays the single source of truth. Editing the
mirror writes straight into the real widget (whose own "changed" handling
then schedules the normal save); the mirror is re-read from the real widget
whenever the AD tab is shown or reloaded. Nothing linked is ever stored
twice.

A link path names the real field the same way the form spec does
(pab_assessment.objective.ad_forms.parse_path): "<section>.<field_id>" for
a fixed objective section, "<region>.<active|passive|muscle|special>.<field_id>"
for a region tab's field. Region widgets only exist while that region is
mounted (toggled on), so LinkResolver also handles the unmounted case:
reading falls back to the saved _objective.json value, cloning uses a
throwaway template container, and writing asks the app to turn the region
on first (user decision 2026-10-22: entering a Hip value from the AD tab
turns Hip on, same as tapping its chip).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..widgets import AutoTextView, CheckButton, CycleField, MultiSelectGroup, RadioGroup, TouchEntry
from ..search import find_by_field_id
from .. import pab_path_bootstrap  # noqa: F401  (sys.path side effect)
from pab_assessment.objective.ad_forms import parse_path  # noqa: E402

# Widgets whose programmatic set_value() deliberately doesn't emit "changed"
# (load() semantics) — a write-through must emit it itself so the owning
# section notices and saves. TouchEntry/AutoTextView emit on their own.
_SILENT_SETTERS = (CheckButton, CycleField, RadioGroup, MultiSelectGroup)


def widget_value(w):
    if isinstance(w, TouchEntry):
        return w.text.strip()
    if isinstance(w, AutoTextView):
        return w.text
    return w.value


def set_widget_value(w, value, notify: bool = False) -> None:
    """Set w to value; notify=True makes it behave like a user edit (emits
    "changed" for widgets whose setter is silent). Never re-sets an
    unchanged text value — that would move the cursor of a field being
    typed in."""
    if isinstance(w, (TouchEntry, AutoTextView)):
        text = value or ""
        if w.text != text:
            w.text = text
        return
    if isinstance(w, MultiSelectGroup):
        value = list(value or [])
    if w.value == value:
        return
    w.set_value(value)
    if notify and isinstance(w, _SILENT_SETTERS):
        w.emit("changed")


def connect_changed(w, callback) -> None:
    if isinstance(w, AutoTextView):
        w.textview.get_buffer().connect("changed", lambda *_a: callback(w))
    else:
        w.connect("changed", lambda *_a: callback(w))


def clone_field_widget(src: Gtk.Widget, label: str = "") -> Gtk.Widget:
    """A new, unparented widget of src's class with src's options and
    field_id. `label` replaces a CheckButton/FlagButton's built-in label."""
    fid = src.field_id
    if isinstance(src, CheckButton):
        return type(src)(label or src.base_label, fid, compact=src.has_css_class("toggle-compact"))
    if isinstance(src, CycleField):
        w = type(src)("", fid)
        w.CYCLE = list(src.CYCLE)
        w.CSS_CLASS = dict(src.CSS_CLASS)
        w.set_value(None)
        return w
    if isinstance(src, MultiSelectGroup):
        return MultiSelectGroup(src._options, fid)
    if isinstance(src, RadioGroup):
        return RadioGroup(src._options, fid)
    if isinstance(src, TouchEntry):
        w = TouchEntry(fid, placeholder=src.get_placeholder_text() or "")
        w.set_hexpand(True)
        return w
    if isinstance(src, AutoTextView):
        return AutoTextView(fid, min_lines=2)
    raise TypeError(f"can't mirror {type(src).__name__} ({fid})")


class LinkResolver:
    """Finds the real widget behind a link path, against a live app window.

    `win` is app.TrialWindow; used duck-typed for: _sections_by_name,
    _active_regions, the four region tabs (active_movement, ...),
    ensure_region_active(region_id), session_file."""

    _REGION_TAB_ATTR = {
        "active": "active_movement",
        "passive": "passive_movement",
        "muscle": "muscle_testing",
        "special": "special_tests",
    }

    def __init__(self, win) -> None:
        self._win = win
        self._templates: dict[tuple[str, str], Gtk.Widget] = {}

    def _container(self, owner: str, sub: str | None):
        if sub is None:
            return self._win._sections_by_name.get(owner)
        tab = getattr(self._win, self._REGION_TAB_ATTR[sub])
        return tab.get_container(owner)

    def is_mounted(self, path: str) -> bool:
        owner, sub, _fid = parse_path(path)
        return sub is None or owner in self._win._active_regions

    def widget(self, path: str, mount: bool = False):
        """The real widget, or None if its region is off and mount=False.
        mount=True turns the region on first."""
        owner, sub, fid = parse_path(path)
        if sub is not None and owner not in self._win._active_regions:
            if not mount:
                return None
            self._win.ensure_region_active(owner)
        container = self._container(owner, sub)
        return find_by_field_id(container, fid) if container is not None else None

    def template(self, path: str):
        """A widget to clone from — the real one when mounted, else from a
        throwaway, never-shown container of that region/tab."""
        w = self.widget(path)
        if w is not None:
            return w
        owner, sub, fid = parse_path(path)
        key = (owner, sub)
        if key not in self._templates:
            from .region_section import RegionContainer
            self._templates[key] = RegionContainer(owner, sub)
        return find_by_field_id(self._templates[key], fid)

    def drop_templates(self) -> None:
        self._templates.clear()
