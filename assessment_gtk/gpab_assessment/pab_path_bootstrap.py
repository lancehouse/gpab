"""Puts this app's own cloned copy of pab_assessment on sys.path.

Resolves to ~/Projects/gpab/assessment — the git-cloned, fully independent
reference copy this clone carries — never ~/Projects/pab/assessment. Import
this module (for its side effect) before importing anything from
pab_assessment.
"""

import sys
from pathlib import Path

_ASSESSMENT_DIR = Path(__file__).resolve().parents[2] / "assessment"

if not _ASSESSMENT_DIR.is_dir():
    raise RuntimeError(
        f"Expected cloned assessment/ package at {_ASSESSMENT_DIR}; "
        "assessment_gtk must live inside the ~/Projects/gpab clone."
    )

_path_str = str(_ASSESSMENT_DIR)
if _path_str not in sys.path:
    sys.path.insert(0, _path_str)
