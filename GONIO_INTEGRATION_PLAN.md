# Goniometer → gpab integration plan

Drafted 2026-09-07. Status: **plan only, nothing implemented.** All work
described here targets `dev` / `gpabd` (see Guardrails at the bottom), plus
one change on the `goniometer` repo (Part 0).

**The 3 open decisions are now settled** (2026-09-07, by the user):

1. **AROM/PROM value format** — detailed range first, then each mark point,
   `;`-separated: `110 (-8->102) ; 43 ; 98`. No degree symbol. Repeats of the
   same field still `" // "`-joined between measurements. This needs mark
   angle values in the manifest — see **Part 0**.
2. **Lateral views** — **keep them.** Charts float over the Objective canvas;
   the lateral SVG stays one tap away behind the per-slot toggle (§D5).
3. **Chart count** — 3–4 per session is typical, never 8–10 ("only formally
   measure key findings after initial screens"). No paging / hidden-charts
   list needed; §D stays simple.

## Goal

Two separate integrations of the on-phone goniometer app's export bundle
(`<session>.gonio.zip`) into gpab:

1. **Visual** — put each measurement's rendered chart PNG (full graph, with
   marks and numbers, exactly as the phone renders it) onto the **Objective
   bodychart**, occupying the space currently used by the two lateral views,
   as free-floating image objects the user can drag and scale so they're
   readable.
2. **Data** — feed the key numbers of each measurement into the **AROM / PROM
   fields of the Objective regional tables**, with slightly more detail than
   the bare degree value written today.

## What already exists (do not rebuild)

### The data pipeline is ~80% built

`assessment_gtk/gpab_assessment/goniometer_import/` is a working port of the
TUI's goniometer importer, wired to **Ctrl+G** in `app.py`
(`_open_gonio_import` → `_run_gonio_import_for`):

| File | Role |
|---|---|
| `importer.py` | `INBOX_ROOT = ~/PAB/_inbox/goniometer/<code>/`; `load_gonio_measurements()`, `apply_grouped_values()` (read-modify-write into `_objective.json` `assessment[region][section_key][field_id]`), `archive_imported_file()` → `_imported/` |
| `matcher.py` | label → ROM field matching, side inference, `group_resolved()` → `GroupedValue(joined_value=" // ".join(...))` |
| `field_dictionary_active.py` | `SECTION_KEY = "active"`, field ids `{prefix}_ax_{side}_range` — extracted from `objective/sections/yaml/<region>.yaml`, not guessed |
| `field_dictionary_passive.py` | `SECTION_KEY = "passive"`, field ids `{prefix}_{side}_txt` |
| `rom_field.py` | `RomField` dataclass, `field_id(side)` |
| `wizard_screen.py` | review/confirm UI, calls `_finish(grouped)` |

**AROM vs PROM** is per-measurement, driven by `Measurement.rom_type`
(the phone's explicit top-row toggle → `manifest.measurements[].rom_type`
`"AROM"`/`"PROM"`), matched against the active vs passive dictionary
independently. This already works.

**Value written today** (`wizard_screen.py:361`, `matcher.group_resolved`):
`joined_value = " // ".join(str(round(primary_range_deg)) ...)` — e.g. a
single capture writes `"110"`, three repeats write `"120 // 130 // 135"`.
Bare integers, no unit, no direction. This is the string §Data below enriches.

### The GSConnect router already exists

- `~/.local/bin/gsconnect-goniometer-router.sh` — `inotifywait` on
  `~/GSConnectInbox`, moves `*.gonio.json` → `~/PAB/_inbox/goniometer/<code>/`
  (`code = filename up to first "_"`).
- `~/.config/systemd/user/gsconnect-goniometer-router.service` — runs it,
  `Restart=on-failure`.

It does **not** handle `.gonio.zip` yet — see §Router below.

## The format gap

| | Old `.gonio.json` (importer reads this today) | New `.gonio.zip` (phone emits this now) |
|---|---|---|
| Container | flat JSON file | zip: `manifest.json` + `session.json` + `charts/NN_<slug>_<AROM\|PROM>.png` |
| Per-measurement range | `measurements[].ranges[primary_channel_index]` (computed) | `manifest.measurements[].primary_range_deg` (denormalised, ready) |
| rom_type | `measurements[].rom_type` (may be absent on pre-toggle files) | `manifest.measurements[].rom_type` (always present) |
| Direction of motion | not available | `min_deg`/`min_t_ms` + `max_deg`/`max_t_ms` |
| Extra | `samples[]` raw IMU stream | `deficit_to_full_deg`, `total_angular_sweep_deg`, `mark_count`, `sample_count`, `duration_ms`, `chart_png` |
| Match key | `patient_code` + `created_ms` | same (`manifest.patient_code` + `manifest.created_ms`) |
| Chart image | none | one PNG per measurement, 1600×900, marks + numbers baked in |

