# gpab — the GTK4 successor to PhysioChart's Textual assessment TUI

gpab is the real, ongoing conversion of PhysioChart's assessment app from a Textual TUI to a
native GTK4 app (`assessment_gtk/`), launched directly by `bodychart` for every real session and
in genuine clinical use — not a prototype, demo, or throwaway experiment. It started life as an
isolated clone of `~/Projects/pab` (bodychart GTK4/C + assessment Textual TUI, its own separate
project with its own `dev`/`main` branch rules and `pabd`/`pab` launchers — see that repo's own
`CLAUDE.md`) specifically so early work here could never risk the working `pab` install; that
provenance is still true and still matters (see the isolation guarantee below), but it's a
technical fact about how this repo is set up, not a statement that this is somehow less real than
`pab`. This repo's only remote is `origin` — a private GitHub backup (`github.com/lancehouse/gpab`,
added 2026-09-07); it still has no link to `pab` or `kb`. Its `dev` branch is just an artifact of
being cloned from `pab` — nothing done here can reach production, and there is no plan to merge
back (see "Permanent end state" below).

**Why this project exists:** the TUI works well with keyboard/mouse but is slow on the
touchscreen of the Lenovo Yoga this runs on, especially in the Objective examination tabs. An
early, narrow touch-vs-terminal comparison (Consent + Subjective only) proved out well enough
that the decision was made to do a **full conversion of the assessment TUI to native GTK4**. See
`PROJECT_BRIEF.md` for what was proven and why, and `CONVERSION_PLAN.md` for the section-by-section
plan going forward.

**Permanent end state (decided 2026-08-23, see `CONVERSION_PLAN.md` Phase 6):** gpab is never
merged back into `pab`, and `~/Projects/pab` itself is never modified by this project — `pab`
stays installed and untouched as a working fallback, and `pabd`/`pabs` keep building and running
its original, unmodified `bodychart/src/integration.c` indefinitely. There is no plan to port
gpab's code into `~/Projects/pab`. Within *this clone only*, `bodychart/src/integration.c` and
`bodychart/meson.build` **have been** deliberately modified (2026-08-23) so this clone's own
`bodychart` build launches `gpab` directly instead of the old VTE-embedded TUI — see the isolation
guarantee below for exactly what that does and doesn't change.

## Isolation guarantee — read before touching anything here

- **This is a `git clone` of `~/Projects/pab`, with its own independent `.git`.** Its one remote,
  `origin`, is a private GitHub backup (`github.com/lancehouse/gpab`) and nothing else — it cannot
  push to, pull from, or otherwise affect the real `pab` or `kb` repos. (`git remote -v` should
  show only that `origin` — anything else is unexpected; confirm before doing anything risky.)
- `assessment/` in this clone was a **fully read-only reference copy** until 2026-09-15, when that
  blanket prohibition was relaxed: gpab is the real, ongoing app now, not a conversion-in-progress
  artifact, so files it genuinely depends on for correctness may be edited directly in this clone
  on an incremental, as-needed basis — decided when adding SpA/SCREEN'D'EM differential-screening
  report fields, which required editing `pab_assessment/storage.py`'s report generation (see git
  history around that date for the first such edit). This is not a green light to rewrite
  `assessment/` freely — most of it is still kept purely for reference/comparison against the TUI
  and isn't expected to need changes; edit only the specific file a specific piece of work actually
  requires, when it actually requires it. Any such edit stays local to this clone only, same as
  `bodychart/`'s prior divergence (see below): it is never copied back to `~/Projects/pab`, and
  `~/Projects/pab` itself is still never touched under any circumstance (see the rule above this
  one, unchanged).
- `bodychart/` was also a read-only reference copy until 2026-08-23, when `integration.c` and
  `meson.build` were deliberately modified (see `CONVERSION_PLAN.md` Phase 6) so this clone's own
  `bodychart` build launches `gpab` in place of the old embedded TUI. This is a vendored,
  intentionally-diverged copy now, **local to this clone only** — the real `~/Projects/pab/bodychart`
  is untouched, `pabd`/`pabs` still build and run that original unmodified source, and nothing here
  is ever copied back. Build this clone's copy with `ninja -C build` only — **never `ninja install`
  / `meson install`** from here, since that would write over the binaries/desktop file the real
  install may use rather than staying confined to this clone's own `build/` directory.
