"""
Body chart (_session.json) → Subjective Location / Nature pre-population.

Pure data transformation — no UI imports, no file I/O.
Input:  parsed _session.json dict (full document, not just a sub-block).
Output: build_prefill() → dict ready to seed per-note and misc fields.

Rewritten 2026-11-11. The clinician always places a note's dot at the
primary / origin site of that symptom, so Location is written from the dot
outward: "R anterior thigh (primary), extending distally through the knee,
shin and ankle to the dorsum of foot". It is built from bodychart's
point-level region coverage of each stroke cluster (cluster
"region_coverage", written by bodychart/src/persistence.c), not the cluster
centroid, so a stroke drawn thigh → foot reports every region it crosses.

Which strokes belong to a note:
  * same view, symptom strokes only (ticks / pencil are never symptoms);
  * the drawing touches the dot (≤ 5 body units), or comes within 30 units
    and is on the dot's side of the body;
  * each cluster goes to its single nearest qualifying note;
  * widespread clusters (spread over ≥ 4 body parts, e.g. a hemibody
    pattern) never attach to one note — they are described under Misc;
  * a cluster on another view joins a note when it is the same symptom
    type as strokes already attached to that note and covers the same
    side + body part (e.g. posterior calves for an anterior shin note).

Sessions saved before region_coverage existed fall back to the original
centroid-based text (_legacy_* below), so nothing breaks on old files.
"""

from __future__ import annotations

import math
from typing import Any

# ── Enum mirrors (must match bodychart stroke.h / window.c) ──────────────────

# SymptomType → clinical name (user decision 2026-11-11: orange X is
# "paraesthesia", also used for generic non-pain symptoms; blue lines are
# "numbness"). 5 = tick (symptom-free), 6 = pencil — never symptoms.
_SYMPTOM_NAMES: dict[int, str] = {
    0: "pain (constant)",
    1: "pain (intermittent)",
    2: "pins & needles",
    3: "numbness",
    4: "paraesthesia",
}
_SYMPTOM_TYPES = set(_SYMPTOM_NAMES)

# Quality index (0–13) → full clinical term. Indices match window.c:
#   0=Throb 1=Press 2=Ache 3=Stab 4=Tight 5=Burn 6=Freez 7=Elec
#   8=Shot 9=P+N 10=Numb 11=Itch 12=Sharp 13=Dull (12/13 appended 2026-10-27)
_QUALITY_TERMS: list[str] = [
    "throbbing", "pressure", "aching",   "stabbing",
    "tight",     "burning",  "freezing", "electrical",
    "shooting",  "pins & needles", "numbness", "itching",
    "sharp",     "dull",
]

_TEMPORAL: dict[int, str] = {0: "constant", 1: "intermittent"}
_DEPTH: dict[int, str] = {0: "superficial", 1: "deep"}

_VIEW_NAMES = {0: "anterior", 1: "posterior", 2: "L lateral", 3: "R lateral"}

# ── Association / coverage tuning (body units; body is 200 × 400) ───────────

_TOUCH_BU = 5.0        # drawing this close to the dot belongs to it, any side
_NEAR_BU = 30.0        # ...this close, if on the dot's side of the body
_TRACE_FRAC = 0.04     # regions under 4% of a note's ink are dropped as trace
_TRACE_MIN_PTS = 3
_WIDESPREAD_PARTS = 4  # cluster over ≥ this many side+part buckets = widespread

# ── Anatomy ──────────────────────────────────────────────────────────────────
#
# Region name (without the L/R prefix) → (body part, rank). Rank orders each
# axis: head 0 … cervical 1–2 … thoracic 4–5 … lumbar 6–7, SIJ 8, then the
# lower limb hip/gluteal 9 → foot 14; upper limb shoulder 20 → fingers 26.
# Higher rank = more caudal (trunk) / more distal (limb).

