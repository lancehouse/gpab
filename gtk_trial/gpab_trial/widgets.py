"""GTK4 widget kit mirroring pab_assessment/widgets.py semantics.

Field ids and 3-state semantics match the TUI 1:1 so collect()/load() dicts
are schema-compatible with pab_assessment.storage. Sizing targets touch
(GNOME HIG minimum ~44-48px) rather than the TUI's terminal-cell sizing.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GObject, Pango  # noqa: E402

MIN_TOUCH = 48  # px, GNOME HIG minimum touch target

# Single source of truth for the "left column" of every field row across the
# whole app — whether that slot holds a Label or a toggle button standing in
# for one (e.g. the Behaviour rows: FlagButton + text field). Every left-slot
# widget gets this exact pixel width via set_size_request, so columns line up
# regardless of widget type or font metrics. Never tune alignment ad hoc in
# an individual section — add the new widget type to field_left_slot() below
# instead, so the fix applies everywhere at once.
FIELD_LEFT_COLUMN_PX = 230


def field_left_slot(widget: Gtk.Widget) -> Gtk.Widget:
    """Constrain any widget to the shared left-column width and return it.

    Use for every label AND every toggle-as-label widget in a field row.
    """
    widget.set_size_request(FIELD_LEFT_COLUMN_PX, -1)
    widget.set_hexpand(False)
    return widget


def make_subsection_header(text: str) -> Gtk.Label:
    """The "— History —" / "— Behaviour —" style subsection divider.

    ONE definition used by every section (consent/subjective/yaml_subsection
    all import this rather than declaring their own copy) so a later styling
    change — or a new section built after this one — automatically gets the
    same look, instead of needing the same CSS class remembered by hand each
    time. Styled as a full-width colored bar (see .subsection-header in
    style.css) to mirror the TUI's high-contrast subsection_header CSS.
    """
    lbl = Gtk.Label(label=f"— {text} —")
    lbl.add_css_class("subsection-header")
    lbl.set_halign(Gtk.Align.FILL)
    lbl.set_hexpand(True)
    lbl.set_xalign(0.0)  # text left-aligned within the full-width bar
    return lbl


# ---------------------------------------------------------------------------
# CheckButton / FlagButton — 3-state toggle
# ---------------------------------------------------------------------------

class CheckButton(Gtk.Button):
    """3-state clinical toggle: blank -> Yes (green) -> No (red).

    Click, Enter, or Space cycles state. Y/N keys set state directly and
    advance focus to the next focusable widget. Mirrors
    pab_assessment.widgets.CheckButton exactly (states, cycle order, id).
    """

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    STATES = [
        ("", "cb-unanswered"),   # blank / orange
        ("Yes", "cb-yes"),       # green
        ("No", "cb-no"),         # red
    ]

    def __init__(self, base_label: str, field_id: str) -> None:
        super().__init__()
        self.base_label = base_label
        self.field_id = field_id
        self._state = 0

        self.set_size_request(-1, MIN_TOUCH)
        # Deliberately NOT hexpand: in a plain (non-homogeneous) Horizontal box
        # (e.g. a Behaviour row pairing a flag + a text field) hexpand would
        # make this button compete 50/50 with the field instead of staying
        # compact. Rows that DO want equal-width buttons (Course, Beliefs) use
        # Gtk.Box(homogeneous=True), which sizes children equally regardless
        # of hexpand — so this is safe there too.
        label_widget = self.get_child()
        if label_widget is None:
            label_widget = Gtk.Label()
            self.set_child(label_widget)
        label_widget.set_wrap(True)
        label_widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label_widget.set_justify(Gtk.Justification.CENTER)

        self.add_css_class("clinical-toggle")
        self.connect("clicked", self._on_clicked)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        self._apply()

    # -- state -----------------------------------------------------------

    @property
    def value(self) -> bool | None:
        return {0: None, 1: True, 2: False}[self._state]

    def set_value(self, value: bool | None) -> None:
        self._state = {None: 0, True: 1, False: 2}[value]
        self._apply()

    def _apply(self) -> None:
        suffix, css_class = self.STATES[self._state]
        text = f"{self.base_label} {suffix}".strip() if suffix else self.base_label
        self.set_label(text)
        for _, cls in self.STATES:
            self.remove_css_class(cls)
        self.add_css_class(css_class)

    def _cycle(self) -> None:
        self._state = (self._state + 1) % 3
        self._apply()
        self.emit("changed")

    def _set_and_advance(self, value: bool) -> None:
        self._state = 1 if value else 2
        self._apply()
        self.emit("changed")
        self.child_focus(Gtk.DirectionType.TAB_FORWARD)

    def _on_clicked(self, _btn) -> None:
        self._cycle()

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name in ("y", "Y"):
            self._set_and_advance(True)
            return True
        if name in ("n", "N"):
            self._set_and_advance(False)
            return True
        return False


class FlagButton(CheckButton):
    """3-state flag: blank -> Yes (red/danger) -> No (green/safe)."""

    STATES = [
        ("", "cb-unanswered"),
        ("Yes", "cb-no"),   # reversed: Yes = danger colour
        ("No", "cb-yes"),   # reversed: No = safe colour
    ]


# ---------------------------------------------------------------------------
# RadioGroup — exclusive single-select chip gang
# ---------------------------------------------------------------------------

class RadioGroup(Gtk.Box):
    """Exclusive single-select gang of chip buttons.

    Tap selects a chip; tapping the already-selected chip deselects it
    (clears to no selection) — matching pab_assessment.widgets.RadioGroup.
    options: list of (label, css_variant) pairs. value/set_value use the
    label string as the stored value, same as the TUI widget.
    """

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    _VARIANT_CLASS = {
        "success": "rb-success",
        "warning": "rb-warning",
        "error": "rb-error",
        "primary": "rb-primary",
        "default": "rb-default",
    }

    def __init__(self, options: list[tuple[str, str]], field_id: str) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.field_id = field_id
        self._options = options
        self._buttons: list[Gtk.ToggleButton] = []
        self._selected: int | None = None
        self.add_css_class("radio-group")

        for label, variant in options:
            btn = Gtk.ToggleButton(label=label)
            btn.set_size_request(MIN_TOUCH, MIN_TOUCH)
            btn.add_css_class(self._VARIANT_CLASS.get(variant, "rb-default"))
            btn.connect("toggled", self._on_toggled)
            self._buttons.append(btn)
            self.append(btn)

    @property
    def value(self) -> str | None:
        if self._selected is None:
            return None
        return self._options[self._selected][0]

    def set_value(self, label: str | None) -> None:
        idx = None
        if label is not None:
            for i, (opt_label, _) in enumerate(self._options):
                if opt_label == label:
                    idx = i
                    break
        self._select(idx, emit=False)

    def _select(self, idx: int | None, emit: bool = True) -> None:
        self._selected = idx
        for i, btn in enumerate(self._buttons):
            btn.handler_block_by_func(self._on_toggled)
            btn.set_active(i == idx)
            btn.handler_unblock_by_func(self._on_toggled)
        if emit:
            self.emit("changed")

    def _on_toggled(self, btn: Gtk.ToggleButton) -> None:
        idx = self._buttons.index(btn)
        if btn.get_active():
            # deactivate every other button (manual exclusivity — no Gtk.CheckButton group,
            # since a real radio group can't be re-clicked back to "no selection")
            for i, other in enumerate(self._buttons):
                if other is not btn and other.get_active():
                    other.handler_block_by_func(self._on_toggled)
                    other.set_active(False)
                    other.handler_unblock_by_func(self._on_toggled)
            self._selected = idx
        else:
            self._selected = None
        self.emit("changed")


# ---------------------------------------------------------------------------
# AutoTextView — multi-line text entry that never swallows Tab
# ---------------------------------------------------------------------------

class AutoTextView(Gtk.ScrolledWindow):
    """Gtk.TextView wrapper with accepts-tab=False so Tab always moves focus.

    Mirrors pab_assessment.widgets TextArea usage (multi-line free text).
    """

    def __init__(self, field_id: str, min_lines: int = 2) -> None:
        super().__init__()
        self.field_id = field_id
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_min_content_height(min_lines * 22)
        self.set_hexpand(True)
        self.add_css_class("auto-textview-frame")

        self.textview = Gtk.TextView()
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.textview.set_accepts_tab(False)  # critical: Tab must move focus, not insert \t
        self.textview.set_top_margin(4)
        self.textview.set_bottom_margin(4)
        self.textview.set_left_margin(6)
        self.textview.set_right_margin(6)
        self.textview.add_css_class("auto-textview")
        self.set_child(self.textview)

    @property
    def text(self) -> str:
        buf = self.textview.get_buffer()
        start, end = buf.get_bounds()
        return buf.get_text(start, end, True)

    @text.setter
    def text(self, value: str) -> None:
        self.textview.get_buffer().set_text(value or "")


# ---------------------------------------------------------------------------
# LabeledEntry — single-line Gtk.Entry, touch-sized
# ---------------------------------------------------------------------------

class TouchEntry(Gtk.Entry):
    def __init__(self, field_id: str, placeholder: str = "") -> None:
        super().__init__()
        self.field_id = field_id
        self.set_size_request(-1, MIN_TOUCH)
        self.set_hexpand(True)
        if placeholder:
            self.set_placeholder_text(placeholder)

    @property
    def text(self) -> str:
        return self.get_text()

    @text.setter
    def text(self, value: str) -> None:
        self.set_text(value or "")
