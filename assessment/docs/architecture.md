# Assessment App — Architecture Overview

This document explains how the different YAML and Python files relate to each
other, what is user-editable without code changes, and how the knowledge base
connects to the assessment form.

---

## The Three YAML Layers

There are three distinct YAML layers in the app. They look similar but serve
completely different purposes.

```
pab/assessment/
│
├── pab_assessment/sections/yaml/
│   └── subj_sleep_pilot.yaml        ← SUBJECTIVE form driver
│
├── pab_assessment/objective/sections/yaml/
│   ├── cervical.yaml                ← OBJECTIVE form driver (cervical)
│   ├── lumbar.yaml                  ← OBJECTIVE form driver (lumbar)
│   ├── shoulder.yaml                ← OBJECTIVE form driver (shoulder)
│   ├── hip.yaml                     ← OBJECTIVE form driver (hip)
│   ├── knee.yaml                    ← OBJECTIVE form driver (knee)
│   └── ankle.yaml                   ← OBJECTIVE form driver (ankle)
│
├── pab_assessment/objective/ad_forms/
│   ├── __init__.py                  ← spec loader, value lookup, report rows (no UI)
│   └── ad_lx_sij.yaml               ← AD position-ordered form (gpab tab 10 + report)
│
├── pab_assessment/objective/kb/
│   ├── cervical.yaml                ← KNOWLEDGE BASE content (cervical)
│   ├── lumbar.yaml                  ← KNOWLEDGE BASE content (lumbar)
│   ├── shoulder.yaml                ← KNOWLEDGE BASE content (shoulder)
│   ├── hip.yaml                     ← KNOWLEDGE BASE content (hip)
│   ├── knee.yaml                    ← KNOWLEDGE BASE content (knee)
│   └── ankle.yaml                   ← KNOWLEDGE BASE content (ankle)
│
└── regions/
    ├── cervical_physical_examination.md   ← clinical REFERENCE (not read by app)
    └── lumbar_physical_examination.md     ← clinical REFERENCE (not read by app)
```

---

## Layer 1 — Form Driver YAML (drives what fields appear in the TUI)

**Files:** `sections/yaml/subj_sleep_pilot.yaml`,
           `objective/sections/yaml/cervical.yaml`,
           `objective/sections/yaml/lumbar.yaml`,
           `objective/sections/yaml/shoulder.yaml`,
           `objective/sections/yaml/hip.yaml`,
           `objective/sections/yaml/knee.yaml`,
           `objective/sections/yaml/ankle.yaml`

These files define the **structure of the form** — which rows exist, what their
labels are, what RadioGroup options are available. The Python rendering code
reads them and builds the TUI from them. If you add a row here, it appears in
the form. If you rename a label, the label changes on screen.

**CRITICAL: never rename a field `id`.** The `id` is the JSON storage key.
Renaming it silently drops all historical data for that field. Labels, options,
and notes can be changed freely.

### What is and isn't YAML-driven yet

| Section | Status |
|---|---|
| Objective: Active Movement | YAML-driven ✓ |
| Objective: Muscle Testing | YAML-driven ✓ |
| Objective: Special Tests | YAML-driven ✓ |
| Subjective: Sleep | YAML-driven ✓ (pilot) |
| Objective: Neurological, Sensory, Functional, General | Hardcoded Python |
| All other Subjective sections | Hardcoded Python |

---

## Layer 2 — Knowledge Base YAML (populates the KB panel on field focus)

**Files:** `objective/kb/cervical.yaml`, `objective/kb/lumbar.yaml`,
           `objective/kb/shoulder.yaml`, `objective/kb/hip.yaml`,
           `objective/kb/knee.yaml`, `objective/kb/ankle.yaml`

These files supply the text shown in the Ctrl+K KB panel when you focus a
special test field. Each entry contains: label, purpose, position, procedure,
Sn/Sp, cluster note.

**How KB entries link to form fields:**

The key in the KB YAML must match the row `id` in the form driver YAML.
Bilateral tests (left/right) use the stem only — the loader automatically
resolves `spurling_l` → `spurling` by stripping the `_l`/`_r` suffix.

```
Form YAML row:      {id: spurling_l, label: "Spurling Left", ...}
KB YAML entry key:  spurling:
                      label: "Spurling's Test"
                      ...
```