- All conversion code lives in `assessment_gtk/` (renamed 2026-08-25 from `gtk_trial/` — that name
  was a holdover from the early touch-trial phase and no longer described what this is; every
  import path, script, launcher, and the app id were updated in the same pass, see git history).
- **Session data isolation was relaxed 2026-08-22**: this app may now read and write real sessions
  under `~/PAB/` directly — the user is not worried about data corruption there and wants saves to
  actually land in `~/PAB` (needed for report generation and the body-chart integration work).
  `~/PAB-assessment-gtk/` (populated via `assessment_gtk/scripts/copy_dev_session.sh`) still works
  if a disposable dev copy is wanted, but is no longer required. **What still never happens
  without explicit, case-by-case user sign-off**: writing to `~/Projects/pab` (unconditional, no
  exceptions) or `~/Projects/kb` (the source project behind `clinical_kb.db`, linked read-only by
  default — see "Maintaining the kb link" below; it has been written to exactly once, 2026-08-24,
  with explicit permission, to add CRPS KB content following kb's own authoring process).
- Before and after any substantial work session, confirm nothing has leaked into `pab`:
  `git -C ~/Projects/pab status --short | wc -l` should be unchanged from whatever it was at the
  start of this project (11 as of this writing) — if it's grown, something wrote where it
  shouldn't have. `kb` doesn't get the same fixed-baseline check any more, since legitimate,
  user-authorized commits now land there (see "Maintaining the kb link" below) — check its `git
  log` for anything unexpected instead of comparing a file count.

## Branch and deployment rules — ABSOLUTE

Mirrors `pab`'s own dev/stable split (see its `CLAUDE.md`) exactly, adapted 1:1 — built
2026-08-25 to close a real gap: before this, there was only one checkout and one build, so every
rebuild took effect the moment the desktop icon was next clicked, with no tested/known-good copy
protected from whatever was mid-change. These rules are non-negotiable and override any other
instruction in this session.

**`dev`/`gpabd` and `main`/`gpabs` run the same embedded architecture** as of 2026-09-01 (see
"Embedded architecture" below) — both embed gpab's Python inside bodychart's own process (one
process, two windows). Before that promotion, `main` ran an older separate-process design
coordinated over D-Bus (two processes); that's gone now on both branches, superseded entirely by
`py_embed.c`. Future `dev`→`main` promotions on either `integration.c` or `py_embed.c` should be
mechanical again (both files are now structurally identical between branches) — the one thing that
still needs a manual check on every promotion is `py_embed.c`'s `GPAB_SITE_PACKAGES`/
`GPAB_APP_ROOT` constants (see below), which must NOT come across unedited from a `dev`→`main`
merge.

| Launcher | Bodychart binary | gpab assessment app | Git branch |
|----------|-------------------|----------------------|------------|
| `gpabd`  | `bodychart/build/bodychart` | embedded in-process (see below) — `gpab-assessment` (this checkout's `assessment_gtk/.venv`) only used for standalone `./gpab`/`scripts/run.sh` testing, not the real bodychart-launched flow any more | `dev` |
| `gpabs`  | `gpab-stable/bodychart/build-stable/bodychart` | embedded in-process (see below) — `gpab-stable/assessment_gtk/.venv`, separate interpreter instance from `gpabd`'s | `main` |

`gpab-stable/` is a **git worktree of this same repo**, nested inside it and pinned to `main` (`git
worktree list` shows both). It has its own build directory, its own Python venv, and its own copy
of every file — a bug in dev code cannot reach it just by existing on disk. The **desktop icon**
(`com.gpab.bodychart.desktop`, `Exec=…/gpab-stable/bodychart/build-stable/bodychart`) points at
`gpabs`'s stable binary — that's the one actually used for real patient sessions. `gpabd`/the
dev binary are for testing changes before they're promoted, not daily clinical use.

`bodychart/src/py_embed.c` differs from its `dev`-branch copy in the `GPAB_SITE_PACKAGES`/
`GPAB_APP_ROOT` path constants only — worktree-specific by necessity (embedding links the
interpreter directly, no `$PATH`-resolved wrapper-script indirection is possible the way process-
spawning used to allow). `main`'s copy points at `gpab-stable/assessment_gtk`, not `dev`'s own
checkout. A mechanical `dev`→`main` merge brings `py_embed.c` across **cleanly, with no conflict
marker** — always manually re-check these two `#define`s after any such merge
(`strings gpab-stable/bodychart/build-stable/bodychart | grep assessment_gtk` should show only
`gpab-stable` paths) before trusting the result.

1. **All development work goes to `dev` first.** Every code change, bug fix, or feature lands on
   `dev`. No exceptions.
2. **`gpabd` is where you test.** Confirm a change works there before considering a merge.
3. **`main` is never touched during development.** Do not commit, merge, or push to `main` (or
   make any change inside `gpab-stable/`) unless the user says explicitly — in that same message —
   "merge to main", "promote to stable", or equivalent. Finishing a feature, fixing a bug, or
   completing a task is NOT permission.
4. **No mid-session merges.** Even if a fix is confirmed working via `gpabd`, it stays on `dev`
   until the user explicitly requests the promotion in a separate, deliberate instruction.
5. Rebuilding `gpab-stable/bodychart` (`ninja -C gpab-stable/bodychart/build-stable`) is itself
   part of "touching main" — don't do it as a side effect of a dev-side rebuild habit.

### Embedded architecture (promoted to `dev`/`gpabd` 2026-08-26, to `main`/`gpabs` 2026-09-01)

`dev`'s bodychart now embeds a CPython interpreter (`bodychart/src/py_embed.c/.h`) and imports
gpab's Python directly into its own process, rather than spawning it as a separate process
coordinated over D-Bus. Root cause this fixed: Wayland blocks one process from forcing focus onto
a *different* process's window, so the earlier D-Bus `gapplication launch` approach could never
really raise gpab's window (just produced a "ready" notification) — a same-process window raising
a sibling window isn't cross-process, so that restriction doesn't apply. `Ctrl+B` in either window
now raises the other for real; closing either window closes both, guarded against the mutual-
recursion this introduces (`TrialWindow._closing` in Python, `window.c`'s static `g_closing` in C)
since both directions are now synchronous, in-process calls rather than async D-Bus round-trips.

Developed and proven on a third-tier `merged-app` worktree/branch (see git log around
2026-08-25/26) before being explicitly promoted to `dev` — that included finding and fixing a real
CSS-bleed bug (`bodychart/src/window.c`'s `apply_css()` had unscoped bare-tag selectors like
`window { background: #2b2b2b; }` that, once both apps shared one `GdkDisplay`, matched gpab's
widgets too — fixed by scoping to a shared `.bodychart-app` CSS class every bodychart-owned window
now carries), and confirming the file read/write/atomic-write/cross-app-sync layer
(`persistence.c`, `storage.py`, `chart_watcher.py`) needed no changes and keeps working correctly
under the new process model. The `merged-app` worktree/branch itself may still exist on disk —
treat it as historical at this point, not a live parallel development target, unless told
otherwise.

**`main`/`gpabs` received this promotion 2026-09-01** (merge commit `c8f05ed`, cherry-pick
`1b0be86` for the Subjective note-slot focus fix that landed on `dev` the same day) — the two
branches are now architecturally aligned; don't assume future `dev` work is automatically mirrored
here though, only what's been explicitly promoted.

## Maintaining the kb link

`clinical_kb.db` (Ctrl+K/Ctrl+D knowledge-base content — procedures, Sn/Sp, cluster membership,
the Budapest/Valencia CRPS criteria) is built by the separate `~/Projects/kb` project and consumed
here read-only, via `~/.local/share/pab/clinical_kb.db` (symlinked into `~/Projects/kb/output/`) —
see `assessment_gtk/gpab_assessment/objective/kb_db.py`. That link stays: gpab is not forking or
vendoring the KB, and `kb`'s own authoring pipeline (source CSVs → `build/import_kb.py` →
`output/clinical_kb.db`, see `~/Projects/kb/CLAUDE.md`) is still the only correct way to add or
change KB content. Editing `kb` from here is normally out of scope (same as `pab`) — the one
exception so far (CRPS content, 2026-08-24) required the user's explicit, case-by-case permission
and followed `kb`'s own process exactly (new rows in `source/msk_clusters_pab.csv`, rebuilt via
`import_kb.py`/`validate_kb.py`, committed in `~/Projects/kb` itself, not here). Don't treat that
as a standing permission — ask again each time.

## What "full conversion" means, concretely

Reuse every piece of `pab_assessment` that has no Textual import unchanged: `storage.py` (JSON
I/O + report generation, ~5.8k lines), `mapping.py` (body-chart → note prefill), `logic.py`
(sleep-efficiency etc.), `models.py`, `cal_cp_model.py`, `form_schema.py` + the YAML subsection
files. Rebuild everything that touches Textual widgets natively in GTK4: every assessment section,
every objective section, the KB lookup panels, jump-search, the section nav chrome. `collect()`/
`load()` dict shapes must stay byte-for-byte schema-compatible with what `storage.py` expects, so
a session file this app writes is indistinguishable from one the TUI wrote (this has been verified
correct via round-trip diffs, not just a visual match, for every assessment section — Consent,
Subjective, Medical, Pain Classification, Outcome Measures, Diagnosis, Barriers, Rx & Plan — and
every objective section: Neurological, General Observation, Functional, Sensory, CRPS, and all six
regional tables — Active Movement/Passive-OP/Muscle Testing/Special Tests for lumbar, cervical,
shoulder, hip, knee, ankle). See `CONVERSION_PLAN.md` for exactly what's left (Ctrl+D KB browser,
Regional Differential panel, live body-chart region sync, and the app-level Phase 3 items).

