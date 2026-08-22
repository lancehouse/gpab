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

    Emits "navigate" (direction: "up"/"down"/"left"/"right"/"next") for a
    containing grid section to interpret — e.g. NeurologicalSection's UMN
    row, where CheckButton has no internal arrow-driven state of its own
    (unlike RadioGroup, which reserves left/right for cycling), so all four
    arrows plus Y/N's post-set advance route through it. A section with no
    grid (Consent/Subjective) simply doesn't connect to it — arrows on those
    CheckButtons remain a no-op, same as before this was added.
    """

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "navigate": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    STATES = [
        ("", "cb-unanswered"),   # blank / orange
        ("Yes", "cb-yes"),       # green
        ("No", "cb-no"),         # red
    ]

    def __init__(self, base_label: str, field_id: str, compact: bool = False) -> None:
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
        if compact:
            # For dense single-row gangs (e.g. Neurological's 9-button UMN
            # row) where the default 120px floor forces horizontal overflow.
            # See .toggle-compact in style.css.
            self.add_css_class("toggle-compact")
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
        # NOTE: was previously `self.child_focus(...)` called on the button
        # itself — a Gtk.Button has no focusable children, so that was a
        # silent no-op and Y/N never actually advanced focus. child_focus
        # must be called on an ancestor that contains the whole chain.
        root = self.get_root()
        if root is not None:
            root.child_focus(Gtk.DirectionType.TAB_FORWARD)
        self.emit("navigate", "next")

    def _on_clicked(self, _btn) -> None:
        self._cycle()

    _ARROW_DIRS = {
        "Up": "up", "Down": "down", "Left": "left", "Right": "right",
    }

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name in ("y", "Y"):
            self._set_and_advance(True)
            return True
        if name in ("n", "N"):
            self._set_and_advance(False)
            return True
        if name in self._ARROW_DIRS:
            self.emit("navigate", self._ARROW_DIRS[name])
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
    """Exclusive single-select gang of chip buttons — ONE tab stop.

    Tap a chip selects it; tapping the already-selected chip deselects it
    (clears to no selection) — matching pab_assessment.widgets.RadioGroup.
    options: list of (label, css_variant) pairs. value/set_value use the
    label string as the stored value, same as the TUI widget.

    Keyboard, mirroring the TUI RadioGroup's key_left/key_right/key_enter
    exactly: the gang itself is the focusable unit (chips are not
    individually focusable), so Tab moves to/past the whole gang in one
    step, same as the TUI's textual widget.
      Left/Right — cycle the selection within this gang (clamped at the
        ends, no wrap; if nothing selected, Right selects the first
        option and Left selects the last — TUI key_left/key_right).
        This is intentionally NOT routed to the container: it's the one
        thing this widget owns internally, so keyboard entry of an
        abnormal (non-first) option is still possible with the gang
        focused only.
      Up/Down — not handled here; emitted as "navigate" for a containing
        grid section to move focus to the row above/below.
      Enter/Space — if nothing is selected yet, select the first
        (normal/success-variant) option; then emit "navigate" with
        "next" so a containing grid section can advance to the next
        cell. This is what makes a full row of normal findings just
        Enter-Enter-Enter-Enter (TUI key_enter/key_space/key_y all call
        screen.focus_next(); the "select normal first" step is additive,
        since GTK's chips have no visible focus ring of their own once
        made non-focusable and there was previously no keyboard entry
        path for this gang at all).
    """

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "navigate": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
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
            btn.set_can_focus(False)  # the gang is one tab stop, not each chip
            btn.set_focus_on_click(False)
            btn.add_css_class(self._VARIANT_CLASS.get(variant, "rb-default"))
            btn.connect("toggled", self._on_toggled)
            chip_label = btn.get_child()
            if isinstance(chip_label, Gtk.Label):
                # Without wrap, a chip's minimum width is its full unbroken
                # label text (e.g. "4+Clons"), which is what forced whole
                # rows — and the Neurological tab as a whole — wider than
                # the window. Wrapping lets a chip actually shrink toward
                # MIN_TOUCH instead of demanding one-line width.
                chip_label.set_wrap(True)
                chip_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                chip_label.set_justify(Gtk.Justification.CENTER)
                chip_label.set_lines(2)
            self._buttons.append(btn)
            self.append(btn)

        self.set_can_focus(True)
        self.set_focusable(True)
        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("enter", lambda _c: self.add_css_class("rg-focused"))
        focus_ctrl.connect("leave", lambda _c: self.remove_css_class("rg-focused"))
        self.add_controller(focus_ctrl)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

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

    # -- keyboard: mirrors pab_assessment.widgets.RadioGroup exactly --------

    def _key_left(self) -> None:
        if not self._buttons:
            return
        if self._selected is None:
            self._select(len(self._buttons) - 1)
        else:
            self._select(max(0, self._selected - 1))

    def _key_right(self) -> None:
        if not self._buttons:
            return
        if self._selected is None:
            self._select(0)
        else:
            self._select(min(len(self._buttons) - 1, self._selected + 1))

    def _key_commit(self) -> None:
        if self._selected is None and self._buttons:
            # Pick the "normal" option first — whichever chip is tagged
            # success, else just the first chip — so an untouched row can
            # be completed with Enter alone (arrow-enter-arrow-enter for
            # abnormal rows, plain enter-enter-enter for normal rows).
            normal_idx = 0
            for i, (_label, variant) in enumerate(self._options):
                if variant == "success":
                    normal_idx = i
                    break
            self._select(normal_idx)
        self.emit("navigate", "next")

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name == "Left":
            self._key_left()
            return True
        if name == "Right":
            self._key_right()
            return True
        if name in ("Up", "Down"):
            self.emit("navigate", "up" if name == "Up" else "down")
            return True
        if name in ("Return", "KP_Enter", "space"):
            self._key_commit()
            return True
        return False


# ---------------------------------------------------------------------------
# AutoTextView — multi-line text entry that never swallows Tab
# ---------------------------------------------------------------------------

class AutoTextView(Gtk.ScrolledWindow):
    """Gtk.TextView wrapper with accepts-tab=False so Tab always moves focus.

    Mirrors pab_assessment.widgets TextArea usage (multi-line free text).

    Emits "navigate" (direction) for a containing grid section, mirroring
    the TUI's GridTextArea boundary-crossing rule: Up/Down always cross
    (a text area has no meaningful "row above/below" within a grid cell
    once it does), Left only at the very start of the buffer, Right only
    at the very end — so normal cursor movement inside multi-line notes
    is untouched, and only crossing the actual boundary hands off to grid
    navigation.
    """

    __gsignals__ = {
        "navigate": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

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

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.textview.add_controller(key_ctrl)

    def grab_focus(self) -> bool:
        # Grid navigation targets this wrapper by field_id; focus must land
        # on the inner TextView, not the ScrolledWindow shell.
        return self.textview.grab_focus()

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name not in ("Up", "Down", "Left", "Right"):
            return False
        buf = self.textview.get_buffer()
        cursor = buf.get_iter_at_mark(buf.get_insert())
        if name == "Up":
            if cursor.get_line() == 0:
                self.emit("navigate", "up")
                return True
            return False
        if name == "Down":
            if cursor.get_line() == buf.get_line_count() - 1:
                self.emit("navigate", "down")
                return True
            return False
        if name == "Left":
            if cursor.is_start():
                self.emit("navigate", "left")
                return True
            return False
        if name == "Right":
            if cursor.is_end():
                self.emit("navigate", "right")
                return True
            return False
        return False

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
    """Single-line entry. Emits "navigate" for grid boundary-crossing,
    mirroring the TUI's GridInput: Up/Down always cross (a single-line
    entry has no internal row concept); Left only at cursor position 0,
    Right only at the end of the text — normal in-field cursor movement
    is otherwise untouched.
    """

    __gsignals__ = {
        "navigate": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, field_id: str, placeholder: str = "") -> None:
        super().__init__()
        self.field_id = field_id
        self.set_size_request(-1, MIN_TOUCH)
        self.set_hexpand(True)
        if placeholder:
            self.set_placeholder_text(placeholder)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name in ("Up", "Down"):
            self.emit("navigate", "up" if name == "Up" else "down")
            return True
        if name == "Left" and self.get_position() == 0:
            self.emit("navigate", "left")
            return True
        if name == "Right" and self.get_position() >= len(self.get_text()):
            self.emit("navigate", "right")
            return True
        return False

    @property
    def text(self) -> str:
        return self.get_text()

    @text.setter
    def text(self, value: str) -> None:
        self.set_text(value or "")