Real samples on disk to preserve compatibility with:
`~/PAB/_inbox/goniometer/MH/_imported/{XX_17_08_2026_2143,MH_18_08_2026_1532}.gonio.json`
(offered for re-apply by `imported_files_for()`), and the new
`~/GSConnectInbox/TEST_07_09_2026_1112.gonio.zip`.

---

## Part 0 — Goniometer app: mark angles in the manifest  (repo: `goniometer`)

Decision 1's format needs the primary-channel angle **at each mark**, in
capture order. The manifest emits only `mark_count` today
(`BundleExporter.kt:128`); `Mark` is `(tMs, sampleIndex)` and
`ChartRenderer.kt:159` already computes the angle at each mark to draw them.

**Change** (`app/src/main/java/com/lancehouse/goniometer/BundleExporter.kt`,
`measurementJson`):

```kotlin
put("mark_count", r.marks.size)
put("marks_deg", JSONArray(r.marks.map { mk ->
    round1(r.samples[mk.sampleIndex].channel(r.primaryChannelIndex))
}))   // primary-channel angle at each mark, capture order
```

(use whatever the existing per-channel accessor is — `channelPeak` /
`Sample` already expose it; `ChartRenderer` line ~159 shows the exact call.)

- Guard `mk.sampleIndex` against `-1` / out-of-range (a mark pressed before
  the first sample — `SessionState.kt:118` already notes this case): skip or
  clamp, don't crash the export.
- **Bump `BUNDLE_SCHEMA` 1 → 2.** Update the schema comment block at the top
  of `BundleExporter.kt`. `bundle_schema` is already in the manifest so the
  gpab importer can branch on it; `marks_deg` absent + `bundle_schema == 1`
  → old bundle, fall back to range-only (see §C).
- Update the goniometer repo's own memory note
  (`goniometer-chart-export.md`) and commit on `main` (that repo is
  single-branch, local-only).
- The `TEST_07_09_2026_1112.gonio.zip` sample already on disk is schema 1 —
  keep it as the back-compat test fixture; capture a fresh schema-2 bundle
  once the phone app is rebuilt.

This is the only goniometer-side change. Everything else is gpab.

---

## Part A — Router: accept `.gonio.zip`

**File:** `~/.local/bin/gsconnect-goniometer-router.sh` (outside both repos —
note in commit message that this script changed).

Add a `*.gonio.zip)` case alongside the existing `*.gonio.json)`:

1. Read `patient_code` from the zip's `manifest.json`
   (`unzip -p "$src" manifest.json | jq -r .patient_code`) rather than
   parsing the filename — the filename prefix is the *session* name, which
   starts with the code today but that's incidental.
2. `mkdir -p "$DEST_ROOT/$code"` and `mv -n "$src" "$DEST_ROOT/$code/"` —
   move the **zip intact**, don't unpack in the router. Keeping it a single
   atomic file matches how the importer archives to `_imported/` and avoids a
   half-written chart set ever being visible.
3. `logger -t` line as today.

Dependency: `jq` (already used elsewhere on this machine — confirm with
`command -v jq` before relying on it; fall back to a tiny Python one-liner if
absent). `unzip` is already a dependency of nothing here — check
`command -v unzip`, else use `bsdtar`/`python3 -m zipfile`.

No systemd unit change needed.

---

## Part B — Importer: read the zip / manifest

**Files:** `assessment_gtk/gpab_assessment/goniometer_import/importer.py`,
`matcher.py`. All on `dev`. Keep the reference copy
`assessment/pab_assessment/goniometer_import/` untouched (read-only).

### B1. `Measurement` gains defaulted fields (`matcher.py`)

```python
@dataclass
class Measurement:
    index: int
    label: str
    primary_range_deg: float
    rom_type: str = "AROM"
    # new — all defaulted so old flat-format files still construct:
    min_deg: float | None = None
    max_deg: float | None = None
    deficit_to_full_deg: float | None = None
    mark_count: int = 0
    marks_deg: list[float] = dataclass_field(default_factory=list)  # manifest schema 2+
    chart_png: str | None = None   # zip-relative path from manifest, or None
```

