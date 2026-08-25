"""Entry point: python -m gpab_assessment.main --session /path/to/<name>/<name>_session.json

Session data isolation was relaxed 2026-08-22: this app may now read/write
real sessions under ~/PAB/ directly (the user is not worried about data
corruption there and wants saves to actually land in PAB for the report/
integration work). The isolation guarantee that still holds unconditionally
is code-repo isolation — this clone (~/Projects/gpab) never touches
~/Projects/pab or ~/Projects/kb; see ../CLAUDE.md. The only remaining check
here is a sanity check on the path shape, not which directory it's under.
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

from .app import build_app


def _validate_session_path(session_file: str) -> Path:
    path = Path(session_file).expanduser().resolve()

    if not path.name.endswith("_session.json"):
        print(f"REFUSING to launch: {path} does not look like a *_session.json path.", file=sys.stderr)
        sys.exit(1)

    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="PAB GTK conversion — assessment TUI port")
    parser.add_argument(
        "--session",
        required=True,
        help="Path to a _session.json (real ~/PAB/<name>/ sessions are fine now)",
    )
    args = parser.parse_args()

    session_path = _validate_session_path(args.session)

    app = build_app(str(session_path))
    app.run(None)


if __name__ == "__main__":
    main()
