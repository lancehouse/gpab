# gtk_trial — the conversion codebase

Started as a touch-vs-terminal trial of just Consent + Subjective; that trial succeeded and
the project is now a full conversion of the assessment TUI to GTK4 (all code still lives here —
see `../PROJECT_BRIEF.md` for what's been proven, `../CONVERSION_PLAN.md` for the section-by-section
plan going forward, and `../CLAUDE.md` for the repo-wide isolation rules). This file covers only
what's specific to running/building the code in this directory.

## Isolation guarantee — read before touching anything here

- **`~/Projects/gpab` is a `git clone` of `~/Projects/pab`, with its own independent
  `.git` and no `origin` remote.** It cannot push to or otherwise affect the real `pab`
  or `kb` repos.
- **Session data isolation was relaxed 2026-08-22**: reading/writing real sessions under
  `~/PAB/<name>/` directly is fine now — `gpab_trial/main.py` no longer refuses it.
  `~/PAB-gtktrial/` (via `scripts/copy_trial_session.sh`) still works if you want a disposable
  copy, but isn't required.
- The `assessment/` and `bodychart/` folders in this clone are untouched reference
  copies — all trial code lives in `gtk_trial/`, imported via `pab_path_bootstrap.py`
  pointing at *this clone's* `assessment/`, never `~/Projects/pab/assessment/`.

## Running it

```bash
cd gtk_trial
bash scripts/setup_venv.sh                      # one-time: venv + pyyaml + pydantic
bash scripts/copy_trial_session.sh <name>        # copy a real session into ~/PAB-gtktrial/
bash scripts/run.sh <name>                       # launch against the copy
```

## What's reused unchanged from `pab_assessment`

`storage.py` (JSON I/O + merge-write save), `mapping.py` (body-chart → note prefill),
`logic.py` (sleep-efficiency calc), `form_schema.py` + `sections/yaml/subj_sleep_pilot.yaml`
(the Sleep subsection's declarative field spec — rendered here by a brand-new GTK renderer,
`gpab_trial/sections/yaml_subsection.py`, consuming the *same* YAML file the TUI uses); the six
regional objective YAML files (`objective/sections/yaml/*.yaml`); `objective/kb_db.py` and
`objective/kb_loader.py` (clinical KB resolution — DB-backed for cervical/shoulder, YAML
fallback elsewhere, unchanged from the TUI).

## What's built (see `CONVERSION_PLAN.md` for the authoritative, up-to-date phase list)

All 8 assessment sections (Consent through Rx & Plan) and all 9 objective tabs (General,
Functional, Active Movement, Passive/OP, Neurological, Sensory, Muscle Testing, Special Tests,
CRPS) are ported and round-trip-verified against real session JSON — including Passive/Muscle
extras for all six regions (lumbar/cervical/shoulder/hip/knee/ankle). Arrow-key spatial grid
navigation (`objective/grid_nav.py`) is standard throughout, not Tab/Shift+Tab only. A body-region
toggle topbar (`objective/region_topbar.py`) mounts/unmounts regions live. Report generation
(Ctrl+R, `report_modal.py`), a Ctrl+K knowledge-base panel (`objective/kb_panel.py`), Pain
Classification's Regional Differential cluster-tally panel (`sections/regional_differential.py`,
live-updated per active region, click-to-KB wired), the Ctrl+D full Clinical KB browser
(`objective/kb_db_screen.py`, region list + condition/cluster/test tree + detail panel + its own
fuzzy search), and Ctrl+F fuzzy jump-search across every assessment/objective field
(`search.py` + `search_widget.py`) are all built and wired. Phase 4 (KB integration) is complete.

## What's still out of scope

No live body-chart file-watcher re-sync (region toggling is manual only), no Ctrl+G heading-map
overview, no wiring into `bodychart/src/integration.c`. See `CONVERSION_PLAN.md`'s Phase 3/6
tables for the full remaining list.
