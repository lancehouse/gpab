#!/bin/bash
# One-time setup: venv with system site-packages (for PyGObject/GTK4) + pyyaml.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv --system-site-packages .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

.venv/bin/python -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk; print('GTK', Gtk.get_major_version())"
echo "venv ready: $(dirname "$0")/../.venv"
