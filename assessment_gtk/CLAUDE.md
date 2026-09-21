# assessment_gtk — the GTK4 assessment app

What began as a small touch-vs-terminal comparison (Consent + Subjective only) proved out well
enough that this is now the real build: a full conversion of the assessment TUI to a native GTK4
app (all code lives here — see `../PROJECT_BRIEF.md` for the background on why this exists,
`../CONVERSION_PLAN.md` for the section-by-section plan going forward, and `../CLAUDE.md` for the
repo-wide isolation rules). This file covers only what's specific to running/building the code in
this directory.

## Isolation guarantee — read before touching anything here

- **`~/Projects/gpab` is a `git clone` of `~/Projects/pab`, with its own independent
  `.git` and no `origin` remote.** It cannot push to or otherwise affect the real `pab`
  or `kb` repos.
- **Session data isolation was relaxed 2026-08-22**: reading/writing real sessions under
  `~/PAB/<name>/` directly is fine — `gpab_assessment/main.py` doesn't refuse it.
  `~/PAB-assessment-gtk/` (via `scripts/copy_dev_session.sh`) still works if you want a disposable
  copy, but isn't required.
- The `assessment/` and `bodychart/` folders in this clone are reference copies — `assessment/`
  is mostly kept untouched (the TUI source this app ports from and stays schema-compatible with),
  though as of 2026-09-15 specific files in it may be edited on an incremental, as-needed basis
  when gpab genuinely depends on the change (see `../CLAUDE.md`'s isolation guarantee section for
  the full rule and reasoning — this is not a blanket green light);
  `bodychart/` is deliberately vendored and locally modified (see `../CLAUDE.md`'s Phase 6 note)
  to launch this app directly. All of this app's own code lives in `assessment_gtk/`, imported via
  `pab_path_bootstrap.py` pointing at *this clone's* `assessment/`, never `~/Projects/pab/assessment/`.

## Running it

```bash
cd assessment_gtk
bash scripts/setup_venv.sh                      # one-time: venv + pyyaml + pydantic
bash scripts/copy_dev_session.sh <name>          # copy a real session into ~/PAB-assessment-gtk/
bash scripts/run.sh <name>                       # launch against it (checks ~/PAB/<name>/ first)
```

## What's reused unchanged from `pab_assessment`

`storage.py` (JSON I/O + merge-write save), `mapping.py` (body-chart → note prefill),
`logic.py` (sleep-efficiency calc), `form_schema.py` + `sections/yaml/subj_sleep_pilot.yaml`
(the Sleep subsection's declarative field spec — rendered here by a brand-new GTK renderer,
`gpab_assessment/sections/yaml_subsection.py`, consuming the *same* YAML file the TUI uses); the
six regional objective YAML files (`objective/sections/yaml/*.yaml`); `objective/kb_db.py` and
`objective/kb_loader.py` (clinical KB resolution — DB-backed for cervical/shoulder/CRPS/pain-
sensitisation/lumbar SIJ, YAML fallback elsewhere, unchanged from the TUI).

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
fuzzy search), Ctrl+F fuzzy jump-search across every assessment/objective field
(`search.py` + `search_widget.py`), a heading-map overview (`grid_overview.py`, Ctrl+T), a
Ctrl+G ROM/goniometer import wizard, and a Ctrl+S spell-check pass (`spellcheck.py` +
`spellcheck_modal.py`, dictionary-backed via `enchant`, walking every free-text field live in the
widget tree and correcting in place — separate from `autocorrect.py`'s fixed-typo table, which
fires inline while typing) are all built and wired. This app is what `bodychart` launches
directly for every real session (see `../bodychart/src/integration.c`) and is in genuine clinical
use, not a prototype running alongside the TUI.

## What's still out of scope

See `CONVERSION_PLAN.md`'s remaining-work table for anything not yet listed above as built.
