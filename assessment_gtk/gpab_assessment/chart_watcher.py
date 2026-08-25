"""Live body-chart re-sync — GTK4 counterpart to pab_assessment.watcher's
BodyChartWatcher, deliberately narrowed in scope. Read this whole docstring
before touching this file: it explains what's ported, what's intentionally
NOT ported, and how it was verified, since this piece has not yet been
exercised by the user against a live bodychart session (see the note at the
bottom on how to test it when you can).

WHAT THIS DOES
---------------
Polls this app's own `session_file` (the *_session.json the real GTK
bodychart app owns and writes strokes/notes/etc. into — never written by
this app, see ../CLAUDE.md's per-file ownership table) for mtime changes,
and when it changes, calls `SubjectiveSection.refresh_from_chart(data)`
(sections/subjective.py) to re-derive that section's dynamic note slots from
the new body-chart content — exactly mirroring tui.py's on_chart_update,
which does the same single thing (`subj.refresh_from_chart(data)`) and
nothing else.

WHAT'S DELIBERATELY NOT PORTED, AND WHY
-----------------------------------------
The reference BodyChartWatcher (pab_assessment/watcher.py) does three things;
this only does one of them:

1. Session-switch detection (watching ~/.local/share/pab/session_current.json
   for the GTK app opening a DIFFERENT patient session, then hot-reloading
   the whole assessment view to match). NOT PORTED: gpab has no session
   picker — main.py launches fixed against exactly one `--session` path for
   the process's whole lifetime (see main.py's own docstring). There is no
   "current session" concept to switch to here; auto-reloading a different
   session's data into a running window would be actively dangerous (risk of
   writing one patient's edits into another patient's file) and doesn't
   correspond to anything the user can even trigger in this app's design.
2. The `.focus_tui` signal file (GTK asking the embedded TUI to raise itself
   to the front). NOT PORTED: this only means something once bodychart is
   actually launching/embedding gpab (Phase 6, `~/Projects/pab`'s own
   `integration.c` wiring) — there is no "front" to raise to yet, since
   nothing launches this app but a person running `run.sh` by hand.
3. `BodyChartPanel` indicator refresh (chart_panel.symptom_types_used /
   .views_drawn — small icons in the TUI's top bar showing which symptom
   types/views have been drawn on). NOT PORTED: gpab has no equivalent
   widget built at all (grep confirms zero references to symptom_types_used
   anywhere in gpab_assessment/) — there's nothing to refresh.

Also unlike the reference implementation, `active_regions` / RegionTabContent
mounting is NOT touched here — re-read tui.py's own on_chart_update (lines
~599-616 as of this writing) and confirm it doesn't touch that either. Region
mount/unmount stays exactly what it already was: a manual toggle via
RegionTopbar, per CONVERSION_PLAN.md's Phase 3 table. Don't add active-region
syncing to this file without deliberately deciding that's now in scope — it
isn't today, and folding it in silently would be scope creep past what this
task asked for.

POLLING, NOT Gio.FileMonitor — DELIBERATE CHOICE
--------------------------------------------------
CONVERSION_PLAN.md's Phase 3 table originally floated Gio.FileMonitor as
"probably the right call" here. This implementation uses plain
`GLib.timeout_add` + mtime-diffing instead, matching the reference
BodyChartWatcher's own algorithm/cadence (2s poll interval) almost exactly.
Reasoning: the user cannot test this component themselves for a while (no
bodychart-integration in this sandbox), so the priority was minimizing the
surface area for new, unverifiable failure modes rather than being maximally
"GTK-idiomatic". Polling is the same approach already proven correct in
production (the reference TUI has run this exact algorithm against the real
bodychart app for a long time); Gio.FileMonitor would add new untested edge
cases (rapid-fire events mid-write, atomic-rename vs in-place-write
semantics, different behaviour if the file doesn't exist yet at watch-start)
that nobody can catch here quickly. If this is ever revisited, do it as a
deliberate follow-up, not folded into this port.

DATA-SAFETY / RECONCILIATION POLICY
-------------------------------------
refresh_from_chart() (see sections/subjective.py) snapshots the CURRENTLY
DISPLAYED widget text before rebuilding note slots, and feeds it back in as
the "saved" base — so anything the clinician has typed since the last save
survives a chart-driven refresh, even mid-keystroke. This is not a new
invention: it's the exact mechanism the reference TUI already uses (see
sections/subjective.py's refresh_from_chart docstring for the full
comparison). refresh_from_chart also deliberately does NOT trigger an
autosave itself (matches tui.py's on_chart_update, which never calls
_schedule_save) — the refreshed slots just ride along with whatever save the
user's own next edit, or app.py's flush-on-quit/Ctrl+R flush, already
performs. This poller never touches any OTHER section's state, so there is
no cross-section reconciliation concern to design for beyond Subjective's
own note slots.

VERIFICATION DONE SO FAR (2026-08-23) — NO LIVE BODYCHART UI INVOLVED
-------------------------------------------------------------------------
The user cannot exercise this against the actual GTK bodychart UI yet, so
verification here was: (1) confirmed a real, already-built bodychart binary
exists (`~/.local/bin/pab` / `pabd`, both symlinks into `~/Projects/pab` —
running them does not touch that repo's git state, only building would);
(2) confirmed `~/.local/share/pab/session_current.json` is a real, live file
with real stroke data in the exact shape `on_chart_update`/`refresh_from_chart`
expect; (3) headlessly wrote a NEW stroke into a copy of a real *_session.json
file (mimicking what bodychart's own save does) while gpab had that same file
open, and confirmed: the poller detects the mtime change, refresh_from_chart
fires, a new note slot appears with body-chart-derived prefill text, and text
already typed into an EXISTING note slot survives the refresh unchanged.
This proves the mechanism; it does NOT prove real bodychart writes are
byte-for-byte what a hand-crafted test stroke assumes — when you can run the
real bodychart app against a real gpab session, drawing a stroke and
confirming a note slot appears with sane text is the real end-to-end check
still outstanding. If anything looks wrong then, start by comparing a fresh
stroke's on-disk shape against the `_OP_ROWS`-style fixtures used in this
port's own test above, in gpab_assessment's git history for this file's
introduction commit.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 2000  # matches pab_assessment.watcher.POLL_INTERVAL (2.0s)


class ChartFileWatcher:
    """Polls one *_session.json for mtime changes and calls
    on_chart_update(data) when it changes. See module docstring for full
    scope/design notes."""

    def __init__(self, session_file: str, on_chart_update) -> None:
        self._path = Path(session_file)
        self._on_chart_update = on_chart_update
        self._last_mtime: float | None = None
        self._source_id: int | None = None

    def start(self) -> None:
        if self._source_id is not None:
            return
        # Baseline the mtime BEFORE the first poll tick fires, using
        # whatever's on disk right now (already loaded once by app.py's own
        # startup _load()) — otherwise the very first poll would see "no
        # prior mtime recorded" as a change and redundantly refresh
        # immediately at launch. Harmless if it did (refresh_from_chart is
        # idempotent), but pointless.
        try:
            self._last_mtime = self._path.stat().st_mtime
        except OSError:
            self._last_mtime = None
        self._source_id = GLib.timeout_add(POLL_INTERVAL_MS, self._poll)

    def stop(self) -> None:
        if self._source_id is not None:
            GLib.source_remove(self._source_id)
            self._source_id = None

    def _poll(self) -> bool:
        # Wrapped in try/except per this project's rule for any recurring
        # callback (mirrors the reference project's asyncio-task rule: an
        # uncaught exception here would otherwise be silently swallowed by
        # GLib's main loop dispatcher — logging it beats losing it outright).
        try:
            mtime = self._path.stat().st_mtime
            if mtime != self._last_mtime:
                self._last_mtime = mtime
                data = json.loads(self._path.read_text())
                self._on_chart_update(data)
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError) as e:
            logger.error("chart_watcher: failed to read %s: %s", self._path, e)
        return True  # keep polling — GLib stops the timeout if this returns False
