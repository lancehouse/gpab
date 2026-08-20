# PhysioChart — Project Overview

Specialist physiotherapy clinical tool for a Lenovo Yoga running Fedora 43 in tablet mode.
Primary input in body-chart mode is pressure-sensitive stylus/touchscreen. Keyboard primary in TUI.

## Two-app architecture

```
bodychart/                 GTK4 / C
  Stylus body chart app
  Writes → ~/PAB/<session>/_session.json
  Writes → ~/.local/share/pab/session_current.json  (active session pointer)

assessment/                Python 3.12 / Textual TUI
  Structured clinical assessment + report generation
  Reads  ← session_current.json  (to know which session is active)
  Reads/writes → ~/PAB/<session>/_assessment.json
  Reads/writes → ~/PAB/<session>/_objective.json
```

The two apps are **independent**. Changes to one do not require changes to the other unless the
shared session JSON schema changes. Schema changes require a version bump in both apps.

## Session file layout

Every session lives in its own directory under `~/PAB/`:

```
~/PAB/<session-name>/
  <name>_session.json       GTK-owned: body chart strokes, overlays, regions, patient identity
  <name>_assessment.json    TUI-owned: assessment sections 01–07 (consent → barriers)
  <name>_objective.json     TUI-owned: objective examination sections 01–07
  <name>_report.md          Generated on every save — compact Markdown clinical report
  <name>_raw.txt            Generated on every save — full plain-text raw export of all fields
```

All files are human-readable JSON or plain text. This is intentional and permanent — do not
introduce binary formats or database files. Files are used individually for various clinical tasks.

## Data persistence model

- **No SQLite.** JSON files are the permanent storage format.
- Auto-save on every field change. No save button anywhere.
- Atomic writes (temp file + rename) to prevent corruption.
- The GTK app owns `_session.json`. The TUI owns `_assessment.json` and `_objective.json`.
  Never write to the other app's file.

## Environment

- Fedora 43, GNOME, Ptyxis terminal (touch-compatible GTK terminal)
- GTK app: build with `ninja -C build` inside `bodychart/`
- TUI: Python 3.12 venv inside `assessment/`; activate before running

## Branch and deployment rules — ABSOLUTE

These rules are non-negotiable and override any other instruction in this session:

| Launcher | Bodychart binary | TUI binary | Git branch |
|----------|-----------------|------------|------------|
| `pabd`   | `bodychart/build/bodychart` | `assessment` → `assessment/.venv` | `dev` |
| `pab`    | `pab-stable/bodychart/build-stable/bodychart` | `assessments` → `pab-stable/assessment/.venv` | `main` |

These two streams are completely isolated. **Never mix them.**
- `bodychart/src/integration.c` must always call `assessment` (dev TUI).
- `pab-stable/bodychart/src/integration.c` must always call `assessments` (stable TUI).
- `~/.local/bin/assessment` → symlink to dev venv.
- `~/.local/bin/assessments` → script pointing to stable venv.

1. **All development work goes to `dev` first.** Every code change, bug fix, or feature
   lands on the `dev` branch. No exceptions.
2. **`pabd` runs `dev`.** Test everything in `pabd` before considering a merge.
3. **`main` is never touched during development.** Do not commit, merge, or push to `main`
   unless the user says explicitly — in that same message — "merge to main", "push to main",
   or equivalent. Finishing a feature, fixing a bug, or completing a task is NOT permission
   to merge.
4. **No mid-session merges.** Even if a fix is confirmed working in `pabd`, it stays on
   `dev` until the user explicitly requests the merge in a separate, deliberate instruction.

## Overarching rules

1. **Button width ≤ ¼ screen** — all interactive button widgets max 25% of available width.
   If a label doesn't fit, place it in an adjacent `Static` widget.
2. **Flag, don't guess clinical content** — if a field label, test name, or clinical term is
   ambiguous, stop and ask before interpreting or inventing content.
3. **No UI logic in storage** — `storage.py` reads/writes JSON only; no Textual imports,
   no clinical decisions. Sections collect/load data; storage persists it.
4. **Never lose data** — auto-save on every field change; atomic writes always.

## Clinical knowledge base — built and live

The clinical knowledge base (`clinical_kb.db`, Ctrl+K field-focus lookup panel, Ctrl+D full
browser, special test widgets with Sn/Sp) is built and in active use — not a planned phase.
Content is authored in the separate `~/Projects/kb` project and consumed read-only via
`~/.local/share/pab/clinical_kb.db`. Rollout is incremental, region by region (cervical and
shoulder are DB-backed; other regions still resolve from `objective/kb/*.yaml`), plus a
region-independent set (`_GLOBAL_DB_FIELDS` in `kb_loader.py`) for fields not tied to any one
body-region tab — e.g. Neurological's UMN signs and the Sensory section's pain-sensitisation
screen (allodynia, hyperalgesia, PPT, CPM, nerve trunk palpation). See
`assessment/CLAUDE.md`'s "Clinical knowledge base" section for the full architecture.

## Planned phases (not yet built)

- **Body-chart-driven pattern matching** — auto-suggesting tests/conditions from body chart
  findings (`query_patterns()`/`query_tests()`/`score_pattern()` in `logic.py`). Blocked on a
  schema addition (`condition_feature` needs a per-feature weight column) before it's
  implementable. Do not build this until explicitly requested. Do not design current code to
  prevent it.
