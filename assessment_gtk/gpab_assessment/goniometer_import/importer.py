"""Reads .gonio.json goniometer exports for a patient (dropped by the GSConnect
router into ~/PAB/_inbox/goniometer/<code>/) and applies confirmed field values
into the open session's _objective.json.

Read-modify-write only touches the exact (region, section, field) triples
being written — save_objective() itself shallow-merges at the top level, so
constructing anything less than the full existing region dict would silently
delete every other field already recorded for that region (active, muscle,
special sections, other passive fields, notes). See matcher.py's docstring
for the field-selection rationale.

GTK port note (2026-08-23): everything through archive_imported_file is
identical to the reference pab_assessment/goniometer_import/importer.py
except the import of `storage` (`from .. import storage` -> `pab_path_bootstrap`
+ `from pab_assessment import storage`, this port's standard pattern for
reaching the reference package — see sections/diagnosis.py's cal_cp_model
import for the same shape). INBOX_ROOT, the read-modify-write logic, and
archive handling are unchanged.

available_patient_codes() (below) is NEW, added the same day per direct
user feedback: the reference TUI's action_import_gonio has no fallback at
all when the open session's own patient_id has no exact-match inbox
folder — a typo'd or mismatched code is a silent dead end there. This port
adds one: app.py's _open_gonio_import tries the exact patient_id first
(unchanged behaviour), and only when that finds nothing does it call this
function to offer whatever codes DO have data waiting, rather than a flat
"no data" message with no way forward.

CALLER MUST, in this order (see app.py's _open_gonio_import): flush any
pending debounced objective save BEFORE calling apply_grouped_values (an
already-armed debounce firing after this writes would silently overwrite the
freshly-imported values with stale in-memory ones), then archive the source
file(s), then reload the whole objective view from disk (this writes
straight to _objective.json, behind whatever's currently in the live widget
tree) — mirrors tui.py's action_import_gonio exactly.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .. import pab_path_bootstrap  # noqa: F401  (sys.path side effect)
from pab_assessment import storage  # noqa: E402
from .matcher import GroupedValue, Measurement

INBOX_ROOT = Path.home() / "PAB" / "_inbox" / "goniometer"


class GonioExportError(Exception):
    """A goniometer export file could not be read (truncated .gonio.zip,
    missing manifest.json, malformed JSON, …). Raised only by
    load_gonio_export() — the raw loaders raise their natural exceptions.
    _run_gonio_import_for catches this and skips the file with a status
    message rather than letting it escape into the GTK key handler."""

# Both export shapes live side by side in an inbox folder: the old flat
# ``<code>_<date>.gonio.json`` and the new ``<session>.gonio.zip`` bundle
# (manifest.json + session.json + charts/). Every discovery glob below counts
# and lists both.
_GONIO_PATTERNS = ("*.gonio.json", "*.gonio.zip")


def _gonio_files(d: Path) -> list[Path]:
    """Every goniometer export file (either shape) directly in *d*, unsorted."""
    out: list[Path] = []
    for pat in _GONIO_PATTERNS:
        out.extend(d.glob(pat))
    return out


def _opt_float(v) -> float | None:
    return None if v is None else float(v)


@dataclass
class InboxPatientSummary:
    code: str
    pending: int   # not-yet-imported .gonio.json count
    imported: int  # already-imported .gonio.json count (available to re-apply)


def available_patient_codes() -> list[InboxPatientSummary]:
    """Every patient code with ANY goniometer data waiting under INBOX_ROOT —
    pending or already-imported — sorted by code. Used only as a fallback
    when the open session's own patient_id has no exact match; see this
    module's own docstring."""
    if not INBOX_ROOT.exists():
        return []
    summaries: list[InboxPatientSummary] = []
    for d in sorted(INBOX_ROOT.iterdir()):
        if not d.is_dir():
            continue
        pending = len(_gonio_files(d))
        imported_dir = d / "_imported"
        imported = len(_gonio_files(imported_dir)) if imported_dir.exists() else 0
        if pending or imported:
            summaries.append(InboxPatientSummary(d.name, pending, imported))
    return summaries


def inbox_files_for(patient_code: str) -> list[Path]:
    """Every not-yet-imported goniometer export (.gonio.json or .gonio.zip)
    for this patient code, oldest first."""
    d = INBOX_ROOT / patient_code
    if not d.exists():
        return []
    return sorted(_gonio_files(d), key=lambda p: p.stat().st_mtime)


def imported_files_for(patient_code: str) -> list[Path]:
    """Already-applied .gonio.json for this patient code, most recent first —
    for re-opening after the fact to fix a mistake (wrong patient/movement/
    angle spotted after Apply). Re-applying is safe: it just overwrites the
    same field(s) again, per apply_grouped_values()'s read-modify-write."""
    d = INBOX_ROOT / patient_code / "_imported"
    if not d.exists():
        return []
    return sorted(_gonio_files(d), key=lambda p: p.stat().st_mtime, reverse=True)