## Rules carried over from the real PhysioChart project (still apply here)

1. **Flag, don't guess clinical content** — if a field label, test name, or clinical term is
   ambiguous in the TUI source, stop and ask before interpreting or inventing content in the port.
2. **No UI logic in storage** — this rule is enforced by construction here: `storage_bridge.py` is
   a thin wrapper around the real `storage.py`, nothing else touches it.
3. **Never lose data** — auto-save on every field change, atomic writes (inherited free from
   `storage.py`), separate debounced save timers per JSON file (`_assessment.json` vs
   `_objective.json`), matching the TUI's own `AssessmentView`/`ObjectiveAssessmentView` split.
4. **Button width ≤ ¼ screen** — still a sane touch-UI rule; see `field_left_slot()` and the
   `GRID_LABEL_COL_PX`/compact-toggle conventions in `assessment_gtk/gpab_assessment/` for how this
   is enforced structurally rather than per-widget.

## Rules established during this project (see `CONVERSION_PLAN.md` for the full list)

Centralize, don't repeat: every shared visual/behavioural rule (left-column width, subsection
header styling, grid-row shape, grid keyboard navigation, pale/bright/focus colour states) lives
in exactly one place (`widgets.py`, `objective/grid_widgets.py`, `objective/grid_nav.py`,
`style.css`) and every section imports it — a new tab should inherit correct look and keyboard
behaviour automatically, not by a human remembering to copy a pattern.

## Running it

```bash
cd assessment_gtk
bash scripts/setup_venv.sh                      # one-time: venv + deps
bash scripts/copy_dev_session.sh <name>          # copy a real session into ~/PAB-assessment-gtk/
bash scripts/run.sh <name>                       # launch against it (checks ~/PAB/<name>/ first)
```
