"""pab-intake `_intake.json` import — scoring, field mapping and raw-text render.

No GTK import: pure data in, data out, so it's testable without a window.
The Outcome Measures section owns the file dialog and the fill-blanks-only
apply step; this module only answers "what would this file put where".

PROMs gpab has fields for are scored into them (DASS-21, PCS, PSEQ /
PSEQ-2, PCL-5, ISI, PBAS) or copied (BPI interference, PHQ-4 items, PSFS
activity names). Every other PROM — and every answer with no
gpab field — goes into the `intake_raw` text field only, via render_raw().
PROMs with a scoring rule but no gpab field (BPI, PHQ-4, PHQ-9, DN4,
painDETECT, NDI, LEFS, QuickDASH, UEFI) get their scores on the raw
render's "Score:" line only, from compute_scores().

Scoring rules (subscale item lists confirmed by the user, 2026-10-29;
the later PROMs per prom-scoring-reference.md in pab-intake, reviewed by the
user 2026-11-04): a score is only produced when every item it needs is
answered — no prorating — except where the instrument itself allows
missing items (BPI interference ≥4 of 7, QuickDASH ≥10 of 11). Each score
needs only its own items, so e.g. PSEQ-2 can import while the PSEQ total
can't.

Requires schema_version 2 files: v2 embeds each PROM's item text and answer
options (`prom_defs`), so the raw render never needs validated wording
duplicated here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SUPPORTED_SCHEMA = 2


class IntakeError(Exception):
    pass


# 1-based item numbers exactly as published; converted to 0-based in _sum().
_DASS_DEP = [3, 5, 10, 13, 16, 17, 21]
_DASS_ANX = [2, 4, 7, 9, 15, 19, 20]
_DASS_STR = [1, 6, 8, 11, 12, 14, 18]
_PCS_RUM = [8, 9, 10, 11]
_PCS_MAG = [6, 7, 13]
_PCS_HELP = [1, 2, 3, 4, 5, 12]
_PSEQ2 = [5, 9]

_BPI_SEVERITY = ["worst", "least", "average", "now"]
_BPI_INTERFERENCE = ["activity", "mood", "walking", "work", "relations", "sleep", "enjoyment"]
_PHQ4_ITEMS = ["nervous", "worry", "noint", "depressed"]
_PHQ9_ITEMS = ["noint", "depressed", "sleep", "tired", "appetite", "guilty",
               "concentrating", "movement", "selfharm"]      # item 10 is not scored
_DN4_ITEMS = ["q1_burning", "q1_cold", "q1_shocks", "q2_tingling", "q2_pins_needles",
              "q2_numbness", "q2_itching"]               # interview items only (DN4i)
_PDQ_SENSORY = ["burning", "tingling", "light_touch", "elec_shocks", "temp_pain",
                "numbness", "pressure"]
_PDQ_PATTERN = {"a": 0, "b": -1, "c": 1, "d": 1}


def load_intake(path: str | Path) -> dict:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise IntakeError(f"Couldn't read {Path(path).name}: {e}") from e
    if not isinstance(data, dict) or "proms" not in data:
        raise IntakeError(f"{Path(path).name} isn't a pab-intake file")
    if data.get("schema_version") != SUPPORTED_SCHEMA:
        raise IntakeError(
            f"{Path(path).name} is intake schema v{data.get('schema_version')}; "
            f"this import needs v{SUPPORTED_SCHEMA} — re-export from a current pab-intake.html"
        )
    return data


# ── Responses ────────────────────────────────────────────────────────────────

def _responses(intake: dict, prom: str):
    """Stored answers for one PROM: a list (numeric-keyed PROMs) or a dict."""
    r = (intake.get("proms") or {}).get(prom)
    if isinstance(r, dict) and isinstance(r.get("items"), list):
        return r["items"]
    return r


def _valid_values(intake: dict, prom: str, key) -> set | None:
    for item in (intake.get("prom_defs") or {}).get(prom, {}).get("items", []):
        if item["key"] == key:
            return {o["v"] for o in item.get("options") or []} or None
    return None


def _answer(intake: dict, prom: str, key):
    """One answer, or None if missing, skipped, or outside the item's
    option set (a value gpab can't vouch for is treated as missing)."""
    r = _responses(intake, prom)
    if isinstance(r, list):
        v = r[key] if isinstance(key, int) and 0 <= key < len(r) else None
    elif isinstance(r, dict):
        v = r.get(key)
    else:
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    valid = _valid_values(intake, prom, key)
    if valid is not None and v not in valid:
        return None
    return v


def _sum(intake: dict, prom: str, items_1based: list[int]) -> int | None:
    vals = [_answer(intake, prom, n - 1) for n in items_1based]
    return None if any(v is None for v in vals) else sum(vals)


def _sum_keys(intake: dict, prom: str, keys: list) -> int | None:
    vals = [_answer(intake, prom, k) for k in keys]
    return None if any(v is None for v in vals) else sum(vals)


def _item_keys(intake: dict, prom: str) -> list:
    return [it["key"] for it in (intake.get("prom_defs") or {}).get(prom, {}).get("items", [])]


def _n_items(intake: dict, prom: str) -> int:
    return len(_item_keys(intake, prom))


def _mean(vals: list[int]) -> str:
    return f"{sum(vals) / len(vals):.1f}"


# ── Field mapping ────────────────────────────────────────────────────────────

def compute_fields(intake: dict) -> dict[str, str]:
    """gpab outcome-measure field id -> value text, for every field this
    intake can fill. Fields it can't fill (incomplete PROM, PROM not done)
    are simply absent."""
    proms = intake.get("proms") or {}
    out: dict[str, str] = {}

    def put(fid: str, v) -> None:
        if v is not None and v != "":
            out[fid] = str(v)

    if "psfs" in proms:
        r = proms["psfs"] or {}
        # Names only: the GTK form has no psfs_act_N_score widgets. Each
        # activity's score stays separate (the PSFS is not summed) and shows
        # in the raw render.
        for n in (1, 2, 3):
            put(f"psfs_act_{n}", (r.get(f"act_{n}_name") or "").strip())

    if "bpi" in proms:
        for k in _BPI_INTERFERENCE:
            put(f"bpi_{k}", _answer(intake, "bpi", k))

    if "dass21" in proms:
        # ×2: gpab's DASS bands (e.g. depression "Extremely severe" ≥28) are
        # on the DASS-42-equivalent scale — unreachable from a raw /21 sum.
        for fid, items in (("dass_dep_score", _DASS_DEP), ("dass_anx_score", _DASS_ANX),
                           ("dass_str_score", _DASS_STR)):
            s = _sum(intake, "dass21", items)
            put(fid, None if s is None else s * 2)

    if "phq4" in proms:
        for k in _PHQ4_ITEMS:
            put(f"phq4_{k}", _answer(intake, "phq4", k))

    if "pcs" in proms:
        put("pcs_rum_score", _sum(intake, "pcs", _PCS_RUM))
        put("pcs_mag_score", _sum(intake, "pcs", _PCS_MAG))
        put("pcs_help_score", _sum(intake, "pcs", _PCS_HELP))
        put("pcs_total_score", _sum(intake, "pcs", list(range(1, 14))))

    if "pseq" in proms:
        put("pseq_score", _sum(intake, "pseq", list(range(1, 11))))
        put("pseq2_score", _sum(intake, "pseq", _PSEQ2))

    if "pcl5" in proms:
        put("pcl5_score", _sum(intake, "pcl5", list(range(1, 21))))

    if "isi" in proms:
        put("isi_score", _sum(intake, "isi", list(range(1, 8))))

    if "pbas" in proms:
        # Mean of the 10 items, /10 (Afolalu 2016: "the total score is based
        # on the average score of all items").
        s = _sum(intake, "pbas", list(range(1, 11)))
        put("pbas_score", None if s is None else f"{s / 10:.1f}")

    return out


# ── Scores with no gpab field ────────────────────────────────────────────────
# Shown on the raw render's "Score:" line only. Each function returns the
# line's parts, or None when the PROM can't be scored at all.

def _band(s: float, bands: list[tuple[float, str]]) -> str:
    """bands: (upper bound inclusive, label), ascending; last label catches the rest."""
    for hi, label in bands:
        if s <= hi:
            return label
    return bands[-1][1]


def _score_bpi(intake: dict) -> list[str]:
    sev = [_answer(intake, "bpi", k) for k in _BPI_SEVERITY]
    parts = [f"Severity {_mean(sev)}/10" if None not in sev else "Severity – (incomplete)"]
    intf = [v for v in (_answer(intake, "bpi", k) for k in _BPI_INTERFERENCE) if v is not None]
    parts.append(f"Interference {_mean(intf)}/10" if len(intf) >= 4
                 else "Interference – (fewer than 4 of 7 answered)")
    worst = _answer(intake, "bpi", "worst")
    if worst is not None:
        parts.append("Worst pain " + _band(worst, [(0, "none"), (4, "mild"), (6, "moderate"),
                                                    (10, "severe")]))
    return parts


def _score_phq4(intake: dict) -> list[str]:
    parts = []
    for label, keys in (("Anxiety (GAD-2)", ["nervous", "worry"]),
                        ("Depression (PHQ-2)", ["noint", "depressed"])):
        s = _sum_keys(intake, "phq4", keys)
        parts.append(f"{label} – (incomplete)" if s is None else
                     f"{label} {s}/6 {'positive (≥3)' if s >= 3 else 'negative (<3)'}")
    return parts


def _score_phq9(intake: dict) -> list[str]:
    s = _sum_keys(intake, "phq9", _PHQ9_ITEMS)
    parts = ["Total – (incomplete)" if s is None else
             f"Total {s}/27 " + _band(s, [(4, "minimal"), (9, "mild"), (14, "moderate"),
                                          (19, "moderately severe"), (27, "severe")])]
    item9 = _answer(intake, "phq9", "selfharm")
    if item9:
        parts.append(f"ITEM 9 (self-harm) = {item9}/3 — FOLLOW UP")
    return parts


def _score_dn4(intake: dict) -> list[str]:
    s = _sum_keys(intake, "dn4", _DN4_ITEMS)
    if s is None:
        return ["DN4 interview – (incomplete)"]
    return [f"DN4 interview {s}/7 {'positive (≥3)' if s >= 3 else 'negative (<3)'}"]


def _score_paindetect(intake: dict) -> list[str]:
    sensory = _sum_keys(intake, "paindetect", _PDQ_SENSORY)
    pattern = ((intake.get("proms") or {}).get("paindetect") or {}).get("pattern")
    radiation = _answer(intake, "paindetect", "radiation")
    if sensory is None or pattern not in _PDQ_PATTERN or radiation is None:
        return ["Total – (incomplete)"]
    s = sensory + _PDQ_PATTERN[pattern] + 2 * radiation
    return [f"Total {s} (−1 to 38) neuropathic component "
            + _band(s, [(12, "unlikely"), (18, "unclear"), (38, "likely")])]


def _score_ndi(intake: dict) -> list[str]:
    s = _sum_keys(intake, "ndi", _item_keys(intake, "ndi"))
    if s is None:
        return ["Total – (incomplete)"]
    return [f"Total {s}/50 ({s * 2}%) " + _band(s, [(4, "no disability"), (14, "mild"),
                                                   (24, "moderate"), (34, "severe"),
                                                   (50, "complete")])]


def _score_raw_sum(prom: str, hi: int):
    def score(intake: dict) -> list[str]:
        s = _sum_keys(intake, prom, _item_keys(intake, prom))
        return ["Total – (incomplete)" if s is None else f"Total {s}/{hi}"]
    return score


def _score_quickdash(intake: dict) -> list[str]:
    vals = [v for v in (_answer(intake, "quickdash", k) for k in _item_keys(intake, "quickdash"))
            if v is not None]
    if len(vals) < 10:
        return ["Score – (more than 1 item missing)"]
    return [f"Score {(sum(vals) / len(vals) - 1) * 25:.1f}/100 (n = {len(vals)})"]


_SCORE_FUNCS = {
    "bpi": _score_bpi,
    "phq4": _score_phq4,
    "phq9": _score_phq9,
    "dn4": _score_dn4,
    "paindetect": _score_paindetect,
    "ndi": _score_ndi,
    "lefs": _score_raw_sum("lefs", 80),
    "uefi": _score_raw_sum("uefi", 80),
    "quickdash": _score_quickdash,
}


def compute_scores(intake: dict) -> dict[str, list[str]]:
    """PROM key -> score-line parts, for answered PROMs gpab has no field for."""
    proms = intake.get("proms") or {}
    return {k: f(intake) for k, f in _SCORE_FUNCS.items() if k in proms}


# ── Raw-text render ──────────────────────────────────────────────────────────
# Laid out for proportional fonts too (the EMR the report is pasted into
# uses one), so nothing relies on padding text into columns. Each row
# starts with the bar, then [n/max], then the item text, on one unwrapped
# line. Every answered bar is the same characters (20 "_" + one MARK) in
# a different order, so it renders the same width in any font and the
# text after it starts at the same point. MARK is "#": no Markdown meaning
# mid-line (unlike "*", which pandoc ate as emphasis), and as wide as "_"
# in Arial-metric fonts, so an unanswered all-"_" bar matches too. Numbers are padded with FIGURE
# SPACE (U+2007, digit-width in proportional fonts), not a plain space.
# Answer wording is deliberately omitted (rapid visual screening); a PROM
# whose items share one scale gets a single left/right legend instead.

BAR_W = 21           # bar interior; spaces 0–10, 0–4 and 0–5 scales exactly
FIG = "\u2007"
MARK = "#"
RULE = "=" * 60


def _bar(options: list[dict], value) -> str:
    # Plotted by the order options were shown to the patient, so MARK sits
    # where they tapped — not by stored value (some scales are stored
    # reversed, e.g. WOMAC/HOOS None=4, intentionally).
    cells = ["_"] * BAR_W
    vs = [o["v"] for o in options]
    if value in vs and len(vs) > 1:
        cells[round(vs.index(value) * (BAR_W - 1) / (len(vs) - 1))] = MARK
    return "|" + "".join(cells) + "|"


def _bracket(options: list[dict], value, width: int) -> str:
    vs = [o["v"] for o in options]
    lo, hi = min(vs), max(vs)
    shown = "–" if value is None else str(value)
    s = f"{shown}/{hi}" if lo == 0 else f"{shown} ({lo}–{hi})"
    return "[" + FIG * (width - len(s)) + s + "]"


def _bracket_width(items: list[dict]) -> int:
    w = 0
    for item in items:
        opts = item.get("options")
        if opts:
            vs = [o["v"] for o in opts]
            lo, hi = min(vs), max(vs)
            widest = max(len(str(v)) for v in vs)
            w = max(w, widest + len(f"/{hi}") if lo == 0 else widest + len(f" ({lo}–{hi})"),
                    3 if _is_yes_no(opts) else 0)
    return w


def _is_yes_no(opts: list[dict]) -> bool:
    return sorted(o["v"] for o in opts) == [0, 1] and {o["text"] for o in opts} == {"Yes", "No"}


def _legend(items: list[dict]) -> str | None:
    """'left = X · right = Y' when every scaled item shares one scale."""
    ends = set()
    for item in items:
        opts = item.get("options")
        if not opts or _is_yes_no(opts):
            continue
        if item.get("type") == "numeric":
            ends.add((len(opts), item.get("low_label") or "", item.get("high_label") or ""))
        else:
            ends.add((len(opts), opts[0]["text"], opts[-1]["text"]))
    if len(ends) != 1:
        return None
    _, left, right = ends.pop()
    return f"left = {left} · right = {right}" if left and right else None


def _num(n: int, width: int) -> str:
    return FIG * (width - len(str(n))) + f"{n}."


def _render_psfs(r: dict) -> list[str]:
    opts = [{"v": v, "text": ""} for v in range(11)]
    out = ["left = unable to do at all because of pain · right = no difficulty at all"]
    for n in (1, 2, 3):
        name = (r.get(f"act_{n}_name") or "").strip()
        if not name:
            continue
        score = r.get(f"act_{n}_score")
        score = score if score in range(11) else None
        out.append(f"{_bar(opts, score)} {_bracket(opts, score, 5)} {n}. {name}")
    return out if len(out) > 1 else ["(no activities entered)"]


def _render_prom(intake: dict, key: str, d: dict) -> list[str]:
    title = f"{d.get('abbr', key)} — {d.get('name', '')}".rstrip(" —")
    out = [title, RULE]
    if d.get("flow") == "psfs":
        return out + _render_psfs((intake.get("proms") or {}).get(key) or {})

    items = d.get("items", [])
    resp = _responses(intake, key)
    bw = _bracket_width(items)
    nw = len(str(len(items)))
    legend = _legend(items)
    if legend:
        out.append(legend)
    answered = 0
    for n, item in enumerate(items, 1):
        if item.get("section"):
            out += ["", item["section"]]
        if isinstance(resp, list):
            v = resp[item["key"]] if isinstance(item["key"], int) and item["key"] < len(resp) else None
        else:
            v = (resp or {}).get(item["key"])
        if v is not None and v != "":
            answered += 1
        # Some PROMs' item text already carries its own "1." numbering.
        item_text = re.sub(r"^\d+\.\s*", "", item["text"])
        text = f"{_num(n, nw)} {item_text}"
        opts = item.get("options")
        if not opts:                                       # free text
            out.append(f"{text} → {v if v else '(blank)'}")
            continue
        if _is_yes_no(opts):
            # By value, No left / Yes right, regardless of on-screen order.
            yn = [{"v": 0, "text": "No"}, {"v": 1, "text": "Yes"}]
            shown = v if v in (0, 1) else None
            answer = {0: "No", 1: "Yes"}.get(shown, "–")
            pad = FIG * max(bw - len(answer), 0)
            out.append(f"{_bar(yn, shown)} [{pad}{answer}] {text}")
            continue
        shown = v if v in [o["v"] for o in opts] else None
        note = "" if shown is not None or v is None else f"  (unrecognised answer: {v!r})"
        out.append(f"{_bar(opts, shown)} {_bracket(opts, shown, bw)} {text}{note}")
    out.append(f"({answered}/{len(items)} items answered)")
    return out


# Score lines reuse compute_fields (and compute_scores for PROMs with no
# gpab field), so the render only ever shows scores gpab actually calculates.
_SCORE_LINES = {
    "dass21": [("Depression", "dass_dep_score", 42), ("Anxiety", "dass_anx_score", 42),
               ("Stress", "dass_str_score", 42)],
    "pcs":    [("Rumination", "pcs_rum_score", 16), ("Magnification", "pcs_mag_score", 12),
               ("Helplessness", "pcs_help_score", 24), ("Total", "pcs_total_score", 52)],
    "pseq":   [("PSEQ", "pseq_score", 60), ("PSEQ-2 (items 5, 9)", "pseq2_score", 12)],
    "pcl5":   [("Total", "pcl5_score", 80)],
    "isi":    [("Total", "isi_score", 28)],
    "pbas":   [("Mean", "pbas_score", 10)],
}


def _score_line(fields: dict[str, str], key: str, scores: dict[str, list[str]]) -> str:
    if key in scores:
        return "Score: " + " · ".join(scores[key])
    if key not in _SCORE_LINES:
        return "Score: not calculated (no scoring rule in gpab)"
    parts = [f"{label} {fields[fid]}/{hi}" if fid in fields else f"{label} – (incomplete)"
             for label, fid, hi in _SCORE_LINES[key]]
    note = {"dass21": " (×2, DASS-42 scale)",
            "pbas": f" (sum {round(float(fields['pbas_score']) * 10)}/100)"
                    if "pbas_score" in fields else ""}.get(key, "")
    return "Score: " + " · ".join(parts) + note


def render_raw(intake: dict) -> str:
    """Every PROM in the intake, item by item: bar, [n/max], item text."""
    defs = intake.get("prom_defs") or {}
    proms = intake.get("proms") or {}
    order = [k for k in intake.get("battery", []) if k in proms] + \
            [k for k in proms if k not in intake.get("battery", [])]
    fields = compute_fields(intake)
    scores = compute_scores(intake)
    blocks = [f"Patient intake {intake.get('session_code', '')}".rstrip()]
    for key in order:
        if key not in defs:
            blocks.append(f"{key}\n{RULE}\n(no item definitions in file — answers not shown)")
            continue
        lines = _render_prom(intake, key, defs[key])
        if defs[key].get("flow") != "psfs":
            lines.append(_score_line(fields, key, scores))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
