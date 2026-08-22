"""GTK4 trial app — Consent + Subjective, touch-first, debounced autosave.

Operates ONLY against the session path passed on the command line. Per the
trial's isolation rule, this should always be a ~/PAB-gtktrial/<name>/ copy,
never a real ~/PAB/<name>/ session — main.py enforces this.
"""

from __future__ import annotations
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

from .storage_bridge import load_assessment_block, save_sections, SECTION_KEYS
from .sections.consent import ConsentSection
from .sections.subjective import SubjectiveSection
from .nav import SectionNav
from .topbar import SubsectionNavBar
from .footer import FooterBar

AUTOSAVE_DEBOUNCE_MS = 2000

_NAME_TO_SECTION_ID = {"consent": "01_consent", "subjective": "02_subjective"}
_SECTION_ID_TO_NAME = {v: k for k, v in _NAME_TO_SECTION_ID.items()}


class TrialWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, session_file: str) -> None:
        super().__init__(application=app, title="PAB GTK Trial — Consent + Subjective")
        self.set_default_size(1100, 900)
        self.session_file = session_file
        self._save_source_id: int | None = None
        self._is_fullscreen = False

        # Narrow OS-drawn titlebar: a HeaderBar with no title widget (just
        # the window controls) is far shorter than the default titlebar,
        # which reserves a full row for a title/subtitle stack we don't
        # need — our own top bar (SubsectionNavBar, below) already shows
        # app-level chrome. See style.css's .compact-headerbar for the
        # actual height reduction (GTK doesn't shrink this on its own).
        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Box())  # empty — suppresses the default title/subtitle stack
        header.add_css_class("compact-headerbar")
        self.set_titlebar(header)

        # Outer vertical: title bar (top) / main row / footer bar (bottom) —
        # mirrors the TUI's Header/content/Footer docking.
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(outer)

        # -- top bar: the ONE persistent bar, shown on every sidebar tab
        # (there is no separate app-title bar — that wasted a second row of
        # vertical space duplicating the OS window title; removed per
        # feedback). Its buttons always jump into Subjective, switching there
        # first if another tab is active.
        self.subsection_nav = SubsectionNavBar()
        self.subsection_nav.connect("jump", self._on_subsection_jump)
        outer.append(self.subsection_nav)

        main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        main_row.set_vexpand(True)
        outer.append(main_row)

        # -- left sidebar nav (mirrors TUI's SectionNav) ----------------------
        self.nav = SectionNav()
        self.nav.connect("section-selected", self._on_nav_selected)
        main_row.append(self.nav)

        content_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_column.set_hexpand(True)
        main_row.append(content_column)

        # -- stack -----------------------------------------------------------
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)

        self.consent = ConsentSection()
        self.subjective = SubjectiveSection()
        self.subjective.session_file = session_file

        consent_scroll = Gtk.ScrolledWindow()
        consent_scroll.set_child(self.consent)
        subjective_scroll = Gtk.ScrolledWindow()
        subjective_scroll.set_child(self.subjective)

        self.stack.add_named(consent_scroll, "consent")
        self.stack.add_named(subjective_scroll, "subjective")
        content_column.append(self.stack)

        # -- bottom bar: hotkey hints + save status -----------------------------
        self.footer = FooterBar()
        outer.append(self.footer)
        self.save_status = self.footer.save_status

        self.consent.set_on_changed(self._on_consent_changed)
        self.subjective.set_on_changed(self._on_subjective_changed)

        # -- global hotkeys (capture phase — fire before the focused widget
        # sees the key, matching Textual's Binding(priority=True)) ------------
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_ctrl.connect("key-pressed", self._on_global_key)
        self.add_controller(key_ctrl)

        self._load()
        self._show_section("01_consent")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _on_nav_selected(self, _nav, section_id: str) -> None:
        self._show_section(section_id)

    def _on_subsection_jump(self, _bar, key: str) -> None:
        self._show_section("02_subjective")
        self.subjective.jump_to(key)

    def _show_section(self, section_id: str) -> None:
        name = _SECTION_ID_TO_NAME.get(section_id)
        if name is None:
            return
        self.nav.set_active(section_id)
        self.stack.set_visible_child_name(name)
        section = self.consent if name == "consent" else self.subjective
        section.focus_first_field()

    def _load(self) -> None:
        assessment = load_assessment_block(self.session_file)
        self.consent.load(assessment.get("consent", {}))
        subjective_data = assessment.get("subjective", {})
        self.subjective.load(subjective_data)
        self.consent.load_goals(subjective_data)

    # ------------------------------------------------------------------
    # Global hotkeys — mirrors main.py's PhysioAssessment.BINDINGS for the
    # two sections this trial implements:
    #   F1/F2            section switch      (BINDINGS f1/f2)
    #   Alt+<letter>     subjective jump     (BINDINGS alt+s/h/b/m/a/w/e/4/p/g/r)
    #   Ctrl+Q           quit, flushing any pending debounced save first
    #   Ctrl+A           select-all in the focused text field
    # ------------------------------------------------------------------

    _ALT_KEY_MAP = {
        "s": "symptoms", "h": "history", "b": "behaviour", "m": "management",
        "a": "activity", "w": "work", "e": "sleep", "4": "24hr",
        "p": "psychosocial", "g": "goals", "r": "risk",
    }

    def _on_global_key(self, _ctrl, keyval, _keycode, state) -> bool:
        ctrl_held = bool(state & Gdk.ModifierType.CONTROL_MASK)
        alt_held = bool(state & Gdk.ModifierType.ALT_MASK)
        name = Gdk.keyval_name(keyval) or ""

        if name == "F1":
            self._show_section("01_consent")
            return True
        if name == "F2":
            self._show_section("02_subjective")
            return True
        if name == "F11":
            self._toggle_fullscreen()
            return True
        if ctrl_held and name.lower() == "q":
            self._flush_and_quit()
            return True
        if ctrl_held and name.lower() == "a":
            return self._select_all_focused()
        if alt_held and name.lower() in self._ALT_KEY_MAP:
            self._show_section("02_subjective")
            self.subjective.jump_to(self._ALT_KEY_MAP[name.lower()])
            return True
        return False

    def _toggle_fullscreen(self) -> None:
        """F11 — matches bodychart's own F11 fullscreen toggle (see
        bodychart/src/integration.c's on_tui_key_pressed) for consistency
        across the two apps sharing this workflow."""
        if self._is_fullscreen:
            self.unfullscreen()
        else:
            self.fullscreen()
        self._is_fullscreen = not self._is_fullscreen

    def _select_all_focused(self) -> bool:
        focused = self.get_focus()
        if isinstance(focused, Gtk.TextView):
            buf = focused.get_buffer()
            buf.select_range(buf.get_start_iter(), buf.get_end_iter())
            return True
        return False

    def _flush_and_quit(self) -> None:
        """Ctrl+Q — flush any pending debounced save before exiting.

        Mirrors main.py's action_quit()/_flush_pending_saves(): a quit within
        the 2s autosave debounce window must not silently drop the last edit.
        """
        if self._save_source_id is not None:
            GLib.source_remove(self._save_source_id)
            self._save_source_id = None
            self._do_save()
        self.close()

    # ------------------------------------------------------------------
    # Live goal mirror — mirrors assessment_view.py's
    # _sync_goals_consent_to_subj / _sync_goals_subj_to_consent exactly:
    # called on EVERY field-changed event (not just at save time), and never
    # overwrites the widget the user is currently typing into.
    # ------------------------------------------------------------------

    def _sync_goals_consent_to_subj(self) -> None:
        focused = self.get_focus()
        self.subjective._loading = True
        try:
            for src, dst in zip(self.consent.consent_goals, self.subjective.goals):
                if dst.textview is focused:
                    continue
                if dst.text != src.text:
                    dst.text = src.text
        finally:
            self.subjective._loading = False

    def _sync_goals_subj_to_consent(self) -> None:
        focused = self.get_focus()
        self.consent._loading = True
        try:
            for src, dst in zip(self.subjective.goals, self.consent.consent_goals):
                if dst.textview is focused:
                    continue
                if dst.text != src.text:
                    dst.text = src.text
        finally:
            self.consent._loading = False

    def _on_consent_changed(self) -> None:
        self._sync_goals_consent_to_subj()
        self._schedule_save()

    def _on_subjective_changed(self) -> None:
        self._sync_goals_subj_to_consent()
        self._schedule_save()

    # ------------------------------------------------------------------
    # Autosave
    # ------------------------------------------------------------------

    def _schedule_save(self) -> None:
        if self._save_source_id is not None:
            GLib.source_remove(self._save_source_id)
        self.save_status.set_label("pending…")
        self._save_source_id = GLib.timeout_add(AUTOSAVE_DEBOUNCE_MS, self._do_save)

    def _do_save(self) -> bool:
        self._save_source_id = None
        self.save_status.set_label("saving…")

        section_data = {
            SECTION_KEYS["01_consent"]: self.consent.collect(),
            SECTION_KEYS["02_subjective"]: self.subjective.collect(),
        }
        sections_complete = {
            "01_consent": self.consent.is_complete(),
            "02_subjective": self.subjective.is_complete(),
        }

        ok = save_sections(self.session_file, section_data, sections_complete)
        self.save_status.set_label("saved" if ok else "SAVE FAILED")
        return GLib.SOURCE_REMOVE


def build_app(session_file: str) -> Gtk.Application:
    app = Gtk.Application(application_id="com.gpab.trial")

    def on_activate(app):
        display = Gdk.Display.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).with_name("style.css")))
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        win = TrialWindow(app, session_file)
        win.present()

    app.connect("activate", on_activate)
    return app
