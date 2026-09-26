"""
GTK body chart → TUI Section 02 field pre-population.

Pure data transformation — no Textual imports, no file I/O.
Input:  parsed _session.json dict (full document, not just a sub-block).
Output: build_prefill() → dict ready to seed per-note and misc fields.

Schema version 3+ required in the session JSON (version key, not schema_version).
Returns empty structure gracefully for older files or missing data.
"""

from __future__ import annotations
from typing import Any

# ── Enum mirrors (must match GTK stroke.h / window.c) ─────────────────────────

# SymptomType integer → clinical display name
# Type 5 (SYMPTOM_TICK) is a "clear" marker, not a symptom — excluded from text.
_SYMPTOM_NAMES: dict[int, str] = {
    0: "pain (constant)",
    1: "pain (intermittent)",
    2: "pins & needles",
    3: "anaesthesia / numbness",
    4: "paraesthesia / deep ache",
}

# Quality index (0–11) → full clinical term
# Indices match QUALITY_SHORT[] in window.c:
#   0=Throb 1=Press 2=Ache  3=Stab
#   4=Tight 5=Burn  6=Freez 7=Elec
#   8=Shot  9=P+N   10=Numb 11=Itch
_QUALITY_TERMS: list[str] = [
    "throbbing", "pressure", "aching",   "stabbing",
    "tight",     "burning",  "freezing", "electrical",
    "shooting",  "pins & needles", "numbness", "itching",
]

# NoteAnnotation.temporal int → descriptor
_TEMPORAL: dict[int, str] = {0: "constant", 1: "intermittent"}

