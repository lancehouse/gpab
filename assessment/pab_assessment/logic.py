"""Clinical logic layer - pure functions, no UI imports, no persistence."""

import re
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from .models import Session, OutcomeMeasureResult


# ---------------------------------------------------------------------------
# Sleep efficiency helpers
# ---------------------------------------------------------------------------

def _extract_time_token(s: str) -> str:
    """Pull the first numeric time token out of a free-text string.

    Handles entries like '645 most days', '22:00 approx', '930'.
    """
    m = re.search(r'\d{1,4}(?::\d{0,2})?', s.strip())
    return m.group() if m else ""


def _parse_clock(s: str) -> int | None:
    """Parse a clock-time string to minutes since midnight, or None.

    Accepts: '22:30', '2230', '645', '6:45', '0645'.
    Rules (no colon): ≤2 digits → hours; 3 digits → h+mm; 4 digits → hhmm.
    Returns None if out of range or unparseable.

    Sleep-diary PM convention (applied when h is in range 5–12):
      No leading zero  →  PM assumed  (9:00 → 21:00, 10:00 → 22:00, 900 → 21:00)
      Leading zero     →  AM literal  (09:00 → 09:00, 0900 → 09:00)
    Hours 1–4 are always treated as AM (post-midnight sleep times; nobody has a
    2 pm bedtime). Hours 0 and 13–23 are always literal 24 h.
    """
    if not s:
        return None
    token = _extract_time_token(s)
    if not token:
        return None
    if ':' in token:
        parts = token.split(':', 1)
        part0 = parts[0] if parts[0] else "0"
        h = int(part0)
        mn = int(parts[1]) if parts[1] else 0
        leading_zero = len(part0) > 1 and part0[0] == '0'
    else:
        d = token
        if len(d) <= 2:
            h, mn = int(d), 0
            leading_zero = len(d) == 2 and d[0] == '0'
        elif len(d) == 3:
            h, mn = int(d[0]), int(d[1:])
            leading_zero = False
        else:
            h, mn = int(d[:2]), int(d[2:])
            leading_zero = d[0] == '0'
    if 5 <= h <= 12 and not leading_zero:
        h = (h + 12) % 24  # 12 wraps to 0 (midnight)
    if h > 23 or mn > 59:
        return None
    return h * 60 + mn


def _parse_duration(s: str) -> int | None:
    """Parse a duration string to total minutes, or None.

    With colon: h:mm → total minutes.
    Without colon: digits treated as total minutes (so '60' → 60 min).
    """
    if not s:
        return None
    token = _extract_time_token(s)
    if not token:
        return None
    if ':' in token:
        parts = token.split(':', 1)
        h = int(parts[0]) if parts[0] else 0
        mn = int(parts[1]) if parts[1] else 0
        return h * 60 + mn
    return int(token)


def calc_sleep_efficiency(
    sleep_onset_time: str,
    sleep_waso_duration: str,
    sleep_final_wakeup: str,
    sleep_time_to_bed: str,
    sleep_awake_out_bed: str,
    sleep_time_out_of_bed: str,
) -> str:
    """Return sleep efficiency as 'NN%', or '' if any required input is missing.

    Formula:
        TST = (FWT - SOL) - WASO_dur
        TIB = (TOB - TIB_start) - WOOB
        SE  = TST / TIB * 100

    Midnight crossing: clock times that fall before TIB_start are assumed to
    be post-midnight; add 1440 min so all arithmetic stays monotonic.
    """
    tib_start = _parse_clock(sleep_time_to_bed)
    sol       = _parse_clock(sleep_onset_time)
    fwt       = _parse_clock(sleep_final_wakeup)
    tob       = _parse_clock(sleep_time_out_of_bed)
    waso_dur  = _parse_duration(sleep_waso_duration)
    woob      = _parse_duration(sleep_awake_out_bed)

    if any(v is None for v in (tib_start, sol, fwt, tob)):
        return ""
    if waso_dur is None:
        waso_dur = 0
    if woob is None:
        woob = 0

    # Midnight crossing for clock times
    if sol < tib_start:
        sol += 1440
    if fwt < tib_start:
        fwt += 1440
    if tob < tib_start:
        tob += 1440

    tst = (fwt - sol) - waso_dur
    tib = (tob - tib_start) - woob

    if tib <= 0 or tst < 0:
        return ""

    se = max(0, min(100, round(tst / tib * 100)))
    return f"{se}%"


def get_bodychart_command(session_path: Path) -> list:
    """
    Generate command line to launch GTK body chart with this session.

    Args:
        session_path: Path to session JSON file

    Returns:
        List ready for subprocess.Popen() or similar
    """
    return ["physio-bodychart", "--session", str(session_path)]


