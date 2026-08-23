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
| `search.py` + `search_widget.py` | 824 + 151 | Ctrl+F/Ctrl+. fuzzy jump-search across all fields | ✅ DONE (`gtk_trial/gpab_trial/search.py` + `search_widget.py`). Every static table and the fuzzy scorer are lifted verbatim (one field-id fix: TUI's `preferred_name_input` → this port's actual field_id, `preferred_name`). `build_index()` is GTK-specific: it walks each section's live `Gtk.Widget` tree matching on each widget's own `field_id` attribute (`search.find_by_field_id`) rather than Textual's `query_one(f"#{id}")`. `search_widget.SearchModal` reuses the same small transient-window pattern as the Ctrl+D browser's own search window. **Anchor-precision scope cut resolved**, reusing the same tagging built for Ctrl+T's grid overview: a "subsection" result now scrolls the exact subsection header to the top of the section's viewport via `app.py::_scroll_section_to_anchor`/`search.find_by_anchor_id`, and Special Tests region results (`st_lumbar` etc.) route through `_jump_to_special_region` to mount the region first if needed. Degrades to plain `_show_section` when `search._SUBSECTIONS`' anchor_id has no matching tagged widget (it carries some region-specific ids, e.g. `pm_cx_overpressure`, that were never given their own distinct header — those regions' Overpressure/PAIVMs headers all share one generic anchor_id). Every "field"/"content" result — the common case, a named field or a hit inside typed text — still jumps to and focuses the exact widget. CAL-CP diagnosis workup entries (dynamic, one per pain-site workup) switch to the right `Gtk.Notebook` tab via a new `DiagnosisSection.select_workup()`. Verified against a real session: index size/kind breakdown, exact-field jumps (assessment fields, an objective KB special-test field, Consent's Entry-delegates-to-inner-Gtk.Text case), scratchpad jump (opens the notes overlay), and a CAL-CP workup jump — all landing on the correct tab/widget. |
| `grid_overview.py` | 381 | Ctrl+G heading map for rapid section/subsection nav | ✅ DONE (`gtk_trial/gpab_trial/grid_overview.py`) — **rebound to Ctrl+T**, matching the reference TUI's own already-rebound `main.py`/`tui.py` BINDINGS table exactly (`ctrl+g` → `import_gonio`, freed for the not-yet-ported goniometer-import wizard; `ctrl+t` → `toggle_grid`, labelled "Overview"). `SUBJ_GRID_DATA`/`OBJ_GRID_DATA`/`section_to_cursor`/`_section_has_data` lifted verbatim — every id in them already matches this port's own section ids 1:1, including the special "04_objective" row (its "headings" are objective section ids, handled by `app.py`'s existing `_show_section` directly, no TUI-style mode-switch special-casing needed). Built as `GridOverviewPage`, an in-place page inside `app.py`'s own main `Gtk.Stack` (named `"grid_overview"`) — **not** a popup window: an early version used a transient window like Ctrl+F/Ctrl+D, but per direct feedback that broke the TUI's actual feel (the real app replaces `#section_content` in the same content area, sidebar still visible/responsive, no new window size to recalibrate around each time), so it was rebuilt to match — `app.py::_toggle_grid_overview`/`_open_grid_overview`/`_close_grid_overview` just swap the stack's visible child, same mechanism as switching to any other tab. Escape/Up/Down/Left/Right are handled by `app.py`'s existing global CAPTURE-phase key controller (checked first, ahead of every other binding) whenever `"grid_overview"` is the visible stack child. Full 2-D keyboard nav (skip-empty-row aware, cursor remembered across opens/toggle-closes) and the ✓ data-completion ticks are real, not simplified. Verified against a real session: in-place stack swap with sidebar untouched, click-to-jump for both a plain section heading and the special objective-mode-entry row, Escape/re-toggle returning to the exact prior tab, arrow-key cursor movement routed through the real global key handler, and ticks reflecting actual per-section `collect()` data, in both assessment and objective modes. **Row-to-sidebar-tab pixel alignment** (per further feedback — rows should line up exactly with `SectionNav`/`ObjectiveNav`'s own tab list, not just sit in the same general area): the in-content per-row label was dropped entirely (the sidebar tab alongside now IS the row label — this only works because `SUBJ_GRID_DATA`/`OBJ_GRID_DATA` already list rows in the same order as `SectionNav.SECTION_LABELS`/`ObjectiveNav.SECTION_LABELS`), and the row container's margin-top/spacing and each heading button's `min-height` were set to the exact values `nav.py`/`objective_nav.py` use for their own tab buttons (`margin-top: 4`, `spacing: 2`, `min-height: 48px`) — confirmed via `Gtk.Widget.measure()` that both button classes compute an identical 58px rendered height under the shared theme. **A second alignment bug, this one pre-existing in the reference TUI itself** (confirmed by inspecting the TUI's own `grid_overview.py`, not assumed): `OBJ_GRID_DATA` had no row at all for Special Tests, so every row from Muscle Test downward sat one row too high next to `ObjectiveNav`'s 9-row tab list, landing CRPS's heading row next to the "08 Special Tests" tab and leaving "09 CRPS" empty — same bug, same cause, in both apps. Fixed here (not reproduced): added an `"08_special"` row whose "headings" are the six body regions (Lumbar/Cervical/Shoulder/Hip/Knee/Ankle) rather than fixed subsection anchors, since Special Tests has no fixed layout of its own — it shows whichever regions `RegionTopbar` currently has active. `OBJ_GRID_DATA`'s row order now matches `ObjectiveNav.SECTION_LABELS` exactly, 9-for-9, confirmed programmatically. **Anchor-precision scope cut resolved**: `widgets.make_subsection_header()` now takes an optional `anchor_id`, tagged at ~40 call sites across every section file with the exact strings `SUBJ_GRID_DATA`/`OBJ_GRID_DATA` already use; `search.find_by_anchor_id()` finds the tagged widget and `app.py::_scroll_section_to_anchor()` aligns it to the top of the section's viewport (`compute_bounds()` + `vadjustment.set_value()`, deferred one frame). Outcome Measures' collapsed `Gtk.Expander` blocks carry `.anchor_id` directly and are expanded before being measured. Special Tests region headings (`st_lumbar` etc.) mount an inactive region via `_sync_active_regions()` before jumping straight to its `RegionContainer` — see `app.py::_jump_to_special_region`. A handful of region-specific YAML group labels with no corresponding grid heading (Ankle/Hip/Knee/Shoulder/Cervical ROM, Cervical Endurance) still fall back to the old focus-first-field behavior — this mirrors `OBJ_GRID_DATA`'s own pre-existing scope, not a new gap. Ctrl+F's jump-search (see `search.py`'s entry above) uses this exact same anchor-scroll mechanism now too. |
| `watcher.py` | 118 | Polls `session_current.json` + the active session file for GTK body-chart-side updates, and a `.focus_tui` signal file | ✅ DONE, narrowed scope (`gtk_trial/gpab_trial/chart_watcher.py`) — see that file's module docstring for the full reasoning. Only the `on_chart_update` path is ported (`GLib.timeout_add` mtime-polling of this app's own `session_file`, calling `SubjectiveSection.refresh_from_chart()`); session-switch detection, the `.focus_tui` signal, and `BodyChartPanel` indicator sync are all deliberately NOT ported — none of them fit gpab's fixed single-session launch model or have a GTK-side equivalent to update. Plain polling was chosen over `Gio.FileMonitor` deliberately (matches the reference implementation's own proven algorithm exactly, since this can't be tested against a live bodychart session yet — see below). Verified headlessly against an isolated `~/PAB-gtktrial` copy: externally wrote a new stroke-cluster/note into the session file (matching the real `session_current.json`'s observed schema) while the app had it open, confirmed a new note slot appears with correct derived text and separately-typed content survives the refresh unchanged. **Not yet verified against the real GTK bodychart app itself** (the user cannot exercise that yet) — when that becomes possible, drawing a real stroke and confirming a sane note slot appears is the outstanding end-to-end check. Also fixed a pre-existing, unrelated bug this testing surfaced: `app.py::_sync_goals` crashed on every Subjective edit because `ConsentSection`'s goal list was named `.consent_goals` while `_sync_goals` expected `.goals` uniformly — fixed with an alias attribute. |
| `report_modal.py` | 70 | Report preview/regenerate trigger | ✅ DONE — Ctrl+R, `report_modal.py`. |
| `assessment_view.py` / `objective_view.py` (remaining features beyond what Phase 0 ported) | 945 / 716 | Section-complete indicators, migration helpers, the rest of the save/load orchestration | ✅ AUDITED 2026-08-23 (fork-based read-only comparison against `app.py`). Confirmed already-ported and equivalent: grid overview/`navigate_to_heading`, KB focus hook, goal-mirroring, region-test push to Pain Classification, Ctrl+R report path, save-status label, objective-mode entry/exit (cleanly superseded by `Gtk.Stack`, no port needed). Confirmed genuinely missing, 3 items: (1) **Medical tab red-flag status colour** — ✅ DONE same day (`MedicalSection.urgent_red_flag_status()` + `SectionNav.set_tab_status()`, left-border accent instead of Textual's full-button recolor since `.nav-active` already claims the background). (2) **Periodic 60s background report regeneration** — ✅ DONE same day (`gtk_trial/gpab_trial/report_timer.py`) — same three calls as `_generate_reports()` (`save_raw_report`/`export_session_report`/`save_clean_reports`), same 60s cadence, deliberately independent of Ctrl+R's `report_modal.py` exactly like the reference; runs in a background `threading.Thread` (sequential, not `asyncio.gather`-style concurrent — documented simplification) so the 60s `GLib.timeout_add` tick never blocks the GTK main thread. (3) **`_migrate_objective()`** — still missing, low priority: migrates pre-region-schema flat objective JSON to the current nested schema; the user's real session is already on the new schema so practical risk is low, but an old archived session would silently load as empty objective data rather than migrating. Also confirmed genuinely dead code in the TUI itself, correctly NOT ported: `SectionNav.set_indicator`/`refresh_indicators` (written, never rendered anywhere in the reference source). |
| `main.py` | 356 | Full `BINDINGS` table: F1–F9 section switches, F10 notes toggle, Ctrl+F1–F8 objective jumps, Alt+letter subsection jumps, Ctrl+Q/Ctrl+A/Ctrl+D | ✅ AUDITED 2026-08-23 (fork-based side-by-side comparison). F1–F10, Ctrl+Q/Ctrl+A/Ctrl+D, and all 11 Alt+letter subjective-subsection jumps (`_ALT_KEY_MAP`) match exactly. **One confirmed gap, still open**: only Ctrl+F5 (Neurological) of the 8 Ctrl+F1–F8 objective-tab jump shortcuts exists, wired as an isolated one-off rather than part of a complete set — General/Functional/Active/Passive/Sensory/Muscle/Special Tests (7 of 8) are missing. |

## Phase 4 — clinical knowledge base integration — ✅ DONE

| TUI file | Lines | Notes |
|---|---|---|
| `objective/kb_db.py` | 189 | ✅ DONE — copied unchanged, zero Textual imports as expected. |
| `objective/kb_loader.py` | 249 | ✅ DONE — copied with only `_KB_DIR` repointed at the read-only reference clone (same `parents[N]` pattern as `region_section.py`'s `_YAML_DIR`). |
| `objective/kb_panel.py` | 73 | ✅ DONE (`gpab_trial/objective/kb_panel.py`) — Ctrl+K field-focus lookup panel. Rendering deliberately does NOT reuse `KBEntry.render_lines()` (that hard-wraps every field to 44 chars for the TUI's fixed terminal width); a separate free-text renderer lets the GTK `Gtk.Label` reflow naturally to whatever width the panel has. Focus-tracking uses a per-widget listener registry (`widgets.add_focus_listener`) rather than a window-level `Gtk.Root` "notify::focus-widget" hook — that hook fired in isolated tests but not once real `Gtk.Stack`/`Gtk.ScrolledWindow` nesting was involved; unresolved why, so don't reach for it again without re-verifying. |
| `sections/regional_differential.py` | 471 | ✅ DONE (`gtk_trial/gpab_trial/sections/regional_differential.py`) — Pain Classification's cluster-tally panel. The pure data functions (`_build_members`, `_load_db_cluster`, `_short_sn_sp`, `_load_region_structure`, `_load_extra_clusters`) were lifted verbatim (zero Textual imports, only KB import paths repointed). `_TestRow`/`_ValueRow`/`_FlagRow`/`_ClusterBlock`/`RegionalDifferentialPanel` rebuilt with `Gtk.Expander` in place of `Collapsible`; click-to-KB uses a plain callback passed down the tree (`RequestKBCallback`) rather than Textual's Message-bubbling. `app.py`'s `_collect_region_tests`/`_push_region_tests_to_pain_classification` build the flattened tests dict from in-memory `collect()` calls (neurological + the active region's active/passive/muscle/special containers), pushed after region toggle, after `_load()`, and after every successful objective autosave — mirrors `assessment_view.py::_flatten_region_fields` + its three TUI push points exactly, verified against real session data for lumbar/cervical/shoulder/hip/knee/ankle (DB-backed cervical/shoulder cluster paths and cervical's Cook Myelopathy flag-row cluster included). |
| `objective/kb_db_screen.py` | 916 | ✅ DONE (`gtk_trial/gpab_trial/objective/kb_db_screen.py`) — Ctrl+D full KB browser. Every SQL query, the fuzzy search index/scorer, and the formatting helpers are lifted verbatim (zero UI imports). Two things were rebuilt rather than ported 1:1: Textual's `Tree` → `Gtk.TreeView` + `Gtk.TreeStore(str, object)` (the object column carries the same `{"type", "row"/"id"}` data dict `node.data` held; the TUI's synthetic root-as-region-name row is dropped since GtkTreeView doesn't need one — a heading label above the tree shows the region name instead, and top-level tree rows are conditions directly), and Rich markup (`[bold]`/`[dim]`/`[red]`) → Pango markup via `_b`/`_dim`/`_italic_dim`/`_color` helpers, with every interpolated DB value escaped through `GLib.markup_escape_text`. Left/Right stay freed for cross-panel focus movement (region list ↔ tree ↔ detail) exactly as in the TUI, via a window-level CAPTURE-phase key controller that runs ahead of GtkTreeView's own Left/Right handling; Enter is wired explicitly to toggle expand/collapse. Ctrl+F/F search reopens as a small transient `_KBSearchWindow`. Verified headlessly: tree building/expansion for a DB-backed region, detail-panel markup rendering for condition/cluster/test nodes, and the full search→navigate path (including a cross-region jump) all confirmed against the real `clinical_kb.db`. |

Per the real project's own CLAUDE.md, this is "built and live, not a planned phase" in the TUI —
treat it the same way here: not optional polish, a required part of full parity. `kb_db.py` should
be checked for Textual imports the same way `storage.py` etc. were, and reused unchanged if clean.
The Sn/Sp special-test widgets mentioned in the source project's CLAUDE.md need their own GTK
widget, likely alongside `objective/grid_widgets.py`.

## Phase 5 — report generation UI

`storage.py`'s report/raw-export generation is already reused unchanged. **Correction (was wrong
above until 2026-08-23):** this does NOT run on every save in either app — in the reference TUI
it's a separate 60s `set_interval`, decoupled from the debounced save cycle (see Phase 3's
`assessment_view.py` audit row). gpab now has the same 60s timer (`report_timer.py`, Phase 3),
independent of Ctrl+R (`report_modal.py`) exactly like the reference — this phase is complete.

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
