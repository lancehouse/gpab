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