Nothing in `match_batch` / `group_resolved` changes except the value string
(§C). Backwards compat: measurements loaded from `.gonio.json` leave the new
fields at their defaults and everything downstream still works.

### B2. New loader for the manifest shape (`importer.py`)

Add `load_gonio_bundle(zip_path: Path) -> tuple[str, list[Measurement], Path]`
**next to** `load_gonio_measurements` (don't rewrite the old one — the
`_imported/*.gonio.json` re-apply path still calls it):

- `zipfile.ZipFile(zip_path)` → read `manifest.json`.
- For each `manifest["measurements"]`: construct `Measurement` straight from
  the denormalised fields (`primary_range_deg` is ready — no `ranges[]`
  indexing), carrying `min_deg`/`max_deg`/`deficit_to_full_deg`/`mark_count`/
  `marks_deg` (default `[]` if absent — schema-1 bundle)/`chart_png`.
- Return `(manifest["patient_code"], measurements, zip_path)`.

### B3. Glob sites accept both extensions

`available_patient_codes`, `inbox_files_for`, `imported_files_for` currently
`glob("*.gonio.json")`. Change to `glob("*.gonio.*")` filtered to
`{.json, .zip}`, or two globs merged. `InboxPatientSummary.pending/imported`
counts then include zips.

### B4. `archive_imported_file` — keep the zip, keep the charts

The zip moves into `_imported/` intact as today (the move already works for
any filename). **But** the charts the user placed on the bodychart must
survive that move — see B5: charts are copied into the *session* dir at apply
time, not referenced from the inbox, so archiving the source zip doesn't
orphan them. Verify this explicitly in a test.

### B5. Extract charts into the session dir at apply time

In `app.py`'s `_run_gonio_import_for` (or a helper in `importer.py`), after
the wizard returns `grouped` and **before** `apply_grouped_values`:

