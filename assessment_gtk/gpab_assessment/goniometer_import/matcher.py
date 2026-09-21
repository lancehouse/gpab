"""Matches goniometer measurement labels ("Left shoulder flexion") to pab ROM
fields, infers an omitted side from earlier measurements of the same movement
in the same batch, and groups repeats of the same field into pab's own
" // "-joined findings convention.

Deliberately conservative: nothing is written anywhere until match_batch()'s
results have been confirmed (by the wizard, or accepted outright when every
item resolved unambiguously). A field/side that can't be determined is left
unresolved rather than guessed — see field_dictionary_active.py's docstring
for why only ROM (not strength/accessory/PAIVM) fields are even candidates.

AROM vs PROM is per-measurement, driven by Measurement.rom_type — set by the
phone app's explicit top-row toggle at capture time (see SessionState.kt's
RomType), not inferred from the label text. "AROM" matches against
field_dictionary_active.py, "PROM" against field_dictionary_passive.py; each
measurement in a batch is matched against its own dictionary independently,
so one batch can freely mix both.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field

from .field_dictionary_active import ROM_FIELDS as _ACTIVE_FIELDS
from .field_dictionary_active import SECTION_KEY as _ACTIVE_SECTION_KEY
from .field_dictionary_passive import ROM_FIELDS as _PASSIVE_FIELDS
from .field_dictionary_passive import SECTION_KEY as _PASSIVE_SECTION_KEY
from .rom_field import RomField

_SIDE_WORDS = {
    "left": "l",
    "right": "r",
}


@dataclass
class Measurement:
    """One kept measurement from a goniometer export.

    The old flat ``.gonio.json`` (importer.load_gonio_measurements) fills only
    the first four fields; the new ``.gonio.zip`` manifest
    (importer.load_gonio_bundle) fills the rest. Everything past ``rom_type``
    is defaulted so a flat-format load still constructs, and every consumer
    that only reads ``primary_range_deg`` keeps working unchanged.

    ``mode`` is "MOTION" (baseline-relative sweep — the original, and the
    only mode the flat format or a schema<3 bundle ever produces) or "TILT"
    (gravity-referenced angle — see the phone app's SessionState.kt). The
    two modes are mutually exclusive in which fields they populate:
    MOTION uses primary_range_deg/min_deg/max_deg/marks_deg/etc.; TILT uses
    only the absolute_* fields below, and format_measurement_value() branches
    on ``mode`` to format one or the other. A TILT measurement's
    primary_range_deg stays at its dataclass default (0.0) — never read for
    that mode — rather than being repurposed to carry a TILT value, so an
    older consumer that ignores ``mode`` and reads primary_range_deg
    unconditionally gets an obviously-wrong 0, not a plausible-looking wrong
    number silently mistaken for a MOTION sweep.
    """
    index: int
    label: str
    primary_range_deg: float
    rom_type: str = "AROM"  # "AROM" or "PROM" — see importer.load_gonio_measurements
    mode: str = "MOTION"  # "MOTION" or "TILT" — manifest schema >= 3; absent (schema 1/2, or the flat format) defaults to "MOTION"
    # ── MOTION only, from the .gonio.zip manifest (bundle_schema >= 1) ──────
    min_deg: float | None = None            # primary-channel low vs baseline (signed)
    max_deg: float | None = None            # primary-channel high vs baseline (signed)
    deficit_to_full_deg: float | None = None
    mark_count: int = 0
    marks_deg: list[float] = dataclass_field(default_factory=list)  # manifest schema 2+; null slots dropped on load
    # ── TILT only, from the .gonio.zip manifest (bundle_schema >= 3) ────────
    absolute_peak_deg: float | None = None       # the reported headline figure — pinned by the therapist, or auto-picked
    absolute_peak_user_selected: bool = False    # schema >= 4 — True if the therapist pinned it via "Set as main" rather than it being auto-picked
    absolute_start_deg: float | None = None      # schema >= 5 — the reading at Start, or None if Start was deleted in the app
    absolute_readings_deg: list[float] = dataclass_field(default_factory=list)  # every surviving reading, capture order
    chart_png: str | None = None            # zip-relative path, or None


@dataclass
class MatchCandidate:
    field: RomField
    score: int


@dataclass
class MatchResult:
    measurement: Measurement
    field: RomField | None = None
    side: str | None = None  # 'l' / 'r' / None
    side_inferred: bool = False
    candidates: list[MatchCandidate] = dataclass_field(default_factory=list)
    section_key: str = _ACTIVE_SECTION_KEY  # which dictionary this was matched against (measurement.rom_type)

    @property
    def resolved(self) -> bool:
        if self.field is None:
            return False
        if self.field.bilateral and self.side is None:
            return False
        return True

    @property
    def status(self) -> str:
        if self.field is None:
            return "no_field_match"
        if self.field.bilateral and self.side is None:
            return "side_missing"
        if self.side_inferred:
            return "side_inferred"
        return "resolved"

    def field_id(self) -> str | None:
        if not self.resolved:
            return None
        assert self.field is not None
        return self.field.field_id(self.side)


def _detect_side(label_lower: str) -> str | None:
    for word, side in _SIDE_WORDS.items():
        if word in label_lower:
            return side
    return None


def _score_field(label_lower: str, rom_field: RomField) -> int:
    score = 0
    for synonym in rom_field.synonyms:
        if synonym in label_lower:
            score += len(synonym.split())  # multi-word synonyms (e.g. "internal rotation") outweigh single words
    return score


def _candidates_for(label_lower: str, fields: list[RomField], limit: int = 3) -> list[MatchCandidate]:
    scored = [MatchCandidate(f, _score_field(label_lower, f)) for f in fields]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:limit]


def match_batch(measurements: list[Measurement]) -> list[MatchResult]:
    """Matches every measurement, in order, inferring omitted sides from
    earlier measurements of the SAME field *within the same AROM/PROM
    section* of this same batch (not globally) — so alternating movements
    don't cross-contaminate side state, and an AROM side never leaks into a
    PROM inference of the same movement or vice versa. Each measurement is
    matched against its own dictionary per measurement.rom_type.
    """
    results: list[MatchResult] = []
    last_side_by_field: dict[tuple[str, str], str] = {}  # (section_key, field_prefix) -> 'l'/'r'

    for m in measurements:
        passive = m.rom_type.upper() == "PROM"
        fields = _PASSIVE_FIELDS if passive else _ACTIVE_FIELDS
        section_key = _PASSIVE_SECTION_KEY if passive else _ACTIVE_SECTION_KEY

        label_lower = m.label.lower()
        candidates = _candidates_for(label_lower, fields)
        best = candidates[0] if candidates and candidates[0].score > 0 else None

        result = MatchResult(measurement=m, candidates=candidates, section_key=section_key)

        if best is not None:
            result.field = best.field
            stated_side = _detect_side(label_lower)
            side_key = (section_key, best.field.field_prefix)

            if not best.field.bilateral:
                result.side = None
            elif stated_side is not None:
                result.side = stated_side
                last_side_by_field[side_key] = stated_side
            else:
                inferred = last_side_by_field.get(side_key)
                if inferred is not None:
                    result.side = inferred
                    result.side_inferred = True
                # else: left None -> status "side_missing"

        results.append(result)

    return results


@dataclass
class GroupedValue:
    field_id: str
    region: str
    section_key: str
    display_label: str  # e.g. "Shoulder flexion (L)"
    joined_value: str  # e.g. "120 // 130 // 135"
    source_indices: list[int]  # measurement indices contributing, chronological


def format_measurement_value(m: Measurement) -> str:
    """The string written into a pab AROM/PROM field for ONE measurement —
    the single source of truth, called from group_resolved() (joined-repeats
    path), the wizard's raw-override path, and the wizard's row preview so all
    three always agree. Repeats of the same field are ' // '-joined by
    group_resolved(); this formats one contribution only.

    Format, MOTION (user, 2026-09-07 — see gpab/GONIO_INTEGRATION_PLAN.md §C):
      marks present         "110 (-8->102) ; 43 ; 98"
      min/max, no marks      "110 (-8->102)"
      neither (schema-1      "110"
        bundle or flat
        .gonio.json)

    '->' is literal ASCII. No degree symbol. lo/hi are signed and may be
    negative. Every printed number is round()ed exactly once here.

    Format, TILT (user, 2026-09-18): NOT the MOTION shape above — a
    gravity-referenced angle is a single absolute reading, not a swept
    range, so there is no "(lo->hi)" bracket to print (see Measurement's own
    docstring for why that distinction matters). Also NOT converted to a
    "degrees of flexion achieved" figure — the app's own primary/headline
    reading is the source of truth for what number a measurement means, by
    explicit user decision (2026-09-18): whatever mode/convention the app
    displays as primary is exactly what lands in the patient record, gpab
    doesn't reinterpret it. If that mounting convention ever needs to change
    (e.g. so the number reads as a standard flexion angle), it changes in
    the app (SensorFusion.kt's gravityInclinationDeg), not here.
      other readings too    "150 ; 180 ; 165 ; 150"
      only one reading       "150"
    The first number is always absolute_peak_deg (the therapist-pinned or
    auto-picked headline). The rest are absolute_readings_deg in capture
    order, UNMODIFIED — including a repeat of the peak's own value, same as
    MOTION's own marks_deg is never deduped against min_deg/max_deg above —
    so the true sequence of attempts (which may have been improving OR
    declining) is never reordered or silently thinned.
    """
    if m.mode == "TILT":
        peak = round(m.absolute_peak_deg or 0.0)
        if not m.absolute_readings_deg:
            return str(peak)
        # Every reading, in capture order — including one that equals the
        # peak, same as MOTION's own marks_deg never dedupes against
        # min_deg/max_deg above. That keeps the sequence honest: "180 ; 165 ;
        # 150" (peak last, attempts improving) reads differently from
        # "150 ; 165 ; 180" (peak first, attempts declining), and only the
        # unmodified capture order preserves which one actually happened.
        return str(peak) + "".join(f" ; {round(x)}" for x in m.absolute_readings_deg)

    rng = round(m.primary_range_deg)
    if m.min_deg is None or m.max_deg is None:
        return str(rng)
    swept = f"{rng} ({round(m.min_deg)}->{round(m.max_deg)})"
    if not m.marks_deg:
        return swept
    return swept + "".join(f" ; {round(x)}" for x in m.marks_deg)


def group_resolved(results: list[MatchResult]) -> list[GroupedValue]:
    """Groups every RESOLVED result by (section_key, field_id), joining
    repeats chronologically as whole-number degrees with ' // ' — pab's own
    findings-field convention. Keying by section_key too (not just field_id)
    keeps an AROM and PROM measurement of the same movement from ever
    merging into one group, even though their field_ids already differ in
    practice (different id templates per dictionary). Unresolved results are
    the wizard's job, not this function's.
    """
    buckets: dict[tuple[str, str], list[MatchResult]] = {}
    order: list[tuple[str, str]] = []
    for r in results:
        if not r.resolved:
            continue
        fid = r.field_id()
        assert fid is not None
        key = (r.section_key, fid)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(r)

    grouped: list[GroupedValue] = []
    for section_key, fid in order:
        items = buckets[(section_key, fid)]
        items.sort(key=lambda r: r.measurement.index)
        values = [format_measurement_value(r.measurement) for r in items]
        first = items[0]
        assert first.field is not None
        side_suffix = ""
        if first.field.bilateral:
            side_suffix = " (L)" if first.side == "l" else " (R)"
        movement = first.field.movement
        region = first.field.region
        # Lumbar/thoracic movement names already embed the region ("lumbar flexion") — don't repeat it.
        base = movement.capitalize() if region in movement else f"{region.capitalize()} {movement}"
        display = f"{base}{side_suffix}"
        grouped.append(GroupedValue(
            field_id=fid,
            region=first.field.region,
            section_key=section_key,
            display_label=display,
            joined_value=" // ".join(values),
            source_indices=[r.measurement.index for r in items],
        ))
    return grouped