_ANATOMY: dict[str, tuple[str, float]] = {
    # head / neck
    "forehead": ("head", 0), "retroorbital": ("head", 0), "face": ("head", 0.5),
    "posterior head": ("head", 0),
    "anterior neck": ("neck", 2), "upper cervical": ("neck", 1),
    "lower cervical": ("neck", 2),
    # trunk
    "posterior superoscapular": ("trunk", 3),
    "upper thoracic": ("trunk", 4), "interscapular": ("trunk", 4),
    "scapular": ("trunk", 4), "anterior chest": ("trunk", 4),
    "lower thoracic": ("trunk", 5),
    "upper lumbar": ("trunk", 6), "posterior flank": ("trunk", 6),
    "anterior abdomen": ("trunk", 6),
    "lower lumbar": ("trunk", 7),
    "SIJ": ("trunk", 8), "anterior genital region": ("trunk", 8),
    # lower limb
    "gluteal": ("lower limb", 9), "anterior hip": ("lower limb", 9),
    "anterior thigh": ("lower limb", 10), "posterior thigh": ("lower limb", 10),
    "anterior knee": ("lower limb", 11),
    "anterior shin": ("lower limb", 12), "posterior leg": ("lower limb", 12),
    "anterior ankle": ("lower limb", 13), "posterior ankle": ("lower limb", 13),
    "dorsum foot": ("lower limb", 14), "medial foot": ("lower limb", 14),
    "lateral foot": ("lower limb", 14), "sole": ("lower limb", 14),
    "medial sole": ("lower limb", 14), "lateral sole": ("lower limb", 14),
    # upper limb
    "anterior shoulder": ("upper limb", 20), "posterior shoulder": ("upper limb", 20),
    "anterior upper arm": ("upper limb", 21), "posterior upper arm": ("upper limb", 21),
    "anterior forearm": ("upper limb", 23), "posterior forearm": ("upper limb", 23),
    "anterior wrist": ("upper limb", 24), "posterior wrist": ("upper limb", 24),
    "palm": ("upper limb", 25), "dorsal hand": ("upper limb", 25),
    "palmar thumb": ("upper limb", 25), "dorsal thumb": ("upper limb", 25),
    "palmar index finger": ("upper limb", 26), "palmar middle finger": ("upper limb", 26),
    "palmar ring finger": ("upper limb", 26), "palmar little finger": ("upper limb", 26),
    "dorsal index finger": ("upper limb", 26), "dorsal middle finger": ("upper limb", 26),
    "dorsal ring finger": ("upper limb", 26), "dorsal little finger": ("upper limb", 26),
}

# Names as they read inside a chain, where the side is already stated and
# the anterior/posterior surface is given once for the whole chain.
_SHORT: dict[str, str] = {
    "anterior thigh": "thigh", "posterior thigh": "thigh",
    "anterior knee": "knee", "anterior shin": "shin", "posterior leg": "calf",
    "anterior ankle": "ankle", "posterior ankle": "ankle",
    "dorsum foot": "dorsum of foot", "medial foot": "medial foot",
    "lateral foot": "lateral foot", "sole": "sole",
    "medial sole": "medial sole", "lateral sole": "lateral sole",
    "anterior hip": "hip", "gluteal": "gluteal region",
    "anterior shoulder": "shoulder", "posterior shoulder": "shoulder",
    "anterior upper arm": "upper arm", "posterior upper arm": "upper arm",
    "anterior forearm": "forearm", "posterior forearm": "forearm",
    "anterior wrist": "wrist", "posterior wrist": "wrist",
    "palm": "palm", "dorsal hand": "dorsum of hand",
    "palmar thumb": "thumb", "dorsal thumb": "thumb",
    "upper cervical": "upper cervical region", "lower cervical": "lower cervical region",
    "posterior superoscapular": "superoscapular region",
    "upper thoracic": "upper thoracic region", "lower thoracic": "lower thoracic region",
    "interscapular": "interscapular region", "scapular": "scapular region",
    "upper lumbar": "upper lumbar region", "lower lumbar": "lower lumbar region",
    "posterior flank": "flank", "anterior chest": "chest",
    "anterior abdomen": "abdomen", "anterior genital region": "genital region",
    "posterior head": "posterior head", "anterior neck": "anterior neck",
}
for _f in ("index", "middle", "ring", "little"):
    _SHORT[f"palmar {_f} finger"] = f"{_f} finger"
    _SHORT[f"dorsal {_f} finger"] = f"{_f} finger"

# When several regions share one rank on a limb, name the station generically.
_STATION_GENERIC: dict[float, str] = {
    9: "hip and gluteal region", 10: "thigh", 11: "knee", 12: "lower leg",
    13: "ankle", 14: "foot", 20: "shoulder", 21: "upper arm", 23: "forearm",
    24: "wrist", 25: "hand", 26: "fingers",
}
_LIMBS = ("lower limb", "upper limb")


# ── Small text helpers ───────────────────────────────────────────────────────

