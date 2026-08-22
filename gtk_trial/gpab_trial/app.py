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
from .objective.sections.general import GeneralSection
from .objective.sections.functional import FunctionalSection
from .objective.sections.sensory import SensorySection
from .objective.sections.crps import CRPSSection
from .objective.region_section import RegionTabContent
from .objective.region_topbar import RegionTopbar
from .objective.objective_nav import ObjectiveNav
from .objective.kb_panel import KBPanel
from .objective.kb_loader import get_registry
from .objective.kb_db_screen import KBDBWindow
from .widgets import add_focus_listener
from .nav import SectionNav
from .topbar import SubsectionNavBar
from .footer import FooterBar
from .report_modal import ReportModal
from .notes_overlay import NotesOverlay

AUTOSAVE_DEBOUNCE_MS = 2000

# Assessment-mode section ids (nav.py's SectionNav) — "04_objective" here is
# not a content page, it's the sentinel that enters Objective mode.
_NAME_TO_SECTION_ID = {
    "consent": "01_consent",
    "subjective": "02_subjective",
    "medical": "03_medical",
    "pain_classification": "04_pain_classification",
    "outcome_measures": "05_outcome_measures",
    "diagnosis": "06_diagnosis",
    "barriers": "07_barriers",
    "rx_plan": "08_rx_plan",
}

# Objective-mode section ids (objective_nav.py's ObjectiveNav) — these are
# the TUI's own ids (see ObjectiveSidebar.SECTION_LABELS), kept 1:1 so this
# dispatch stays a direct mirror of assessment_view.py's.
_OBJECTIVE_NAME_TO_SECTION_ID = {
    "general": "01_general",
    "functional": "07_functional",
    "active_movement": "02_active",
    "passive_movement": "03_passive",
    "neurological": "04_neurological",
    "sensory": "05_sensory",
    "muscle_testing": "06_muscle",
    "special_tests": "08_special",
    "crps": "09_crps",
}

_NAME_TO_SECTION_ID.update(_OBJECTIVE_NAME_TO_SECTION_ID)

# Default active region on a fresh/unsaved session — toggled live from
# RegionTopbar thereafter, and overridden by whatever "active_regions" list
# was last saved once a session is loaded. No live body-chart region sync in
# this trial (same deferral as the KB panel) — toggling is manual only.
_DEFAULT_ACTIVE_REGIONS = ["lumbar"]

