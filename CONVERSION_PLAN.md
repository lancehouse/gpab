# Conversion Plan — full TUI → GTK4

## Scope

Port the entire `pab_assessment` package (Textual TUI, ~22.8k lines across `assessment/` — see
breakdown below) to native GTK4 inside `gtk_trial/`, reusing every Textual-independent module
unchanged. `bodychart/` (already GTK4/C) is out of scope; the eventual integration point between
the two apps is addressed in Phase 6.

Reused unchanged (confirmed zero Textual imports): `storage.py` (5832 lines — JSON I/O, atomic
writes, report/raw-export generation), `mapping.py` (225), `logic.py` (295), `models.py` (74),
`cal_cp_model.py` (396), `form_schema.py` (286) + the YAML subsection files. That's a substantial
fraction of the total codebase inherited for free — the port's real work is the ~16k lines of
Textual widget/screen code below.

## Already done (Phase 0 — see `PROJECT_BRIEF.md`)

- Widget kit: `CheckButton`/`FlagButton` (3-state toggle), `RadioGroup` (exclusive gang, full
  keyboard parity), `AutoTextView`, `TouchEntry` — all in `gpab_trial/widgets.py`.
- Shared layout/style rules: `field_left_slot()`, `make_subsection_header()`,
  `GRID_LABEL_COL_PX`/`bilateral_*` row builders, the pale/bright/focus colour convention.
- Grid navigation: `objective/grid_nav.py` (`GridNav` mixin) — row/column spatial nav plus
  Enter-commits-and-advances, reusable by any dense objective tab.
- App chrome: compact titlebar, F11 fullscreen, one persistent top mnemonic bar, left section nav,
  footer hotkey bar, per-file debounced autosave (`_assessment.json` / `_objective.json` on
  separate timers, matching the TUI's `AssessmentView`/`ObjectiveAssessmentView` split).
- Sections built: **01 Consent**, **02 Subjective** (incl. the YAML-driven Sleep subsection),
  **04 Neurological** (objective).

## Phase 1 — remaining assessment-side sections

| TUI file | Lines | Notes |
|---|---|---|
| `sections/medical.py` | 583 | |
| `sections/pain_classification.py` | 846 | Per-item tables — likely wants its own `PainRow` builder analogous to `grid_widgets.py`, not a copy of the Neurological grid shape. |
| `sections/outcome_measures.py` | 993 | Largest single section; check for scored/calculated fields akin to Sleep Efficiency (route through the same `_FORMULA_REGISTRY` pattern used by `yaml_subsection.py` if so). |
| `sections/diagnosis.py` | 764 | |
| `sections/regional_differential.py` | 471 | |
| `sections/barriers.py` | 542 | |
| `sections/rx_plan.py` | 344 | |
| `sections/scratchpad.py` / `placeholder.py` / `objective.py` | 117 / 39 / 27 | Small utility sections — confirm each still has a purpose before porting; `placeholder.py` in particular may be a stub for a section not yet built in the TUI itself. |

Each section: port field-for-field against the live TUI source (never guess a field's meaning —
ask, per the standing "flag don't guess clinical content" rule), verify with a `collect()`/`load()`
round-trip diff against real session data before moving on, same as Phase 0.

## Phase 2 — remaining objective-side sections

| TUI file | Lines | Notes |
|---|---|---|
| `objective/sections/region_section.py` | 844 | Appears to be the shared framework the six regional table files below build on — read this first; if it's a genuine base class, the GTK port should mirror that with a shared base rather than porting each region independently. |
| `objective/sections/cervical_tables.py` | 356 | |
| `objective/sections/shoulder_tables.py` | 397 | |
| `objective/sections/lumbar_tables.py` | 379 | |
| `objective/sections/hip_tables.py` | 320 | |
| `objective/sections/knee_tables.py` | 313 | |
| `objective/sections/ankle_tables.py` | 314 | |
| `objective/sections/sensory.py` | 210 | Already partly KB-integrated in the TUI (pain-sensitisation screen) — check what that wiring needs before porting (see Phase 4). |
| `objective/sections/muscle.py` | 338 | Likely reuses the same bilateral-gang shape as Neurological — should mostly be `GridNav` + `grid_widgets.py` reuse, not new mechanism. |
| `objective/sections/active_movement.py` | 317 | |
| `objective/sections/functional.py` | 329 | |
| `objective/sections/crps.py` | 417 | |
| `objective/sections/general.py` | 164 | |

Expect this phase to mostly be *reuse*, not new invention — Neurological (Phase 0) was deliberately
chosen first because it's the densest, most representative tab. If a new section needs a grid shape
`grid_widgets.py`/`grid_nav.py` doesn't already support, extend those shared files rather than
one-off code in the section — same rule as before.

## Phase 3 — app-level, cross-cutting features

| TUI file | Lines | What it does | GTK approach |
|---|---|---|---|
| `search.py` + `search_widget.py` | 824 + 151 | Ctrl+F/Ctrl+. fuzzy jump-search across all fields | A `Gtk.SearchEntry` + filtered `Gtk.ListView`/popover over the same search-index data structure; index-building logic likely reusable unchanged. |
| `grid_overview.py` | 381 | Ctrl+G heading map for rapid section/subsection nav | GTK popover/dialog listing `SUBJ_GRID_DATA`-equivalent; mostly a rendering exercise once the data structure is ported. |
| `watcher.py` | 118 | Polls `session_current.json` + the active session file for GTK body-chart-side updates, and a `.focus_tui` signal file | This is the live body-chart re-sync explicitly deferred in Phase 0 (`refresh_from_chart`). Needs a GLib-native equivalent (`GLib.timeout_add` poll or a `Gio.FileMonitor` on the session file) — the latter is probably the right call now that we're in GTK anyway, since GTK doesn't need to poll the way a Textual async loop did. |
| `report_modal.py` | 70 | Report preview/regenerate trigger | Small — a `Gtk.Dialog` wrapping the same `storage.py` report-generation call. |
| `assessment_view.py` / `objective_view.py` (remaining features beyond what Phase 0 ported) | 945 / 716 | Section-complete indicators, migration helpers, the rest of the save/load orchestration | Audit what's left once Phases 1–2 land — some of this (e.g. `_migrate_objective`) may not need a GTK equivalent at all if it's schema-migration logic that runs at load time regardless of UI. |
| `main.py` | 356 | Full `BINDINGS` table: F1–F9 section switches, F10 notes toggle, Ctrl+F1–F8 objective jumps, Alt+letter subsection jumps, Ctrl+Q/Ctrl+A/Ctrl+D | Phase 0's `app.py` already replicates the F1/F2/F4/F11/Ctrl+Q/Ctrl+A subset; extend the same global `Gtk.EventControllerKey` table as each new section lands, rather than adding ad hoc key handling per section. |

## Phase 4 — clinical knowledge base integration

| TUI file | Lines | Notes |
|---|---|---|
| `objective/kb_panel.py` | — | Ctrl+K field-focus lookup popover |
| `objective/kb_db_screen.py` | 916 | Ctrl+D full KB browser — the single largest remaining screen in the app |
| `objective/kb_db.py` | 189 | DB access layer (SQLite, read-only against `clinical_kb.db`) — very likely reusable unchanged, same as `storage.py` |
| `objective/kb_loader.py` | 249 | Resolves DB-backed vs. YAML-fallback content per region; region-independent `_GLOBAL_DB_FIELDS` |

Per the real project's own CLAUDE.md, this is "built and live, not a planned phase" in the TUI —
treat it the same way here: not optional polish, a required part of full parity. `kb_db.py` should
be checked for Textual imports the same way `storage.py` etc. were, and reused unchanged if clean.
The Sn/Sp special-test widgets mentioned in the source project's CLAUDE.md need their own GTK
widget, likely alongside `objective/grid_widgets.py`.

## Phase 5 — report generation UI

`storage.py`'s report/raw-export generation is already reused unchanged and runs on every save
regardless of UI. What's GTK-side work is purely the trigger/preview surface (`report_modal.py`,
Phase 3) — no new logic needed here.

