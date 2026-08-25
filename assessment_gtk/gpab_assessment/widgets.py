"""GTK4 widget kit mirroring pab_assessment/widgets.py semantics.

Field ids and 3-state semantics match the TUI 1:1 so collect()/load() dicts
are schema-compatible with pab_assessment.storage. Sizing targets touch
(GNOME HIG minimum ~44-48px) rather than the TUI's terminal-cell sizing.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GObject, Pango, GLib  # noqa: E402

MIN_TOUCH = 48  # px, GNOME HIG minimum touch target

# RadioGroup/MultiSelectGroup chip minimum width. A RadioGroup chip's natural
# width comes from its own label text (e.g. "↓Mrkd" naturally measures ~82px,
# "Absent"/"↑Hyper" similarly ~85-90px) and normally displays at that full
# comfortable width — but a bilateral row (two side-by-side RadioGroups, e.g.
# Neurological's dermatome rows) can be squeezed below that natural width
# once something else on the same page (the Ctrl+K KB panel, chiefly) takes
# real room from the tab, and the row's *label chips* (5-7 chars: "Absent",
# "↑Hyper") need a bit more floor than reflex/myotome's shorter ones (3-4
# chars: "5/5", "2+ Norm") to avoid wrapping first. RADIO_CHIP_MIN_WIDTH is
# that floor — 58px, not the MIN_TOUCH-only 48px a chip would otherwise
# shrink to, but well short of an earlier 72px attempt that (combined with
# two separate, since-fixed bugs — Gtk.Stack's default hhomogeneous sizing,
# and the footer's ~1660px-wide unwrapped hotkey row) forced the whole
# window wider than the screen. With both of those fixed, this modest floor
# is safe: it can't on its own reproduce that overflow.
RADIO_CHIP_MIN_WIDTH = 58

# ---------------------------------------------------------------------------
# Focus-listener registry — powers the Ctrl+K KB panel's focus-follow
# behaviour (objective/kb_panel.py). A window-level Gtk.Root
# "notify::focus-widget" hook was tried first and proved unreliable for
# widgets nested inside a Gtk.Stack page in this app's structure (fired in
# isolated tests, silently didn't fire once real Stack/ScrolledWindow
# nesting was involved) — piggybacking on each widget's own
# Gtk.EventControllerFocus "enter" signal instead, which already reliably
# drives the focus-ring CSS below, is the trustworthy mechanism.
# ---------------------------------------------------------------------------

_focus_listeners: list = []


def add_focus_listener(callback) -> None:
    """Register callback(widget) to be invoked whenever any KB-relevant
    widget (RadioGroup/MultiSelectGroup/CycleField/TouchEntry/AutoTextView)
    gains focus."""
    _focus_listeners.append(callback)


def _notify_focus(widget: Gtk.Widget) -> None:
    for cb in _focus_listeners:
        cb(widget)

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


def field_row(label_text: str, widget: Gtk.Widget) -> Gtk.Box:
    """Label + field row, using the shared left-column width. Previously
    duplicated identically in consent.py and subjective.py; promoted here
    when medical.py needed a third copy of the same pattern."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    lbl = Gtk.Label(label=label_text)
    lbl.add_css_class("field-label")
    lbl.set_halign(Gtk.Align.START)
    lbl.set_valign(Gtk.Align.START)
    lbl.set_wrap(True)
    field_left_slot(lbl)
    row.append(lbl)
    row.append(widget)
    return row


def field_row_pair(flag_widget: Gtk.Widget, text_widget: Gtk.Widget) -> Gtk.Box:
    """A toggle button standing in for the row's label, paired with a field.

    field_left_slot() forces the toggle to the exact same width as every
    plain label (FIELD_LEFT_COLUMN_PX) so its row's text field starts at the
    same x position as every other field row — this is the single place that
    rule is enforced, so it can never drift out of sync section by section.
    Originally a subjective.py-local helper; promoted here once medical.py
    needed the identical pattern for its imaging rows.
    """
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    field_left_slot(flag_widget)
    row.append(flag_widget)
    row.append(text_widget)
    return row


def make_subgroup_header(text: str) -> Gtk.Label:
    """A smaller, muted/italic sub-heading nested inside a subsection — e.g.
    "Malignancy:" within Red Flags, or "Ankylosing Spondylitis:" within
    Differential Screening. Mirrors the TUI's .subgroup_header CSS (muted,
    italic) as distinct from make_subsection_header()'s full-width bar.
    """
    lbl = Gtk.Label(label=text)
    lbl.add_css_class("subgroup-header")
    lbl.set_halign(Gtk.Align.START)
    return lbl


