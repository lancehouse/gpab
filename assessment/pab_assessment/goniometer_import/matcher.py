"""Matches goniometer measurement labels ("Left shoulder flexion") to pab ROM
fields, infers an omitted side from earlier measurements of the same movement
in the same batch, and groups repeats of the same field into pab's own
" // "-joined findings convention.

Deliberately conservative: nothing is written anywhere until match_batch()'s
results have been confirmed (by the wizard, or accepted outright when every
item resolved unambiguously). A field/side that can't be determined is left
unresolved rather than guessed — see field_dictionary_active.py's docstring
for why only ROM (not strength/accessory/PAIVM) fields are even candidates.

Defaults to field_dictionary_active.py's Active-ROM fields (Ax column) —
that's the everyday target. field_dictionary_passive.py exists for a later
phase where a label explicitly says "passive" (e.g. "Passive shoulder
internal rotation"); pass fields=PASSIVE_ROM_FIELDS/section_key="passive"
to opt into it once that detection is built. Not wired up automatically yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field

from .field_dictionary_active import ROM_FIELDS as _DEFAULT_FIELDS
from .field_dictionary_active import SECTION_KEY as _DEFAULT_SECTION_KEY
from .rom_field import RomField

_SIDE_WORDS = {
    "left": "l",
    "right": "r",
}


@dataclass
class Measurement:
    """One kept measurement from a goniometer .gonio.json session file."""
    index: int
    label: str
    primary_range_deg: float


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


def match_batch(measurements: list[Measurement], fields: list[RomField] | None = None) -> list[MatchResult]:
    """Matches every measurement, in order, inferring omitted sides from
    earlier measurements of the SAME field within this same batch (not
    globally) — so alternating movements don't cross-contaminate side state.
    Defaults to the Active-ROM dictionary; pass fields=PASSIVE_ROM_FIELDS to
    match against Passive/OP instead.
    """
    if fields is None:
        fields = _DEFAULT_FIELDS
    results: list[MatchResult] = []
    last_side_by_field: dict[str, str] = {}  # field_prefix -> 'l'/'r'

    for m in measurements:
        label_lower = m.label.lower()
        candidates = _candidates_for(label_lower, fields)
        best = candidates[0] if candidates and candidates[0].score > 0 else None

        result = MatchResult(measurement=m, candidates=candidates)

        if best is not None:
            result.field = best.field
            stated_side = _detect_side(label_lower)

            if not best.field.bilateral:
                result.side = None
            elif stated_side is not None:
                result.side = stated_side
                last_side_by_field[best.field.field_prefix] = stated_side
            else:
                inferred = last_side_by_field.get(best.field.field_prefix)
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


def group_resolved(results: list[MatchResult], section_key: str | None = None) -> list[GroupedValue]:
    """Groups every RESOLVED result by field_id, joining repeats chronologically
    as whole-number degrees with ' // ' — pab's own findings-field convention.
    Unresolved results are the wizard's job, not this function's.
    """
    if section_key is None:
        section_key = _DEFAULT_SECTION_KEY

    buckets: dict[str, list[MatchResult]] = {}
    order: list[str] = []
    for r in results:
        if not r.resolved:
            continue
        fid = r.field_id()
        assert fid is not None
        if fid not in buckets:
            buckets[fid] = []
            order.append(fid)
        buckets[fid].append(r)

    grouped: list[GroupedValue] = []
    for fid in order:
        items = buckets[fid]
        items.sort(key=lambda r: r.measurement.index)
        values = [str(round(r.measurement.primary_range_deg)) for r in items]
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