- Destination: `~/PAB/<session_name>/gonio_charts/`  (NOT the session root —
  `bodychart/src/session.c`'s `session_build_path` writes `subj.png`,
  `obj.png`, `combined.png`, `obj_focus.png` etc. to the session root; a
  dedicated subdir can't collide).
- For every measurement that (a) resolved to a field in `grouped` and (b) has
  `chart_png`, extract that entry from the zip to
  `gonio_charts/<NN>_<slug>_<AROM|PROM>.png` (reuse the zip's own basename).
- Overwrite on re-apply (same as the field write — re-applying is already
  defined as safe/idempotent).
- Leave a breadcrumb the C side can read without parsing the zip: the PNG
  filenames in that dir ARE the manifest (NN, slug, AROM/PROM all in the
  name). No sidecar JSON needed.

### B6. Caller ordering (unchanged, restated because it's load-bearing)

Per `importer.py`'s docstring and `tui.py`'s `action_import_gonio`:
flush pending debounced `_objective.json` save → `apply_grouped_values` →
extract charts (B5) → `archive_imported_file` → reload the whole objective
view from disk.

---

## Part C — Enrich the AROM / PROM field value  ✅ FORMAT SETTLED

**Constraint:** this string is stored in `_objective.json` and flows through
`storage.py` into **generated clinical reports**, so it must read cleanly.
Repeats of the same field are `" // "`-joined between measurements.

**Format (user, 2026-09-07):** detailed range first, then each mark point,
`" ; "`-separated:

```
per measurement:
    "<rng> (<lo>-><hi>) ; <m1> ; <m2> ; ..."   when marks_deg present
    "<rng> (<lo>-><hi>)"                        when min/max present, no marks
    "<rng>"                                     fallback: schema-1 bundle or
                                                old .gonio.json (no min/max)

rng = round(primary_range_deg)
lo  = round(min_deg),  hi = round(max_deg)      (signed; may be negative)
mN  = round(marks_deg[N])  in capture order
```

No degree symbol. `->` is literal ASCII (user wrote it that way — swap to
`→` only if the user later prefers it).

Examples:
- lumbar flexion, range 110, swept −8→102, marks at 43 and 98
  →  `110 (-8->102) ; 43 ; 98`
- lumbar extension, range 37, swept −37→0, no marks
  →  `37 (-37->0)`
- two flexion repeats (2 marks each)
  →  `110 (-8->102) ; 43 ; 98 // 115 (-2->106) ; 45 ; 99`
- re-applied old `.gonio.json` (no min/max, no marks)
  →  `110`   (unchanged from today's behaviour)

**Do not** include `total_angular_sweep_deg`, `deficit_to_full_deg`,
`duration_ms`, `sample_count`, `app_version`.

Implementation point: the value is built in **two** places that must stay in
sync — `matcher.group_resolved` (builds `values = [...]` then
`" // ".join(values)`, ~line 205) and `wizard_screen._apply`'s override
branch (`joined_value=str(round(...))`, ~line 361). Factor a single
`format_measurement_value(m: Measurement) -> str` helper and call it from
both. The wizard's *preview* label (`wizard_screen.py:256`, currently
`f"{round(primary_range_deg)}°"`) should call the same helper so the preview
matches what gets written.

---

## Part D — Charts on the Objective bodychart  ✅ UI CHOICES SETTLED

**Files:** `bodychart/src/canvas.c`, `obj_chart.c/.h`, `persistence.c`,
`meson.build`. All on `dev`; build with `ninja -C bodychart/build`.

### D1. Ownership handshake (this is the part most likely to be fudged)

`bodychart/CLAUDE.md` is absolute: **bodychart writes `_session.json` only,
never `_objective.json`.** The import runs in Python. Clean split:

- **Python** (Part B5) extracts the PNGs into `~/PAB/<session>/gonio_charts/`.
  That's all Python does for the visual side.
- **C / bodychart** discovers charts by globbing `gonio_charts/*.png`, and
  writes **placement only** into `_session.json` under a new
  `objective.gonio_charts[]` array. No chart metadata crosses through
  `_objective.json`; neither app writes the other's file.

`_session.json` schema addition (`objective` block, alongside
`zones`/`points`/`ticks`):

```json
"gonio_charts": [
  { "file": "01_lumbar-flexion_AROM.png",
    "bx": 300.0, "by": 40.0, "scale": 1.0, "visible": true }
]
```

`bx`/`by` in body-space, same convention as `legend_bx/by` and
`obj_point.anchor.lx/ly`; all fields defaulted on absence
(`jd(obj, "bx", <col-4 default>)`), so an old session with no `gonio_charts`
key just shows nothing. Persistence follows the existing
`obj_points_to_json` / load pattern in `persistence.c` (lines ~181, ~766).

### D2. Discovery / sync

One process, two windows — no file watcher, no IPC. Rescan
`gonio_charts/*.png` **on session load and on entering Objective mode**:

- new PNG in the dir with no matching `gonio_charts[]` entry → create one at
  the default position (stacked down the right column, small offset each so
  they don't fully overlap).
- `gonio_charts[]` entry whose file no longer exists → drop it.
- existing entry keeps its saved `bx/by/scale/visible`.

### D3. Rendering — use the PNG verbatim

The PNG already has the marks and the numbers drawn in by the phone's
`ChartRenderer`. Do **not** re-render in Cairo from `session.json`.

- Load with `cairo_image_surface_create_from_png(path)` — cairo is already a
  dependency; this avoids declaring a new `gdk-pixbuf` dep. Cache the
  surface per file (invalidate if mtime changes).
- Draw in the Objective canvas draw pass, after the SVG/outline layer and
  after zones, before or after points (probably after, so a chart dragged
  over the body doesn't hide a PPT marker — TBD, cheap to change).
- `cairo_translate(bx,by) ; cairo_scale(s,s) ; cairo_set_source_surface ;
  paint`. Respect the panel's own zoom/pan transform so a chart pans with the
  body like everything else.

### D4. Interaction — reuse existing gesture plumbing

The canvas already drags notes (`note_drag_idx`), the legend
(`legend_drag_active`), and objective point anchors (`obj_point_drag_idx`).
Add `gonio_chart_drag_idx` following the same pattern:

- hit-test: pointer inside a chart's drawn rect (in body-space) and no
  higher-priority object grabbed the press.
- drag → update `bx/by`, `queue_draw`, mark session dirty (debounced save,
  same as note drags).
- **scale** instead of resize handles: two-finger pinch on a chart (the
  canvas already has `GtkGestureZoom` wired for panel zoom — scope it to the
  chart when the gesture starts over one), or `Ctrl`+scroll-wheel over a
  chart, or +/- keys while a chart is "active". Pinch is the most natural on
  the Yoga touchscreen. Per-chart `scale` in `_session.json`.
- a small close/hide affordance (corner ✕) toggles `visible:false` rather
  than deleting — re-entering Objective mode brings hidden ones back only if
  the user asks. With 3–4 charts typical (§D6) no "show N hidden" chip is
  needed; a hidden chart just isn't drawn.

### D5. "In place of the lateral views" — SETTLED: keep the lateral views

The lateral views stay. The two right-column quad slots (`g_col[2]`,
`g_col[3]`, `app->right_slot_views`) are already cyclable views — add one
more per-slot mode that collapses the slot to a plain backdrop the floating
charts sit over. **Default that mode to "charts" once a session has any
`gonio_charts[]`**, else the lateral SVG as today. The lateral view is always
one tap away on the slot's existing view-cycle control; nothing is removed.

The charts themselves **float free** over the whole Objective canvas — not
pinned into the grid cell — so they can be dragged over the anterior/
posterior panels and scaled up to be readable (a 1600×900 chart in the
untouched col-4 cell renders ~200×110 px on the Yoga, which is why
fixed-slot placement was rejected).

### D6. Chart count — SETTLED: 3–4 typical, never 8–10

User only formally measures key findings after the initial screen, so a
session carries roughly 3–4 charts. The free-floating model in D2/D4 is
comfortable at that count with no paging, no scrollable list, no
"hidden charts" chip. Don't build those.

---

## Suggested implementation order

0. **Part 0** (goniometer: `marks_deg` in manifest, schema 1→2). Repo:
   `goniometer`, branch `main`. Rebuild the phone app, capture one fresh
   schema-2 bundle to test with. Keeps the schema-1 `TEST` zip as the
   back-compat fixture.
1. **Part A** (router `.gonio.zip`) — smallest, unblocks real bundles landing
   in the inbox. Test: SEND from phone → zip appears in
   `~/PAB/_inbox/goniometer/<code>/`.
2. **Part B1–B4** (importer reads manifest) + **Part C** (value format) —
   the data half end-to-end. Test: Ctrl+G on a session whose `patient_id`
   matches, wizard shows measurements, Apply writes
   `110 (-8->102) ; 43 ; 98` into the right `active`/`passive` field,
   `_objective.json` round-trips, other fields untouched. Re-test the old
   `.gonio.json` re-apply path still writes plain `110`.
3. **Part B5** (extract charts to `gonio_charts/`) — bridge to the visual
   half. Test: after an import, PNGs are in `~/PAB/<session>/gonio_charts/`
   and survive `archive_imported_file` moving the zip to `_imported/`.
4. **Part D** (bodychart charts) — biggest, most iteration expected on
   readability/placement. Do D1–D3 first (charts appear, correct, persist
   position across reload), then D4 (drag + scale), then D5 (right-slot
   "charts" mode + default).

Parts 0–C are independently useful even if D slips.

---

## Guardrails (from `CLAUDE.md` — non-negotiable)

- **All work on `dev`, tested via `gpabd`.** Never commit/merge/build in
  `gpab-stable/` or on `main` without the user saying "merge to main" /
  "promote to stable" in that same message. Finishing a feature is not
  permission.
- Build bodychart with `ninja -C bodychart/build` only — **never**
  `ninja install` / `meson install` from this clone.
- New `.c` files → add to `bodychart/meson.build`, then
  `meson setup --reconfigure build`.
- Any new bodychart-owned window/dialog needs the `.bodychart-app` CSS
  scoping class (unscoped bare-tag selectors bled into gpab's widgets once
  the two apps shared a `GdkDisplay` — already-fixed bug, don't reintroduce).
- Never write `~/Projects/pab` (unconditional) or `~/Projects/kb`.
- `assessment/` and the reference `assessment/pab_assessment/goniometer_import/`
  are read-only reference copies — port changes into `assessment_gtk/`, not
  there.
- Session writes stay atomic (inherited from `storage.py` /
  `persistence.c`); separate debounced timers for `_assessment.json` vs
  `_objective.json` vs `_session.json`.
- Both repos (`goniometer`, `gpab`) are **remote-less** — back up the
  directories to external storage before the PC reset.

## Decisions — all settled (2026-09-07)

1. **AROM/PROM value format** (§C) — `110 (-8->102) ; 43 ; 98` (detailed
   range, then each mark point, `;`-separated). No degree symbol. Repeats
   still `" // "`-joined.
2. **Lateral views** (§D5) — kept. Charts float over the canvas; a right-slot
   "charts" mode defaults on once a session has charts, lateral view one tap
   away.
3. **Chart count** (§D6) — 3–4 typical, never 8–10. No paging / hidden-list
   UI.

Nothing is blocked on further input — this plan is ready to implement in a
fresh session, Part 0 first.
