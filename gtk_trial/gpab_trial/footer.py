"""Bottom hotkey-hint bar — GTK4 port of the TUI's Footer widget.

Only shows hotkeys this trial actually implements (see main.py's BINDINGS
for the full TUI list — most of it, e.g. Ctrl+K/Ctrl+D/Ctrl+N, has no
equivalent here since those sections/panels aren't built in this trial).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

# (key label, description) shown left-to-right, mirroring the TUI Footer's
# "^s Save  ^u Reload Chart  ..." layout.
HINTS = [
    ("F1", "Consent"),
    ("F2", "Subjective"),
    ("Alt+letter", "Jump subsection"),
    ("Ctrl+A", "Select All"),
    ("Ctrl+Q", "Quit"),
]


class FooterBar(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.add_css_class("app-footer")
        self.set_margin_start(8)
        self.set_margin_end(8)

        for key, desc in HINTS:
            pair = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            key_lbl = Gtk.Label(label=key)
            key_lbl.add_css_class("footer-key")
            desc_lbl = Gtk.Label(label=desc)
            desc_lbl.add_css_class("footer-desc")
            pair.append(key_lbl)
            pair.append(desc_lbl)
            self.append(pair)

        # Save status pinned to the far right, like the TUI footer's right-aligned hint.
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.append(spacer)

        self.save_status = Gtk.Label(label="")
        self.save_status.add_css_class("footer-desc")
        self.save_status.set_halign(Gtk.Align.END)
        self.append(self.save_status)