def make_subsection_header(text: str, anchor_id: str | None = None) -> Gtk.Label:
    """The "— History —" / "— Behaviour —" style subsection divider.

    ONE definition used by every section (consent/subjective/yaml_subsection
    all import this rather than declaring their own copy) so a later styling
    change — or a new section built after this one — automatically gets the
    same look, instead of needing the same CSS class remembered by hand each
    time. Styled as a full-width colored bar (see .subsection-header in
    style.css) to mirror the TUI's high-contrast subsection_header CSS.

    anchor_id, when given, is the same (section_id, anchor_id) vocabulary
    used by grid_overview.py's SUBJ_GRID_DATA/OBJ_GRID_DATA and search.py's
    _SUBSECTIONS — stashed as a plain attribute so app.py's grid-overview
    jump can find this exact header widget (via search.find_by_anchor_id)
    and scroll it to the top of the section's viewport, instead of only
    focusing the section's first field (which can leave the header itself
    scrolled off above the visible area).
    """
    lbl = Gtk.Label(label=f"— {text} —")
    lbl.add_css_class("subsection-header")
    lbl.set_halign(Gtk.Align.FILL)
    lbl.set_hexpand(True)
    lbl.set_xalign(0.0)  # text left-aligned within the full-width bar
    lbl.anchor_id = anchor_id
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

        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("enter", lambda _c: _notify_focus(self))
        self.add_controller(focus_ctrl)

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
# CycleField — label + single button cycling through a fixed state list
# ---------------------------------------------------------------------------