def _join_and(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _split_side(name: str) -> tuple[str | None, str]:
    name = name.strip()
    if name[:2] in ("R ", "L "):
        return name[0], name[2:]
    return None, name


def _anat(base: str) -> tuple[str, float]:
    return _ANATOMY.get(base, ("other", 50))


def _short(base: str) -> str:
    return _SHORT.get(base, base)


def _full(side: str | None, base: str) -> str:
    return f"{side} {base}" if side else base


# ── Geometry over the session JSON ───────────────────────────────────────────

def _axis(part: str) -> str:
    """Spread is followed along one continuous axis: head → neck → trunk →
    lower limb is one chain (so lumbar pain can run down into the thigh);
    each upper limb is its own chain."""
    return "upper limb" if part == "upper limb" else "axial"


class _Cluster:
    """One stroke cluster plus the derived facts association/text need."""

    def __init__(self, cl: dict[str, Any], strokes_by_id: dict[int, dict]):
        self.id = int(cl["id"])
        self.view = int(cl.get("view", 0))
        self.type = int(cl.get("type", -1))
        self.lines: list[list[tuple[float, float]]] = []
        for sid in cl.get("stroke_ids", []):
            st = strokes_by_id.get(int(sid))
            if st:
                self.lines.append([(float(p[0]), float(p[1])) for p in st.get("pts", [])])
        # name → [n, top, bottom]
        self.cov: dict[str, list[float]] = {}
        for e in cl.get("region_coverage", []):
            self.cov[e["name"]] = [int(e["n"]), float(e["top"]), float(e["bottom"])]
        self.n_unlabelled = int(cl.get("n_unlabelled", 0))
        lab = sum(v[0] for v in self.cov.values())
        side_pts = {"R": 0, "L": 0}
        buckets: dict[tuple, int] = {}
        levels: dict[tuple, int] = {}
        for name, (n, _t, _b) in self.cov.items():
            side, base = _split_side(name)
            if side:
                side_pts[side] += n
            part, rank = _anat(base)
            buckets[(side, part)] = buckets.get((side, part), 0) + n
            levels[(side, part, rank)] = levels.get((side, part, rank), 0) + n
        self.side_pts = side_pts
        self.buckets = {k for k, n in buckets.items() if lab and n / lab >= 0.05}
        self.levels = {k for k, n in levels.items() if lab and n / lab >= 0.05}
        self.widespread = len(self.buckets) >= _WIDESPREAD_PARTS

    def min_dist(self, x: float, y: float) -> float:
        """Distance from (x, y) to the drawn lines (segments, not just the
        recorded points — some fills are long straight segments)."""
        best = 1e9
        for line in self.lines:
            if len(line) == 1:
                best = min(best, math.hypot(line[0][0] - x, line[0][1] - y))
            for (ax, ay), (bx, by) in zip(line, line[1:]):
                dx, dy = bx - ax, by - ay
                l2 = dx * dx + dy * dy
                t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / l2)) if l2 else 0.0
                best = min(best, math.hypot(ax + t * dx - x, ay + t * dy - y))
        return best

    def on_side(self, side: str | None) -> bool:
        """True if a meaningful share of this cluster is on `side` (or no side applies)."""
        if side is None:
            return True
        tot = self.side_pts["R"] + self.side_pts["L"]
        return tot == 0 or self.side_pts[side] / tot >= 0.2


def _levels_meet(a: set, b: set) -> bool:
    """Same side and body part, at the same or an adjacent level (rank ±1)."""
    return any(sa == sb and pa == pb and abs(ra - rb) <= 1
               for sa, pa, ra in a for sb, pb, rb in b)


def _associate(notes: list[dict], clusters: list[_Cluster]) -> dict[int, list[_Cluster]]:
    """note stable_id → clusters, per the rules in the module docstring."""
    out: dict[int, list[_Cluster]] = {int(n.get("stable_id", -1)): [] for n in notes}
    direct: dict[int, int] = {}   # cluster id → note sid
    for c in clusters:
        if c.type not in _SYMPTOM_TYPES or c.widespread:
            continue
        best, best_d = None, 1e9
        for n in notes:
            if int(n.get("view", -1)) != c.view:
                continue
            d = c.min_dist(float(n.get("bx", 0)), float(n.get("by", 0)))
            side = _split_side(str(n.get("region_label", "")))[0]
            if d <= _TOUCH_BU or (d <= _NEAR_BU and c.on_side(side)):
                if d < best_d:
                    best, best_d = n, d
        if best is not None:
            sid = int(best.get("stable_id", -1))
            out[sid].append(c)
            direct[c.id] = sid

    # Cross-view: same symptom type, same side + body part at a matching
    # level as strokes already on the note (posterior calves ↔ anterior shins).
    for c in clusters:
        if c.type not in _SYMPTOM_TYPES or c.widespread or c.id in direct:
            continue
        best_sid, best_overlap = None, 0
        for n in notes:
            sid = int(n.get("stable_id", -1))
            if int(n.get("view", -1)) == c.view:
                continue
            mine = [d for d in out[sid] if d.id in direct and d.type == c.type]
            if not mine:
                continue
            theirs = set().union(*(d.levels for d in mine))
            if not _levels_meet(c.levels, theirs):
                continue
            overlap = len(c.buckets & set().union(*(d.buckets for d in mine)))
            if overlap > best_overlap:
                best_sid, best_overlap = sid, overlap
        if best_sid is not None:
            out[best_sid].append(c)
    return out


