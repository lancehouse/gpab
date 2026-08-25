"""Periodic background report regeneration — GTK4 port of
assessment_view.py's 60s `_report_interval` (`self.set_interval(_REPORT_INTERVAL,
lambda: asyncio.create_task(self._generate_reports()))`).

This is intentionally the ONE piece of report-generation logic that lives
outside `report_modal.py` (Ctrl+R) — same separation the reference TUI
already has: `_generate_reports()` (this timer's target, three calls: raw +
markdown + clean) is a completely different call shape from `tui.py`'s own
Ctrl+R handler (which does raw + markdown-with-clean/dev flags + clean +
pandoc/docx, and shows a viewer). Porting the timer here does NOT touch
`report_modal.py` — see `storage_bridge.generate_all_reports()`'s docstring
for the exact TUI call it mirrors.

WHY A BACKGROUND THREAD
------------------------
The reference implementation runs its three report writers concurrently via
`asyncio.gather(asyncio.to_thread(...), ...)`, off Textual's own asyncio
event loop. GTK's main loop is GLib's, not asyncio's, so there's no
`asyncio.to_thread` equivalent to reach for — but the underlying reason is
the same either way: `save_raw_report`/`export_session_report`/
`save_clean_reports` do real file I/O and markdown rendering, and calling
them directly from a `GLib.timeout_add` callback would block GTK's main
thread (and therefore the UI) for however long that takes, every 60
seconds, for the life of the app. A plain Python `threading.Thread` sidesteps
that. Unlike the reference's `asyncio.gather` (three calls running
concurrently), this runs the three sequentially inside one thread — a
deliberate simplification, not an oversight: the reports are small
JSON-driven text/markdown, so the wall-clock difference is negligible, and
one thread instead of three is less new-and-unverified machinery to trust
(same reasoning as chart_watcher.py's polling-not-FileMonitor choice).

storage.py's writes are already atomic (per this repo's own CLAUDE.md
guarantee) and these functions hold no shared mutable state, so running them
from a background thread while the GTK main thread might independently be
mid-autosave via app.py's own debounced `_do_save()`/`_do_save_obj()` is
safe — worst case here is two independent, unrelated atomic writes racing to
finish first, not a torn/corrupted file.

NOT WIRED TO SECTION-CHANGE EVENTS
------------------------------------
Exactly like the reference: this timer runs on a fixed cadence regardless of
whether anything actually changed since the last tick (rewriting the same
content is harmless, if slightly wasteful) — it is NOT triggered by
`_schedule_save`/`_do_save`/`_do_save_obj`, matching `assessment_view.py`'s
own `_do_save()`, which does not call `_generate_reports()` either (checked
directly, not assumed — `storage.py`'s own `save_clean_reports()` docstring
claims otherwise ("Called from _do_save() alongside...") but that comment is
stale relative to the actual reference `_do_save()` body, which contains no
such call).
"""

from __future__ import annotations

import logging
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

from .storage_bridge import generate_all_reports

logger = logging.getLogger(__name__)

REPORT_INTERVAL_MS = 60_000  # matches pab_assessment.assessment_view._REPORT_INTERVAL (60.0s)


class ReportTimer:
    """Regenerates *_raw.txt / *_report.md / *_clean.{txt,md} every 60s in a
    background thread. See module docstring for the full design/rationale."""

    def __init__(self, session_file: str) -> None:
        self._session_file = session_file
        self._source_id: int | None = None

    def start(self) -> None:
        if self._source_id is not None:
            return
        self._source_id = GLib.timeout_add(REPORT_INTERVAL_MS, self._tick)

    def stop(self) -> None:
        if self._source_id is not None:
            GLib.source_remove(self._source_id)
            self._source_id = None

    def _tick(self) -> bool:
        threading.Thread(target=self._run, daemon=True).start()
        return True  # keep the 60s interval running — GLib stops it on False

    def _run(self) -> None:
        # Runs on the background thread — never touch GTK widgets from here.
        # Wrapped in try/except per this project's rule for any recurring
        # callback (mirrors _generate_reports()'s own try/except, and
        # chart_watcher.py's identical reasoning): an uncaught exception on
        # a bare background thread is otherwise printed to stderr and the
        # thread just dies silently, with no next tick to retry until the
        # 60s timer fires again anyway — logging it here beats losing it.
        try:
            generate_all_reports(self._session_file)
        except Exception as e:
            logger.error("report_timer: generate_all_reports failed: %s", e)
