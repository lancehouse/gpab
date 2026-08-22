# GTK Touch Trial — Consent + Subjective

## Purpose

Native GTK4 (PyGObject) trial of the PAB clinical assessment's first two subjective-side
tabs — **Consent** and **Subjective** — to evaluate touch/mouse interaction versus the
Textual TUI, which is slow on the Lenovo Yoga's touchscreen. See
`~/.claude/plans/delegated-gathering-newell.md` for the full plan, decisions, and
pass/fail criteria.

## Isolation guarantee — read before touching anything here

- **`~/Projects/gpab` is a `git clone` of `~/Projects/pab`, with its own independent
  `.git` and no `origin` remote.** It cannot push to or otherwise affect the real `pab`
  or `kb` repos.
- **This trial only ever reads/writes inside `~/Projects/gpab` and `~/PAB-gtktrial/`.**
  It never opens `~/PAB/<name>/` (the real, live session directory) for writing.
  `gpab_trial/main.py` actively refuses to launch against any path under `~/PAB/`.
- To test with real data, copy a session out first:
  `scripts/copy_trial_session.sh <session-name>` (reads `~/PAB/<name>/`, writes only to
  `~/PAB-gtktrial/<name>/`).
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
