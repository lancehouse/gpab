# gpab — the GTK4 successor to PhysioChart's Textual assessment TUI

gpab is the real, ongoing conversion of PhysioChart's assessment app from a Textual TUI to a
native GTK4 app (`assessment_gtk/`), launched directly by `bodychart` for every real session and
in genuine clinical use — not a prototype, demo, or throwaway experiment. It started life as an
isolated clone of `~/Projects/pab` (bodychart GTK4/C + assessment Textual TUI, its own separate
project with its own `dev`/`main` branch rules and `pabd`/`pab` launchers — see that repo's own
`CLAUDE.md`) specifically so early work here could never risk the working `pab` install; that
provenance is still true and still matters (see the isolation guarantee below), but it's a
technical fact about how this repo is set up, not a statement that this is somehow less real than
`pab`. This repo has no remote, and its `dev` branch is just an artifact of being cloned from
`pab` — nothing done here can reach production, and there is no plan to merge back (see
"Permanent end state" below).

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

- **This is a `git clone` of `~/Projects/pab`, with its own independent `.git` and no remote.**
  (`git remote -v` returns nothing — confirm this hasn't changed before doing anything risky.)
  It cannot push to, pull from, or otherwise affect the real `pab` or `kb` repos.
- `assessment/` in this clone is a **read-only reference copy** — the actual TUI source, kept so
  the conversion has something authoritative to port from and compare against. Never edit it; if a
  fix is needed, it needs to happen in the real `~/Projects/pab` separately, by hand, later — not
  here.
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

| Launcher | Bodychart binary | gpab assessment app | Git branch |
|----------|-------------------|----------------------|------------|
| `gpabd`  | `bodychart/build/bodychart` | `gpab-assessment` → this checkout's `assessment_gtk/.venv` | `dev` |
| `gpabs`  | `gpab-stable/bodychart/build-stable/bodychart` | `gpab-assessment-stable` → `gpab-stable/assessment_gtk/.venv` | `main` |

`gpab-stable/` is a **git worktree of this same repo**, nested inside it and pinned to `main` (`git
worktree list` shows both). It has its own build directory, its own Python venv, and its own copy
of every file — a bug in dev code cannot reach it just by existing on disk. The **desktop icon**
(`com.gpab.bodychart.desktop`, `Exec=…/gpab-stable/bodychart/build-stable/bodychart`) points at
`gpabs`'s stable binary — that's the one actually used for real patient sessions. `gpabd`/the
dev binary are for testing changes before they're promoted, not daily clinical use.

`bodychart/src/integration.c` differs from its `main`-branch copy in exactly one line — the
`GPAB_LAUNCHER` macro (`"gpab-assessment"` on `dev`, `"gpab-assessment-stable"` on `main`) — by
design, so a `dev`→`main` merge always surfaces it as a conflict to resolve by hand (keep `main`'s
value), never a silent overwrite of which checkout stable launches. This is the same shape as
pab's own single-line `"assessment"`/`"assessments"` divergence in its `integration.c`.

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

### Third tier — `merged-app/` (R&D spike, 2026-08-25)

A **third git worktree**, same pattern as `gpab-stable/` but protecting `dev`/`gpabd` itself
rather than `main`/`gpabs`: pinned to its own `merged-app` branch (cut from `dev`'s tested HEAD),
own `bodychart/build-merged/`, own `assessment_gtk/.venv/`. Exists because embedding gpab's Python
inside bodychart's own process (to fix Ctrl+B's window-raise — see git log around 2026-08-25 for
the full "why") is a genuinely structural, iterative change that could leave things broken
mid-way for a while. `gpabd` is itself relied on day-to-day to test *other*, unrelated work, so it
needs to keep working throughout — not just `gpabs`/`main`.

- **All embedding work happens in `merged-app/` only.** Never touch `dev`'s own
  `bodychart/build/` or `assessment_gtk/.venv` for this — those must keep reflecting exactly
  commit `f2e6c9a` (the last known-good `gpabd` state before this spike started) until the user
  explicitly says to bring `merged-app` back into `dev`.
- Same promotion discipline as `main`, one level down: merging `merged-app` → `dev` needs an
  explicit instruction in that exact message, same as `main` needs for a promotion from `dev`.
  Nothing here is a fast-forward or a given — the user has explicitly floated the idea that this
  might end up needing its *own* internal dev/stable split once it's far enough along, rather
  than merging straight into `dev`. Don't assume the answer; ask when it's actually relevant.
- `gpab-stable`/`main` stay completely out of scope for this work — two levels of insulation
  between this spike and daily clinical use, not one.

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
