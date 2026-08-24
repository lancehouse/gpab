"""Session-length clock widget — sits pinned at the bottom of the left
sidebar column, persistent across every assessment AND objective tab (see
app.py, where it is placed as a sibling below sidebar_stack rather than
inside either SectionNav or ObjectiveNav individually — those two swap
wholesale, so anything placed only inside one of them would disappear when
the other is shown).

New feature, no TUI equivalent (flagged/confirmed with the user 2026-08-24;
sound + flash were workshopped standalone in scratchpad before landing
here — see conversation history, not a repo file, for that process).

Behaviour (all confirmed with the user 2026-08-24):
  - Starts at 00:00 the first time any field below "Session Framing" in the
    Consent tab is edited (app.py wires ConsentSection.set_on_below_framing_
    changed to self._session_timer.start_if_needed via this widget's
    on_field_edit()).
  - Single tap: pause/resume. Double tap: reset to 00:00. Distinguished via
    Gtk.GestureClick's n_press — a single tap is held for
    _DOUBLE_TAP_WINDOW_MS in case a second tap arrives (making it a double
    tap instead), which is the standard GTK idiom for this, not a hand-rolled
    timer-on-a-timer.
  - Alerts at 20 / 40 min: one beep + one screen flash. At 55 min: two of
    each, _ALERT_PULSE_GAP_MS apart. Pause excludes time from the 20/40/55
    thresholds (SessionTimer.poll_newly_crossed_thresholds only advances
    while running) — "it's a timer not a wall clock."
  - Alert delivery itself (the beep + the actual full-window flash) is owned
    by app.py, not this widget — the flash must cover the whole window, not
    just this ~190px sidebar column, so this widget only reports "N pulses
    happened" via on_alert(pulses) and lets the window handle it.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

from .session_timer import SessionTimer, THRESHOLDS_SECONDS

TICK_MS = 1000
_DOUBLE_TAP_WINDOW_MS = 300


def _format_elapsed(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class SessionTimerWidget(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.add_css_class("session-timer")
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(4)
        self.set_margin_end(4)

        self.timer = SessionTimer()
        self._on_alert = None  # set by app.py: callable(pulses: int)
        self._pending_single_tap_id: int | None = None
        self._tick_source_id: int | None = None

        heading = Gtk.Label(label="SESSION TIME")
        heading.add_css_class("session-timer-heading")
        self.append(heading)

        self.clock_label = Gtk.Label(label="00:00")
        self.clock_label.add_css_class("session-timer-clock")
        self.append(self.clock_label)

        self.status_label = Gtk.Label(label="tap to start")
        self.status_label.add_css_class("session-timer-status")
        self.append(self.status_label)

        gesture = Gtk.GestureClick.new()
        gesture.connect("pressed", self._on_pressed)
        self.add_controller(gesture)

        self._tick_source_id = GLib.timeout_add(TICK_MS, self._tick)

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_on_alert(self, callback) -> None:
        self._on_alert = callback

    def on_field_edit(self) -> None:
        """Called by app.py on every qualifying Consent field edit — a
        no-op after the first call, since SessionTimer.start_if_needed is
        itself idempotent once started."""
        was_started = self.timer.started
        self.timer.start_if_needed()
        if not was_started:
            self._refresh_display()

    # ------------------------------------------------------------------
    # Tap handling
    # ------------------------------------------------------------------

    def _on_pressed(self, _gesture, n_press: int, _x: float, _y: float) -> None:
        if n_press == 1:
            self._pending_single_tap_id = GLib.timeout_add(
                _DOUBLE_TAP_WINDOW_MS, self._fire_single_tap
            )
        elif n_press == 2:
            if self._pending_single_tap_id is not None:
                GLib.source_remove(self._pending_single_tap_id)
                self._pending_single_tap_id = None
            self.timer.reset()
            self._refresh_display()

    def _fire_single_tap(self) -> bool:
        self._pending_single_tap_id = None
        self.timer.toggle_pause()
        self._refresh_display()
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------
    # Ticking / display
    # ------------------------------------------------------------------

    def _tick(self) -> bool:
        self._refresh_display()
        newly = self.timer.poll_newly_crossed_thresholds()
        if newly and self._on_alert:
            # 55 min (the last threshold) is the double-pulse alert; 20/40
            # are single. THRESHOLDS_SECONDS is fixed at exactly 3 entries
            # in that order, so "last" is a safe/simple way to spot it.
            for t in newly:
                pulses = 2 if t == THRESHOLDS_SECONDS[-1] else 1
                self._on_alert(pulses)
        return True  # keep ticking

    def _refresh_display(self) -> None:
        self.clock_label.set_label(_format_elapsed(self.timer.elapsed_seconds()))
        self.clock_label.remove_css_class("session-timer-clock-paused")
        if not self.timer.started:
            self.status_label.set_label("tap to start")
        elif self.timer.running:
            self.status_label.set_label("")
        else:
            self.status_label.set_label("paused")
            self.clock_label.add_css_class("session-timer-clock-paused")

    def stop(self) -> None:
        """Called from app.py's _on_close_request, matching report_timer.py/
        chart_watcher.py's own stop() convention — avoids a dangling
        GLib source after the window is gone."""
        if self._tick_source_id is not None:
            GLib.source_remove(self._tick_source_id)
            self._tick_source_id = None
        if self._pending_single_tap_id is not None:
            GLib.source_remove(self._pending_single_tap_id)
            self._pending_single_tap_id = None
