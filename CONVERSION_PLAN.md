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
  per-file debounced autosave (`_assessment.json` / `_objective.json` on separate timers, matching
  the TUI's `AssessmentView`/`ObjectiveAssessmentView` split). The footer hotkey bar built here was
  later removed (2026-08-22) per user feedback — it duplicated the sidebar/mode-switch navigation,
  and its ~15 unwrapped hint labels turned out to be the actual cause of a window-overflow bug (see
  the `kb_integration_and_layout` memory note); only the save-status indicator remains in it.
- Sections built: **01 Consent**, **02 Subjective** (incl. the YAML-driven Sleep subsection),
  **04 Neurological** (objective).

## Phase 1 — remaining assessment-side sections — ✅ DONE

All eight assessment sections are built and round-trip-verified: `medical.py`,
`pain_classification.py`, `outcome_measures.py`, `diagnosis.py` (the CAL-CP walker, with GTK-native
flowchart connectors and temporal-pattern sparkline diagrams — a genuine enhancement over the
TUI's own rendering, not just a port), `barriers.py`, `rx_plan.py`, plus the F10 Notes overlay
(replacing the dead `scratchpad.py`/`placeholder.py`/`objective.py` stubs — confirmed via grep to
be unreferenced anywhere in the real TUI, so nothing there needed porting).
`sections/regional_differential.py` (471 lines) turned out to belong with Phase 4 (KB
integration) — it's Pain Classification's cluster-tally panel, driven by KB data — and is tracked
there instead, still not built.

## Phase 2 — remaining objective-side sections — ✅ DONE

`region_section.py` was indeed the shared framework it looked like — ported as
`objective/region_section.py` (`ROMGroupWidget`, `GradeGroupWidget`, `TrunkStrengthWidget`,
`SpecialTestsWidget`, `BilateralGridSpecialTestsWidget`, `RegionContainer`, `RegionTabContent`),
driven by the same per-region YAML files the TUI uses. All six regions' Python "extras" (OP/PAIVM
passive tables, muscle strength grids) are ported too — factored into two shared shapes
(`objective/passive_widgets.py`'s `OPPAIVMTable`/`BilateralNormTable`/`StrengthGridTable`) once it
became clear every region duplicated one of two patterns almost verbatim, rather than porting each
region's `*_tables.py` as a one-off. `general.py`, `functional.py` (with a 3-way SMART Goals mirror
to Consent/Subjective), `sensory.py`, and `crps.py` (reactive Budapest-criteria domain indicators)
are also done. A body-region toggle topbar (`objective/region_topbar.py`) replaces the Subjective
mnemonic bar in Objective mode and mounts/unmounts regions live across the four region tabs —
manual toggle only, no body-chart sync yet (see Phase 3).

## Phase 3 — app-level, cross-cutting features

| TUI file | Lines | What it does | GTK approach |
|---|---|---|---|
| `search.py` + `search_widget.py` | 824 + 151 | Ctrl+F/Ctrl+. fuzzy jump-search across all fields | A `Gtk.SearchEntry` + filtered `Gtk.ListView`/popover over the same search-index data structure; index-building logic likely reusable unchanged. |
| `grid_overview.py` | 381 | Ctrl+G heading map for rapid section/subsection nav | GTK popover/dialog listing `SUBJ_GRID_DATA`-equivalent; mostly a rendering exercise once the data structure is ported. |
| `watcher.py` | 118 | Polls `session_current.json` + the active session file for GTK body-chart-side updates, and a `.focus_tui` signal file | This is the live body-chart re-sync explicitly deferred in Phase 0 (`refresh_from_chart`). Needs a GLib-native equivalent (`GLib.timeout_add` poll or a `Gio.FileMonitor` on the session file) — the latter is probably the right call now that we're in GTK anyway, since GTK doesn't need to poll the way a Textual async loop did. |
| `report_modal.py` | 70 | Report preview/regenerate trigger | ✅ DONE — Ctrl+R, `report_modal.py`. |
| `assessment_view.py` / `objective_view.py` (remaining features beyond what Phase 0 ported) | 945 / 716 | Section-complete indicators, migration helpers, the rest of the save/load orchestration | Audit what's left once Phases 1–2 land — some of this (e.g. `_migrate_objective`) may not need a GTK equivalent at all if it's schema-migration logic that runs at load time regardless of UI. |
| `main.py` | 356 | Full `BINDINGS` table: F1–F9 section switches, F10 notes toggle, Ctrl+F1–F8 objective jumps, Alt+letter subsection jumps, Ctrl+Q/Ctrl+A/Ctrl+D | Phase 0's `app.py` already replicates the F1/F2/F4/F11/Ctrl+Q/Ctrl+A subset; extend the same global `Gtk.EventControllerKey` table as each new section lands, rather than adding ad hoc key handling per section. |

## Phase 4 — clinical knowledge base integration — IN PROGRESS

| TUI file | Lines | Notes |
|---|---|---|
| `objective/kb_db.py` | 189 | ✅ DONE — copied unchanged, zero Textual imports as expected. |
| `objective/kb_loader.py` | 249 | ✅ DONE — copied with only `_KB_DIR` repointed at the read-only reference clone (same `parents[N]` pattern as `region_section.py`'s `_YAML_DIR`). |
| `objective/kb_panel.py` | 73 | ✅ DONE (`gpab_trial/objective/kb_panel.py`) — Ctrl+K field-focus lookup panel. Rendering deliberately does NOT reuse `KBEntry.render_lines()` (that hard-wraps every field to 44 chars for the TUI's fixed terminal width); a separate free-text renderer lets the GTK `Gtk.Label` reflow naturally to whatever width the panel has. Focus-tracking uses a per-widget listener registry (`widgets.add_focus_listener`) rather than a window-level `Gtk.Root` "notify::focus-widget" hook — that hook fired in isolated tests but not once real `Gtk.Stack`/`Gtk.ScrolledWindow` nesting was involved; unresolved why, so don't reach for it again without re-verifying. |
| `sections/regional_differential.py` | 471 | **Not built.** Pain Classification's cluster-tally panel (pos/total per special-tests group, live-updated from in-memory region data). The pure data functions (`_build_members`, `_load_db_cluster`, `_short_sn_sp`, `_load_region_structure`, `_load_extra_clusters`) have zero Textual imports and can likely be lifted verbatim; only the `_TestRow`/`_ValueRow`/`_FlagRow`/`_ClusterBlock`/panel widgets need rebuilding (a `Gtk.Expander` per cluster, in place of `Collapsible`). Needs `tests` dict assembled the same way `assessment_view.py::_flatten_region_fields` does (neurological dict merged with the active region's flattened active/passive/muscle/special dicts) — build that from in-memory `collect()` calls, not a disk re-read, matching how this app already does cross-ref refreshes elsewhere. |
| `objective/kb_db_screen.py` | 916 | **Not built.** Ctrl+D full KB browser — the single largest remaining screen in the app, but the least coupled to anything else (a standalone browser window; nothing else depends on it). Do this last. |

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
