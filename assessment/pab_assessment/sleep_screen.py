"""Sleep dysfunction screen — pure functions, stdlib only (no UI, no pydantic).

Imported by storage.py (reports), and gpab's yaml_subsection.py / outcome_measures.py
(live prompts), so every consumer applies the same rules.
"""

import re
# ---------------------------------------------------------------------------
# Sleep dysfunction screen (gpab, 2026-11-16) — the 3-step flowchart of
# Shepherd, Neilson & Siengsukon 2026 (JOSPT Open 4(1):12-22, Figure 1).
# Pure functions: the GTK Sleep subsection's live prompts, Outcome Measures'
# STOP-BANG total and both storage.py report generators all call these, so
# the trigger rules live in exactly one place.
#
# User decisions 2026-11-16 (where the figure is ambiguous or differs from the
# existing fields):
#   - "Sometimes" (well rested) counts as NOT well rested → triggers Step 2.
#   - Sleep apnea → STOP-BANG is triggered by Step 3 Q1 AND Q2 AND Q3 all Yes
#     (the figure's "Yes to Q1-3?" read literally).
# ---------------------------------------------------------------------------

SLEEP_SCREEN_REFERENCE = (
    "Shepherd MH, Neilson BD, Siengsukon CF. The Pain of Poor Sleep: A "
    "Clinician's Guide to Assessing and Addressing Sleep Dysfunction in People "
    "With Musculoskeletal Pain Conditions. JOSPT Open 2026;4(1):12-22. "
    "doi:10.2519/josptopen.2025.0198"
)

# Outcome Measures STOP-BANG items, in questionnaire order. The first four
# (S, T, O, P) are the "STOP" items the referral rule counts separately.
STOPBANG_ITEMS = (
    "stopbang_snoring", "stopbang_tired", "stopbang_observed", "stopbang_pressure",
    "stopbang_bmi", "stopbang_age", "stopbang_neck", "stopbang_male",
)


def _yes(val) -> bool:
    return val is True or (isinstance(val, str) and val.strip().lower() == "yes")


def _no(val) -> bool:
    return val is False or (isinstance(val, str) and val.strip().lower() == "no")


def parse_sleep_hours(s) -> float | None:
    """First number in a free-text hours answer ("6", "6.5 h", "6-7", "5 or so").
    A range reads as its lower bound. None when there is no number."""
    m = re.search(r"\d+(?:\.\d+)?", str(s or ""))
    return float(m.group()) if m else None


def sleep_screen_step1(subj: dict) -> str:
    """Step 1 (general sleep screening) result line, or "" when not enough answered."""
    hours = parse_sleep_hours(subj.get("sleep_hours_typical"))
    rested = (subj.get("sleep_feels_rested") or "").strip().lower()
    quality = (subj.get("sleep_quality_4pt") or "").strip().lower()
    reasons = []
    if hours is not None and hours < 7:
        reasons.append(f"<7 h sleep ({hours:g} h)")
    if rested in ("no", "sometimes"):
        reasons.append("not well rested" + (" (sometimes)" if rested == "sometimes" else ""))
    if quality in ("fairly bad", "very bad"):
        reasons.append(f"rates sleep {quality}")
    if reasons:
        return "Positive (" + "; ".join(reasons) + ") → Step 2"
    if hours is not None and rested and quality:
        return "Negative (≥7 h, well rested, sleep quality good)"
    return ""


def sleep_screen_step2(subj: dict) -> str:
    """Step 2 (sleep dysfunction vs pain condition) result line, or ""."""
    impacts = subj.get("sleep_pain_impacts")
    before = subj.get("sleep_issues_before_pain")
    contrib = subj.get("sleep_pain_contributing")
    reasons = []
    if _no(impacts):
        reasons.append("pain not impacting sleep")
    if _yes(before):
        reasons.append("sleep issues began before the pain condition")
    if _no(contrib):
        reasons.append("pain not judged to be contributing")
    if reasons:
        return "→ Step 3 (" + "; ".join(reasons) + ")"
    if _yes(impacts) and (_no(before) or _yes(contrib)):
        return "Sleep issues appear related to the pain condition — flowchart does not direct to Step 3"
    return ""


def sleep_screen_step3(subj: dict) -> list[str]:
    """Step 3 ("big three") — one line per indicated tool; [] if none/unanswered."""
    q = [subj.get(k) for k in ("sleep_s3_insomnia", "sleep_s3_daily_function",
                                "sleep_s3_apnea", "sleep_s3_rls")]
    out = []
    if _yes(q[0]) and _yes(q[1]):
        out.append("Insomnia: administer ISI (Outcome Measures) — >15 = refer to "
                   "physician for further sleep assessment")
    if _yes(q[3]):
        out.append("Restless legs: administer RLS-DI (Outcome Measures) — consider whether "
                   "another condition (e.g. neuropathy) explains the Yes; refer to physician "
                   "to determine RLS, or if treating comorbid symptoms disrupting sleep is warranted")
    if _yes(q[0]) and _yes(q[1]) and _yes(q[2]):
        out.append("Sleep apnea: administer STOP-BANG (Outcome Measures)")
    if not out and all(_yes(v) or _no(v) for v in q):
        out.append("No screening tool indicated")
    return out


