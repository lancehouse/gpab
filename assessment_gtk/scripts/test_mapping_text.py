#!/usr/bin/env python3
"""Checks pab_assessment.mapping.build_prefill() — the body chart → Subjective
Location/Nature text — on synthetic session data only (no patient sessions).

Run from assessment_gtk/: .venv/bin/python scripts/test_mapping_text.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gpab_assessment import pab_path_bootstrap  # noqa: E402,F401
from pab_assessment.mapping import build_prefill  # noqa: E402

failures = 0


def check(label: str, cond: bool, got: str = "") -> None:
    global failures
    if not cond:
        failures += 1
        print(f"FAIL {label}\n     got: {got}")
    else:
        print(f"ok   {label}")


def cov(*entries):
    """entries: (name, n[, top, bottom])"""
    return [{"name": e[0], "n": e[1], "top": e[2] if len(e) > 2 else 0.0,
             "bottom": e[3] if len(e) > 3 else 1.0} for e in entries]


def session(notes, clusters):
    strokes = []
    out_clusters = []
    for i, c in enumerate(clusters):
        strokes.append({"id": i, "type": c["type"], "view": c["view"], "pts": c["pts"]})
        out_clusters.append({"id": i, "type": c["type"], "view": c["view"],
                             "centroid_bx": 0, "centroid_by": 0, "region_label": "",
                             "stroke_ids": [i], "region_coverage": c["cov"],
                             "n_pts": sum(e["n"] for e in c["cov"]) + c.get("unl", 0),
                             "n_unlabelled": c.get("unl", 0)})
    full_notes = []
    for i, n in enumerate(notes):
        base = {"stable_id": i, "number": i + 1, "temporal": -1, "depth": -1,
                "qualities": [], "low": -1, "high": -1}
        base.update(n)
        full_notes.append(base)
    return {"version": 4, "subjective": {"strokes": strokes, "notes": full_notes,
                                         "stroke_clusters": out_clusters}}


line = lambda x, y0, y1: [[x, y0 + (y1 - y0) * k / 10, 0.5] for k in range(11)]

# 1. Dot is the origin: long numbness thigh → foot, dot on the thigh.
s = session(
    [{"view": 0, "bx": 70, "by": 240, "region_label": "R anterior thigh",
      "temporal": 1, "depth": 0, "qualities": [10]}],
    [{"type": 3, "view": 0, "pts": line(70, 230, 380),
      "cov": cov(("R anterior thigh", 40, 0.1, 1), ("R anterior knee", 10),
                 ("R anterior shin", 30), ("R anterior ankle", 8), ("R dorsum foot", 8, 0, 0.5))},
     # tick right next to the dot must be ignored
     {"type": 5, "view": 0, "pts": line(72, 238, 242), "cov": cov(("L anterior thigh", 5))},
     # posterior numbness on the R sole joins via cross-view (same type/side/level)
     {"type": 3, "view": 1, "pts": line(110, 370, 380), "cov": cov(("R sole", 10))},
     # posterior L gluteal numbness is NOT at a matching level → stays Misc
     {"type": 3, "view": 1, "pts": line(80, 170, 185), "cov": cov(("L gluteal", 10))}])
p = build_prefill(s)
loc = p["notes"][0]["location_distribution"]
check("origin + distal chain", loc.startswith("R anterior thigh (primary), extending distally through the knee, shin and ankle to the foot"), loc)
check("cross-view sole joined (anterior and posterior)", "(anterior and posterior)" in loc, loc)
check("tick never counted", "L anterior thigh" not in loc and "L thigh" not in loc, loc)
check("unmatched level stays in Misc", "gluteal" in p["misc"]["location_distribution"], p["misc"]["location_distribution"])
nat = p["notes"][0]["nature"]
check("answers kept, numbness not repeated", nat == "Intermittent, superficial, numbness", nat)
check("header region", p["notes"][0]["region"] == "R anterior thigh", p["notes"][0]["region"])

# 2. Opposite-side cluster near the dot is not claimed unless it touches.
s = session(
    [{"view": 0, "bx": 118, "by": 360, "region_label": "L anterior ankle"}],
    [{"type": 1, "view": 0, "pts": line(118, 355, 365), "cov": cov(("L anterior ankle", 20))},
     {"type": 1, "view": 0, "pts": line(96, 355, 365), "cov": cov(("R anterior ankle", 20))}])
p = build_prefill(s)
loc = p["notes"][0]["location_distribution"]
check("other-side cluster 22bu away not claimed", "R" not in loc.replace("(primary)", ""), loc)
check("...goes to Misc", "R ankle" in p["misc"]["location_distribution"], p["misc"]["location_distribution"])

# 3. Widespread cluster never attaches to a note; Misc calls it a hemibody.
wide = cov(("L forehead", 10), ("L anterior chest", 10), ("L anterior forearm", 10),
           ("L anterior thigh", 10), ("L anterior shin", 10), ("anterior abdomen", 2))
s = session([{"view": 0, "bx": 120, "by": 330, "region_label": "L anterior shin"}],
            [{"type": 1, "view": 0, "pts": line(120, 20, 340), "cov": wide}])
p = build_prefill(s)
check("widespread not on note", p["notes"][0]["location_distribution"] == "L anterior shin (primary)",
      p["notes"][0]["location_distribution"])
check("widespread → hemibody in Misc", "L hemibody" in p["misc"]["location_distribution"],
      p["misc"]["location_distribution"])

# 4. Bilateral lower limbs from an ankle dot, with mid-shin extent.
s = session(
    [{"view": 0, "bx": 118, "by": 360, "region_label": "L anterior ankle", "low": 5, "high": 5,
      "qualities": [9]}],
    [{"type": 2, "view": 0, "pts": line(118, 330, 380),
      "cov": cov(("L anterior shin", 20, 0.5, 1), ("L anterior ankle", 10), ("L dorsum foot", 10),
                 ("R anterior shin", 20, 0.45, 1), ("R anterior ankle", 10), ("R dorsum foot", 10))}])
p = build_prefill(s)
loc = p["notes"][0]["location_distribution"]
check("bilateral + mid shin", loc == "L anterior ankle (primary); bilateral lower limbs, mid shin to dorsum of foot", loc)
check("no doubled pins & needles", p["notes"][0]["nature"] == "Pins & needles; 5/10", p["notes"][0]["nature"])

# 4b. Bilateral limb never spills into the trunk: L strokes lumbar → foot,
#     R strokes shin → foot, dot on the L ankle.
s = session(
    [{"view": 0, "bx": 118, "by": 360, "region_label": "L anterior ankle"}],
    [{"type": 1, "view": 0, "pts": line(118, 150, 380),
      "cov": cov(("L lower lumbar", 15), ("L anterior thigh", 15), ("L anterior shin", 15),
                 ("L anterior ankle", 10), ("L dorsum foot", 10))},
     {"type": 1, "view": 0, "pts": line(115, 330, 380),
      "cov": cov(("R anterior shin", 15), ("R anterior ankle", 10), ("R dorsum foot", 10))}])
loc = build_prefill(s)["notes"][0]["location_distribution"]
check("bilateral limb only, lumbar separate",
      loc == "L anterior ankle (primary); bilateral lower limbs, thigh to dorsum of foot; also L lower lumbar region", loc)

# 5. Typed / dictated text keeps the tapped answers alongside it.
s = session([{"view": 1, "bx": 100, "by": 160, "region_label": "L lower lumbar",
              "voice_note": "Knife twisting,", "temporal": 0, "depth": 1, "low": 5, "high": 10}],
            [{"type": 0, "view": 1, "pts": line(100, 155, 165), "cov": cov(("L lower lumbar", 30))}])
nat = build_prefill(s)["notes"][0]["nature"]
check("free text + answers", nat == "Knife twisting. Constant, deep; 5–10/10. Drawn as pain", nat)

# 6. Sessions saved before region_coverage existed use the legacy text.
legacy = {"version": 4, "subjective": {
    "notes": [{"stable_id": 0, "number": 1, "region_label": "R anterior shoulder",
               "distribution_labels": ["R anterior shoulder"], "associated_cluster_ids": [0],
               "temporal": 1, "depth": 0, "qualities": [2], "low": 4, "high": 4}],
    "stroke_clusters": [{"id": 0, "type": 0, "view": 0, "region_label": "R anterior shoulder"}],
    "misc_cluster_ids": []}}
nat = build_prefill(legacy)["notes"][0]["nature"]
check("legacy fallback", nat == "pain (constant); superficial; aching; 4/10", nat)

print(f"\n{failures} failure(s)")
sys.exit(1 if failures else 0)