# ── Location ─────────────────────────────────────────────────────────────────

# Only long segments get "mid / lower / upper" — on a wrist, ankle or spinal
# region that precision is noise from a few stray points.
_EXTENT_RANKS = {10, 12, 21, 23}


def _merge_cov(clusters: list[_Cluster]) -> dict[str, list[float]]:
    cov: dict[str, list[float]] = {}
    for c in clusters:
        for name, (n, t, b) in c.cov.items():
            if name in cov:
                cov[name][0] += n
                cov[name][1] = min(cov[name][1], t)
                cov[name][2] = max(cov[name][2], b)
            else:
                cov[name] = [n, t, b]
    return cov


def _significant(cov: dict[str, list[float]], keep: str = "") -> dict[str, list[float]]:
    tot = sum(v[0] for v in cov.values()) or 1
    return {k: v for k, v in cov.items()
            if k == keep or (v[0] >= _TRACE_MIN_PTS and v[0] / tot >= _TRACE_FRAC)}


_MODIFIERS = {"upper", "lower", "mid", "medial", "lateral", "anterior",
              "posterior", "proximal", "distal", "palmar", "dorsal"}


def _factor(shorts: list[str]) -> str:
    """Join names, sharing a common noun: 'lateral foot', 'medial foot' →
    'lateral and medial foot'; 'upper lumbar region', 'lower lumbar region',
    'SIJ' → 'upper and lower lumbar region and SIJ'."""
    groups: list[tuple[str, list[str]]] = []   # (noun, modifiers) or (name, [])
    for s in shorts:
        first, _, rest = s.partition(" ")
        if first in _MODIFIERS and rest:
            for noun, mods in groups:
                if noun == rest and mods:
                    mods.append(first)
                    break
            else:
                groups.append((rest, [first]))
        else:
            groups.append((s, []))
    return _join_and([f"{_join_and(m)} {n}" if m else n for n, m in groups])


class _Station:
    """All regions at one rank (level) on one side of one axis."""

    def __init__(self, rank: float, part: str):
        self.rank = rank
        self.part = part
        self.bases: list[str] = []
        self.top = 1.0
        self.bottom = 0.0

    def add(self, base: str, top: float, bottom: float) -> None:
        if base not in self.bases:
            self.bases.append(base)
        self.top = min(self.top, top)
        self.bottom = max(self.bottom, bottom)

    def name(self) -> str:
        shorts: list[str] = []
        for b in self.bases:
            s = _short(b)
            if s not in shorts:
                shorts.append(s)
        if len(shorts) > 1 and self.part in _LIMBS and self.rank in _STATION_GENERIC:
            return _STATION_GENERIC[self.rank]
        return _factor(shorts)

    def end_name(self, proximal_end: bool) -> str:
        """Name with how far into it the drawing reaches, e.g. 'mid shin'."""
        name = self.name()
        if self.rank not in _EXTENT_RANKS:
            return name
        if proximal_end:
            if self.top >= 0.66:
                return f"distal {name}"
            if self.top >= 0.33:
                return f"mid {name}"
        else:
            if self.bottom <= 0.34:
                return f"proximal {name}"
            if self.bottom <= 0.67:
                return f"mid {name}"
        return name


def _stations(cov: dict[str, list[float]], sides: set, axis: str,
              parts: set | None = None) -> list[_Station]:
    st: dict[float, _Station] = {}
    for name, (_n, t, b) in cov.items():
        s, base = _split_side(name)
        part, rank = _anat(base)
        if s not in sides or _axis(part) != axis or part == "other":
            continue
        if parts is not None and part not in parts:
            continue
        st.setdefault(rank, _Station(rank, part)).add(base, t, b)
    return [st[r] for r in sorted(st)]


def _span(stations: list[_Station]) -> str:
    """'mid shin to dorsum of foot' / 'knee' — a whole chain, no origin."""
    if not stations:
        return ""
    if len(stations) == 1:
        st = stations[0]
        name = st.name()
        if st.rank in _EXTENT_RANKS:
            if st.top >= 0.5:
                return f"distal {name}"
            if st.bottom <= 0.5:
                return f"proximal {name}"
        return name
    return f"{stations[0].end_name(True)} to {stations[-1].end_name(False)}"


def _directional(stations: list[_Station], limb: bool, proximal: bool) -> str:
    """'distally through the knee and shin to the dorsum of foot'."""
    if not stations:
        return ""
    ordered = list(reversed(stations)) if proximal else stations
    end = ordered[-1].end_name(proximal_end=proximal)
    via = [s.name() for s in ordered[:-1]]
    if via:
        return f"{_direction_word(limb, proximal)} through the {_factor(via)} to the {end}"
    return f"{_direction_word(limb, proximal)} to the {end}"


