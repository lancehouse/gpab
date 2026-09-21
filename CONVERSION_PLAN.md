# Conversion Plan — full TUI → GTK4

## Scope

Port the entire `pab_assessment` package (Textual TUI, ~22.8k lines across `assessment/` — see
breakdown below) to native GTK4 inside `assessment_gtk/`, reusing every Textual-independent module
unchanged. `bodychart/` (already GTK4/C) is out of scope; the eventual integration point between
the two apps is addressed in Phase 6.

Reused unchanged (confirmed zero Textual imports): `storage.py` (5832 lines — JSON I/O, atomic
writes, report/raw-export generation), `mapping.py` (225), `logic.py` (295), `models.py` (74),
`cal_cp_model.py` (396), `form_schema.py` (286) + the YAML subsection files. That's a substantial
fraction of the total codebase inherited for free — the port's real work is the ~16k lines of
Textual widget/screen code below.

## Already done (Phase 0 — see `PROJECT_BRIEF.md`)

- Widget kit: `CheckButton`/`FlagButton` (3-state toggle), `RadioGroup` (exclusive gang, full
  keyboard parity), `AutoTextView`, `TouchEntry` — all in `gpab_assessment/widgets.py`.
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
| `search.py` + `search_widget.py` | 824 + 151 | Ctrl+F/Ctrl+. fuzzy jump-search across all fields | ✅ DONE (`assessment_gtk/gpab_assessment/search.py` + `search_widget.py`). Every static table and the fuzzy scorer are lifted verbatim (one field-id fix: TUI's `preferred_name_input` → this port's actual field_id, `preferred_name`). `build_index()` is GTK-specific: it walks each section's live `Gtk.Widget` tree matching on each widget's own `field_id` attribute (`search.find_by_field_id`) rather than Textual's `query_one(f"#{id}")`. `search_widget.SearchModal` reuses the same small transient-window pattern as the Ctrl+D browser's own search window. **Anchor-precision scope cut resolved**, reusing the same tagging built for Ctrl+T's grid overview: a "subsection" result now scrolls the exact subsection header to the top of the section's viewport via `app.py::_scroll_section_to_anchor`/`search.find_by_anchor_id`, and Special Tests region results (`st_lumbar` etc.) route through `_jump_to_special_region` to mount the region first if needed. Degrades to plain `_show_section` when `search._SUBSECTIONS`' anchor_id has no matching tagged widget (it carries some region-specific ids, e.g. `pm_cx_overpressure`, that were never given their own distinct header — those regions' Overpressure/PAIVMs headers all share one generic anchor_id). Every "field"/"content" result — the common case, a named field or a hit inside typed text — still jumps to and focuses the exact widget. CAL-CP diagnosis workup entries (dynamic, one per pain-site workup) switch to the right `Gtk.Notebook` tab via a new `DiagnosisSection.select_workup()`. Verified against a real session: index size/kind breakdown, exact-field jumps (assessment fields, an objective KB special-test field, Consent's Entry-delegates-to-inner-Gtk.Text case), scratchpad jump (opens the notes overlay), and a CAL-CP workup jump — all landing on the correct tab/widget. |
| `grid_overview.py` | 381 | Ctrl+G heading map for rapid section/subsection nav | ✅ DONE (`assessment_gtk/gpab_assessment/grid_overview.py`) — **rebound to Ctrl+T**, matching the reference TUI's own already-rebound `main.py`/`tui.py` BINDINGS table exactly (`ctrl+g` → `import_gonio`, freed for the goniometer-import wizard — see Phase 6's own entry for that, ported 2026-08-23; `ctrl+t` → `toggle_grid`, labelled "Overview"). `SUBJ_GRID_DATA`/`OBJ_GRID_DATA`/`section_to_cursor`/`_section_has_data` lifted verbatim — every id in them already matches this port's own section ids 1:1, including the special "04_objective" row (its "headings" are objective section ids, handled by `app.py`'s existing `_show_section` directly, no TUI-style mode-switch special-casing needed). Built as `GridOverviewPage`, an in-place page inside `app.py`'s own main `Gtk.Stack` (named `"grid_overview"`) — **not** a popup window: an early version used a transient window like Ctrl+F/Ctrl+D, but per direct feedback that broke the TUI's actual feel (the real app replaces `#section_content` in the same content area, sidebar still visible/responsive, no new window size to recalibrate around each time), so it was rebuilt to match — `app.py::_toggle_grid_overview`/`_open_grid_overview`/`_close_grid_overview` just swap the stack's visible child, same mechanism as switching to any other tab. Escape/Up/Down/Left/Right are handled by `app.py`'s existing global CAPTURE-phase key controller (checked first, ahead of every other binding) whenever `"grid_overview"` is the visible stack child. Full 2-D keyboard nav (skip-empty-row aware, cursor remembered across opens/toggle-closes) and the ✓ data-completion ticks are real, not simplified. Verified against a real session: in-place stack swap with sidebar untouched, click-to-jump for both a plain section heading and the special objective-mode-entry row, Escape/re-toggle returning to the exact prior tab, arrow-key cursor movement routed through the real global key handler, and ticks reflecting actual per-section `collect()` data, in both assessment and objective modes. **Row-to-sidebar-tab pixel alignment** (per further feedback — rows should line up exactly with `SectionNav`/`ObjectiveNav`'s own tab list, not just sit in the same general area): the in-content per-row label was dropped entirely (the sidebar tab alongside now IS the row label — this only works because `SUBJ_GRID_DATA`/`OBJ_GRID_DATA` already list rows in the same order as `SectionNav.SECTION_LABELS`/`ObjectiveNav.SECTION_LABELS`), and the row container's margin-top/spacing and each heading button's `min-height` were set to the exact values `nav.py`/`objective_nav.py` use for their own tab buttons (`margin-top: 4`, `spacing: 2`, `min-height: 48px`) — confirmed via `Gtk.Widget.measure()` that both button classes compute an identical 58px rendered height under the shared theme. **A second alignment bug, this one pre-existing in the reference TUI itself** (confirmed by inspecting the TUI's own `grid_overview.py`, not assumed): `OBJ_GRID_DATA` had no row at all for Special Tests, so every row from Muscle Test downward sat one row too high next to `ObjectiveNav`'s 9-row tab list, landing CRPS's heading row next to the "08 Special Tests" tab and leaving "09 CRPS" empty — same bug, same cause, in both apps. Fixed here (not reproduced): added an `"08_special"` row whose "headings" are the six body regions (Lumbar/Cervical/Shoulder/Hip/Knee/Ankle) rather than fixed subsection anchors, since Special Tests has no fixed layout of its own — it shows whichever regions `RegionTopbar` currently has active. `OBJ_GRID_DATA`'s row order now matches `ObjectiveNav.SECTION_LABELS` exactly, 9-for-9, confirmed programmatically. **Anchor-precision scope cut resolved**: `widgets.make_subsection_header()` now takes an optional `anchor_id`, tagged at ~40 call sites across every section file with the exact strings `SUBJ_GRID_DATA`/`OBJ_GRID_DATA` already use; `search.find_by_anchor_id()` finds the tagged widget and `app.py::_scroll_section_to_anchor()` aligns it to the top of the section's viewport (`compute_bounds()` + `vadjustment.set_value()`, deferred one frame). Outcome Measures' collapsed `Gtk.Expander` blocks carry `.anchor_id` directly and are expanded before being measured. Special Tests region headings (`st_lumbar` etc.) mount an inactive region via `_sync_active_regions()` before jumping straight to its `RegionContainer` — see `app.py::_jump_to_special_region`. A handful of region-specific YAML group labels with no corresponding grid heading (Ankle/Hip/Knee/Shoulder/Cervical ROM, Cervical Endurance) still fall back to the old focus-first-field behavior — this mirrors `OBJ_GRID_DATA`'s own pre-existing scope, not a new gap. Ctrl+F's jump-search (see `search.py`'s entry above) uses this exact same anchor-scroll mechanism now too. |
| `watcher.py` | 118 | Polls `session_current.json` + the active session file for GTK body-chart-side updates, and a `.focus_tui` signal file | ✅ DONE, narrowed scope (`assessment_gtk/gpab_assessment/chart_watcher.py`) — see that file's module docstring for the full reasoning. Only the `on_chart_update` path is ported (`GLib.timeout_add` mtime-polling of this app's own `session_file`, calling `SubjectiveSection.refresh_from_chart()`); session-switch detection, the `.focus_tui` signal, and `BodyChartPanel` indicator sync are all deliberately NOT ported — none of them fit gpab's fixed single-session launch model or have a GTK-side equivalent to update. Plain polling was chosen over `Gio.FileMonitor` deliberately (matches the reference implementation's own proven algorithm exactly, since this can't be tested against a live bodychart session yet — see below). Verified headlessly against an isolated `~/PAB-assessment-gtk` copy: externally wrote a new stroke-cluster/note into the session file (matching the real `session_current.json`'s observed schema) while the app had it open, confirmed a new note slot appears with correct derived text and separately-typed content survives the refresh unchanged. **Not yet verified against the real GTK bodychart app itself** (the user cannot exercise that yet) — when that becomes possible, drawing a real stroke and confirming a sane note slot appears is the outstanding end-to-end check. Also fixed a pre-existing, unrelated bug this testing surfaced: `app.py::_sync_goals` crashed on every Subjective edit because `ConsentSection`'s goal list was named `.consent_goals` while `_sync_goals` expected `.goals` uniformly — fixed with an alias attribute. |
| `report_modal.py` | 70 | Report preview/regenerate trigger | ✅ DONE — Ctrl+R, `report_modal.py`. |
| `assessment_view.py` / `objective_view.py` (remaining features beyond what Phase 0 ported) | 945 / 716 | Section-complete indicators, migration helpers, the rest of the save/load orchestration | ✅ AUDITED 2026-08-23 (fork-based read-only comparison against `app.py`). Confirmed already-ported and equivalent: grid overview/`navigate_to_heading`, KB focus hook, goal-mirroring, region-test push to Pain Classification, Ctrl+R report path, save-status label, objective-mode entry/exit (cleanly superseded by `Gtk.Stack`, no port needed). Confirmed genuinely missing, 3 items: (1) **Medical tab red-flag status colour** — ✅ DONE same day (`MedicalSection.urgent_red_flag_status()` + `SectionNav.set_tab_status()`, left-border accent instead of Textual's full-button recolor since `.nav-active` already claims the background). (2) **Periodic 60s background report regeneration** — ✅ DONE same day (`assessment_gtk/gpab_assessment/report_timer.py`) — same three calls as `_generate_reports()` (`save_raw_report`/`export_session_report`/`save_clean_reports`), same 60s cadence, deliberately independent of Ctrl+R's `report_modal.py` exactly like the reference; runs in a background `threading.Thread` (sequential, not `asyncio.gather`-style concurrent — documented simplification) so the 60s `GLib.timeout_add` tick never blocks the GTK main thread. (3) **`_migrate_objective()`** — deliberately NOT ported, by explicit user decision 2026-08-23: migrates pre-region-schema flat objective JSON to the current nested schema, but a scan of every real session in `~/PAB/` confirmed none are on the old flat schema — the user has no old data to migrate and considers that schema obsolete, so this is out of scope permanently, not deferred. (Flagged in that same discussion: the risk profile was actually worse than "loads empty" — gpab autosaves, so opening a genuinely old-schema file would have silently and permanently destroyed the flat data on first edit, since the migration guard only fires when `active_regions` is absent. Moot now, but worth remembering if raw old-format objective JSON is ever reintroduced by some other path.) Also confirmed genuinely dead code in the TUI itself, correctly NOT ported: `SectionNav.set_indicator`/`refresh_indicators` (written, never rendered anywhere in the reference source). |
| `main.py` | 356 | Full `BINDINGS` table: F1–F9 section switches, F10 notes toggle, Ctrl+F1–F8 objective jumps, Alt+letter subsection jumps, Ctrl+Q/Ctrl+A/Ctrl+D | ✅ DONE — fully audited 2026-08-23 (fork-based side-by-side comparison) and now complete. F1–F10, Ctrl+Q/Ctrl+A/Ctrl+D, and all 11 Alt+letter subjective-subsection jumps (`_ALT_KEY_MAP`) matched exactly from the start. The one confirmed gap — only Ctrl+F5 (Neurological) of the 8 Ctrl+F1–F8 objective-tab jump shortcuts existed, as an isolated one-off — is fixed: `_CTRL_FN_OBJECTIVE_MAP` in `app.py` now covers all 8 (General/Functional/Active/Passive/Neurological/Sensory/Muscle/Special Tests), matching `main.py`'s `action_obj_*` targets exactly. Also fixed a latent bug the fix surfaced: F1–F4's plain-F-key branches lacked the `not ctrl_held` guard F5–F9 already had, so Ctrl+F1–F4 were silently swallowed by the plain F-key handler rather than reaching any Ctrl+F binding — guards added for consistency (checking the new map first already prevented the fallthrough on its own). Verified headlessly: all 8 Ctrl+F1–F8 combinations enter objective mode and land on the correct section; plain F1 confirmed unaffected. |

## Phase 4 — clinical knowledge base integration — ✅ DONE

| TUI file | Lines | Notes |
|---|---|---|
| `objective/kb_db.py` | 189 | ✅ DONE — copied unchanged, zero Textual imports as expected. |
| `objective/kb_loader.py` | 249 | ✅ DONE — copied with only `_KB_DIR` repointed at the read-only reference clone (same `parents[N]` pattern as `region_section.py`'s `_YAML_DIR`). |
| `objective/kb_panel.py` | 73 | ✅ DONE (`gpab_assessment/objective/kb_panel.py`) — Ctrl+K field-focus lookup panel. Rendering deliberately does NOT reuse `KBEntry.render_lines()` (that hard-wraps every field to 44 chars for the TUI's fixed terminal width); a separate free-text renderer lets the GTK `Gtk.Label` reflow naturally to whatever width the panel has. Focus-tracking uses a per-widget listener registry (`widgets.add_focus_listener`) rather than a window-level `Gtk.Root` "notify::focus-widget" hook — that hook fired in isolated tests but not once real `Gtk.Stack`/`Gtk.ScrolledWindow` nesting was involved; unresolved why, so don't reach for it again without re-verifying. |
| `sections/regional_differential.py` | 471 | ✅ DONE (`assessment_gtk/gpab_assessment/sections/regional_differential.py`) — Pain Classification's cluster-tally panel. The pure data functions (`_build_members`, `_load_db_cluster`, `_short_sn_sp`, `_load_region_structure`, `_load_extra_clusters`) were lifted verbatim (zero Textual imports, only KB import paths repointed). `_TestRow`/`_ValueRow`/`_FlagRow`/`_ClusterBlock`/`RegionalDifferentialPanel` rebuilt with `Gtk.Expander` in place of `Collapsible`; click-to-KB uses a plain callback passed down the tree (`RequestKBCallback`) rather than Textual's Message-bubbling. `app.py`'s `_collect_region_tests`/`_push_region_tests_to_pain_classification` build the flattened tests dict from in-memory `collect()` calls (neurological + the active region's active/passive/muscle/special containers), pushed after region toggle, after `_load()`, and after every successful objective autosave — mirrors `assessment_view.py::_flatten_region_fields` + its three TUI push points exactly, verified against real session data for lumbar/cervical/shoulder/hip/knee/ankle (DB-backed cervical/shoulder cluster paths and cervical's Cook Myelopathy flag-row cluster included). |
| `objective/kb_db_screen.py` | 916 | ✅ DONE (`assessment_gtk/gpab_assessment/objective/kb_db_screen.py`) — Ctrl+D full KB browser. Every SQL query, the fuzzy search index/scorer, and the formatting helpers are lifted verbatim (zero UI imports). Two things were rebuilt rather than ported 1:1: Textual's `Tree` → `Gtk.TreeView` + `Gtk.TreeStore(str, object)` (the object column carries the same `{"type", "row"/"id"}` data dict `node.data` held; the TUI's synthetic root-as-region-name row is dropped since GtkTreeView doesn't need one — a heading label above the tree shows the region name instead, and top-level tree rows are conditions directly), and Rich markup (`[bold]`/`[dim]`/`[red]`) → Pango markup via `_b`/`_dim`/`_italic_dim`/`_color` helpers, with every interpolated DB value escaped through `GLib.markup_escape_text`. Left/Right stay freed for cross-panel focus movement (region list ↔ tree ↔ detail) exactly as in the TUI, via a window-level CAPTURE-phase key controller that runs ahead of GtkTreeView's own Left/Right handling; Enter is wired explicitly to toggle expand/collapse. Ctrl+F/F search reopens as a small transient `_KBSearchWindow`. Verified headlessly: tree building/expansion for a DB-backed region, detail-panel markup rendering for condition/cluster/test nodes, and the full search→navigate path (including a cross-region jump) all confirmed against the real `clinical_kb.db`. |

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

## Phase 6 — daily-use cutover (revised 2026-08-23 — supersedes the plan below)

**Direction reversed by explicit user decision 2026-08-23.** The original plan below (port gpab's
code back into `~/Projects/pab` and wire `bodychart/src/integration.c` to launch it) is **not**
happening. `pab` stays permanently untouched as a safe, working fallback install — `pabd`/`pabs`
keep launching the real bodychart + Textual TUI exactly as they do today, unmodified, indefinitely.
`gpab` becomes the thing actually used day-to-day instead, as a fully standalone app — not merged
into `pab`, not wired into `bodychart/src/integration.c`, never pushed back. This is *less* work
than the original Phase 6 and has already-lower risk: `gpab` already writes real `~/PAB/` sessions
(relaxed 2026-08-22) and already has its own launcher (root `./gpab <session>`), so no new
integration code is needed for this to work — the two apps cooperate purely by reading/writing the
same session files under `~/PAB/`, the same way bodychart and the old TUI always did.

**Concretely, day-to-day use looks like:** run real bodychart (via `pabd`/`pabs`, untouched) for
body-chart drawing; run `gpab <session>` separately for the assessment, instead of the Textual TUI
that used to be embedded inside bodychart's VTE terminal. `gpab_assessment/chart_watcher.py`
(`assessment_gtk/gpab_assessment/chart_watcher.py`) is what's supposed to keep gpab in sync with strokes drawn
in the separately-running bodychart window, by polling the shared session file for changes.

**What "pull from pab as needed" means going forward** (the user's own framing): this clone is
frozen at the moment it was cloned and has no remote, so there is no automatic sync. If a real bug
gets fixed in `pab`'s `storage.py`/`mapping.py`/`logic.py`/etc. later, pulling it into gpab means
manually copying the changed file(s) from `~/Projects/pab/assessment/` into this clone's own
`assessment/` (still exactly the same "reference copy `assessment_gtk` imports from via
`pab_path_bootstrap.py`" role it has always had — nothing about that changes) and re-running the
`collect()`/`load()` round-trip diffs per Standing Rule 1 to confirm the copy didn't silently change
behavior. Never the other direction.

**Live test run 2026-08-23 found the actual blocker, and it's now being fixed.** Ran real bodychart
(`pabd`) + gpab side by side against a fresh test session (`GPAB-test_23_08_2026_1044`). Findings:
- Chart→gpab sync (`chart_watcher.py`) **worked**: bodychart strokes/notes did flow into gpab's
  Subjective tab correctly.
- But **bodychart's own launcher unconditionally auto-spawns the old embedded Textual TUI** in a
  VTE terminal every time a session is opened (`bodychart/src/window.c`'s
  `launch_commit_new`/`launch_commit_open` both call `integration_create_tui_window`) — there was
  no way to get bodychart running *without* the old TUI also opening and independently writing
  `_assessment.json`/`_objective.json`. With three programs (bodychart, TUI, gpab) all touching the
  same session files, the TUI and gpab drifted apart (each only reads its files once at startup,
  neither watches the other's writes — expected, but made side-by-side literally unusable), and
  Ctrl+C on the TUI terminal killed bodychart too, so the TUI couldn't even be closed independently
  to work around it.
- **User's explicit call in response**: don't modify `~/Projects/pab` (stays untouched, permanent
  safe fallback, `pabd`/`pabs` keep building/running the original code) — instead vendor+modify
  bodychart's C source **inside this clone's own `bodychart/` directory** so gpab's own build can
  launch gpab instead of the TUI. This is a further refinement of the same Phase 6 direction above,
  not a reversal of it.

**In progress, NOT yet built or tested (mid-edit when the session ended for a reboot)**:
`bodychart/src/integration.c` in this clone has been rewritten — `integration_create_tui_window` no
longer creates a VTE terminal/embedded window at all; it `g_spawn_async`s
`assessment_gtk/.venv/bin/python -m gpab_assessment.main --session <path>` as a fully independent process
(gpab manages its own window). `integration_focus_tui`/`integration_destroy_tui` are now no-ops —
this is a deliberate decoupling, not an oversight: bodychart and gpab no longer own each other's
lifecycle the way bodychart used to own the embedded TUI's (closing one no longer closes the
other — the old Ctrl+C-kills-both problem that triggered this work is gone by construction).
`meson.build`'s `vte_dep` was removed (confirmed via grep: `vte` was only ever referenced from
`integration.c`, nowhere else in `bodychart/src/`). **Next session must**, in order: (1) run
`meson setup --reconfigure build && ninja -C build` inside `~/Projects/gpab/bodychart/` and fix any
compile errors — this has not been attempted yet; (2) confirm
`git -C ~/Projects/pab status --short | wc -l` is still 11 and `~/Projects/kb` still 5 (isolation
check, unaffected by this since only this clone's own `bodychart/` was edited, but verify, don't
assume); (3) kill the currently-running old bodychart/TUI/gpab trio from the live test, launch the
newly-built `bodychart` binary against a session, confirm it spawns gpab directly with no VTE/TUI
window and both apps save correctly with no file contention; (4) update
`bodychart/CLAUDE.md` (still describes the VTE/TUI-embedding architecture as current — now stale
for this clone specifically) and the top-level `CLAUDE.md`'s isolation section, which currently
says `bodychart/` (like `assessment/`) is a "read-only reference copy... never edit them" — that
sentence is now factually wrong for `bodychart/` specifically (`assessment/` is still correctly
read-only; only `bodychart/` changed) and needs correcting before it misleads a future session.

**✅ ALL OF THE ABOVE DONE, 2026-08-23 (same day, follow-on session).** Top-level `CLAUDE.md`
corrected (the "Permanent end state" paragraph and the isolation-guarantee bullet now correctly
describe `bodychart/` as a deliberately-modified vendored copy, `assessment/` still read-only, plus
an explicit "`ninja -C build` only, never `ninja install`" rule). `meson setup --reconfigure build
&& ninja -C build` succeeded cleanly (one pre-existing, unrelated warning in `canvas.c`; nothing
from the isolation-check grep or the AppState struct broke the build — both prior-session claims
held up). Isolation counts re-confirmed unchanged (`pab` 11, `kb` 5) both before and after the
build, which stayed fully contained in this clone's own `bodychart/build/`.

**Live-tested against real sessions on the actual machine, not just headlessly**, and this surfaced
a real bug beyond what was planned: `integration_create_tui_window` originally tracked gpab's PID
per-bodychart-process and killed only that one before respawning — but bodychart only shows its
launch dialog once, at startup, so in real use a bodychart process only ever calls
`integration_create_tui_window` once; that PID check could never fire for the actual failure mode.
Confirmed live: with gpab open for one patient, launching a second gpab process (e.g. via a freshly
relaunched bodychart, for a different patient) doesn't open a new window — gpab's own
single-instance `GtkApplication` silently hands the second launch off to the existing instance and
exits, leaving the wrong patient's data on screen with no error at all. Fixed by killing any
running gpab process **by name** (`pkill -f 'gpab_assessment\.main'`, mirroring the same approach the
`./gpab` launcher script already uses for its own staleness problem) before every spawn, rather
than relying on this-process-only PID tracking — verified live: patient A open in gpab, bodychart
quit and relaunched for patient B, old gpab process gone, exactly one new gpab process running
against B's session file, screen confirmed showing B's data. Also added a visible `GtkAlertDialog`
(matching the existing style in `window.c`, not the deprecated `gtk_message_dialog_new`) for a spawn
failure, so it's never silent on a touchscreen-only machine — not yet exercised live (would require
deliberately breaking the launch, e.g. renaming the venv), but the code path is in place.

**Still outstanding before Phase 6 is fully done** (unchanged from the list below): the full manual
touchscreen pass, the goniometer-import hold, and the `DEFAULT_SESSION` fallback / `.desktop` entry
cleanup items.

**Once the above passes, still left before calling gpab "done" for daily use**:
1. **A real full manual pass on the Yoga touchscreen**, not just headless round-trip diffs — walk
   every assessment section and every objective region/tab by hand with the stylus, per
   `PROJECT_BRIEF.md`'s own "Decision" section, which called for this before considering the trial
   phase's promise (touch-latency fix without losing keyboard workflow) actually validated end to
   end.
2. **✅ DONE, 2026-08-23.** Goniometer-import wizard (Ctrl+G) ported —
   `assessment_gtk/gpab_assessment/goniometer_import/`. `rom_field.py`/`matcher.py`/`field_dictionary_active.py`/
   `field_dictionary_passive.py` copied verbatim (grep-confirmed zero Textual imports, exactly like
   `storage.py`/`kb_db.py`). `importer.py` copied with one change: `from .. import storage` →
   `pab_path_bootstrap` + `from pab_assessment import storage` (this port's standard pattern) —
   `INBOX_ROOT`, the read-modify-write `apply_grouped_values`, and archive logic are unchanged.
   `wizard_screen.py` is the one real port: Textual `ModalScreen[T]` → plain `Gtk.Window` +
   callback (same pattern as `search_widget.SearchModal`), `DataTable` → `Gtk.ListBox` (selection
   preserved by index across a refresh — a small deliberate improvement over the reference, so
   fixing several ambiguous rows in a row doesn't jump back to the top each time), Enter-to-fix
   wired via `ListBox`'s own `row-activated` rather than a window-level key handler (the two would
   otherwise race for the same key). `app.py::_open_gonio_import` (Ctrl+G, freed for this since
   Ctrl+T already took over grid-overview) mirrors `tui.py::action_import_gonio` exactly: same
   inbox-then-most-recently-imported fallback, same multi-file combine-into-one-review-pass, same
   reload-from-disk after apply. Patient code comes from `_session.json`'s own `patient_id` field
   (gpab has no `SessionHeader` widget to read it from, unlike the TUI) — confirmed this matches the
   real inbox directory-naming convention against the two genuine `.gonio.json` samples already
   present on this machine from prior real device testing.

   **Two real bugs found and fixed during this port, both via live testing against a real captured
   sample, not just headless diffs:** (1) *Ordering race*, caught before it could bite — mirroring
   `tui.py`'s own on-disk-write mid-session, `apply_grouped_values` writes `_objective.json` directly,
   behind the live widget tree; an already-armed 2s autosave debounce firing after that write would
   silently overwrite the freshly-imported values with stale in-memory ones (same class as the
   `_on_region_toggled` fix earlier the same day). Fixed by flushing any pending objective save
   *before* calling `apply_grouped_values`, not just reloading after. (2) *Stale display after
   reload*, caught live: an import into an ALREADY-active region (Shoulder, in testing) wrote
   correctly to disk and `self._load()` ran, but the on-screen field kept showing its old value —
   because `_sync_active_regions` (which `_load()` calls) only mounts, and therefore only loads data
   into, regions newly transitioning to active; a region active both before and after a reload never
   goes through that path again. Fixed by extracting `_load_region_data()` and having `_load()` call
   it unconditionally for every currently-active region, not relying on `_mount_region`'s own load
   step alone. Verified live end-to-end against a real `.gonio.json` capture (copied to a scratch
   inbox dir, not the only real samples on disk): unresolved "needs review" row for a side-unstated
   measurement, candidate-picker fix to Left then a second run to Right, Apply, on-disk
   `_objective.json` write confirmed, source file correctly archived to `_imported/`, and — after
   the stale-display fix — the on-screen field updating immediately with no app restart needed.
3. **✅ DONE, 2026-08-23.** Retired the `DEFAULT_SESSION` fallback in the root `gpab` launcher
   script — it's now a manual/dev entry point only (`bodychart` is the real daily launch path since
   it spawns `gpab` per session directly), so a missing session name is a plain usage error again,
   matching `scripts/run.sh`'s own behavior. **A standalone "launch gpab directly" `.desktop` entry
   was deliberately skipped**, by user decision — `gpab` always requires a session name with no
   picker, so a bare icon for it would have nothing to open.

   **A `.desktop` entry for this clone's own `bodychart` build was added instead** (same day,
   follow-on request) — `bodychart/data/com.gpab.bodychart.desktop`, installed at
   `~/.local/share/applications/com.gpab.bodychart.desktop`, `Exec`ing this clone's binary
   (`~/Projects/gpab/bodychart/build/bodychart`) by absolute path directly, never through
   `pabd`/`pabs`. This is what makes "launch from the GNOME app grid instead of a terminal" actually
   work, since *this* bodychart is the one that spawns `gpab` per session. Building it surfaced one
   more instance of the exact bug class fixed earlier for `gpab` itself: `main.c` still used
   production's own GTK application ID (`com.pab.bodychart`), and `GtkApplication` is single-instance
   per ID — launching this build while `pabd`/`pabs`'s production bodychart was already running would
   have silently handed off to *that* process instead of starting this one. Fixed by giving this
   clone's `main.c` a distinct ID, `com.gpab.bodychart` (source change, this clone only — production
   `~/Projects/pab/bodychart/src/main.c` untouched). Verified live via `gtk-launch com.gpab.bodychart`
   (the same path GNOME's app grid uses): launch dialog appeared, icon shows correctly in the GNOME
   grid/search.

<details>
<summary>Original Phase 6 plan (superseded 2026-08-23, kept for history)</summary>

This repo (`gpab`) has no remote and stays a pure R&D sandbox permanently — it is never the
deployment target. Once the conversion is validated here end-to-end (every section ported,
round-trip verified, a full manual pass on the Yoga against the original trial's pass/fail
criteria), the actual cutover is separate, deliberate work that happens **in `~/Projects/pab`
itself**, where that repo's own branch rules apply in full (all work to `dev`, `pabd` for testing,
never `main` without an explicit instruction in that exact message). Concretely: hand-port (or
directly copy, then re-verify) the validated `assessment_gtk/gpab_assessment/` code into a new module inside
the real `assessment/` package, wire `bodychart/src/integration.c` to launch it in place of (or
alongside, during a transition period) the VTE-embedded Textual TUI, and only then consider `pab`'s
Textual `tui.py`/`main.py` for retirement. None of that work should start until this plan's Phases
1–5 are substantially complete and tested here.

</details>

## Flagged for future work (2026-08-23 — deliberately not started)

User is taking gpab into real clinical use starting tomorrow and wants real-world feedback to drive
what comes next, rather than speculatively building either of these now. Both were researched and
discussed in detail same day as the KB image feature (commits `80222af`/`96e1baf`); recorded here so
neither needs re-deriving cold.

**1. Non-region-based KB images (e.g. a dermatome map in the Neurological section).** The mechanism
built for region-based test images (Ctrl+K/Ctrl+D, `image_filename` column, `output/images/`) applies
identically here — no new plumbing needed. What's actually needed:
- Real, reusable source assets already exist and don't need to be created: `bodychart/views/anterior
  dermatomes.svg` / `posterior dermatomes.svg` (full labeled reference diagrams), and
  `bodychart/src/overlay_data/dermatomes.c` (per-dermatome path data C4–S2, what bodychart's own live
  overlay renders from).
- Two tiers: (a) cheap — export the two existing SVGs as-is, show the same whole map for every
  dermatome field (~an hour); (b) better — batch-render each dermatome's own highlighted shape into
  its own PNG from the existing per-segment path data (no live bodychart coupling needed, a one-time
  script), mapped per-field like any other KB image.
- **Real blocker, found during research, not about images at all**: individual dermatome fields
  (`sn_c5_l`, `sn_t1_l`, etc.) have **no `test_field_map` entry in the KB database yet** —
  `source/msk_clusters_pab.csv` has an explicit existing note flagging this as an unresolved
  authorship decision (one entry per dermatome vs. one composite entry). This needs a clinical-content
  decision before an image would even have a field to attach to — not something to solve in code.
- Durability risk: `overlay_data/dermatomes.c` self-describes as "clinically-approximate initial
  paths — refine over time." Pre-rendered per-dermatome PNGs (tier b) would silently drift from
  bodychart's own live shapes if those are ever corrected, with no automatic link between the two.

**2. Drag-gesture bulk-select for grid rows** (e.g. dragging down a myotome grade column C5→T1 to set
several rows to the same value in one motion, instead of tapping each one). Technically a good fit —
`Gtk.GestureDrag` + `Gtk.Widget.pick()` for live hit-testing, not `Gtk.GestureZoom`/pinch (that's a
2-finger distance gesture, the wrong tool for "apply this value to a range"). Estimated ~a day or two
for a first working version on one grid type, built as a shared/reusable behavior (same pattern as
`grid_nav.py`) so it generalizes to Sensory/Muscle grades rather than being one-off. **Three design
decisions still needed from the user before building, not something to decide unilaterally**:
1. Same column-position replicated down every row the drag passes over (recommended — more
   touch-reliable than raw spatial hit-testing on a dense grid), vs. literally whatever's under the
   finger.
2. Live visual feedback (highlight each row as the drag passes over it, before commit on release) —
   recommended given "never lose data" is already a standing project rule; a silent bulk-set is the
   wrong default.
3. Misfire protection so an accidental drag-that-starts-as-a-scroll doesn't turn into a bulk edit,
   and so the gesture coexists cleanly with the tab's own normal scroll behavior on the same surface.

**3. Other Ctrl+K candidates found in the existing KB pool while wiring medical.py's SpA flags
(2026-09-16) — deliberately not built now, `medical.py`-only per user instruction; other sections
not reviewed for this yet.** Checked every `medical.py` field id (`rf_*`, `cvd_*`, `comorbid_*`,
`diff_as_*`, `diff_aaa_*`, `diff_vc_*`, `img_*`) against `clinical_kb.db`'s `test_field_map` —
none has an existing field-mapped entry (`diff_spa_*`, added same day, is the only medical.py
content in that table). But the KB does already hold unmapped, content-only material that's an
obvious future match:
- **Ankylosing Spondylitis condition (id 22, "Ankylosing Spondylitis / Axial Spondyloarthropathy")**
  is already Tier-1 validated CPR content in the KB (`msk_test_clusters_comprehensive.csv`), with a
  cluster ("AS Clinical Assessment Cluster — BASMI + SIJ + Chest") — but `validate_kb.py` lists it
  among the 30 CPR-panel clusters with **zero field-mapped tests**. Wiring `medical.py`'s existing
  `diff_as_*` flags (or the AS cluster's own BASMI/SIJ/chest-expansion tests) to it would need new
  `test_field_map` rows authored in `~/Projects/kb`, same effort as the SCREEN'D'EM work just done —
  not a flip-a-switch case like the others below.
- **Rheumatoid Arthritis (id 13) and Gout (id 39)** conditions also exist in the KB with no
  `medical.py` field mapped to either — `comorbid_inflammatory`/`comorbid_fibromyalgia`-type flags
  are plausible candidates but would need the same new-authoring pass.
- **`red_flag` and `clinical_concept` tables** hold real, relevant content (e.g. red_flag row 5:
  "Pulsatile abdominal mass (suspect AAA)", directly on point for `diff_aaa_pulsating`) but have
  **no `pab_field_id` column at all** and no code path resolves them today — `kb_db.py` only ever
  queries `test_field_map`. Wiring these in would need a genuinely new resolution mechanism, not
  just new CSV rows, so it's a bigger lift than either point above.

### History-implied barrier query flags (raised 2026-09-19 — not started)

Idea from the Subjective goal-orientation work (`goal_type_*`, Crombez et al 2012): Barriers
toggles could take on a distinct "history implies a barrier — please check this" colour/state,
driven automatically from what's already been recorded elsewhere (e.g. treatment-seeking or
social-validation goal orientation ↔ `bx_belief_cure_focus` / `bx_belief_further_tx`). Kept
**separate and un-linked for now** on purpose — the goal-orientation flags are descriptive
only. Barriers already has `update_cross_refs()` + `_xref_badge()` plumbing to build on. Needs a
new toggle state/colour in `widgets.py`/`style.css` (centralised, per the standing rules), not a
per-section one-off, and needs the user to decide which history items imply which barrier
before any mapping is written (flag, don't guess clinical content).

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