def generate_report_paragraph(section: str, session_data: Session) -> str:
    """
    Generate Jinja2 template for given section with session data substitutions.

    Args:
        section: Section name (e.g. "consent", "subjective", "pain_classification")
        session_data: Completed session model

    Returns:
        Generated paragraph text with placeholders replaced
    """
    # TODO: Wire up Jinja2 templates from core/*.md files
    return ""


def query_patterns(region: str, symptom_zones: List[str], active_overlay: Optional[str]) -> List[Tuple[str, float]]:
    """
    Query clinical patterns matching body chart findings.

    Args:
        region: Body region (e.g. "lumbar")
        symptom_zones: List of symptom locations/types from body chart
        active_overlay: Active overlay type (dermatome, peripheral, somatic)

    Returns:
        List of (pattern_id, confidence_score) tuples, ranked by score
    """
    # TODO: clinical_kb.db has no BodyChartTrigger table (that was the originally
    # planned schema, superseded by what actually got built — see kb_db.py). The
    # real schema has condition/condition_feature (region-scoped, free-text
    # feature_name/feature_value, no body-chart-zone linkage yet). Matching body
    # chart symptom_zones to conditions needs new logic against condition_feature,
    # not a lookup against a trigger table.
    return []


def query_tests(pattern_ids: List[str], priority_filter: Optional[str] = None) -> List[Dict]:
    """
    Get special tests for given patterns, ordered by priority.

    Args:
        pattern_ids: List of pattern IDs
        priority_filter: Filter by "essential" or "supporting"

    Returns:
        List of special test dicts with metadata
    """
    # TODO: clinical_kb.db has no SpecialTest/PatternTest tables (originally
    # planned schema, superseded — see kb_db.py). The real schema's `test` +
    # `cluster_test` + `cluster` tables map reasonably well onto "tests for a
    # pattern/cluster id" (see kb_db.load_tests_for_pab_region /
    # kb_db.load_clusters_for_test for working examples of this join). There is
    # no essential/supporting priority_filter column on test or cluster_test
    # today — closest analogs are cluster.cluster_type and cluster_test.display_order,
    # not a direct flag.
    return []


def score_pattern(pattern_id: str, features_present: List[str]) -> float:
    """
    Score confidence in a pattern based on present features.

    Args:
        pattern_id: Pattern ID
        features_present: List of feature IDs confirmed present

    Returns:
        Confidence score 0.0–1.0
    """
    # TODO: clinical_kb.db has no PatternFeature table (originally planned schema,
    # superseded). The real analog, condition_feature, has no weight column —
    # just feature_name/feature_value/feature_domain free text. This function
    # cannot be implemented against the current schema without a schema addition
    # (per-feature weights), not just new query logic.
    return 0.0


def suggest_icd11_pathway(duration: Optional[str], mechanism: Optional[str],
                         pain_type: Optional[str]) -> Tuple[str, str]:
    """
    Suggest most likely ICD-11 pathway based on clinical data.

    Args:
        duration: Symptom duration
        mechanism: Pain mechanism/cause
        pain_type: Dominant pain type from classification

    Returns:
        Tuple of (pathway_code, reasoning_text)
    """
    # TODO: Implement ICD-11 pathway logic per core/06
    return ("", "")


def suggest_barriers(outcome_scores: Dict[str, float], pain_type: str) -> List[str]:
    """
    Suggest likely treatment barriers based on outcome measures and pain type.

    Args:
        outcome_scores: Dict of measure_name → score
        pain_type: Dominant pain type

    Returns:
        List of barrier IDs to suggest ticking
    """
    # TODO: Implement barrier suggestion logic
    return []


def calculate_bmi(height_cm: float, weight_kg: float) -> float:
    """Calculate BMI (display only, not editable)."""
    if height_cm <= 0:
        return 0.0
    height_m = height_cm / 100
    return weight_kg / (height_m ** 2)


def tally_inflammatory_score(features_checked: Dict[str, bool]) -> int:
    """
    Tally inflammatory pain features (0–4).

    Returns:
        Count of checked inflammatory features
    """
    return sum(1 for v in features_checked.values() if v)


def tally_pain_type_features(features_checked: Dict[str, bool]) -> Dict[str, int]:
    """
    Tally pain type feature counts (subjective + examination separate).

    Returns:
        Dict of pain_type → count
    """
    return {}


def interpret_outcome_score(measure_name: str, score: float) -> str:
    """
    Return interpretation label for an outcome measure score.

    Args:
        measure_name: Measure name (e.g. "PSFS", "BPI", "CSI")
        score: Raw score

    Returns:
        Interpretation label (e.g. "Mild", "Moderate", "High risk")
    """
    # TODO: Implement per core/05 thresholds
    return ""