class CycleField(Gtk.Box):
    """Generic base for a label + one button that cycles through a fixed list
    of states on click, each state carrying its own CSS class. Generalizes
    pab_assessment's LikelihoodField and PainTypeSelector (medical.py /
    pain_classification.py) — identical mechanism in the TUI, just a
    different state list and colour map, so a subclass here only needs to
    set CYCLE/CSS_CLASS rather than reimplementing the widget.
    """

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "navigate": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    CYCLE: list[str | None] = [None]
    CSS_CLASS: dict[str | None, str] = {None: "cb-unanswered"}

    # variant string (as used throughout pab_assessment.widgets, e.g.
    # "success"/"warning"/"error"/"primary"/"default") -> existing chip CSS
    # class from RadioGroup's palette (style.css), reused here so an ad-hoc
    # options list (outcome_measures.py's many interpretation scales) needs
    # no new CSS of its own.
    _VARIANT_CLASS = {
        "success": "rb-success", "warning": "rb-warning", "error": "rb-error",
        "primary": "rb-primary", "default": "rb-default",
    }

    def __init__(self, label: str, field_id: str, options: list[tuple[str, str]] | None = None) -> None:
        """label may be "" to omit the internal label — used where the
        caller places its own Label beside this widget instead (e.g.
        outcome_measures.py's inline "Dep: [score] [interp]" rows).

        options, when given, overrides CYCLE/CSS_CLASS for this instance:
        a list of (state_label, variant) pairs, mirroring
        pab_assessment.sections.outcome_measures.CycleField exactly (None is
        prepended automatically as the unanswered state) — lets a section
        with many one-off interpretation scales (DASS/PCS/PCL-5/ISI/PSEQ/...)
        use this widget directly instead of writing a subclass per scale.
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.field_id = field_id
        self._value: str | None = None

        if options is not None:
            self.CYCLE = [None] + [opt_label for opt_label, _ in options]
            self.CSS_CLASS = {None: "cb-unanswered"}
            for opt_label, variant in options:
                self.CSS_CLASS[opt_label] = self._VARIANT_CLASS.get(variant, "rb-default")

        if label:
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            self.append(lbl)

        self.button = Gtk.Button(label="?")
        self.button.set_size_request(MIN_TOUCH, MIN_TOUCH)
        self.button.add_css_class("clinical-toggle")
        self.button.connect("clicked", self._on_clicked)
        self.append(self.button)

        # Arrow-key grid nav, mirroring RadioGroup's pattern: Up/Down escape
        # to the containing grid; Enter/Space cycle this cell then advance,
        # so an objective table row can be filled with Enter alone the same
        # way a RadioGroup row can.
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.button.add_controller(key_ctrl)

        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("enter", lambda _c: _notify_focus(self))
        self.button.add_controller(focus_ctrl)

        self._apply()

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name in ("Up", "Down"):
            self.emit("navigate", "up" if name == "Up" else "down")
            return True
        if name in ("Return", "KP_Enter", "space"):
            self._on_clicked(self.button)
            self.emit("navigate", "next")
            return True
        return False

    @property
    def value(self) -> str | None:
        return self._value

    def set_value(self, value: str | None) -> None:
        self._value = value if value in self.CYCLE else None
        self._apply()

    def _apply(self) -> None:
        self.button.set_label(self._value or "?")
        for cls in self.CSS_CLASS.values():
            self.button.remove_css_class(cls)
        self.button.add_css_class(self.CSS_CLASS[self._value])

    def _on_clicked(self, _btn) -> None:
        idx = self.CYCLE.index(self._value)
        self._value = self.CYCLE[(idx + 1) % len(self.CYCLE)]
        self._apply()
        self.emit("changed")

    def grab_focus(self) -> bool:
        return self.button.grab_focus()


class LikelihoodField(CycleField):
    """None -> Low -> Moderate -> High -> None. Mirrors
    pab_assessment.sections.medical.LikelihoodField."""

    CYCLE = [None, "Low", "Moderate", "High"]
    CSS_CLASS = {
        None: "cb-unanswered", "Low": "cb-yes",
        "Moderate": "lf-moderate", "High": "cb-no",
    }


class PainTypeSelector(CycleField):
    """None -> Nociceptive -> Neuropathic -> Nociplastic -> Mixed -> None.
    Mirrors pab_assessment.sections.pain_classification.PainTypeSelector."""

    CYCLE = [None, "Nociceptive", "Neuropathic", "Nociplastic", "Mixed — unable to determine"]
    CSS_CLASS = {
        None: "cb-unanswered",
        "Nociceptive": "cb-yes",
        "Neuropathic": "lf-moderate",
        "Nociplastic": "cb-no",
        "Mixed — unable to determine": "rb-default",
    }


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
            btn.set_size_request(RADIO_CHIP_MIN_WIDTH, MIN_TOUCH)
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
        focus_ctrl.connect("enter", self._on_focus_enter)
        focus_ctrl.connect("leave", lambda _c: self.remove_css_class("rg-focused"))
        self.add_controller(focus_ctrl)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

    def _on_focus_enter(self, _c) -> None:
        self.add_css_class("rg-focused")
        _notify_focus(self)

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

    def chip_index_at(self, x: float, y: float) -> int | None:
        """Which chip (by option index) is at (x, y) in this gang's own
        coordinate space, or None if the point misses every chip (e.g. the
        small gaps between them). Used by grid_drag_select.py to resolve a
        drag's start/hover position — kept here so that module never needs
        to reach into self._buttons directly."""
        picked = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        while picked is not None and picked is not self:
            if picked in self._buttons:
                return self._buttons.index(picked)
            picked = picked.get_parent()
        return None

    def select_by_index(self, idx: int) -> None:
        """Public wrapper around _select with emit=True — used by
        grid_drag_select.py to set a value the same way a real tap would,
        so autosave/live-sync pick it up exactly as if the user had tapped
        this chip directly (unlike set_value, which is for silent
        programmatic load() and deliberately does not emit "changed")."""
        self._select(idx, emit=True)

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


class MultiSelectGroup(Gtk.Box):
    """Independent multi-select gang of chip buttons — ONE tab stop.

    Same visual chip appearance as RadioGroup, but each chip toggles
    independently (any number selected, including none). value returns
    list[str] of selected labels in option order, mirroring
    pab_assessment.widgets.MultiSelectGroup exactly (used for General
    Observation's "Antalgic lean" row, where more than one direction can
    apply at once — unlike every other row on that tab, which is exclusive).
    """

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "navigate": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    _VARIANT_CLASS = RadioGroup._VARIANT_CLASS

    def __init__(self, options: list[tuple[str, str]], field_id: str) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.field_id = field_id
        self._options = options
        self._buttons: list[Gtk.ToggleButton] = []
        self.add_css_class("radio-group")

        for label, variant in options:
            btn = Gtk.ToggleButton(label=label)
            btn.set_size_request(RADIO_CHIP_MIN_WIDTH, MIN_TOUCH)
            btn.set_can_focus(False)
            btn.set_focus_on_click(False)
            btn.add_css_class(self._VARIANT_CLASS.get(variant, "rb-default"))
            btn.connect("toggled", self._on_toggled)
            chip_label = btn.get_child()
            if isinstance(chip_label, Gtk.Label):
                chip_label.set_wrap(True)
                chip_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                chip_label.set_justify(Gtk.Justification.CENTER)
                chip_label.set_lines(2)
            self._buttons.append(btn)
            self.append(btn)

        self.set_can_focus(True)
        self.set_focusable(True)
        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("enter", self._on_focus_enter)
        focus_ctrl.connect("leave", lambda _c: self.remove_css_class("rg-focused"))
        self.add_controller(focus_ctrl)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

    def _on_focus_enter(self, _c) -> None:
        self.add_css_class("rg-focused")
        _notify_focus(self)

    @property
    def value(self) -> list[str]:
        return [label for (label, _), btn in zip(self._options, self._buttons) if btn.get_active()]

    def set_value(self, labels) -> None:
        if isinstance(labels, str):
            labels = [labels] if labels else []
        labels = set(labels or [])
        for (label, _), btn in zip(self._options, self._buttons):
            active = label in labels
            if btn.get_active() != active:
                btn.handler_block_by_func(self._on_toggled)
                btn.set_active(active)
                btn.handler_unblock_by_func(self._on_toggled)

    def _on_toggled(self, _btn) -> None:
        self.emit("changed")

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name in ("Up", "Down"):
            self.emit("navigate", "up" if name == "Up" else "down")
            return True
        if name in ("Return", "KP_Enter", "space"):
            self.emit("navigate", "next")
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

    expand=True (the default, matching every section's field): the field
    grows with typed content instead of scrolling internally. Note this is
    NOT Gtk.ScrolledWindow.set_propagate_natural_height — that was tried
    first and does not reliably track a GtkTextView's content height in
    practice (TextView is designed to assume it's always host to a scrolled
    viewport, not to report a growing natural size the way Gtk.Label does).
    What actually works: measure the buffer's real laid-out height via
    get_iter_location() on every buffer change, and drive
    set_min_content_height() from that directly, clamped to
    [min_lines, max_lines] * an estimated line height. Growth caps at
    max_lines (default 20) so one very long note can't consume the whole
    window — same min/max discipline as the mandatory TextArea height
    pattern in pab's own CLAUDE.md (there: min-height 3, max-height 12,
    internal scroll beyond that), just driven by measurement instead of a
    static CSS rule since GTK has no height:auto equivalent for TextView.
    expand=False: the old fixed-height-and-scroll behaviour — used only by
    the F10 notes overlay, which is deliberately a small fixed-size panel
    docked at the bottom of the window, not a field that should push the
    rest of the form around as it's typed into.
    """

    __gsignals__ = {
        "navigate": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    _LINE_PX = 22  # matches the estimate min_lines*22/max_lines*22 always used here

    def __init__(self, field_id: str, min_lines: int = 2, max_lines: int = 20, expand: bool = True) -> None:
        super().__init__()
        self.field_id = field_id
        self._expand = expand
        self._min_h = min_lines * self._LINE_PX
        self._max_h = max_lines * self._LINE_PX
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_min_content_height(self._min_h)
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

        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("enter", lambda _c: _notify_focus(self))
        self.textview.add_controller(focus_ctrl)

        if self._expand:
            # GtkTextView recomputes its internal text layout lazily, not
            # synchronously inside the buffer's own "changed" signal — measuring
            # get_iter_location() immediately in that handler reads stale
            # (pre-edit) geometry. Deferring via GLib.idle_add runs the
            # measurement after GTK has had a chance to relayout, which is
            # what actually makes the height track what's on screen.
            self.textview.get_buffer().connect("changed", lambda _b: GLib.idle_add(self._recompute_height))
            self.textview.connect("map", lambda _w: GLib.idle_add(self._recompute_height))

    def _recompute_height(self) -> bool:
        buf = self.textview.get_buffer()
        rect = self.textview.get_iter_location(buf.get_end_iter())
        content_h = rect.y + rect.height + self.textview.get_top_margin() + self.textview.get_bottom_margin() + 4
        self.set_min_content_height(max(self._min_h, min(content_h, self._max_h)))
        return GLib.SOURCE_REMOVE

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

        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("enter", lambda _c: _notify_focus(self))
        self.add_controller(focus_ctrl)

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