def _direction_word(limb: bool, proximal: bool) -> str:
    """Limbs read distally/proximally from the dot; the axial chain up/down."""
    if limb:
        return "proximally" if proximal else "distally"
    return "up" if proximal else "down"


def _views_note(clusters: list[_Cluster]) -> str:
    views = {c.view for c in clusters if c.cov}
    return " (anterior and posterior)" if {0, 1} <= views else ""


def _other(side: str | None) -> str | None:
    return {"R": "L", "L": "R"}.get(side or "")


def _bilateral_span(cov: dict, part: str) -> str:
    """Combined L+R extent of one body part (never spills into the trunk)."""
    merged: dict[float, _Station] = {}
    for st in _stations(cov, {"R", "L"}, _axis(part), {part}):
        m = merged.setdefault(st.rank, _Station(st.rank, st.part))
        for b in st.bases:
            m.add(b, st.top, st.bottom)
        m.top, m.bottom = min(m.top, st.top), max(m.bottom, st.bottom)
    return _span([merged[r] for r in sorted(merged)])


def _fmt_location_v2(note: dict[str, Any], clusters: list[_Cluster]) -> str:
    pside, pbase = _split_side(str(note.get("region_label", "")))
    pview = int(note.get("view", 0))

    raw = _merge_cov(clusters)
    keep = _full(pside, pbase) if pbase else ""
    if keep and keep not in raw:
        raw[keep] = [0, 0.0, 1.0]
    cov = _significant(raw, keep)

    # (side, body part) groups present, in drawing order
    groups: list[tuple[str | None, str]] = []
    for name in cov:
        s, base = _split_side(name)
        part = _anat(base)[0]
        if part != "other" and (s, part) not in groups:
            groups.append((s, part))

    clauses: list[str] = []
    handled: set[tuple] = set()

    if not pbase:
        clauses.append(f"{_VIEW_NAMES.get(pview, '')} view".strip())
    else:
        primary = _full(pside, pbase)
        ppart, prank = _anat(pbase)
        axis = _axis(ppart)
        limb = ppart in _LIMBS
        other = _other(pside)
        opp_limb = limb and (other, ppart) in groups

        head = f"{primary} (primary)"
        if opp_limb:
            # Bilateral limb pattern: the dot stays the primary site and the
            # combined extent of that limb on both sides follows. Anything
            # beyond the limb (e.g. lumbar spread) is listed under "also".
            own = _stations(cov, {pside}, axis, {ppart})
            handled.update({(pside, ppart), (other, ppart)})
        else:
            own = _stations(cov, {pside, None}, axis)
            handled.update({(sd, st.part) for st in own for sd in (pside, None)})
        same = [st for st in own if st.rank == prank]
        prox = [st for st in own if st.rank < prank]
        dist = [st for st in own if st.rank > prank]
        extra_same = [b for st in same for b in st.bases if b != pbase]

        if opp_limb:
            text = head
            if extra_same:
                text += f" and adjacent {_factor([_short(b) for b in extra_same])}"
            text += (f"; bilateral {ppart}s, {_bilateral_span(cov, ppart)}"
                     f"{_views_note(clusters)}")
            clauses.append(text)
        else:
            if not prox and not dist and not extra_same \
                    and prank in _EXTENT_RANKS and raw.get(keep, [0])[0]:
                st = same[0]
                if st.top >= 0.5:
                    head = f"distal {primary} (primary)"
                elif st.bottom <= 0.5:
                    head = f"proximal {primary} (primary)"
            text = head
            if extra_same:
                text += f" and adjacent {_factor([_short(b) for b in extra_same])}"
            moves = [m for m in (_directional(dist, limb, False),
                                 _directional(prox, limb, True)) if m]
            if moves:
                text += ", extending " + " and ".join(moves) + _views_note(clusters)
            clauses.append(text)
            opp = _stations(cov, {other}, axis) if other else []
            if opp and not limb:
                # Trunk/neck/head crossing the midline from a one-sided dot.
                handled.update({(other, st.part) for st in opp})
                clauses.append(f"across to the {other} {_factor([st.name() for st in opp])}")

    # Everything else the note's strokes cover, one body part at a time.
    also: list[str] = []
    for side, part in groups:
        if (side, part) in handled:
            continue
        other = _other(side)
        if other and (other, part) in groups and (other, part) not in handled:
            also.append(f"bilateral {_bilateral_span(cov, part)}")
            handled.add((other, part))
        else:
            span = _span(_stations(cov, {side}, _axis(part), {part}))
            also.append(f"{side} {span}" if side else span)
        handled.add((side, part))
    if also:
        clauses.append("also " + _join_and(also))

    lat = [c for c in clusters if c.view in (2, 3) and c.n_unlabelled]
    if lat and any(c.view != pview for c in lat):
        views = sorted({_VIEW_NAMES[c.view] for c in lat})
        clauses.append(f"also drawn on the {_join_and(views)} view")

    return "; ".join(clauses)


