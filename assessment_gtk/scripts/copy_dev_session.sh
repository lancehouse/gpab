#!/bin/bash
# Copy a real session out of ~/PAB/<name>/ into ~/PAB-assessment-gtk/<name>/ for
# disposable dev use. READS from ~/PAB/ only. NEVER writes back to it.
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: $0 <session-name>" >&2
    echo "Available sessions in ~/PAB:" >&2
    ls "$HOME/PAB" 2>/dev/null >&2 || echo "  (none — ~/PAB does not exist)" >&2
    exit 1
fi

NAME="$1"
SRC="$HOME/PAB/$NAME"
DST="$HOME/PAB-assessment-gtk/$NAME"

if [ ! -d "$SRC" ]; then
    echo "No such session: $SRC" >&2
    exit 1
fi

if [ -d "$DST" ]; then
    echo "Dev copy already exists at $DST — remove it first if you want a fresh copy." >&2
    exit 1
fi

mkdir -p "$HOME/PAB-assessment-gtk"
cp -r "$SRC" "$DST"

echo "Copied $SRC -> $DST"
echo "Session file for --session:"
ls "$DST"/*_session.json 2>/dev/null || echo "  (no *_session.json found in the copy)"
