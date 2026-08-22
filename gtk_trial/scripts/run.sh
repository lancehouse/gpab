#!/bin/bash
# Launch the GTK trial app against a session copy.
# Usage: scripts/run.sh <session-name>   (name of the dir under ~/PAB-gtktrial/)
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -ne 1 ]; then
    echo "Usage: $0 <session-name>" >&2
    echo "Available trial sessions:" >&2
    ls "$HOME/PAB-gtktrial" 2>/dev/null >&2 || echo "  (none yet — run scripts/copy_trial_session.sh first)" >&2
    exit 1
fi

NAME="$1"
SESSION_FILE=$(ls "$HOME/PAB-gtktrial/$NAME"/*_session.json 2>/dev/null | head -1)

if [ -z "$SESSION_FILE" ]; then
    echo "No *_session.json found under $HOME/PAB-gtktrial/$NAME" >&2
    exit 1
fi

exec .venv/bin/python -m gpab_trial.main --session "$SESSION_FILE"