# ── Nature ───────────────────────────────────────────────────────────────────

def _severity(note: dict[str, Any], version: int) -> str:
    low = int(note.get("low", 0))
    high = int(note.get("high", 0))
    # -1 = unanswered. Before session version 4 there was no -1 and 0/0 was
    # the untouched default, so it's dropped there; from 4 on, 0/0 is a
    # deliberately tapped 0/10 and is kept (user decision 2026-10-27).
    if low >= 0 and high >= 0 and not (version < 4 and low == 0 and high == 0):
        return f"{high}/10" if low == high else f"{low}–{high}/10"
    return ""


def _quality_words(note: dict[str, Any]) -> list[str]:
    words: list[str] = []
    for idx in note.get("qualities", []):
        try:
            w = _QUALITY_TERMS[int(idx)]
        except (IndexError, TypeError, ValueError):
            continue
        if w not in words:
            words.append(w)
    return words


def _drawn_types(note: dict[str, Any], clusters: list[_Cluster]) -> list[tuple[str, list[_Cluster]]]:
    """Symptom types drawn for this note, minus any the answers already say."""
    by_type: dict[int, list[_Cluster]] = {}
    for c in clusters:
        if c.type in _SYMPTOM_TYPES:
            by_type.setdefault(c.type, []).append(c)
    quals = set(_quality_words(note))
    temporal = _TEMPORAL.get(int(note.get("temporal", -1)))
    out: list[tuple[str, list[_Cluster]]] = []
    pain = by_type.get(0, []) + by_type.get(1, [])
    if pain:
        if temporal:
            label = "pain"
        elif 0 in by_type and 1 in by_type:
            label = "constant and intermittent pain"
        else:
            label = "constant pain" if 0 in by_type else "intermittent pain"
        out.append((label, pain))
    for t, label in ((2, "pins & needles"), (3, "numbness"), (4, "paraesthesia")):
        if t in by_type and label not in quals:
            out.append((label, by_type[t]))
    return out


def _extent_text(clusters: list[_Cluster]) -> str:
    """Compact where-is-it for one symptom type: 'bilateral mid lower leg to foot'."""
    cov = _significant(_merge_cov(clusters))
    groups: list[tuple[str | None, str]] = []
    for name in cov:
        s, base = _split_side(name)
        part = _anat(base)[0]
        if part != "other" and (s, part) not in groups:
            groups.append((s, part))
    bits: list[str] = []
    done: set = set()
    for side, part in groups:
        if (side, part) in done:
            continue
        other = _other(side)
        if other and (other, part) in groups:
            bits.append("bilateral " + _bilateral_span(cov, part))
            done.add((other, part))
        else:
            span = _span(_stations(cov, {side}, _axis(part), {part}))
            bits.append(f"{side} {span}" if side else span)
        done.add((side, part))
    return _join_and(bits)


def _fmt_nature_v2(note: dict[str, Any], clusters: list[_Cluster], version: int) -> str:
    sentences: list[str] = []
    voice = str(note.get("voice_note", "")).strip().rstrip(" ,;.")
    if voice:
        sentences.append(_cap(voice))

    temporal = _TEMPORAL.get(int(note.get("temporal", -1)))
    depth = _DEPTH.get(int(note.get("depth", -1)))
    quals = _quality_words(note)
    answer = ", ".join(x for x in (temporal, depth, _join_and(quals)) if x)
    sev = _severity(note, version)
    if sev:
        answer = f"{answer}; {sev}" if answer else sev
    if answer:
        sentences.append(_cap(answer))

    drawn = _drawn_types(note, clusters)
    if len(drawn) == 1:
        sentences.append(f"Drawn as {drawn[0][0]}")
    elif drawn:
        items = []
        for label, cls in drawn:
            ext = _extent_text(cls)
            items.append(f"{label} ({ext})" if ext else label)
        sentences.append("Drawn as " + _join_and(items))
    return ". ".join(sentences)


# ── Misc (strokes not attached to any note) ──────────────────────────────────

_PART_ORDER = ("head", "neck", "trunk", "upper limb", "lower limb", "other")


def _widespread_text(cls: list[_Cluster]) -> str:
    buckets = set().union(*(c.buckets for c in cls))
    parts = [p for p in _PART_ORDER if any(b[1] == p for b in buckets)]
    r = sum(c.side_pts["R"] for c in cls)
    l = sum(c.side_pts["L"] for c in cls)
    views = _views_note(cls)
    for side, n in (("L", l), ("R", r)):
        if r + l and n / (r + l) >= 0.85:
            return f"widespread over the {side} hemibody ({_join_and(parts)}){views}"
    return f"widespread ({_join_and(parts)}){views}"


