"""Thin wrapper around the cloned pab_assessment.storage module.

Import order matters: pab_path_bootstrap must run before pab_assessment is
imported anywhere, so it is imported here first for its side effect.
"""

from . import pab_path_bootstrap  # noqa: F401  (sys.path side effect)

import json
import time
from pathlib import Path

from pab_assessment.storage import (  # noqa: E402
    assessment_path,
    save_all_sections,
    objective_path,
    load_objective,
    save_objective,
)

# Section id -> JSON key, matching assessment_view.py's _SEC_KEYS convention.
SECTION_KEYS = {
    "01_consent": "consent",
    "02_subjective": "subjective",
}

# Same convention for the separate _objective.json file (objective_view.py's
# _GENERIC_TABS list).
OBJECTIVE_SECTION_KEYS = {
    "04_neurological": "neurological",
}


def load_session_json(session_file: str) -> dict:
    """Read the full _session.json (GTK body-chart data) for mapping.build_prefill()."""
    path = Path(session_file)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_assessment_block(session_file: str) -> dict:
    """Read the 'assessment' block from the sibling _assessment.json file.

    Mirrors assessment_view.py's load_session(): reads the TUI-owned
    _assessment.json directly rather than embedded data in _session.json.
    """
    assess_p = assessment_path(session_file)
    if not assess_p.exists():
        return {}
    try:
        return json.loads(assess_p.read_text(encoding="utf-8")).get("assessment", {})
    except Exception:
        return {}


def save_sections(session_file: str, section_data: dict[str, dict], sections_complete: dict[str, bool]) -> bool:
    """Save {json_key: collected_dict} via storage.save_all_sections (merge-write).

    Never touches _session.json; writes only the sibling _assessment.json,
    preserving any other sections already stored there (e.g. from the real TUI).
    """
    return save_all_sections(session_file, section_data, sections_complete)


def load_objective_block(session_file: str) -> dict:
    """Read the 'assessment' block from the sibling _objective.json file.

    Separate file from _assessment.json (see pab CLAUDE.md's two-app data
    layout) — the TUI's ObjectiveAssessmentView saves/loads this
    independently of AssessmentView, and this trial mirrors that split.
    """
    data = load_objective(session_file)
    return data.get("assessment", {})


def save_objective_sections(
    session_file: str, section_data: dict[str, dict], sections_complete: dict[str, bool]
) -> bool:
    """Save {json_key: collected_dict} via storage.save_objective (merge-write)
    into the sibling _objective.json. Never touches _assessment.json."""
    return save_objective(session_file, section_data, sections_complete)


__all__ = [
    "assessment_path",
    "objective_path",
    "load_session_json",
    "load_assessment_block",
    "save_sections",
    "load_objective_block",
    "save_objective_sections",
    "SECTION_KEYS",
    "OBJECTIVE_SECTION_KEYS",
]
