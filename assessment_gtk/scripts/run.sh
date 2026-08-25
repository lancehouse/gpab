#!/bin/bash
# Launch the GTK app against a session by name.
# Usage: scripts/run.sh <session-name>
# Looks under ~/PAB/<name>/ first (real sessions — reading/writing these
# directly is fine now, see gpab_assessment/main.py), falling back to
# ~/PAB-assessment-gtk/<name>/ (a copy made via copy_dev_session.sh) if not found.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -ne 1 ]; then
    echo "Usage: $0 <session-name>" >&2
    echo "Available sessions in ~/PAB:" >&2
    ls "$HOME/PAB" >&2 2>/dev/null || echo "  (none)" >&2
    echo "Available dev-copy sessions in ~/PAB-assessment-gtk:" >&2
    ls "$HOME/PAB-assessment-gtk" >&2 2>/dev/null || echo "  (none)" >&2
    exit 1
fi

NAME="$1"
SESSION_FILE=$(ls "$HOME/PAB/$NAME"/*_session.json 2>/dev/null | head -1)

if [ -z "$SESSION_FILE" ]; then
    SESSION_FILE=$(ls "$HOME/PAB-assessment-gtk/$NAME"/*_session.json 2>/dev/null | head -1)
fi

if [ -z "$SESSION_FILE" ]; then
    echo "No *_session.json found under $HOME/PAB/$NAME or $HOME/PAB-assessment-gtk/$NAME" >&2
    exit 1
fi

exec .venv/bin/python -m gpab_assessment.main --session "$SESSION_FILE"