def _cluster_spans(c: _Cluster) -> list[tuple[str | None, str, float]]:
    """(side, span text, sort rank) per side+axis chain within one cluster."""
    cov = _significant(c.cov)
    out = []
    seen: set = set()
    for name in cov:
        s, base = _split_side(name)
        part = _anat(base)[0]
        key = (s, _axis(part))
        if part == "other" or key in seen:
            continue
        seen.add(key)
        sts = _stations(cov, {s}, _axis(part))
        if sts:
            out.append((s, _span(sts), sts[0].rank))
    return out


def _misc_location_for(clusters: list[_Cluster]) -> str:
    bits: list[str] = []
    wide = [c for c in clusters if c.widespread]
    if wide:
        bits.append(_widespread_text(wide))
    # One entry per drawn area; identical L and R areas fold to "bilateral".
    spans: dict[str, tuple[set, float]] = {}
    for c in clusters:
        if c.widespread:
            continue
        for side, text, rank in _cluster_spans(c):
            sides, r = spans.get(text, (set(), rank))
            sides.add(side)
            spans[text] = (sides, min(r, rank))
    # Many small separate areas that together cover much of the body read
    # as widespread first, then the itemised list.
    small = [c for c in clusters if not c.widespread]
    union = set().union(*(c.buckets for c in small)) if small else set()
    if len(small) >= 3 and len(union) >= _WIDESPREAD_PARTS:
        both = {b[0] for b in union} >= {"R", "L"}
        bits.append("widespread and bilateral:" if both else "widespread:")
    for text, (sides, _r) in sorted(spans.items(), key=lambda kv: kv[1][1]):
        if {"R", "L"} <= sides:
            bits.append(f"bilateral {text}")
            sides = sides - {"R", "L"}
        for s in sorted(sides, key=lambda x: x or ""):
            bits.append(f"{s} {text}" if s else text)
    lat = sorted({_VIEW_NAMES[c.view] for c in clusters
                  if c.view in (2, 3) and c.n_unlabelled and not c.widespread})
    if lat:
        bits.append(f"{_join_and(lat)} view (unlabelled)")
    return ", ".join(bits).replace(":,", ":")


def _misc_type_label(t: int) -> str:
    return {0: "constant pain", 1: "intermittent pain"}.get(t, _SYMPTOM_NAMES.get(t, ""))


def _fmt_misc_v2(clusters: list[_Cluster]) -> tuple[str, str]:
    by_type: dict[int, list[_Cluster]] = {}
    for c in clusters:
        by_type.setdefault(c.type, []).append(c)
    types = sorted(by_type)
    if len(types) == 1:
        return (_cap(_misc_location_for(by_type[types[0]])),
                _cap(_misc_type_label(types[0])))
    loc = "; ".join(f"{_cap(_misc_type_label(t))}: {_misc_location_for(by_type[t])}"
                    for t in types)
    nat = _cap(_join_and([_misc_type_label(t) for t in types]))
    return loc, nat


# ── Legacy (sessions saved before region_coverage existed) ───────────────────

def _title_region(label: str) -> str:
    s = label.strip()
    return s[:1].upper() + s[1:] if s else s


def _legacy_location(note: dict[str, Any], dist_labels: list[str]) -> str:
    region = note.get("region_label", "").strip()
    extras = [r for r in dist_labels if r.strip() and r.strip() != region]
    parts: list[str] = []
    if region:
        parts.append(_title_region(region))
    if extras:
        parts.append("extending to " + ", ".join(_title_region(r) for r in extras))
    return "; ".join(parts)


def _legacy_nature(note: dict[str, Any], assoc_clusters: list[dict[str, Any]],
                   version: int = 4) -> str:
    severity = _severity(note, version)
    voice = note.get("voice_note", "").strip()
    if voice:
        return "; ".join([voice] + ([severity] if severity else []))
    seen_types: list[str] = []
    for cl in assoc_clusters:
        t = _SYMPTOM_NAMES.get(int(cl.get("type", -1)))
        if t and t not in seen_types:
            seen_types.append(t)
    temporal = _TEMPORAL.get(int(note.get("temporal", 0)))
    depth = _DEPTH.get(int(note.get("depth", 0)))
    if seen_types:
        parts = [", ".join(seen_types)]
    elif temporal:
        parts = [f"{temporal} symptoms"]
    else:
        parts = []
    if depth:
        parts.append(depth)
    quals = _quality_words(note)
    if quals:
        parts.append(", ".join(quals))
    if severity:
        parts.append(severity)
    return "; ".join(parts)


