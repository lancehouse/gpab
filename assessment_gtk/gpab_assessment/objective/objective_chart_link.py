"""Objective-side counterpart to mapping.py's Subjective body-chart -> note
prefill, built 2026-08-26 for the Sensory-tab bodychart realignment (see
CONVERSION_PLAN.md). Bodychart's own `_session.json` "objective" block
(zones/points/ticks — see bodychart/src/persistence.c) now carries a
region_label per item, computed by the same svg_regions_hit() lookup
already used for Subjective strokes/notes. This module turns matching
items into a short "See Bodychart. ..." summary per Sensory/CRPS field —
the same cross-link style the user asked for (direct quote: "a tick and a
'see objective body chart' entry, with brief description ... similar to
the subjective region crosslinking").

Pure data transformation — no GTK imports, no file I/O of its own (callers
pass in the already-parsed session JSON, same shape ChartFileWatcher's
on_chart_update callback receives).
"""

from __future__ import annotations

from typing import Any

# ── Type-int mirrors — MUST match bodychart/src/obj_chart.h's enums exactly.
# Zone indices 0-7 are the pre-2026-08-26 values (load-bearing, never
# renumbered); 8-11 were appended for this feature. See obj_chart.h's
# ObjZoneType comment for why.
ZONE_ALLODYNIA         = 0
ZONE_HYPERALGESIA       = 1
ZONE_ERYTHEMA           = 2
ZONE_TEMP_COOL          = 3
ZONE_TEMP_WARM          = 4
ZONE_NUMB               = 5
ZONE_OEDEMA             = 6
ZONE_TROPHIC            = 7
ZONE_ALLODYNIA_DYNAMIC  = 8
ZONE_HEAT_HYPERALGESIA  = 9
ZONE_COLD_HYPERALGESIA  = 10
ZONE_BODY_PERCEPTION    = 11

POINT_PPT           = 0
POINT_TEMPORAL_SUM  = 1
POINT_MONOFILAMENT  = 2
POINT_TWO_PD        = 3

TICK_VIBRATION               = 0
TICK_PROPRIOCEPTION          = 1
TICK_NERVE_TRUNK_PALPATION   = 2

TICK_STATE_TICK  = 0   # intact / normal finding
TICK_STATE_CROSS = 1   # reduced / impaired finding

# Sensory/CRPS field_id -> bodychart zone type. OBJ_ZONE_NUMB ("Reduced
# Sensation") is mapped to "sn_lt" (light touch / hypoaesthesia) as the
# closest single fit — sharp/blunt testing has no dedicated zone type of
# its own yet, left for a future pass rather than guessed.
_ZONE_FIELD_MAP: dict[str, int] = {
    "sn_static_allodynia":  ZONE_ALLODYNIA,
    "sn_dynamic_allodynia": ZONE_ALLODYNIA_DYNAMIC,
    "sn_pin_prick":         ZONE_HYPERALGESIA,
    "sn_lt":                ZONE_NUMB,
    "sn_heat":              ZONE_HEAT_HYPERALGESIA,
    "sn_cold":              ZONE_COLD_HYPERALGESIA,
    "sn_body":              ZONE_BODY_PERCEPTION,   # cross-links into CRPS too, see crps.py
}

# OBJ_POINT_MONOFILAMENT deliberately excluded — clinically used for both
# static-allodynia grading AND light-touch threshold testing, so it doesn't
# map cleanly onto one Sensory field. Flagged rather than guessed.
_POINT_FIELD_MAP: dict[str, int] = {
    "sn_secondary_hyper": POINT_PPT,
    "sn_temporal_sum":    POINT_TEMPORAL_SUM,
    "sn_tpd":             POINT_TWO_PD,
}

_TICK_FIELD_MAP: dict[str, int] = {
    "sn_vibration":       TICK_VIBRATION,
    "sn_proprioception":  TICK_PROPRIOCEPTION,
    "sn_nerve_palpation": TICK_NERVE_TRUNK_PALPATION,
}

_TICK_LABELS: dict[str, str] = {
    "sn_vibration":       "vibration sense",
    "sn_proprioception":  "proprioception",
    "sn_nerve_palpation": "nerve trunk palpation",
}

# Fields sourced from bodychart's Objective chart at all (zone, point, or
# tick) — CRPS's own field additions reuse this to know which of Sensory's
# fields to cross-link from, without duplicating the maps above.
CHART_LINKED_FIELDS: frozenset[str] = frozenset(
    set(_ZONE_FIELD_MAP) | set(_POINT_FIELD_MAP) | set(_TICK_FIELD_MAP)
)


def _regions_for(items: list[dict[str, Any]], predicate) -> list[str]:
    seen: list[str] = []
    for it in items:
        if not predicate(it):
            continue
        label = str(it.get("region_label", "")).strip()
        if label and label not in seen:
            seen.append(label)
    return seen


def build_chart_links(session_json: dict[str, Any]) -> dict[str, str]:
    """Returns {field_id: summary text} for every mapped field that has at
    least one matching Objective bodychart item. A field_id absent from the
    result has no chart data yet — callers must leave it untouched, never
    clear an existing manual entry because of that absence."""
    objective = session_json.get("objective", {}) or {}
    zones  = objective.get("zones", [])  or []
    points = objective.get("points", []) or []
    ticks  = objective.get("ticks", [])  or []

    out: dict[str, str] = {}

    for field_id, ztype in _ZONE_FIELD_MAP.items():
        regions = _regions_for(zones, lambda z, t=ztype: z.get("type") == t)
        if regions:
            out[field_id] = "See Bodychart. " + ", ".join(regions) + "."

    for field_id, ptype in _POINT_FIELD_MAP.items():
        matches = [p for p in points if p.get("type") == ptype]
        if not matches:
            continue
        parts = []
        for p in matches:
            region = str(p.get("region_label", "")).strip()
            label  = str(p.get("label", "")).strip()
            if region and label:
                parts.append(f"{label} at {region}")
            elif label:
                parts.append(label)
        out[field_id] = "See Bodychart." + (" " + "; ".join(parts) + "." if parts else "")

    for field_id, ttype in _TICK_FIELD_MAP.items():
        matches = [t for t in ticks if t.get("type") == ttype]
        if not matches:
            continue
        reduced = _regions_for(matches, lambda t: t.get("state") == TICK_STATE_CROSS)
        intact  = _regions_for(matches, lambda t: t.get("state") == TICK_STATE_TICK)
        label = _TICK_LABELS.get(field_id, "finding")
        sentences = []
        if reduced:
            sentences.append(f"Reduced {label} {', '.join(reduced)}.")
        if intact:
            sentences.append(f"Maintained {label} {', '.join(intact)}.")
        if sentences:
            out[field_id] = "See Bodychart. " + " ".join(sentences)

    return out
