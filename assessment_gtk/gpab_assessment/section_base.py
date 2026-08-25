"""Shared contract every ported section implements.

Defined now, with only 3 of ~23 sections built, so the interface is fixed
before the remaining ~20 are ported rather than retrofitted across all of
them afterward (see CONVERSION_PLAN.md Phase 3). Not an ABC: sections are
Gtk.Box (GObject) subclasses, and GObject's metaclass conflicts with
abc.ABCMeta, so this is a plain mixin — stub methods raise NotImplementedError
as documentation, not enforcement.

Methods a section must implement itself: collect(), load(data), is_complete(),
focus_first_field(), set_on_changed(callback) — these already exist on every
built section (see sections/consent.py etc.), this class just formalizes them.

reload() is new: the hook a future live re-sync (body-chart watcher, KB
update) calls to re-apply freshly-read session data. Default implementation
is just load() — sections only need to override it if they hold state a
plain load() would be wrong to stomp (e.g. a field the user is mid-typing
into elsewhere in the window); see app.py's _sync_goals_* methods for the
existing pattern of skipping whatever widget currently has focus.
"""

from __future__ import annotations


class SectionBase:
    def collect(self) -> dict:
        raise NotImplementedError

    def load(self, data: dict) -> None:
        raise NotImplementedError

    def is_complete(self) -> bool:
        raise NotImplementedError

    def focus_first_field(self) -> None:
        raise NotImplementedError

    def set_on_changed(self, callback) -> None:
        raise NotImplementedError

    def reload(self, data: dict) -> None:
        self.load(data)
