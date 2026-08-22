"""Top subsection nav bar — GTK4 port of assessment_view.py's
#subsection_nav_bar (the mnemonic row: Symptoms/History/Behaviour/Mgmt/
Activity/Work/slEep/24Hr/Psychosocial/Goals/Risk).

This is the app's ONE persistent top bar — there is deliberately no separate
app-title bar above it (that duplicated the OS window title for no benefit
and cost a full extra row of vertical space; removed per feedback). It's
shown permanently across every sidebar tab, not just Subjective — clicking
an item switches to Subjective and jumps, from wherever you currently are.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject, GLib  # noqa: E402

# (underline-mnemonic label, jump key) — jump key matches app.py's _ALT_KEY_MAP
# values and SubjectiveSection._jump_targets keys. Labels match the TUI's
# alt-key row text exactly (main.py's alt+s/h/b/m/a/w/e/4/p/g/r bindings).
SUBSECTION_ITEMS = [
    ("_Symptoms", "symptoms"),
    ("_History", "history"),
    ("_Behaviour", "behaviour"),
    ("_Mgmt", "management"),
    ("_Activity", "activity"),
    ("_Work", "work"),
    ("sl_Eep", "sleep"),
    ("2_4Hr", "24hr"),
    ("_Psychosocial", "psychosocial"),
    ("_Goals", "goals"),
    ("_Risk", "risk"),
]


def _permanent_mnemonic_markup(label: str) -> str:
    """Turn '_Symptoms' into markup with the mnemonic letter ALWAYS underlined.

    Gtk.Button(use_underline=True) only shows its underline while Alt is
    held — useless as a permanent keyboard hint. A plain Gtk.Label with
    Pango markup underlines the letter unconditionally instead.
    """
    idx = label.find("_")
    if idx == -1 or idx + 1 >= len(label):
        return GLib.markup_escape_text(label)
    before, letter, after = label[:idx], label[idx + 1], label[idx + 2:]
    esc = GLib.markup_escape_text
    return f"{esc(before)}<u>{esc(letter)}</u>{esc(after)}"


class SubsectionNavBar(Gtk.Box):
    """Mnemonic row for Subjective subsections — permanently displayed
    across every sidebar tab (per user direction: this replaces the old
    black title bar as the app's one persistent top strip)."""

    __gsignals__ = {
        "jump": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.add_css_class("subsection-nav-bar")

        for label, key in SUBSECTION_ITEMS:
            btn = Gtk.Button()
            btn.add_css_class("subsection-nav-btn")
            inner = Gtk.Label()
            inner.set_markup(_permanent_mnemonic_markup(label))
            btn.set_child(inner)
            btn.connect("clicked", self._on_clicked, key)
            self.append(btn)

    def _on_clicked(self, _btn, key: str) -> None:
        self.emit("jump", key)