# NoteAnnotation.depth int → descriptor
_DEPTH: dict[int, str] = {0: "superficial", 1: "deep"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _title_region(label: str) -> str:
    """'l anterior thigh' → 'L anterior thigh'  (capitalise first word only)."""
    s = label.strip()
    return s[:1].upper() + s[1:] if s else s


def _fmt_location(note: dict[str, Any], dist_labels: list[str]) -> str:
    """Build a Location/Distribution string from note region + cluster distribution."""
    region = note.get("region_label", "").strip()
    extras = [r for r in dist_labels if r.strip() and r.strip() != region]

    parts: list[str] = []
    if region:
        parts.append(_title_region(region))
    if extras:
        parts.append("extending to " + ", ".join(_title_region(r) for r in extras))

    return "; ".join(parts)


def _fmt_nature(note: dict[str, Any], assoc_clusters: list[dict[str, Any]]) -> str:
    """Build a Nature of Symptoms string from cluster types + note temporal/depth/qualities."""
    low  = int(note.get("low",  0))
    high = int(note.get("high", 0))
    severity = ""
    if high > 0 or low > 0:
        severity = f"{high}/10" if low == high else f"{low}–{high}/10"

    # Voice transcript takes priority over index-based quality lookup
    voice = note.get("voice_note", "").strip()
    if voice:
        parts = [voice]
        if severity:
            parts.append(severity)
        return "; ".join(parts)

    # Symptom types present across associated clusters (skip TICK=5)
    seen_types: list[str] = []
    for cl in assoc_clusters:
        t = _SYMPTOM_NAMES.get(int(cl.get("type", -1)))
        if t and t not in seen_types:
            seen_types.append(t)

    temporal = _TEMPORAL.get(int(note.get("temporal", 0)), "constant")
    depth    = _DEPTH.get(int(note.get("depth", 0)), "superficial")

    # Quality indices (0–11)
    quality_words: list[str] = []
    for idx in note.get("qualities", []):
        try:
            word = _QUALITY_TERMS[int(idx)]
        except (IndexError, TypeError, ValueError):
            continue
        if word and word not in quality_words:
            quality_words.append(word)

    # Assemble: symptom types from clusters encode temporal for pain types,
    # so only prepend temporal when there are no associated clusters.
    if seen_types:
        parts = [", ".join(seen_types), depth]
    else:
        parts = [f"{temporal} symptoms", depth]

    if quality_words:
        parts.append(", ".join(quality_words))

    if severity:
        parts.append(severity)

    return "; ".join(parts)


def _fmt_misc_location(misc_clusters: list[dict[str, Any]]) -> str:
    """Location text for clusters not associated with any note."""
    seen: list[str] = []
    for cl in misc_clusters:
        r = cl.get("region_label", "").strip()
        if r and r not in seen:
            seen.append(r)
    return ", ".join(_title_region(r) for r in seen)


def _fmt_misc_nature(misc_clusters: list[dict[str, Any]]) -> str:
    """Nature text for clusters not associated with any note."""
    seen: list[str] = []
    for cl in misc_clusters:
        t = _SYMPTOM_NAMES.get(int(cl.get("type", -1)))
        if t and t not in seen:
            seen.append(t)
    return ", ".join(seen)


# ── Public API ─────────────────────────────────────────────────────────────────

def build_prefill(session_json: dict[str, Any]) -> dict[str, Any]:
    """
    Transform a parsed _session.json dict into pre-population data for Section 02.

    Returns:
        {
            "notes": [
                {
                    "stable_id": int,
                    "number": int,
                    "location_distribution": str,
                    "nature": str,
                    "aggravating_factors": str,   # always "" — clinician fills
                    "easing_factors": str,         # always "" — clinician fills
                },
                ...  (in note.number order)
            ],
            "misc": {
                "location_distribution": str,  # unassociated clusters
                "nature": str,
            },
            "schema_ok": bool,   # False if session is too old to have spatial data
        }
    """
    empty = {"notes": [], "misc": {"location_distribution": "", "nature": ""}, "schema_ok": False}

    version = session_json.get("version", 0)
    if version < 3:
        return empty

    subj = session_json.get("subjective", {})
    if not subj:
        return empty

    # Index clusters by id for O(1) lookup
    clusters_by_id: dict[int, dict[str, Any]] = {
        int(cl["id"]): cl
        for cl in subj.get("stroke_clusters", [])
        if "id" in cl
    }

    # Build per-note output
    notes_out: list[dict[str, Any]] = []
    for note in sorted(subj.get("notes", []), key=lambda n: n.get("number", 0)):
        assoc_ids   = [int(i) for i in note.get("associated_cluster_ids", [])]
        assoc_cls   = [
            clusters_by_id[i] for i in assoc_ids
            if i in clusters_by_id and int(clusters_by_id[i].get("type", -1)) != 5
        ]
        dist_labels = [str(r) for r in note.get("distribution_labels", [])]

        notes_out.append({
            "stable_id":             int(note.get("stable_id", -1)),
            "number":                int(note.get("number", 0)),
            "location_distribution": _fmt_location(note, dist_labels),
            "nature":                _fmt_nature(note, assoc_cls),
            "aggravating_factors":   "",
            "easing_factors":        "",
            # Clinician's own wording for the on-chart pin label — round-trips
            # both ways (see bodychart/src/persistence.c's chart_note_text /
            # regen_note_text()). Purely passed through here, never derived;
            # gpab writes edits back into _session.json via
            # storage_bridge.write_chart_note_texts().
            "brief":                 str(note.get("chart_note_text", "")),
        })

    # Misc clusters (no nearby note) — exclude type 5 (SYMPTOM_TICK = zone clear marker)
    misc_ids = [int(i) for i in subj.get("misc_cluster_ids", [])]
    misc_cls = [
        clusters_by_id[i] for i in misc_ids
        if i in clusters_by_id and int(clusters_by_id[i].get("type", -1)) != 5
    ]

    return {
        "notes":     notes_out,
        "misc": {
            "location_distribution": _fmt_misc_location(misc_cls),
            "nature":                _fmt_misc_nature(misc_cls),
        },
        "schema_ok": True,
    }


def prefill_is_empty(prefill: dict[str, Any]) -> bool:
    """True if there is nothing useful to pre-populate (no notes, no misc)."""
    if not prefill.get("schema_ok"):
        return True
    if prefill.get("notes"):
        return False
    misc = prefill.get("misc", {})
    return not (misc.get("location_distribution") or misc.get("nature"))
