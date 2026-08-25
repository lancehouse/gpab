"""Session-length clock — pure state/logic, no widgets.

New feature, no TUI equivalent to port from (flagged and confirmed with the
user 2026-08-24, workshopped standalone in scratchpad before landing here).

Owned by TrialWindow (like report_timer.py's ReportTimer) so it survives
switching between every assessment/objective tab — a per-section object
would be torn down/rebuilt on every tab switch, which a session-length clock
obviously can't tolerate.

Elapsed time is computed from GLib.get_monotonic_time() deltas rather than
counted in one-second increments, so a long session doesn't drift the way a
naive "add 1 every tick" counter would.

Deliberately in-memory only — does not persist across an app restart/crash
(confirmed acceptable with the user 2026-08-24: crashes are rare and losing
the elapsed time in that case is fine). Resets to 00:00 on next launch.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

# Alert thresholds, in seconds of RUNNING time (paused time does not count
# toward these — confirmed with the user 2026-08-24: "it's a timer not a
# wall clock"). Each fires once per run; reset() clears all three so a
# re-run session can hit them again.
THRESHOLDS_SECONDS = (20 * 60, 40 * 60, 55 * 60)


class SessionTimer:
    def __init__(self) -> None:
        self._started = False
        self._running = False
        self._accumulated_us = 0
        self._segment_start_us: int | None = None
        self._fired: set[int] = set()

    # ------------------------------------------------------------------

    def start_if_needed(self) -> None:
        """Called on the first qualifying field edit — a no-op on every
        edit after the first (see app.py's ConsentSection wiring)."""
        if self._started:
            return
        self._started = True
        self._running = True
        self._segment_start_us = GLib.get_monotonic_time()

    def toggle_pause(self) -> None:
        if not self._started:
            return
        if self._running:
            self._accumulated_us += GLib.get_monotonic_time() - self._segment_start_us
            self._segment_start_us = None
            self._running = False
        else:
            self._segment_start_us = GLib.get_monotonic_time()
            self._running = True

    def reset(self) -> None:
        self._started = False
        self._running = False
        self._accumulated_us = 0
        self._segment_start_us = None
        self._fired.clear()

    # ------------------------------------------------------------------

    @property
    def started(self) -> bool:
        return self._started

    @property
    def running(self) -> bool:
        return self._running

    def elapsed_seconds(self) -> int:
        us = self._accumulated_us
        if self._running and self._segment_start_us is not None:
            us += GLib.get_monotonic_time() - self._segment_start_us
        return int(us // 1_000_000)

    def poll_newly_crossed_thresholds(self) -> list[int]:
        """Call once per tick. Returns any threshold (seconds) crossed since
        the last call, each returned exactly once per run/reset cycle."""
        if not self._running:
            return []
        elapsed = self.elapsed_seconds()
        newly = []
        for t in THRESHOLDS_SECONDS:
            if elapsed >= t and t not in self._fired:
                self._fired.add(t)
                newly.append(t)
        return newly
