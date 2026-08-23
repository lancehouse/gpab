# gpab — GTK4 conversion of PhysioChart's Textual TUI

This repo is a **standalone, isolated R&D fork**, not the production PhysioChart codebase.
Production lives at `~/Projects/pab` (bodychart GTK4/C + assessment Textual TUI, with its own
`dev`/`main` branch rules, `pabd`/`pab` launchers — see that repo's own `CLAUDE.md`). Those rules
do **not** apply here; this repo has no remote, its `dev` branch is just an artifact of being
cloned from `pab`, and nothing done here can reach production.

**Why this repo exists:** the TUI works well with keyboard/mouse but is slow on the touchscreen
of the Lenovo Yoga this runs on, especially in the Objective examination tabs. What started as a
small touch-vs-terminal trial (Consent + Subjective only) proved out well enough that the plan is
now a **full conversion of the assessment TUI to native GTK4**. See `PROJECT_BRIEF.md` for what's
been proven so far and why, and `CONVERSION_PLAN.md` for the section-by-section plan going forward.

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
- All new conversion code lives in `gtk_trial/` (name is a holdover from the touch-trial phase;
  not yet renamed since renaming mid-conversion would churn every import path for no benefit —
  revisit once the conversion is far enough along that a rename is worth the diff).
- **Session data isolation was relaxed 2026-08-22**: this app may now read and write real sessions
  under `~/PAB/` directly — the user is not worried about data corruption there and wants saves to
  actually land in `~/PAB` (needed for report generation and the eventual body-chart integration
  work). `~/PAB-gtktrial/` (populated via `gtk_trial/scripts/copy_trial_session.sh`) still exists
  and still works, but is no longer required. **What still never happens**: writing to
  `~/Projects/pab` or `~/Projects/kb` — the code-repo isolation below is unconditional and
  unaffected by this relaxation.
- Before and after any substantial work session, confirm nothing has leaked:
  `git -C ~/Projects/pab status --short | wc -l` and `git -C ~/Projects/kb status --short | wc -l`
  should be unchanged from whatever they were at the start of this project (11 and 5 as of this
  writing) — if either has grown, something wrote where it shouldn't have.

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
   `GRID_LABEL_COL_PX`/compact-toggle conventions in `gtk_trial/gpab_trial/` for how this is
   enforced structurally rather than per-widget.

## Rules established during this project (see `CONVERSION_PLAN.md` for the full list)

Centralize, don't repeat: every shared visual/behavioural rule (left-column width, subsection
header styling, grid-row shape, grid keyboard navigation, pale/bright/focus colour states) lives
in exactly one place (`widgets.py`, `objective/grid_widgets.py`, `objective/grid_nav.py`,
`style.css`) and every section imports it — a new tab should inherit correct look and keyboard
behaviour automatically, not by a human remembering to copy a pattern.

## Running it

```bash
cd gtk_trial
bash scripts/setup_venv.sh                      # one-time: venv + deps
bash scripts/copy_trial_session.sh <name>        # copy a real session into ~/PAB-gtktrial/
bash scripts/run.sh <name>                       # launch against the copy
```