def _legacy_misc(misc_cls: list[dict[str, Any]]) -> tuple[str, str]:
    regions: list[str] = []
    types: list[str] = []
    for cl in misc_cls:
        r = cl.get("region_label", "").strip()
        if r and r not in regions:
            regions.append(r)
        t = _SYMPTOM_NAMES.get(int(cl.get("type", -1)))
        if t and t not in types:
            types.append(t)
    return ", ".join(_title_region(r) for r in regions), ", ".join(types)


# ── Public API ───────────────────────────────────────────────────────────────

def build_prefill(session_json: dict[str, Any]) -> dict[str, Any]:
    """
    Transform a parsed _session.json dict into pre-population data for Section 02.

    Returns:
        {
            "notes": [
                {
                    "stable_id": int,
                    "number": int,
                    "region": str,                 # the dot's region (primary site)
                    "location_distribution": str,
                    "nature": str,
                    "aggravating_factors": str,   # always "" — clinician fills
                    "easing_factors": str,         # always "" — clinician fills
                    "brief": str,
                },
                ...  (in note.number order)
            ],
            "misc": {"location_distribution": str, "nature": str},
            "schema_ok": bool,   # False if session is too old to have spatial data
        }
    """
    empty = {"notes": [], "misc": {"location_distribution": "", "nature": ""},
             "schema_ok": False}

    version = session_json.get("version", 0)
    if version < 3:
        return empty
    subj = session_json.get("subjective", {})
    if not subj:
        return empty

    raw_clusters = subj.get("stroke_clusters", [])
    notes = sorted(subj.get("notes", []), key=lambda n: n.get("number", 0))
    has_cov = bool(raw_clusters) and all("region_coverage" in c for c in raw_clusters)

    notes_out: list[dict[str, Any]] = []
    if has_cov:
        strokes_by_id = {int(s["id"]): s for s in subj.get("strokes", []) if "id" in s}
        clusters = [_Cluster(c, strokes_by_id) for c in raw_clusters if "id" in c]
        assoc = _associate(notes, clusters)
        claimed = {c.id for cl in assoc.values() for c in cl}
        for note in notes:
            sid = int(note.get("stable_id", -1))
            cls = assoc.get(sid, [])
            notes_out.append(_note_out(note,
                                       _fmt_location_v2(note, cls),
                                       _fmt_nature_v2(note, cls, version)))
        misc_cls = [c for c in clusters
                    if c.type in _SYMPTOM_TYPES and c.id not in claimed]
        misc_loc, misc_nat = _fmt_misc_v2(misc_cls) if misc_cls else ("", "")
    else:
        clusters_by_id = {int(cl["id"]): cl for cl in raw_clusters if "id" in cl}
        for note in notes:
            assoc_cls = [clusters_by_id[i] for i in
                         (int(x) for x in note.get("associated_cluster_ids", []))
                         if i in clusters_by_id
                         and int(clusters_by_id[i].get("type", -1)) in _SYMPTOM_TYPES]
            dist = [str(r) for r in note.get("distribution_labels", [])]
            notes_out.append(_note_out(note, _legacy_location(note, dist),
                                       _legacy_nature(note, assoc_cls, version)))
        misc_cls = [clusters_by_id[i] for i in
                    (int(x) for x in subj.get("misc_cluster_ids", []))
                    if i in clusters_by_id
                    and int(clusters_by_id[i].get("type", -1)) in _SYMPTOM_TYPES]
        misc_loc, misc_nat = _legacy_misc(misc_cls)

    return {
        "notes": notes_out,
        "misc": {"location_distribution": misc_loc, "nature": misc_nat},
        "schema_ok": True,
    }


def _note_out(note: dict[str, Any], location: str, nature: str) -> dict[str, Any]:
    return {
        "stable_id":             int(note.get("stable_id", -1)),
        "number":                int(note.get("number", 0)),
        "region":                str(note.get("region_label", "")).strip(),
        "location_distribution": location,
        "nature":                nature,
        "aggravating_factors":   "",
        "easing_factors":        "",
        # Clinician's own wording for the on-chart pin label — round-trips
        # both ways (bodychart persistence.c chart_note_text /
        # regen_note_text()). Passed through, never derived here.
        "brief":                 str(note.get("chart_note_text", "")),
    }


def prefill_is_empty(prefill: dict[str, Any]) -> bool:
    """True if there is nothing useful to pre-populate (no notes, no misc)."""
    if not prefill.get("schema_ok"):
        return True
    if prefill.get("notes"):
        return False
    misc = prefill.get("misc", {})
    return not (misc.get("location_distribution") or misc.get("nature"))