def stopbang_result(om: dict) -> str:
    """STOP-BANG total + the figure's referral rule, or "" with nothing answered.

    REFER when ≥5 Yes, OR ≥2 Yes on the STOP items plus BMI >35 kg/m², neck
    circumference >40 cm (16 in) or male."""
    vals = [om.get(k) for k in STOPBANG_ITEMS]
    answered = sum(1 for v in vals if _yes(v) or _no(v))
    if not answered:
        return ""
    score = sum(1 for v in vals if _yes(v))
    stop = sum(1 for v in vals[:4] if _yes(v))
    bang_extra = [n for n, v in zip(("BMI >35", "neck >40 cm", "male"),
                                    (vals[4], vals[6], vals[7])) if _yes(v)]
    text = f"{score}/8"
    if score >= 5:
        text += " — REFER (≥5 yes)"
    elif stop >= 2 and bang_extra:
        text += f" — REFER (≥2 STOP yes + {', '.join(bang_extra)})"
    else:
        text += " — referral criteria not met" + (" yet" if answered < 8 else "")
    if answered < 8:
        text += f" ({8 - answered} unanswered)"
    return text



# ---------------------------------------------------------------------------
# RLS-DI — Restless Legs Syndrome Diagnostic Index (added 2026-11-16, from the
# user's form sheet ~/Documents/STP/PROM/RLS-DI.jpg: Beneš, Somni bene
# Institute, Version 3.2 / 03 June 2008). Item scores are copied from that
# sheet. The sheet states no cut-off, so none is applied here.
#
# Items 1-5 (essential criteria): asked of the patient over the past 7 days.
# Items 6-10 (associated/supportive): assessed by the clinician from questioning,
# records and findings; "Not done" (not assessable) scores 0. Item 6 has no
# "Not done" column on the sheet.
# Stored value = the chip label.
# ---------------------------------------------------------------------------

_RLSDI_ESSENTIAL = (("Regular", 2), ("Occasional", 1))
RLSDI_ITEMS: tuple[tuple[str, str, tuple[tuple[str, int], ...]], ...] = (
    ("rlsdi_1", "Do you feel an urge to move your legs (arms)?",
     _RLSDI_ESSENTIAL + (("Not present", -4),)),
    ("rlsdi_2", "When feeling an urge to move, do you experience unpleasant sensations "
                "in your legs (arms) such as tingling, burning, cramps, pain?",
     _RLSDI_ESSENTIAL + (("Not present", -1),)),
    ("rlsdi_3", "Does the urge to move / unpleasant sensations begin or worsen when you "
                "are at rest (lying, sitting) or when you are inactive?",
     _RLSDI_ESSENTIAL + (("Not present", -4),)),
    ("rlsdi_4", "Does moving partially or completely relieve the urge to move / "
                "unpleasant sensations (e.g. walking or stretching)?",
     _RLSDI_ESSENTIAL + (("Not present", -4),)),
    ("rlsdi_5", "Does the urge to move / unpleasant sensations increase in the evening or "
                "at night compared to the day? (Worse at night than during the day, or occur "
                "only in the evening or at night. In severe RLS this must have been "
                "previously present.)",
     _RLSDI_ESSENTIAL + (("Not present", -1),)),
    ("rlsdi_6", "Sleep disturbance in the past 7 days (prolonged time to fall asleep and/or "
                "sleep interrupted and/or shortened sleep duration)?",
     (("Definite", 2), ("Uncertain", 1), ("No", -1))),
    ("rlsdi_7", "A first-degree relative (parents, siblings, children) suffers from the "
                "urge to move / unpleasant sensations (items 1-5)?",
     (("Definite", 2), ("Uncertain", 1), ("No", 0), ("Not done", 0))),
    ("rlsdi_8", "Urge to move / unpleasant sensations ever improved with dopaminergic "
                "therapy (any previous or current L-dopa or dopamine agonist)?",
     (("Definite", 2), ("Uncertain", 1), ("No", -4), ("Not done", 0))),
    ("rlsdi_9", "Objective findings of PLM in PSG / actimetry and/or SIT (e.g. PLM/h >15 "
                "and/or PLMS arousal index >5/h and/or PLMW/h >15)?",
     (("Definite", 2), ("Uncertain", 1), ("No", -2), ("Not done", 0))),
    ("rlsdi_10", "Can the urge to move / unpleasant sensations be satisfactorily explained "
                 "by other medical factors / concomitant diseases (e.g. muscle cramps, "
                 "positional discomfort, polyneuropathy)? Score \"No\" (2) if due to "
                 "conditions that can cause a secondary RLS (e.g. anaemia).",
     (("Definite", -4), ("Uncertain", -1), ("No", 2), ("Not done", 0))),
)
RLSDI_ITEM_IDS = tuple(fid for fid, _q, _opts in RLSDI_ITEMS)


def rlsdi_result(om: dict) -> str:
    """RLS-DI items 1-5 sum score + total (items 1-10), or "" with nothing answered.

    Counts only answered items; when any are unanswered the line says how many
    (a partial total is not comparable to a full one)."""
    sums = [0, 0]
    answered = [0, 0]
    for i, (fid, _q, opts) in enumerate(RLSDI_ITEMS):
        val = om.get(fid)
        score = dict(opts).get(val) if isinstance(val, str) else None
        if score is None:
            continue
        part = 0 if i < 5 else 1
        sums[part] += score
        answered[part] += 1
    if not any(answered):
        return ""
    unanswered = 10 - sum(answered)
    text = f"items 1–5 sum {sums[0]:+d}"
    if answered[0] < 5:
        text += f" ({5 - answered[0]} unanswered)"
    text += f"; total (items 1–10) {sums[0] + sums[1]:+d}"
    if unanswered:
        text += f" — {unanswered} unanswered, partial"
    return text


def isi_referral(om: dict) -> str:
    """ISI >15 → referral line (Shepherd et al. 2026, Fig 1), else "".

    Sits alongside the isi_interp "Clinically significant (≥10)" band: the user
    wants both in the reports (2026-11-16)."""
    m = re.fullmatch(r"\s*(\d+)\s*", str(om.get("isi_score") or ""))
    if m and int(m.group(1)) > 15:
        return "ISI >15 — refer to physician for further sleep assessment"
    return ""