## Phase 6 — cutover to production

This repo (`gpab`) has no remote and stays a pure R&D sandbox permanently — it is never the
deployment target. Once the conversion is validated here end-to-end (every section ported,
round-trip verified, a full manual pass on the Yoga against the original trial's pass/fail
criteria), the actual cutover is separate, deliberate work that happens **in `~/Projects/pab`
itself**, where that repo's own branch rules apply in full (all work to `dev`, `pabd` for testing,
never `main` without an explicit instruction in that exact message). Concretely: hand-port (or
directly copy, then re-verify) the validated `gtk_trial/gpab_trial/` code into a new module inside
the real `assessment/` package, wire `bodychart/src/integration.c` to launch it in place of (or
alongside, during a transition period) the VTE-embedded Textual TUI, and only then consider `pab`'s
Textual `tui.py`/`main.py` for retirement. None of that work should start until this plan's Phases
1–5 are substantially complete and tested here.

## Standing rules for every phase

1. **Verify, don't eyeball.** Every section gets a `collect()`/`load()` round-trip diff against
   real session data before being considered done, the same way Phase 0's sections were checked.
2. **Centralize, don't repeat.** A new visual or keyboard pattern goes into the shared files
   (`widgets.py`, `grid_widgets.py`, `grid_nav.py`, `style.css`) once; sections only ever consume
   them. If two sections seem to need slightly different versions of the same thing, that's a sign
   the shared helper needs a parameter, not that the section should have its own copy.
3. **Flag, don't guess clinical content.** Inherited directly from the real project's rules —
   applies equally to a field label as to a KB cross-reference.
4. **Isolation holds every session.** Check `~/Projects/pab` / `~/Projects/kb` `git status --short`
   counts are unchanged before and after work, same as throughout Phase 0.
5. **Commit at natural phase boundaries, only when asked.** Matches how Phase 0 was actually
   worked — commits landed after "commit this," not automatically at the end of every section.