def load_gonio_measurements(path: Path) -> tuple[str, list[Measurement]]:
    """Returns (patient_code, measurements) from one exported session file."""
    data = json.loads(path.read_text())
    measurements: list[Measurement] = []
    for i, m in enumerate(data.get("measurements", [])):
        label = m.get("label") or ""
        ranges = m.get("ranges", [])
        primary_idx = m.get("primary_channel_index", 0)
        primary = ranges[primary_idx] if 0 <= primary_idx < len(ranges) else 0.0
        rom_type = str(m.get("rom_type") or "AROM").upper()
        if rom_type not in ("AROM", "PROM"):
            rom_type = "AROM"  # missing on pre-toggle files, or anything unexpected
        measurements.append(Measurement(i, label, float(primary), rom_type))
    return data.get("patient_code", ""), measurements


def load_gonio_bundle(zip_path: Path) -> tuple[str, list[Measurement], Path]:
    """Returns (patient_code, measurements, zip_path) from one .gonio.zip
    export bundle. Reads manifest.json only — session.json and charts/ are
    left in the zip (charts are extracted later, at apply time; see
    GONIO_INTEGRATION_PLAN.md §B5).

    Kept SEPARATE from load_gonio_measurements() on purpose: that one still
    serves the flat ``_imported/*.gonio.json`` re-apply path. The manifest is
    already denormalised — primary_range_deg is ready, no ranges[] indexing —
    and it carries the min/max + marks_deg that format_measurement_value()
    needs for the richer field string. A schema-1 bundle simply has no
    marks_deg, so the formatter falls back to the range-only form.
    """
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))

    measurements: list[Measurement] = []
    for i, m in enumerate(manifest.get("measurements", [])):
        rom_type = str(m.get("rom_type") or "AROM").upper()
        if rom_type not in ("AROM", "PROM"):
            rom_type = "AROM"
        # marks_deg length is == mark_count in the manifest; a slot is null
        # only when a corrupt/hand-edited session pointed a mark outside its
        # sample stream. Drop nulls here — the formatter lists whatever real
        # angles remain, in capture order.
        marks_deg = [float(x) for x in (m.get("marks_deg") or []) if x is not None]
        measurements.append(Measurement(
            index=i,
            label=m.get("label") or "",
            primary_range_deg=float(m.get("primary_range_deg") or 0.0),
            rom_type=rom_type,
            min_deg=_opt_float(m.get("min_deg")),
            max_deg=_opt_float(m.get("max_deg")),
            deficit_to_full_deg=_opt_float(m.get("deficit_to_full_deg")),
            mark_count=int(m.get("mark_count") or 0),
            marks_deg=marks_deg,
            chart_png=m.get("chart_png"),
        ))
    return manifest.get("patient_code", ""), measurements, zip_path


def load_gonio_export(path: Path) -> tuple[str, list[Measurement]]:
    """Shape-agnostic front door: dispatches to load_gonio_bundle() for a
    ``.gonio.zip`` and load_gonio_measurements() for a flat ``.gonio.json``.
    Returns (patient_code, measurements) either way — callers that don't need
    the zip path (the wizard flow) use this.

    This is the SAFE boundary: any structural failure of either loader (bad
    zip, absent manifest.json, unparseable JSON, unreadable file) is
    re-raised as GonioExportError so _run_gonio_import_for can skip the file
    instead of crashing the Ctrl+G handler. The raw loaders stay strict.
    """
    try:
        if path.name.endswith(".gonio.zip"):
            code, measurements, _ = load_gonio_bundle(path)
            return code, measurements
        return load_gonio_measurements(path)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as e:
        # ValueError covers json.JSONDecodeError and a float()/int() cast on
        # a malformed field; KeyError covers ZipFile.read("manifest.json")
        # when the entry is absent.
        raise GonioExportError(f"{path.name}: {type(e).__name__}: {e}") from e


def apply_grouped_values(session_file: str, grouped: list[GroupedValue]) -> None:
    """Writes every GroupedValue into the session's _objective.json without
    disturbing any other field, section, or region already recorded there."""
    existing = storage.load_objective(session_file)
    assessment = existing.get("assessment", {})
    sections_complete = existing.get("sections_complete", {})

    active_regions = set(assessment.get("active_regions", []))
    touched_regions: dict[str, dict] = {}

    for g in grouped:
        region_data = touched_regions.setdefault(g.region, dict(assessment.get(g.region, {})))
        section_data = dict(region_data.get(g.section_key, {}))
        section_data[g.field_id] = g.joined_value
        region_data[g.section_key] = section_data
        active_regions.add(g.region)

    payload: dict = dict(touched_regions)
    payload["active_regions"] = list(active_regions)

    storage.save_objective(session_file, payload, sections_complete)


def archive_imported_file(path: Path) -> None:
    """Moves a fully-applied .gonio.json into an _imported/ subfolder so it's
    never offered as *new* work again, without deleting the original data.
    No-ops if it's already archived (re-applying a file from imported_files_for
    would otherwise try to nest it into _imported/_imported/)."""
    if path.parent.name == "_imported":
        return
    archive_dir = path.parent / "_imported"
    archive_dir.mkdir(exist_ok=True)
    path.rename(archive_dir / path.name)
