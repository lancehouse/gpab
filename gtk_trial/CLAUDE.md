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
`gpab_trial/sections/yaml_subsection.py`, consuming the *same* YAML file the TUI uses).

## What's out of scope for this trial

See the plan file — briefly: no live file-watcher re-sync, no Ctrl+F search, no report
generation, no wiring into `bodychart/src/integration.c`, no arrow-key spatial nav
(Tab/Shift+Tab only), and no other assessment/objective sections.
