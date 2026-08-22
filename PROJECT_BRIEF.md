# Project Brief — GTK4 conversion of PhysioChart's assessment TUI

## Background

PhysioChart is a two-app clinical tool: `bodychart` (GTK4/C, stylus body-chart drawing) and
`assessment` (Python/Textual TUI, structured clinical assessment + report generation). Both are
used on a Lenovo Yoga in tablet mode, primarily with a stylus/touchscreen. The TUI is fast and
keyboard-friendly, but Textual's terminal rendering is noticeably slow to respond to touch input —
felt most in the Objective examination tabs, which are used heavily and are also the densest in
widget count.

## Goal

Determine whether rebuilding the assessment app natively in GTK4 solves the touch-latency problem
without losing the TUI's keyboard-first workflow, and — if so — do it for real. This started as a
narrow, reversible trial and has now graduated to a full conversion effort.

## Why a separate repo

The user's explicit instruction at the outset: prove nothing here can break the working `pab`
install. `~/Projects/gpab` is a full `git clone` of `~/Projects/pab` with its own `.git` and no
remote — not a worktree, which would have shared refs with the real repo. All new code lives in
`gtk_trial/`; the cloned `assessment/`/`bodychart/` trees are read-only reference material. Session
data used for testing is copied into a new `~/PAB-gtktrial/` directory and the app refuses to
launch against a path under the real `~/PAB/`. This has been checked repeatedly throughout (`git
status --short` on `~/Projects/pab` and `~/Projects/kb` staying at a constant 11/5 files, unrelated
to this work) and held at every check.

## What's been built and proven

**Phase 1 — touch trial (Consent + Subjective).** Ported the first two assessment sections
field-for-field, including the YAML-driven Sleep subsection (a second, independent GTK renderer of
the same `subj_sleep_pilot.yaml` the TUI uses — proving the YAML-schema approach isn't
Textual-specific) and the live SMART Goals mirroring between the two tabs. Confirmed `storage.py`,
`mapping.py`, `logic.py`, and `form_schema.py` import and run unmodified with zero Textual
dependency — the "logic separate from UI" claim in the TUI's own CLAUDE.md holds at exactly the
layer needed for this to work.

**UI iteration, from screenshots and direct feedback**, converging on a set of durable, centralized
rules rather than one-off fixes:
- A single shared left-column width (`FIELD_LEFT_COLUMN_PX` / `field_left_slot()`) so every label
  and every toggle-as-label widget lines up, regardless of type.
- A single subsection-header style (`make_subsection_header()`) so "History", "Behaviour" etc. read
  clearly and consistently everywhere, automatically, in any future section.
- One persistent top bar (subsection mnemonic nav) replacing a redundant black app-bar that
  wasted vertical space; a narrowed OS titlebar; F11 fullscreen.
- Permanent (not hold-to-see) mnemonic underlines via Pango markup, since GTK's native
  `use_underline` only shows on Alt-hold.

**Phase 2 — Neurological objective tab + arrow-key grid navigation.** Ported the single
most-used, most widget-dense TUI tab (reflex/myotome/dermatome bilateral grids, neurodynamics rows,
a 9-item UMN row, 10 notes fields — ~509 lines in the TUI). Built full TUI-parity keyboard
navigation on top of the shared widget kit:
- `RadioGroup` became a proper single tab-stop with Left/Right cycling its own selection (clamped,
  no wrap — preserving keyboard entry of abnormal findings, not just normal ones) and Enter/Space
  committing (selecting the normal/success option first if nothing's chosen) and advancing to the
  next grid cell — so a fully-normal row is just Enter-Enter-Enter-Enter, strictly faster than the
  TUI it's replacing rather than a regression.
- A reusable `GridNav` mixin (`objective/grid_nav.py`) replicates the TUI's row/column spatial
  navigation once, for any future dense objective tab (Sensory, Muscle, the regional ROM tables) to
  reuse rather than reimplement.
- Fixed a real, pre-existing bug surfaced while doing this: the TUI-derived Y/N hotkey handler was
  calling `child_focus` on the button itself (which has no children, so it silently never advanced
  focus) — now correctly routed through the window root.

**Follow-up fixes from live use** (this is the state as committed):
- Chips had no visible focus indicator once made non-focusable for grid nav, and were fully
  saturated in colour even before selection, so it was hard to tell either where the keyboard
  cursor was or what was actually chosen. Fixed with a three-way, centrally-documented convention
  in `style.css`: pale background until selected, full saturated colour + a bright cyan border once
  selected, and a separate glowing yellow focus ring around whichever gang currently has keyboard
  focus — deliberately never reusing one signal for the other.
- The Neurological tab required horizontal scrolling even at fullscreen. Root-caused (not
  guessed) via headless width measurement to two real defects: RadioGroup chip labels never
  wrapped, so a chip's minimum width was its full unwrapped text; and the UMN row used
  `homogeneous=True` sizing, so a single already-answered field with a long label (e.g. "Coord
  impaired No") stretched all nine buttons to match it. Fixed both (chip label wrapping + a
  `compact` button variant + making the UMN row non-homogeneous, since nothing else needs its
  columns aligned), bringing the tab's measured minimum width from 1452px to 832px, and set
  every tab's scrolled window to never allow horizontal scrolling as a standing guarantee rather
  than a one-off fix.

## Verification method used throughout

Every claim above was checked, not assumed: headless round-trip diffs of `collect()`/`load()`
dict keys against real session JSON (Consent 18 keys, Subjective ~89 static keys, Neurological 89
keys — all zero-diff); a scripted exercise of the grid-nav logic itself (cycling, clamping,
commit-selects-normal, cross-row movement); and live width/CSS-class measurement via a temporary
debug harness (added, used, then removed) run through `scripts/run.sh` under `timeout`, rather than
trusting a screenshot or a guess about GTK's box model.

## Decision

The trial phase is over. The user has decided to proceed with a full conversion of the assessment
TUI to GTK4. See `CONVERSION_PLAN.md` for scope and phasing.