**How to update KB content:**
1. Open `objective/kb/cervical.yaml` or `lumbar.yaml`
2. Find the entry by its key (= the row `id` from the form YAML, without `_l`/`_r`)
3. Edit any field — label, purpose, position, procedure, sn_sp, cluster, note
4. Restart the app — the KB registry loads once at startup

**How to add a new KB entry:**
1. Find the field's row `id` in the relevant form YAML (see `docs/field-key-reference.md`)
2. Add an entry to the matching KB YAML with that key
3. Restart the app

The KB covers objective **special tests** for cervical, lumbar, shoulder, hip, knee,
and ankle. Adding KB entries for muscle tests, neurological fields, or subjective
fields is straightforward — see `docs/field-key-reference.md` for all available keys.

---

## AD position-ordered forms (gpab only, 2026-10-22)

**Files:** `objective/ad_forms/ad_lx_sij.yaml` (+ `ad_forms/__init__.py`)

A form arranged by patient position (Standing → Sitting → Supine → …) instead of by test type.
Each cell either **links** to an existing field (`<section>.<field_id>` or
`<region>.<active|passive|muscle|special>.<field_id>` — the form edits that real field, nothing
is stored twice) or is an **AD-only** field saved under `_objective.json`'s `ad_lx_sij` key. The
same spec drives gpab's GTK tab (`assessment_gtk/.../objective/sections/ad_form.py`) and
`storage.py`'s "10 AD Lx/SIJ" report section (both renderers), so layout and report can't drift.
The TUI does not read it. Quote `"Yes"`/`"No"` option labels — unquoted they parse as booleans.

---

## Layer 3 — Reference Documents (human-readable clinical spec, not read by app)

**Files:** `regions/cervical_physical_examination.md`,
           `regions/lumbar_physical_examination.md`

These are clinical documentation — the full physical examination spec including
tests, normal values, Sn/Sp, and clinical patterns. The app does **not** read
these files. They exist as the authoritative clinical reference behind the app
design and as a source for KB content when writing or updating KB YAML entries.

You can edit them freely.

---

## Data Flow (end-to-end)

```
Form driver YAML
      │ read once at startup
      ▼
Python section renders widgets (each widget gets an id)
      │ user interacts
      ▼
FieldChanged message → 2s debounce → collect() → storage.py
      │ atomic write
      ▼
~/Physio-Bodychart/<session>/_objective.json   (objective)
~/Physio-Bodychart/<session>/_assessment.json  (subjective)

KB YAML
      │ read once at startup → KBRegistry (dict in memory)
      ▼
on_descendant_focus → resolve(region, widget_id) → KBPanel.update()
```

---

## Adding a New Region

Currently implemented regions: cervical, lumbar, shoulder, hip, knee, ankle.

To add another region:

1. Create `objective/sections/yaml/{region}.yaml` — define `active_movement` and
   `special_tests` sections. Omit `muscle_testing` if using a Python extra table (preferred).
2. Create `objective/kb/{region}.yaml` — add KB entries for the special tests; keys must
   exactly match the row `id` values in the YAML (without `_l`/`_r` suffix).
3. Add `("{region}", "Label")` to `_ALL_REGIONS` in `objective_view.py`.
4. If the region needs passive OP or muscle tables, create `sections/{region}_tables.py`
   (see `hip_tables.py`, `knee_tables.py`, `ankle_tables.py` as templates) and add entries
   to `REGION_EXTRAS` in `region_section.py`.
5. Add storage rendering blocks to `_render_objective_md` and `_render_objective_raw`
   in `storage.py`.
6. Add field IDs to `docs/field-key-reference.md` and entries to `search.py`.

**ID prefix convention:** all field IDs must be prefixed with a region-unique 2–3 char code
(e.g. `hp_`, `kn_`, `ak_`) to prevent key collisions in the merged `spl` dict in storage.py.

---

## Separation of Concerns — enforced rules

| Layer | Location | Contains | Must NOT contain |
|---|---|---|---|
| Form structure | `sections/yaml/*.yaml` | Field IDs, labels, options | Clinical logic, storage |
| KB content | `kb/*.yaml` | Test descriptions, Sn/Sp | UI code, storage calls |
| Rendering | Python section files | Widget composition, CSS | Storage I/O, clinical decisions |
| Persistence | `storage.py` | JSON read/write | Textual imports, clinical logic |
| Search index | `search.py` | Static field tables | UI state, storage |
