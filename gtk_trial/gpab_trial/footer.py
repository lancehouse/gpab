"""Bottom status bar — GTK4 port of the TUI's Footer widget, hotkey hints
removed per user feedback (they're all represented by the actual sidebar
tabs/mode already, and the full hint row's ~15 unwrapped labels measured
~1660px natural width — the real reason the whole window was once forced
wider than the screen). Only the live save-status indicator remains.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


class FooterBar(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.add_css_class("app-footer")
        self.set_margin_start(8)
        self.set_margin_end(8)

        self.save_status = Gtk.Label(label="")
        self.save_status.add_css_class("footer-desc")
        self.save_status.set_halign(Gtk.Align.END)
        self.save_status.set_hexpand(True)
        self.append(self.save_status)
