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
    export_session_report,
    save_raw_report,
    save_clean_reports,
    save_docx_report,
)

# Section id -> JSON key, matching assessment_view.py's _SEC_KEYS convention.
SECTION_KEYS = {
    "01_consent": "consent",
    "02_subjective": "subjective",
    "03_medical": "medical",
    "04_pain_classification": "pain_classification",
    "05_outcome_measures": "outcome_measures",
    "06_diagnosis": "diagnosis",
    "07_barriers": "barriers",
    "08_rx_plan": "rx_plan",
}

# Same convention for the separate _objective.json file (objective_view.py's
# _GENERIC_TABS list).
OBJECTIVE_SECTION_KEYS = {
    "04_neurological": "neurological",
    "04a_general": "general",
    "04f_functional": "functional",
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
    independently of AssessmentView, and this app mirrors that split.
    """
    data = load_objective(session_file)
    return data.get("assessment", {})


def save_objective_sections(
    session_file: str, section_data: dict[str, dict], sections_complete: dict[str, bool]
) -> bool:
    """Save {json_key: collected_dict} via storage.save_objective (merge-write)
    into the sibling _objective.json. Never touches _assessment.json."""
    return save_objective(session_file, section_data, sections_complete)


def generate_report(session_file: str) -> str:
    """Regenerate *_report.md via storage.export_session_report and return its text.

    Writes the file (so it's current on disk, same as a real save would leave
    it) and returns the freshly-written content for direct display, rather
    than reading the file back a second time.
    """
    out_path = export_session_report(session_file)
    if not out_path:
        return ""
    try:
        return Path(out_path).read_text(encoding="utf-8")
    except Exception:
        return ""


def generate_clean_report(session_file: str) -> str:
    """Regenerate *_clean.md via storage.export_session_report(clean=True, dev=True)
    and return its text — same call shape as save_clean_reports' own second call,
    so this always reflects what the periodic/exit clean-report path itself writes.

    Writes the file (so it's current on disk) and returns the freshly-written
    content for direct display, rather than reading the file back a second time.
    """
    out_path = export_session_report(session_file, clean=True, dev=True)
    if not out_path:
        return ""
    try:
        return Path(out_path).read_text(encoding="utf-8")
    except Exception:
        return ""


def generate_all_reports(session_file: str) -> None:
    """Regenerate *_raw.txt, *_report.md, and *_clean.txt/*_clean.md — same
    three calls as assessment_view.py's _generate_reports() (its 60s
    background-timer path, not Ctrl+R's, which additionally passes
    clean=True/dev=True to export_session_report and also runs pandoc/docx —
    neither of those apply to this 60s path, matching the TUI exactly: see
    tui.py's action_open_report_modal vs assessment_view.py's
    _generate_reports for the two different call shapes). Called from
    report_timer.py's background thread — see that module's docstring for
    why storage.py's own functions are safe to call off the GTK main thread.
    """
    save_raw_report(session_file)
    export_session_report(session_file)
    save_clean_reports(session_file)


def generate_all_reports_final(session_file: str) -> None:
    """Final regeneration on app exit — same four calls as assessment_view.py's
    on_unmount()/_exit_generate_all_reports() (raw + markdown + clean +
    **docx**, the one report format the 60s timer above deliberately doesn't
    produce). Ported gap fixed 2026-08-23: gpab had generate_all_reports()
    (the periodic path) wired to a 60s timer, but nothing wired to app exit
    — every close path (window-close button, window-manager close, and
    Ctrl+Q) skipped straight to destroying the window with no final
    regeneration, so any edit made after the last periodic tick (or made
    during a session too short-lived for the timer to ever fire, e.g.
    reopened/closed quickly) was saved correctly to *_assessment.json /
    *_objective.json but never made it into any report file. Confirmed live:
    text typed into a real session showed up in *_assessment.json but not in
    *_report.md/_clean.*, exactly matching this gap. Call from a non-daemon
    background thread on window close (see app.py's close-request handler)
    — daemon=False is deliberate, mirroring the reference thread exactly:
    CPython waits for non-daemon threads at interpreter shutdown, which is
    what lets this finish (including the slower pandoc/docx step) even
    though the GTK window itself has already visually closed.
    """
    save_raw_report(session_file)
    export_session_report(session_file)
    save_clean_reports(session_file)
    save_docx_report(session_file)


__all__ = [
    "assessment_path",
    "objective_path",
    "load_session_json",
    "load_assessment_block",
    "save_sections",
    "load_objective_block",
    "save_objective_sections",
    "generate_report",
    "generate_clean_report",
    "generate_all_reports",
    "generate_all_reports_final",
    "SECTION_KEYS",
    "OBJECTIVE_SECTION_KEYS",
]
