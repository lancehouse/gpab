"""Entry point: gpab_trial --session /path/to/PAB-gtktrial/<name>/<name>_session.json

Safety rule (see plan's isolation guarantee): this trial must never write to
a real ~/PAB/<name>/ session. --session must point inside PAB-gtktrial/ (or
any directory NOT named exactly the real ~/PAB session root); we refuse to
launch otherwise. Use scripts/copy_trial_session.sh to create a safe copy.
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

from .app import build_app

REAL_SESSION_ROOT = Path.home() / "PAB"
TRIAL_SESSION_ROOT = Path.home() / "PAB-gtktrial"


def _validate_session_path(session_file: str) -> Path:
    path = Path(session_file).expanduser().resolve()

    try:
        path.relative_to(REAL_SESSION_ROOT.resolve())
        real_session_dir = True
    except (ValueError, FileNotFoundError):
        real_session_dir = False

    if real_session_dir:
        print(
            f"REFUSING to launch: {path} is inside {REAL_SESSION_ROOT} (a real, live session).\n"
            f"This trial app must only ever run against a copy under {TRIAL_SESSION_ROOT}.\n"
            f"Run scripts/copy_trial_session.sh <session-name> first.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not path.name.endswith("_session.json"):
        print(f"REFUSING to launch: {path} does not look like a *_session.json path.", file=sys.stderr)
        sys.exit(1)

    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="PAB GTK touch trial — Consent + Subjective")
    parser.add_argument(
        "--session",
        required=True,
        help="Path to a _session.json inside ~/PAB-gtktrial/<name>/ (never a real ~/PAB/ session)",
    )
    args = parser.parse_args()

    session_path = _validate_session_path(args.session)

    app = build_app(str(session_path))
    app.run(None)


if __name__ == "__main__":
    main()