_SECTION_ID_TO_NAME = {v: k for k, v in _NAME_TO_SECTION_ID.items()}
_OBJECTIVE_SECTION_IDS = set(_OBJECTIVE_NAME_TO_SECTION_ID.values())


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
        # feedback). It swaps content depending on the active tab: the
        # Subjective mnemonic row everywhere, or the body-region toggle
        # chips across every Objective tab (mirrors the TUI's RegionTopbar
        # being shown for the whole Objective mode, not just the
        # region-variable tabs) — see _show_section.
        self._active_regions: list[str] = []
        self.subsection_nav = SubsectionNavBar()
        self.subsection_nav.connect("jump", self._on_subsection_jump)
        self.region_topbar = RegionTopbar(_DEFAULT_ACTIVE_REGIONS)
        self.region_topbar.connect("region-toggled", self._on_region_toggled)

        self.topbar_stack = Gtk.Stack()
        self.topbar_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.topbar_stack.add_named(self.subsection_nav, "subjective")
        self.topbar_stack.add_named(self.region_topbar, "region")
        outer.append(self.topbar_stack)

        main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        main_row.set_vexpand(True)
        outer.append(main_row)

        # -- left sidebar nav — TWO separate sidebars that swap wholesale,
        # mirroring the TUI's SectionNav / ObjectiveSidebar split (see
        # _enter_objective_mode/_exit_objective_mode), not one combined list.
        self._in_objective_mode = False
        self._last_assessment_section_id = "01_consent"
        self.nav = SectionNav()
        self.nav.connect("section-selected", self._on_nav_selected)
        self.objective_nav = ObjectiveNav()
        self.objective_nav.connect("section-selected", self._on_objective_nav_selected)
        self.objective_nav.connect("back", self._on_objective_back)

        self.sidebar_stack = Gtk.Stack()
        self.sidebar_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.sidebar_stack.add_named(self.nav, "assessment")
        self.sidebar_stack.add_named(self.objective_nav, "objective")
        main_row.append(self.sidebar_stack)

        content_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_column.set_hexpand(True)

        # -- Ctrl+K knowledge-base panel: right-hand side, hidden until
        # toggled, shown across every tab (mirrors the TUI's KBPanel being
        # mounted once at AssessmentView level, not per-section). Content
        # only updates while in Objective mode (see _on_focus_changed) —
        # matches the TUI, where the focus hook lives on
        # ObjectiveAssessmentView, not the whole app.
        #
        # content_column/kb_panel share a Gtk.Paned rather than plain Box
        # slots: a plain Box honours each child's minimum size literally, so
        # giving the panel a ~50%-of-window width floor (KBPanel.KB_PANEL_WIDTH)
        # forced the WHOLE WINDOW wider than the screen once the panel was
        # toggled on (confirmed live — windowed mode grew past screen width,
        # fullscreen cut off the sidebar). A Paned's divider is draggable and
        # only enforces each side's own small natural minimum, so the window
        # never has to grow to fit it — the panel gets its nominal share when
        # there's room and shrinks (draggable, not just automatic) when there
        # isn't, with no horizontal scrolling either way.
        self.kb_panel = KBPanel()
        self.main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_paned.set_hexpand(True)
        self.main_paned.set_start_child(content_column)
        self.main_paned.set_resize_start_child(True)
        self.main_paned.set_shrink_start_child(True)
        self.main_paned.set_end_child(self.kb_panel)
        # resize=True: the KB panel's pixel width should track window size
        # (a fixed-pixel-forever setting made it a barely-usable ~170px
        # sliver in fullscreen on a large monitor, since content absorbed
        # all of the extra fullscreen space and the panel got none of it).
        # The panel's *proportion* of the window is what should stay
        # roughly constant, not its absolute pixel count — see
        # _toggle_kb_panel, which sets the actual position as a fraction of
        # the paned's real current width every time the panel is shown,
        # rather than a single pixel value guessed at construction time
        # (before the window has real geometry) that never gets revisited.
        self.main_paned.set_resize_end_child(True)
        self.main_paned.set_shrink_end_child(True)
        main_row.append(self.main_paned)

        # -- stack -----------------------------------------------------------
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        # Gtk.Stack defaults hhomogeneous=True: it sizes itself to the
        # WIDEST page among ALL mounted tabs (visible or not), not just the
        # one currently shown — found via measurement that this, not the KB
        # panel or the chip-button width, was the real source of a huge
        # (1000px+) minimum width forcing the window wider than the screen.
        # Each tab already has its own per-page ScrolledWindow (below) for
        # independent scrolling, so there's no reason for one wide hidden
        # tab (e.g. a wide region table) to inflate every other tab's
        # minimum size.
        self.stack.set_hhomogeneous(False)

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
        self.general = GeneralSection()
        self.functional = FunctionalSection()
        self.sensory = SensorySection()
        self.crps = CRPSSection()

        self.active_movement = RegionTabContent("active", "02 Active Movement")
        self.passive_movement = RegionTabContent("passive", "03 Passive / OP")
        self.muscle_testing = RegionTabContent("muscle", "06 Muscle Testing")
        self.special_tests = RegionTabContent("special", "08 Special Tests")
        self._region_tabs = (self.active_movement, self.passive_movement,
                              self.muscle_testing, self.special_tests)
        for region_id in _DEFAULT_ACTIVE_REGIONS:
            self._mount_region(region_id)
            self._active_regions.append(region_id)

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
            "general": self.general,
            "functional": self.functional,
            "sensory": self.sensory,
            "crps": self.crps,
            "active_movement": self.active_movement,
            "passive_movement": self.passive_movement,
            "muscle_testing": self.muscle_testing,
            "special_tests": self.special_tests,
        }

        for name, section in self._sections_by_name.items():
            scroll = Gtk.ScrolledWindow()
            # Horizontal AUTOMATIC, not NEVER: every tab's content should
            # fit the window's actual width and reflow into it, not spill
            # sideways — but horizontal-NEVER turned out to mean something
            # different in GTK4 than "never scroll, just shrink to fit": a
            # ScrolledWindow with policy=NEVER on an axis treats the child's
            # NATURAL size as a hard floor on that axis (verified — this was
            # the actual mechanism behind both the KB-panel and footer
            # overflow bugs), so a section that's wider than the space the
            # KB panel leaves it got silently clipped with no way to reach
            # the cut-off portion, rather than shrinking into the space it
            # was actually given. AUTOMATIC lets a tab genuinely narrow to
            # fit; the horizontal scrollbar it enables is a fallback for
            # whatever a tab's own internal layout can't shrink into, not
            # the normal case.
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scroll.set_child(section)
            self.stack.add_named(scroll, name)
        content_column.append(self.stack)

        # -- F10 notes overlay: freeform notes, hidden until toggled --------
        self.notes_overlay = NotesOverlay()
        self.notes_overlay.connect_changed(self._on_notes_changed)
        content_column.append(self.notes_overlay)

        # -- bottom bar: save status only (hotkey hints removed — they
        # duplicated the sidebar tabs, and their combined ~1660px natural
        # width was the actual cause of an earlier window-overflow bug).
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
        self.general.set_on_changed(self._schedule_save_obj)
        self.functional.set_on_changed(self._schedule_save_obj)
        self.sensory.set_on_changed(self._schedule_save_obj)
        self.crps.set_on_changed(self._schedule_save_obj)
        self.functional.set_on_goals_changed(self._on_functional_goal_changed)
        self.pain_classification.set_on_request_kb(self._on_request_kb_entry)
        for tab in (self.active_movement, self.passive_movement,
                    self.muscle_testing, self.special_tests):
            tab.connect("field-changed", lambda *_a: self._schedule_save_obj())

        # -- global hotkeys (capture phase — fire before the focused widget
        # sees the key, matching Textual's Binding(priority=True)) ------------
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_ctrl.connect("key-pressed", self._on_global_key)
        self.add_controller(key_ctrl)

        # -- KB panel focus hook: every KB-relevant widget notifies this app
        # via widgets.add_focus_listener when it gains focus (see widgets.py
        # module docstring for why this is used instead of the window-level
        # Gtk.Root "notify::focus-widget" signal — that proved unreliable
        # once real Stack/ScrolledWindow nesting was involved).
        add_focus_listener(self._on_widget_focused)

        self._load()
        self._show_section("01_consent")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _on_nav_selected(self, _nav, section_id: str) -> None:
        self._show_section(section_id)

    def _on_objective_nav_selected(self, _nav, section_id: str) -> None:
        self._show_section(section_id)

    def _on_objective_back(self, _nav) -> None:
        self._show_section(self._last_assessment_section_id or "01_consent")

    def _on_subsection_jump(self, _bar, key: str) -> None:
        self._show_section("02_subjective")
        self.subjective.jump_to(key)

    def _enter_objective_mode(self) -> None:
        self._show_section("04_objective")

    def _current_section_id(self) -> str:
        return self.objective_nav.active_section if self._in_objective_mode else self.nav.active_section

    def _show_section(self, section_id: str) -> None:
        """Single dispatch point for both sidebars — mirrors
        assessment_view.py's _show_section: "04_objective" enters Objective
        mode (swapping to the second sidebar + region topbar); any
        assessment-mode id exits Objective mode first if it was active
        (any assessment F-key/nav click while in Objective mode leaves it,
        same as the TUI); any Objective-mode id enters Objective mode's UI
        chrome without changing which assessment section to return to."""
        if section_id == "04_objective":
            if not self._in_objective_mode:
                self._last_assessment_section_id = self.nav.active_section
            self._in_objective_mode = True
            self.sidebar_stack.set_visible_child_name("objective")
            self.topbar_stack.set_visible_child_name("region")
            section_id = self.objective_nav.active_section
        elif section_id in _OBJECTIVE_SECTION_IDS:
            if not self._in_objective_mode:
                self._last_assessment_section_id = self.nav.active_section
            self._in_objective_mode = True
            self.sidebar_stack.set_visible_child_name("objective")
            self.topbar_stack.set_visible_child_name("region")
        else:
            if self._in_objective_mode:
                self._in_objective_mode = False
                self.sidebar_stack.set_visible_child_name("assessment")
                self.topbar_stack.set_visible_child_name("subjective")
            self._last_assessment_section_id = section_id

        name = _SECTION_ID_TO_NAME.get(section_id)
        if name is None:
            return
        if section_id in _OBJECTIVE_SECTION_IDS:
            self.objective_nav.set_active(section_id)
        else:
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

    # ------------------------------------------------------------------
    # Region toggling — mirrors objective_view.py's _mount_region /
    # _unmount_region / _sync_active_regions exactly. Only the four Phase 2
    # region tabs are affected; Neurological (and any future generic
    # objective tab) is untouched.
    # ------------------------------------------------------------------

    def _mount_region(self, region_id: str) -> None:
        for tab in self._region_tabs:
            tab.mount_region(region_id)

    def _unmount_region(self, region_id: str) -> None:
        for tab in self._region_tabs:
            tab.unmount_region(region_id)

    def _sync_active_regions(self, regions: list[str]) -> None:
        current = set(self._active_regions)
        target = set(regions)
        for rid in current - target:
            self._unmount_region(rid)
        for rid in target - current:
            self._mount_region(rid)
        self._active_regions = list(regions)
        self.region_topbar.set_active_regions(regions)
        self.pain_classification.set_active_regions(regions)
        self._push_region_tests_to_pain_classification()

    def _collect_region_tests(self, region_id: str) -> dict:
        """Flatten one region's in-memory field values (special/active/muscle/
        passive containers) plus the generic Neurological section into a
        single field-id -> value dict, for the Regional Differential panel.
        Mirrors assessment_view.py's _flatten_region_fields exactly, except
        built from live collect() calls rather than a disk re-read — see
        CONVERSION_PLAN.md's Phase 4 note on why that's the right approach
        here (this app already does the same for cross-ref badge refreshes)."""
        flat: dict = {}
        flat.update(self.neurological.collect())
        flat.update(self.active_movement.get_container(region_id).collect())
        flat.update(self.passive_movement.get_container(region_id).collect())
        flat.update(self.muscle_testing.get_container(region_id).collect())
        flat.update(self.special_tests.get_container(region_id).collect())
        return flat

    def _push_region_tests_to_pain_classification(self) -> None:
        for region_id in self._active_regions:
            self.pain_classification.set_region_test_data(
                region_id, self._collect_region_tests(region_id)
            )

    def _on_request_kb_entry(self, region_id: str, field_id: str) -> None:
        """Wired to PainClassificationSection.set_on_request_kb — clicking a
        Regional Differential test/flag row shows its KB entry, forcing the
        panel visible if it was hidden (matches the TUI's RequestKBEntry
        handler, which always sets kb.display = True on click regardless of
        the panel's current toggle state)."""
        self.kb_panel.update(region_id, field_id)
        if not self.kb_panel.get_visible():
            self.kb_panel.set_visible(True)
            paned_width = self.main_paned.get_width()
            if paned_width > 0:
                content_width = round(paned_width * (1 - self._KB_PANEL_FRACTION))
                self.main_paned.set_position(content_width)

    def _on_region_toggled(self, _bar, region_id: str, active: bool) -> None:
        regions = list(self._active_regions)
        if active and region_id not in regions:
            regions.append(region_id)
        elif not active and region_id in regions:
            regions.remove(region_id)
        else:
            return
        self._sync_active_regions(regions)
        self._schedule_save_obj()

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
        self.general.load(objective.get("general", {}))
        self.functional.load(objective.get("functional", {}))
        self.sensory.load(objective.get("sensory", {}))
        self.crps.load(objective.get("crps", {}))
        self.functional.load_goals(subjective_data)
        self._sync_active_regions(objective.get("active_regions", _DEFAULT_ACTIVE_REGIONS))
        for region_id in self._active_regions:
            region_data = objective.get(region_id, {})
            self.active_movement.get_container(region_id).load(region_data.get("active", {}))
            self.passive_movement.get_container(region_id).load(region_data.get("passive", {}))
            self.muscle_testing.get_container(region_id).load(region_data.get("muscle", {}))
            self.special_tests.get_container(region_id).load(region_data.get("special", {}))
        # _sync_active_regions above already pushed once (mount time, before
        # these loads ran) — push again now that region data is populated.
        self._push_region_tests_to_pain_classification()

    # ------------------------------------------------------------------
    # Global hotkeys — mirrors main.py's PhysioAssessment.BINDINGS for the
    # sections this trial implements:
    #   F1/F2            section switch      (BINDINGS f1/f2)
    #   F4               → Objective mode    (BINDINGS f4 "section_objective" —
    #                      enters Objective mode, resuming whichever objective
    #                      tab was last active there, default General Obs)
    #   Ctrl+F5          → Neurological      (BINDINGS ctrl+f5 "obj_neurological"
    #                      — the TUI's precise jump straight to this section)
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
            self._enter_objective_mode()
            return True
        if name == "F11":
            self._toggle_fullscreen()
            return True
        if ctrl_held and name == "F5":
            self._enter_objective_mode()
            self._show_section("04_neurological")
            return True
        if ctrl_held and name.lower() == "q":
            self._flush_and_quit()
            return True
        if ctrl_held and name.lower() == "a":
            return self._select_all_focused()
        if ctrl_held and name.lower() == "r":
            self._show_report()
            return True
        if ctrl_held and name.lower() == "k":
            self._toggle_kb_panel()
            return True
        if ctrl_held and name.lower() == "d":
            self._open_kb_browser()
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
            name = _SECTION_ID_TO_NAME.get(self._current_section_id())
            if name:
                self._sections_by_name[name].focus_first_field()
        else:
            self.notes_overlay.grab_focus()

    def _on_notes_changed(self, _buffer) -> None:
        if self._loading_notes:
            return
        self._schedule_save()

    # Fraction of the paned's own current width given to the KB panel when
    # shown — a proportion, not a fixed pixel count, so it reads the same
    # relative size in a small window and in fullscreen on a large monitor
    # (a fixed pixel target either ballooned past the screen when it also
    # absorbed window-resize deltas, or shrank to an unreadable sliver in
    # fullscreen when it didn't — both tried and rejected).
    _KB_PANEL_FRACTION = 0.32

    def _open_kb_browser(self) -> None:
        """Ctrl+D — full Clinical KB browser, independent of the Ctrl+K
        focus-triggered cheat sheet (KBDBWindow reads the DB directly, not
        via self.kb_panel)."""
        KBDBWindow(self).present()

    def _toggle_kb_panel(self) -> None:
        """Ctrl+K — matches the TUI's KBPanel toggle."""
        showing = not self.kb_panel.get_visible()
        self.kb_panel.set_visible(showing)
        if showing:
            paned_width = self.main_paned.get_width()
            # get_width() can be 0 before the window's first real layout
            # pass (e.g. toggled a frame after construction, before present()
            # has fully settled) — skip the recompute rather than set a
            # position derived from that, which is what forced the toplevel
            # to grow past the screen in an earlier version of this method.
            if paned_width > 0:
                content_width = round(paned_width * (1 - self._KB_PANEL_FRACTION))
                self.main_paned.set_position(content_width)

    def _on_widget_focused(self, widget) -> None:
        """Per-widget focus hook driving the KB panel — only resolves while
        in Objective mode and only while the panel is actually visible,
        matching the TUI's on_descendant_focus (scoped to
        ObjectiveAssessmentView, and a no-op guard on panel.display)."""
        if not self._in_objective_mode or not self.kb_panel.get_visible():
            return
        field_id = getattr(widget, "field_id", None)
        if field_id is None:
            return
        if field_id.startswith("st_"):
            field_id = field_id[3:]
        registry = get_registry()
        for region_id in self._active_regions:
            entry = registry.resolve(region_id, field_id)
            if entry is not None:
                self.kb_panel.update(region_id, field_id)
                return

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

    def _sync_goals(self, source_goals: list, *dest_sections) -> None:
        """Push source_goals' text into each dest section's .goals list,
        skipping whichever widget currently has focus (never overwrite what
        the user is actively typing into) and any dest whose text already
        matches (avoids redundant "changed" churn)."""
        focused = self.get_focus()
        for dest in dest_sections:
            dest._loading = True
            try:
                for src, dst in zip(source_goals, dest.goals):
                    if dst.textview is focused:
                        continue
                    if dst.text != src.text:
                        dst.text = src.text
            finally:
                dest._loading = False

    def _on_consent_changed(self) -> None:
        self._sync_goals(self.consent.consent_goals, self.subjective, self.functional)
        self._schedule_save()

    def _on_subjective_changed(self) -> None:
        self._sync_goals(self.subjective.goals, self.consent, self.functional)
        self._schedule_save()

    def _on_functional_goal_changed(self) -> None:
        """Functional's ft_goal_N mirror lives in _objective.json, but
        Consent/Subjective's own goal fields (assessment.json) must reflect
        an edit made here too — so this also flushes the assessment-file
        save, on top of the objective-file save already triggered by
        set_on_changed for every Functional field edit."""
        self._sync_goals(self.functional.goals, self.consent, self.subjective)
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

        section_data = {
            OBJECTIVE_SECTION_KEYS["04_neurological"]: self.neurological.collect(),
            "general": self.general.collect(),
            "functional": self.functional.collect(),
            "sensory": self.sensory.collect(),
            "crps": self.crps.collect(),
            "active_regions": list(self._active_regions),
        }
        sections_complete = {
            "04_neurological": self.neurological.is_complete(),
            "04_general": self.general.is_complete(),
            "04_functional": self.functional.is_complete(),
            "04_sensory": self.sensory.is_complete(),
            "04_crps": self.crps.is_complete(),
            "04_active": self.active_movement.is_complete(),
            "04_passive": self.passive_movement.is_complete(),
            "04_muscle": self.muscle_testing.is_complete(),
            "04_special": self.special_tests.is_complete(),
        }
        for region_id in self._active_regions:
            section_data[region_id] = {
                "active": self.active_movement.get_container(region_id).collect(),
                "passive": self.passive_movement.get_container(region_id).collect(),
                "muscle": self.muscle_testing.get_container(region_id).collect(),
                "special": self.special_tests.get_container(region_id).collect(),
            }

        ok = save_objective_sections(self.session_file, section_data, sections_complete)
        self.save_status.set_label("saved" if ok else "SAVE FAILED")
        if ok:
            self._push_region_tests_to_pain_classification()
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
