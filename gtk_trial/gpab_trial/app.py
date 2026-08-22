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

from .storage_bridge import (
    load_assessment_block, save_sections, SECTION_KEYS,
    load_objective_block, save_objective_sections, OBJECTIVE_SECTION_KEYS,
)
from .sections.consent import ConsentSection
from .sections.subjective import SubjectiveSection
from .sections.medical import MedicalSection
from .sections.pain_classification import PainClassificationSection
from .sections.outcome_measures import OutcomeMeasuresSection
from .sections.diagnosis import DiagnosisSection
from .sections.barriers import BarriersSection
from .sections.rx_plan import RxPlanSection
from .objective.sections.neurological import NeurologicalSection
from .nav import SectionNav
from .topbar import SubsectionNavBar
from .footer import FooterBar
from .report_modal import ReportModal
from .notes_overlay import NotesOverlay

AUTOSAVE_DEBOUNCE_MS = 2000

_NAME_TO_SECTION_ID = {
    "consent": "01_consent",
    "subjective": "02_subjective",
    "medical": "03_medical",
    "pain_classification": "04_pain_classification",
    "outcome_measures": "05_outcome_measures",
    "diagnosis": "06_diagnosis",
    "barriers": "07_barriers",
    "rx_plan": "08_rx_plan",
    "neurological": "04_objective",
}
_SECTION_ID_TO_NAME = {v: k for k, v in _NAME_TO_SECTION_ID.items()}


class TrialWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, session_file: str) -> None:
        super().__init__(application=app, title="PAB GTK Trial — Consent + Subjective")
        self.set_default_size(1100, 900)
        self.session_file = session_file
        self._save_source_id: int | None = None       # debounce for _assessment.json
        self._save_source_id_obj: int | None = None    # debounce for _objective.json (separate file, separate timer — matches TUI's AssessmentView/ObjectiveAssessmentView split)
        self._is_fullscreen = False
        self._loading_notes = False

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
        self.medical = MedicalSection()
        self.pain_classification = PainClassificationSection()
        self.outcome_measures = OutcomeMeasuresSection()
        self.diagnosis = DiagnosisSection()
        self.barriers = BarriersSection()
        self.rx_plan = RxPlanSection()
        self.neurological = NeurologicalSection()

        self._sections_by_name = {
            "consent": self.consent,
            "subjective": self.subjective,
            "medical": self.medical,
            "pain_classification": self.pain_classification,
            "outcome_measures": self.outcome_measures,
            "diagnosis": self.diagnosis,
            "barriers": self.barriers,
            "rx_plan": self.rx_plan,
            "neurological": self.neurological,
        }

        for name, section in self._sections_by_name.items():
            scroll = Gtk.ScrolledWindow()
            # Never horizontal-scroll: every tab's content must fit the
            # window's actual width and use all of it, not spill sideways.
            # Vertical-only scrolling is the one axis these forms need.
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.set_child(section)
            self.stack.add_named(scroll, name)
        content_column.append(self.stack)

        # -- F10 notes overlay: freeform notes, hidden until toggled --------
        self.notes_overlay = NotesOverlay()
        self.notes_overlay.connect_changed(self._on_notes_changed)
        content_column.append(self.notes_overlay)

        # -- bottom bar: hotkey hints + save status -----------------------------
        self.footer = FooterBar()
        outer.append(self.footer)
        self.save_status = self.footer.save_status

        self.consent.set_on_changed(self._on_consent_changed)
        self.subjective.set_on_changed(self._on_subjective_changed)
        self.medical.set_on_changed(self._schedule_save)
        self.pain_classification.set_on_changed(self._schedule_save)
        self.outcome_measures.set_on_changed(self._schedule_save)
        self.diagnosis.set_on_changed(self._schedule_save)
        self.barriers.set_on_changed(self._schedule_save)
        self.rx_plan.set_on_changed(self._schedule_save)
        self.neurological.set_on_changed(self._schedule_save_obj)

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
        self._sections_by_name[name].focus_first_field()
        if name in ("pain_classification", "outcome_measures"):
            # Mirrors assessment_view.py's _show_section: cross-reference
            # badges are computed from in-memory sibling-section data (no
            # disk I/O), refreshed on every switch into this tab.
            self._sections_by_name[name].update_cross_refs({
                "medical": self.medical.collect(),
                "subjective": self.subjective.collect(),
            })
        elif name == "barriers":
            self.barriers.update_cross_refs({
                "medical": self.medical.collect(),
                "subjective": self.subjective.collect(),
                "pain_classification": self.pain_classification.collect(),
                "outcome_measures": self.outcome_measures.collect(),
                "diagnosis": self.diagnosis.collect(),
            })

    def _load(self) -> None:
        assessment = load_assessment_block(self.session_file)
        self.consent.load(assessment.get("consent", {}))
        subjective_data = assessment.get("subjective", {})
        self.subjective.load(subjective_data)
        self.consent.load_goals(subjective_data)
        self.medical.load(assessment.get("medical", {}))
        self.pain_classification.load(assessment.get("pain_classification", {}))
        self.outcome_measures.load(assessment.get("outcome_measures", {}))
        self.diagnosis.load(assessment.get("diagnosis", {}))
        self.barriers.load(assessment.get("barriers", {}))
        self.rx_plan.load(assessment.get("rx_plan", {}))

        self._loading_notes = True
        try:
            self.notes_overlay.load_text(assessment.get("scratchpad", {}).get("notes", ""))
        finally:
            self._loading_notes = False

        objective = load_objective_block(self.session_file)
        self.neurological.load(objective.get("neurological", {}))

    # ------------------------------------------------------------------
    # Global hotkeys — mirrors main.py's PhysioAssessment.BINDINGS for the
    # sections this trial implements:
    #   F1/F2            section switch      (BINDINGS f1/f2)
    #   F4               → Neurological      (BINDINGS f4 "section_objective" —
    #                      the TUI's F4 opens Objective mode's first section;
    #                      Neurological is the only Objective tab built here,
    #                      so F4 goes straight to it)
    #   Ctrl+F5          → Neurological      (BINDINGS ctrl+f5 "obj_neurological"
    #                      — the TUI's precise jump straight to this section;
    #                      kept as well since it's the more exact match)
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
        if name == "F3":
            self._show_section("03_medical")
            return True
        if name == "F5" and not ctrl_held:
            self._show_section("04_pain_classification")
            return True
        if name == "F6" and not ctrl_held:
            self._show_section("05_outcome_measures")
            return True
        if name == "F7" and not ctrl_held:
            self._show_section("06_diagnosis")
            return True
        if name == "F8" and not ctrl_held:
            self._show_section("07_barriers")
            return True
        if name == "F9" and not ctrl_held:
            self._show_section("08_rx_plan")
            return True
        if name == "F10":
            self._toggle_notes()
            return True
        if name == "F4":
            self._show_section("04_objective")
            return True
        if name == "F11":
            self._toggle_fullscreen()
            return True
        if ctrl_held and name == "F5":
            self._show_section("04_objective")
            return True
        if ctrl_held and name.lower() == "q":
            self._flush_and_quit()
            return True
        if ctrl_held and name.lower() == "a":
            return self._select_all_focused()
        if ctrl_held and name.lower() == "r":
            self._show_report()
            return True
        if alt_held and name.lower() in self._ALT_KEY_MAP:
            self._show_section("02_subjective")
            self.subjective.jump_to(self._ALT_KEY_MAP[name.lower()])
            return True
        return False

    def _show_report(self) -> None:
        """Ctrl+R — flush any pending debounced save first, same reasoning as
        _flush_and_quit: the report must reflect the latest edit, not whatever
        was last on disk before the 2s autosave debounce fired."""
        if self._save_source_id is not None:
            GLib.source_remove(self._save_source_id)
            self._save_source_id = None
            self._do_save()
        if self._save_source_id_obj is not None:
            GLib.source_remove(self._save_source_id_obj)
            self._save_source_id_obj = None
            self._do_save_obj()
        ReportModal(self, self.session_file).present()

    def _toggle_notes(self) -> None:
        """F10 — matches main.py's action_toggle_notes: hiding refocuses the
        active section's first field so hotkeys work immediately, exactly as
        the TUI does after dismissing the overlay."""
        visible = self.notes_overlay.get_visible()
        self.notes_overlay.set_visible(not visible)
        if visible:
            name = _SECTION_ID_TO_NAME.get(self.nav.active_section)
            if name:
                self._sections_by_name[name].focus_first_field()
        else:
            self.notes_overlay.grab_focus()

    def _on_notes_changed(self, _buffer) -> None:
        if self._loading_notes:
            return
        self._schedule_save()

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
        if self._save_source_id_obj is not None:
            GLib.source_remove(self._save_source_id_obj)
            self._save_source_id_obj = None
            self._do_save_obj()
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
            SECTION_KEYS["03_medical"]: self.medical.collect(),
            SECTION_KEYS["04_pain_classification"]: self.pain_classification.collect(),
            SECTION_KEYS["05_outcome_measures"]: self.outcome_measures.collect(),
            SECTION_KEYS["06_diagnosis"]: self.diagnosis.collect(),
            SECTION_KEYS["07_barriers"]: self.barriers.collect(),
            SECTION_KEYS["08_rx_plan"]: self.rx_plan.collect(),
            # Legacy key (not one of SECTION_KEYS — the TUI's own F10 notes
            # overlay is window-level chrome, not a numbered section), saved
            # under "scratchpad" for backward compat with existing sessions.
            "scratchpad": {"notes": self.notes_overlay.text},
        }
        sections_complete = {
            "01_consent": self.consent.is_complete(),
            "02_subjective": self.subjective.is_complete(),
            "03_medical": self.medical.is_complete(),
            "04_pain_classification": self.pain_classification.is_complete(),
            "05_outcome_measures": self.outcome_measures.is_complete(),
            "06_diagnosis": self.diagnosis.is_complete(),
            "07_barriers": self.barriers.is_complete(),
            "08_rx_plan": self.rx_plan.is_complete(),
        }

        ok = save_sections(self.session_file, section_data, sections_complete)
        self.save_status.set_label("saved" if ok else "SAVE FAILED")
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------
    # Objective autosave — separate file (_objective.json), separate debounce
    # timer, mirroring the TUI's AssessmentView/ObjectiveAssessmentView split
    # (each has its own _schedule_save/_do_save in assessment_view.py resp.
    # objective/objective_view.py — they never share one debounce timer).
    # ------------------------------------------------------------------

    def _schedule_save_obj(self) -> None:
        if self._save_source_id_obj is not None:
            GLib.source_remove(self._save_source_id_obj)
        self.save_status.set_label("pending…")
        self._save_source_id_obj = GLib.timeout_add(AUTOSAVE_DEBOUNCE_MS, self._do_save_obj)

    def _do_save_obj(self) -> bool:
        self._save_source_id_obj = None
        self.save_status.set_label("saving…")

        section_data = {OBJECTIVE_SECTION_KEYS["04_neurological"]: self.neurological.collect()}
        sections_complete = {"04_neurological": self.neurological.is_complete()}

        ok = save_objective_sections(self.session_file, section_data, sections_complete)
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

        # GTK CSS has no light/dark media query, so app.py detects the
        # system preference itself (via Gtk.Settings, which GNOME's
        # appearance portal keeps in sync) and toggles a .theme-dark class
        # the stylesheet keys off of — see style.css's focus-ring rules.
        # Re-applied live on toggle (e.g. GNOME's dark-mode switch) as well
        # as at startup, not just once.
        settings = Gtk.Settings.get_default()

        def _apply_theme_class(*_args) -> None:
            is_dark = settings.get_property("gtk-application-prefer-dark-theme")
            if is_dark:
                win.add_css_class("theme-dark")
            else:
                win.remove_css_class("theme-dark")

        settings.connect("notify::gtk-application-prefer-dark-theme", _apply_theme_class)
        _apply_theme_class()

        win.present()

    app.connect("activate", on_activate)
    return app
