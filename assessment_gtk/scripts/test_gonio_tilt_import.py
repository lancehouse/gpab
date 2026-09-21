#!/usr/bin/env python3
"""Exercises the goniometer-import pipeline end to end against a SYNTHETIC
.gonio.zip bundle carrying both a TILT measurement and a MOTION measurement,
to verify TILT integrates into gpab exactly the way MOTION already does
(matcher.Measurement, matcher.format_measurement_value,
importer.load_gonio_bundle, importer.apply_grouped_values,
importer.extract_charts) — added 2026-09-18 while wiring up TILT-mode gpab
support, since there was no real patient data to test the new code path
against.

SAFETY: every path this script touches carries the patient code "TESTGONIO",
which cannot collide with a real patient code — it never reads or writes
anything under a real patient's directory. Everything it creates is printed
at the end so it's trivial to inspect or delete:
  ~/PAB/_inbox/goniometer/TESTGONIO/synthetic.gonio.zip   (input, synthetic)
  ~/PAB/_inbox/goniometer/TESTGONIO/_imported/...          (after archiving)
  ~/PAB/TESTGONIO_test_session/TESTGONIO_test_session_objective.json  (output)
  ~/PAB/TESTGONIO_test_session/gonio_charts/*.png           (extracted charts)

Run from assessment_gtk/: .venv/bin/python scripts/test_gonio_tilt_import.py
No GTK/display needed — this exercises importer.py + matcher.py +
pab_assessment.storage directly, the same calls app.py's
_run_gonio_import_for makes, without the wizard UI in between.
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # this app's own package root

from gpab_assessment import pab_path_bootstrap  # noqa: F401  (sys.path side effect for pab_assessment)
from pab_assessment import storage  # noqa: E402

from gpab_assessment.goniometer_import import importer as gonio_importer  # noqa: E402
from gpab_assessment.goniometer_import.matcher import format_measurement_value, group_resolved, match_batch  # noqa: E402

PATIENT_CODE = "TESTGONIO"
INBOX_DIR = gonio_importer.INBOX_ROOT / PATIENT_CODE
SESSION_DIR = Path.home() / "PAB" / f"{PATIENT_CODE}_test_session"
SESSION_FILE = str(SESSION_DIR / f"{PATIENT_CODE}_test_session_session.json")

# Minimal valid 1x1 black PNG — stands in for a rendered chart; nothing reads its pixels.
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415478da6360606060000000050001a5f6454000000049454e44ae426082"
)


def build_synthetic_manifest() -> dict:
    """One TILT measurement (shoulder flexion R, AROM — the new code path)
    plus one MOTION measurement (knee flexion L, PROM — the existing path,
    included so a mixed batch, which is the realistic clinic case, is what
    actually gets exercised) — bundle_schema 5, matching the phone app's
    current BundleExporter.kt exactly."""
    return {
        "bundle_schema": 5,
        "session_name": f"{PATIENT_CODE}_test",
        "patient_code": PATIENT_CODE,
        "created_ms": 1_758_000_000_000,
        "created_iso": "2026-09-18T00:00:00Z",
        "app_version": "test (0)",
        "measurements": [
            {
                "index": 1,
                "label": "Right shoulder flexion",
                "rom_type": "AROM",
                "mode": "TILT",
                "chart_png": "charts/01_right-shoulder-flexion_AROM.png",
                "absolute_peak_deg": 150.0,
                "absolute_peak_user_selected": True,
                "absolute_start_deg": 180.0,
                "reading_count": 3,
                "absolute_readings_deg": [180.0, 165.0, 150.0],
            },
            {
                "index": 2,
                "label": "Left knee flexion",
                "rom_type": "PROM",
                "mode": "MOTION",
                "chart_png": "charts/02_left-knee-flexion_PROM.png",
                "primary_channel": 1,
                "primary_channel_label": "Range B",
                "primary_range_deg": 135.0,
                "deficit_to_full_deg": 45.0,
                "secondary_ranges_deg": [4.0, 2.0],
                "min_deg": -2.0,
                "min_t_ms": 0,
                "max_deg": 133.0,
                "max_t_ms": 1800,
                "total_angular_sweep_deg": 135.0,
                "mark_count": 1,
                "marks_deg": [128.0],
                "sample_count": 90,
                "duration_ms": 1800,
            },
        ],
    }


def write_synthetic_bundle(manifest: dict) -> Path:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = INBOX_DIR / "synthetic.gonio.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for m in manifest["measurements"]:
            zf.writestr(m["chart_png"], _TINY_PNG)
    return zip_path


def main() -> None:
    print(f"1. Building synthetic bundle under {INBOX_DIR} ...")
    zip_path = write_synthetic_bundle(build_synthetic_manifest())
    print(f"   wrote {zip_path}")

    print("\n2. load_gonio_export() — same call app.py's _run_gonio_import_for makes:")
    patient_code, measurements = gonio_importer.load_gonio_export(zip_path)
    assert patient_code == PATIENT_CODE, patient_code
    for m in measurements:
        print(f"   [{m.index}] mode={m.mode} rom_type={m.rom_type} label={m.label!r}")
        if m.mode == "TILT":
            print(f"       absolute_peak_deg={m.absolute_peak_deg} user_selected={m.absolute_peak_user_selected}"
                  f" start={m.absolute_start_deg} readings={m.absolute_readings_deg}")
        else:
            print(f"       primary_range_deg={m.primary_range_deg} min={m.min_deg} max={m.max_deg} marks={m.marks_deg}")

    print("\n3. match_batch() — field/side resolution (label + rom_type only, mode-agnostic):")
    results = match_batch(measurements)
    for r in results:
        field_desc = f"{r.field.region} {r.field.movement}" if r.field else "NO MATCH"
        print(f"   [{r.measurement.index}] -> {field_desc} side={r.side} status={r.status}")
        assert r.resolved, f"measurement {r.measurement.index} ({r.measurement.label!r}) did not resolve — fix the test's field labels"

    print("\n4. format_measurement_value() — what actually gets written per measurement:")
    for r in results:
        print(f"   [{r.measurement.index}] mode={r.measurement.mode}: {format_measurement_value(r.measurement)!r}")

    print("\n5. group_resolved() — grouped writes:")
    grouped = group_resolved(results)
    for g in grouped:
        print(f"   {g.field_id} ({g.display_label}): {g.joined_value!r}")

    print(f"\n6. apply_grouped_values() into a throwaway session at {SESSION_FILE} ...")
    if SESSION_DIR.exists():
        shutil.rmtree(SESSION_DIR)  # start clean — this dir only ever holds this test's own output
    gonio_importer.apply_grouped_values(SESSION_FILE, grouped)
    written = storage.load_objective(SESSION_FILE).get("assessment", {})
    print(f"   wrote {storage.objective_path(SESSION_FILE)}")
    for g in grouped:
        region_data = written.get(g.region, {})
        section_data = region_data.get(g.section_key, {})
        actual = section_data.get(g.field_id)
        print(f"   read back {g.region}.{g.section_key}.{g.field_id} = {actual!r}"
              f"  (expected {g.joined_value!r})  {'OK' if actual == g.joined_value else 'MISMATCH'}")

    print("\n7. extract_charts() — chart PNGs for every resolved measurement:")
    chart_sources = {r.measurement.index: (zip_path, r.measurement.chart_png) for r in results}
    keep_indices = {i for g in grouped for i in g.source_indices}
    written_charts = gonio_importer.extract_charts(SESSION_FILE, chart_sources, keep_indices)
    for name in written_charts:
        print(f"   extracted {SESSION_DIR / 'gonio_charts' / name}")

    print("\n8. archive_imported_file() — moves the synthetic bundle into _imported/:")
    gonio_importer.archive_imported_file(zip_path)
    print(f"   {INBOX_DIR / '_imported' / zip_path.name}")

    print("\nAll steps completed. Files created by this run (safe to delete, all TESTGONIO-scoped):")
    print(f"  {INBOX_DIR}")
    print(f"  {SESSION_DIR}")


if __name__ == "__main__":
    main()
