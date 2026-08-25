"""GTK4 assessment app — full conversion of the assessment TUI, touch-first,
debounced autosave.

Operates against the exact session path passed on the command line —
main.py accepts either a ~/PAB-assessment-gtk/<name>/ disposable dev copy or
(since the isolation relaxation of 2026-08-22) a real ~/PAB/<name>/ session
directly.
"""

from __future__ import annotations
import logging
import subprocess
import threading
from pathlib import Path

import gi

logger = logging.getLogger(__name__)

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Gio  # noqa: E402

from .storage_bridge import (
    load_assessment_block, save_sections, SECTION_KEYS,
    load_objective_block, save_objective_sections, OBJECTIVE_SECTION_KEYS,
    generate_all_reports_final, load_session_json,
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
from .search import build_index, find_by_field_id, find_by_anchor_id
from .search_widget import SearchModal
from .grid_overview import (
    GridOverviewPage, SUBJ_GRID_DATA, OBJ_GRID_DATA,
    section_to_cursor, _section_has_data,
)
from .widgets import add_focus_listener
from .nav import SectionNav
from .topbar import SubsectionNavBar
from .footer import FooterBar
from .report_modal import ReportModal
from .notes_overlay import NotesOverlay
from .chart_watcher import ChartFileWatcher
from .report_timer import ReportTimer
from .timer_widget import SessionTimerWidget
from .objective.sections.lumbar_tables import sij_report_compat
from .goniometer_import import importer as gonio_importer
from .goniometer_import.matcher import match_batch
from .goniometer_import.wizard_screen import GonioImportWizard, GonioPatientPickerWindow

AUTOSAVE_DEBOUNCE_MS = 2000

# Session-timer alert tuning — dialled in with the user 2026-08-24 via a
# standalone scratchpad workshop app before landing here (see
# session_timer.py / timer_widget.py for the rest of the timer design).
TIMER_ALERT_SOUND = Path(__file__).parent / "assets" / "timer_alert.wav"
TIMER_ALERT_VOLUME_PCT = 80
TIMER_FLASH_OPACITY = 0.80
TIMER_FLASH_DURATION_MS = 150
TIMER_FLASH_PULSE_GAP_MS = 700

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
# was last saved once a session is loaded. No live body-chart region sync
# yet (same deferral as the KB panel) — toggling is manual only.
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

        # Wrapped in a Gtk.Overlay so the session-timer's 20/40/55-min
        # screen flash (self._timer_flash_box, below) can cover the WHOLE
        # window rather than just one section — the overlay child has
        # can_target(False) so it never intercepts clicks/taps, matching
        # the "brief, non-blocking, doesn't steal focus" requirement
        # confirmed with the user 2026-08-24.
        root_overlay = Gtk.Overlay()
        root_overlay.set_child(outer)
        self.set_child(root_overlay)

        self._timer_flash_box = Gtk.Box()
        self._timer_flash_box.add_css_class("timer-flash-overlay")
        self._timer_flash_box.set_can_target(False)
        self._timer_flash_box.set_opacity(0)
        root_overlay.add_overlay(self._timer_flash_box)

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
        self.sidebar_stack.set_vexpand(True)

        # -- session-length clock — pinned at the bottom of the left sidebar
        # column, below sidebar_stack rather than inside SectionNav or
        # ObjectiveNav individually, so it stays put across BOTH modes
        # (those two swap wholesale via sidebar_stack — anything placed only
        # inside one would vanish when the other is shown). See
        # timer_widget.py's module docstring for the full behaviour.
        self.session_timer_widget = SessionTimerWidget()
        self.session_timer_widget.set_on_alert(self._on_session_timer_alert)

        sidebar_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_column.append(self.sidebar_stack)
        sidebar_column.append(self.session_timer_widget)
        main_row.append(sidebar_column)

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

        # -- Ctrl+T heading map: a page in this SAME stack (not a popup
        # window) — see grid_overview.py's module docstring for why an
        # in-place page, not an overlay, is the deliberate choice here.
        self.grid_overview = GridOverviewPage()
        self._grid_cursor: tuple[int, int] = (0, 0)
        self._grid_cursor_set = False
        self._pre_grid_stack_name: str | None = None
        self.stack.add_named(self.grid_overview, "grid_overview")

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
        self.consent.set_on_below_framing_changed(self.session_timer_widget.on_field_edit)
        self.subjective.set_on_changed(self._on_subjective_changed)
        self.medical.set_on_changed(self._on_medical_changed)
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

        # -- Live body-chart re-sync — see chart_watcher.py's module
        # docstring for full scope/verification notes. Started only after
        # _load() so the baseline mtime it records reflects what was just
        # read, not a stale/absent value.
        self._chart_watcher = ChartFileWatcher(self.session_file, self._on_chart_update)
        self._chart_watcher.start()

        # -- Periodic background report regeneration — see report_timer.py's
        # module docstring for the full design (60s cadence, matching
        # assessment_view.py's own _report_interval; independent of Ctrl+R's
        # report_modal.py, exactly like the reference TUI).
        self._report_timer = ReportTimer(self.session_file)
        self._report_timer.start()

        self.connect("close-request", self._on_close_request)

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

    def _load_region_data(self, region_id: str, objective: dict | None = None) -> None:
        """Loads region_id's saved data (active/passive/muscle/special) from
        _objective.json into its four containers — regardless of whether
        they were just mounted or have been sitting mounted all along.
        Pass a pre-read objective block (from load_objective_block) to
        avoid re-reading the file when the caller already has one, e.g.
        _load()'s own loop over every active region; omit it for a
        standalone call, e.g. from _mount_region."""
        if objective is None:
            objective = load_objective_block(self.session_file)
        region_data = objective.get(region_id, {})
        self.active_movement.get_container(region_id).load(region_data.get("active", {}))
        self.passive_movement.get_container(region_id).load(region_data.get("passive", {}))
        self.muscle_testing.get_container(region_id).load(region_data.get("muscle", {}))
        # SIJ Provocation Signs (Lumbar Special Tests) is the one field set
        # whose real data lives entirely in "special" — the OLD-shape values
        # also written into "muscle" (see _do_save_obj) are a write-only
        # summary for storage.py's report generator, never read back here.
        self.special_tests.get_container(region_id).load(region_data.get("special", {}))

    def _mount_region(self, region_id: str) -> None:
        """Mount region_id's four containers (active/passive/muscle/special)
        AND load its previously-saved data into them — see bug fixed
        2026-08-23. RegionTabContent.mount_region() only ever creates blank
        containers; nothing loaded saved data back in except a one-time loop
        in _load() covering whichever regions happened to already be active
        at session-open time. Toggling a region off then back on (or any
        region not active at open) called this method directly with no
        equivalent step, so the new container stayed blank — and the very
        next debounced autosave then collected that blank container and
        overwrote the correct on-disk data with it. Confirmed live: cervical
        flexion ROM entered, region toggled off (data still correct on
        disk), toggled back on (field blank), which then got saved back as
        blank, wiping the real value. Loading here, unconditionally on every
        mount (construction-time default regions included), makes "freshly
        mounted" and "has its saved data" the same thing.

        NOTE (bug found 2026-08-23, same day, goniometer-import testing):
        this alone is NOT enough for _load() to correctly refresh an
        ALREADY-mounted region — _sync_active_regions only calls this for
        regions newly transitioning to active, so a region that was active
        both before and after a reload (the common case) never went through
        here again, and its on-screen values silently stayed stale even
        though the file changed. Confirmed live: a goniometer import wrote
        124° into an already-active Shoulder region's data, apply correctly
        rewrote _objective.json and called _load(), but the on-screen field
        kept showing an old manually-typed value — because _load() only
        reloads a region THROUGH here when _sync_active_regions treats it as
        newly-mounted. Fixed there, not here — see _load()'s own explicit
        loop over every currently-active region."""
        for tab in self._region_tabs:
            tab.mount_region(region_id)
        self._load_region_data(region_id)

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
        # Flush any pending debounced save FIRST, same reasoning as
        # _flush_and_quit/_show_report: _sync_active_regions below destroys
        # the outgoing region's container immediately. If a save was already
        # scheduled (2s debounce) from an edit made moments ago and hadn't
        # fired yet, _do_save_obj would run AFTER the container is gone —
        # collect() can't see a destroyed widget, so that edit would be
        # silently dropped from the merge-write entirely (found + fixed
        # 2026-08-23 alongside the mount_region data-loss bug, as part of an
        # audit for the same class of "widget destroyed before its data was
        # ever read" bug).
        if self._save_source_id_obj is not None:
            GLib.source_remove(self._save_source_id_obj)
            self._save_source_id_obj = None
            self._do_save_obj()
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
        # Explicit, unconditional loop — NOT redundant with _mount_region's
        # own load (bug found 2026-08-23, see _mount_region's docstring
        # note): _sync_active_regions only mounts (and therefore only loads)
        # regions newly transitioning to active. A region already active
        # both before and after this _load() call — the common case for any
        # reload of an already-open session, e.g. after a goniometer import
        # writes new values into an already-active region — would otherwise
        # never have its on-screen containers refreshed at all, even though
        # the file just changed underneath them.
        for region_id in self._active_regions:
            self._load_region_data(region_id, objective)
        self._push_region_tests_to_pain_classification()
        self._update_medical_tab_color()

    def _on_medical_changed(self) -> None:
        """Medical section's set_on_changed callback — GTK counterpart to
        tui.py's on_medical_section_field_changed, which does the same two
        things (_schedule_save then _update_medical_tab_color) on every
        field edit. Unlike the TUI, this port doesn't also refresh on
        leaving the Medical tab or after every _do_save() — this single
        continuously-live hook already keeps the tab colour correct at all
        times, making those extra TUI call sites redundant here rather than
        a missing feature."""
        self._schedule_save()
        self._update_medical_tab_color()

    def _update_medical_tab_color(self) -> None:
        """GTK port of assessment_view.py's _update_medical_tab_color —
        colours the "03 Medical" sidebar tab from
        MedicalSection.urgent_red_flag_status()."""
        self.nav.set_tab_status("03_medical", self.medical.urgent_red_flag_status())

    def _on_chart_update(self, data: dict) -> None:
        """ChartFileWatcher callback — GTK counterpart to tui.py's
        on_chart_update. See chart_watcher.py's module docstring for exactly
        what this does and does not do (only Subjective's note slots;
        no active-region sync, no session-switch, no focus-signal)."""
        try:
            self.subjective.refresh_from_chart(data)
        except Exception as e:
            logger.error("chart update handler failed: %s", e)

    # ------------------------------------------------------------------
    # Global hotkeys — mirrors main.py's PhysioAssessment.BINDINGS for the
    # sections implemented here:
    #   F1/F2            section switch      (BINDINGS f1/f2)
    #   F4               → Objective mode    (BINDINGS f4 "section_objective" —
    #                      enters Objective mode, resuming whichever objective
    #                      tab was last active there, default General Obs)
    #   Ctrl+F1–F8       → direct objective-tab jump (BINDINGS ctrl+f1..f8
    #                      "obj_general"/"obj_functional"/"obj_active"/
    #                      "obj_passive"/"obj_neurological"/"obj_sensory"/
    #                      "obj_muscle"/"obj_special" — each just
    #                      _enter_objective_mode() + _show_section(), same as
    #                      main.py's own _goto_objective_section helper)
    #   Alt+<letter>     subjective jump     (BINDINGS alt+s/h/b/m/a/w/e/4/p/g/r)
    #   Ctrl+Q           quit, flushing any pending debounced save first
    #   Ctrl+A           select-all in the focused text field
    # ------------------------------------------------------------------

    _ALT_KEY_MAP = {
        "s": "symptoms", "h": "history", "b": "behaviour", "m": "management",
        "a": "activity", "w": "work", "e": "sleep", "4": "24hr",
        "p": "psychosocial", "g": "goals", "r": "risk",
    }

    # Ctrl+F1..F8 -> objective section id, matching main.py's BINDINGS table
    # and action_obj_* methods exactly (order: General, Functional, Active,
    # Passive, Neurological, Sensory, Muscle, Special — NOT the sidebar's
    # own display order, which puts Functional after Active/Passive; this
    # is the TUI's own F-key numbering, kept as-is for muscle memory).
    _CTRL_FN_OBJECTIVE_MAP = {
        "F1": "01_general",
        "F2": "07_functional",
        "F3": "02_active",
        "F4": "03_passive",
        "F5": "04_neurological",
        "F6": "05_sensory",
        "F7": "06_muscle",
        "F8": "08_special",
    }

    def _on_global_key(self, _ctrl, keyval, _keycode, state) -> bool:
        ctrl_held = bool(state & Gdk.ModifierType.CONTROL_MASK)
        alt_held = bool(state & Gdk.ModifierType.ALT_MASK)
        name = Gdk.keyval_name(keyval) or ""

        # Grid overview page owns Escape/arrows while it's the visible
        # stack child — checked first, ahead of every other binding below,
        # since Up/Down/Left/Right would otherwise fall through unhandled.
        if self.stack.get_visible_child_name() == "grid_overview":
            if name == "Escape":
                self._close_grid_overview()
                return True
            if name in ("Up", "Down", "Left", "Right"):
                self.grid_overview.move_cursor(name)
                return True

        if ctrl_held and name in self._CTRL_FN_OBJECTIVE_MAP:
            self._enter_objective_mode()
            self._show_section(self._CTRL_FN_OBJECTIVE_MAP[name])
            return True

        if name == "F1" and not ctrl_held:
            self._show_section("01_consent")
            return True
        if name == "F2" and not ctrl_held:
            self._show_section("02_subjective")
            return True
        if name == "F3" and not ctrl_held:
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
        if name == "F4" and not ctrl_held:
            self._enter_objective_mode()
            return True
        if name == "F11":
            self._toggle_fullscreen()
            return True
        if ctrl_held and name.lower() == "q":
            self._flush_and_quit()
            return True
        if ctrl_held and name.lower() == "b":
            self._switch_to_bodychart()
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
        if ctrl_held and name.lower() == "f":
            self._open_search()
            return True
        if ctrl_held and name.lower() == "t":
            self._toggle_grid_overview()
            return True
        if ctrl_held and name.lower() == "g":
            self._open_gonio_import()
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

    def _open_gonio_import(self) -> None:
        """Ctrl+G — import goniometer ROM measurements for the open patient
        from ~/PAB/_inbox/goniometer/<code>/, via a fast review wizard, into
        the matching AROM or PROM fields per each measurement's phone-set
        mode. GTK port of tui.py's action_import_gonio — same fallback to
        the most-recently-imported file when nothing new is pending (so a
        mistake spotted after Apply can be fixed by re-running and
        re-applying), same combine-multiple-pending-files-into-one-review
        behaviour, same reload-from-disk after apply.

        patient_code source: the reference TUI reads SessionHeader.patient_id
        (a TUI-only widget gpab has no equivalent of) — this port reads the
        same value gpab already has on disk, _session.json's own
        "patient_id" field, via load_session_json. That file also happens to
        be what determines the inbox directory name convention
        (~/PAB/_inbox/goniometer/<code>/) in real use, confirmed against the
        two real .gonio.json samples already on this machine.

        NO REFERENCE EQUIVALENT for what happens next (added 2026-08-23 per
        direct user feedback): the reference TUI's exact-code match has no
        fallback at all — a typo'd or mismatched patient_id is a silent
        dead end there. This port tries the exact code first (unchanged
        behaviour otherwise), and only when that finds nothing does it offer
        a picker over whatever codes DO have data waiting
        (GonioPatientPickerWindow), via importer.available_patient_codes().
        """
        session_json = load_session_json(self.session_file)
        patient_code = (session_json.get("patient_id") or "").strip()

        if patient_code and (gonio_importer.inbox_files_for(patient_code)
                              or gonio_importer.imported_files_for(patient_code)):
            self._run_gonio_import_for(patient_code)
            return

        available = [s for s in gonio_importer.available_patient_codes() if s.code != patient_code]
        if not available:
            msg = (f"No goniometer data waiting for {patient_code}" if patient_code
                   else "No goniometer data waiting for any patient")
            self.save_status.set_label(msg)
            return

        def _after_pick(code: str | None) -> None:
            if code:
                self._run_gonio_import_for(code)

        GonioPatientPickerWindow(self, patient_code, available, _after_pick).present()

    def _run_gonio_import_for(self, patient_code: str) -> None:
        """Given a resolved patient_code (exact match, or picked from
        GonioPatientPickerWindow's fallback list), runs the actual
        find-files -> match -> wizard -> apply flow. Split out from
        _open_gonio_import so both the direct-match and picker-fallback
        paths share it."""
        files = gonio_importer.inbox_files_for(patient_code)
        reimporting = False
        if not files:
            files = gonio_importer.imported_files_for(patient_code)[:1]  # most recent only
            reimporting = True
        if not files:
            self.save_status.set_label(f"No goniometer data waiting for {patient_code}")
            return

        # Combine every pending file for this patient into one review pass —
        # grouping/side-inference then spans the whole visit even if the
        # phone sent it in more than one batch.
        combined = []
        offset = 0
        for f in files:
            _, measurements = gonio_importer.load_gonio_measurements(f)
            for m in measurements:
                m.index += offset
            combined.extend(measurements)
            offset += len(measurements)

        if not combined:
            self.save_status.set_label(f"Goniometer file(s) for {patient_code} had no measurements")
            return

        results = match_batch(combined)

        def _after_wizard(grouped) -> None:
            if not grouped:
                return  # cancelled — nothing written, files stay where they were

            # Flush any pending debounced objective save FIRST — apply_grouped_values
            # writes _objective.json directly, behind the live widget tree. An
            # already-armed debounce firing AFTER that write would collect
            # stale in-memory values and silently overwrite the freshly
            # imported ones (same class of bug fixed in _on_region_toggled
            # earlier the same day). Order matters: flush, then apply, then
            # archive, then reload.
            if self._save_source_id_obj is not None:
                GLib.source_remove(self._save_source_id_obj)
                self._save_source_id_obj = None
                self._do_save_obj()

            gonio_importer.apply_grouped_values(self.session_file, grouped)
            for f in files:
                gonio_importer.archive_imported_file(f)

            verb = "Re-imported" if reimporting else "Imported"
            self.save_status.set_label(f"{verb} {len(grouped)} ROM field(s) for {patient_code}")

            # Reload everything from disk so the new values show immediately
            # — same path used for opening a session, and the only way the
            # live widget tree picks up a write that just happened entirely
            # outside it. _load()'s _sync_active_regions call correctly
            # mounts (and now loads data into, per the mount_region fix)
            # any region the import newly activated.
            self._load()

        GonioImportWizard(self, results, _after_wizard).present()

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

    def _show_notes(self) -> None:
        """Unconditionally show + focus the notes overlay — used by search
        jump (a scratchpad_text hit), unlike _toggle_notes (F10) which flips
        whatever the current state is."""
        self.notes_overlay.set_visible(True)
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

    def _open_search(self) -> None:
        """Ctrl+F — jump-search across sections, subsections, and fields.
        Mirrors the TUI's action_search/SearchModal."""
        index = build_index(self)

        def on_selected(entry) -> None:
            if entry is not None:
                self._execute_jump(entry)

        SearchModal(self, index, on_selected).present()

    def _execute_jump(self, entry) -> None:
        """Navigate to a chosen search result — GTK counterpart to
        tui.py's _execute_jump. A "subsection" entry (no widget_id) scrolls
        the subsection's own header to the top of the section's viewport,
        via the same anchor_id tagging/machinery Ctrl+T's grid overview
        uses (widgets.make_subsection_header's anchor_id, found by
        search.find_by_anchor_id, aligned by _scroll_section_to_anchor) —
        no longer just switching to the section's first field. Every
        "field"/"content" entry (the common case — a named field or typed
        text) still jumps to the exact widget and focuses it, via
        find_by_field_id against whichever page is now on screen."""
        if entry.widget_id and entry.widget_id.startswith("__workup_"):
            wid = entry.widget_id.split("__", 2)[-1]
            self._show_section("06_diagnosis")
            self.diagnosis.select_workup(wid)
            return

        if entry.section_id == "scratchpad":
            self._show_notes()
            return

        section_id = entry.section_id[4:] if entry.section_id.startswith("obj:") else entry.section_id
        self._show_section(section_id)

        if entry.widget_id:
            page = self.stack.get_visible_child()
            widget = find_by_field_id(page, entry.widget_id) if page is not None else None
            if widget is not None:
                widget.grab_focus()
        elif entry.anchor_id:
            if section_id == "08_special" and entry.anchor_id.startswith("st_"):
                # Same as the grid overview's Special Tests row: these
                # anchor_ids name a body region, not a subsection header,
                # and the region may not be mounted yet.
                self._jump_to_special_region(entry.anchor_id)
            else:
                name = _SECTION_ID_TO_NAME.get(section_id)
                if name is not None:
                    self._scroll_section_to_anchor(name, entry.anchor_id)

    def _collect_grid_has_data(self, grid_data) -> dict[str, bool]:
        has_data: dict[str, bool] = {}
        for sid, _, _ in grid_data:
            name = _SECTION_ID_TO_NAME.get(sid)
            section = self._sections_by_name.get(name) if name else None
            if section is None:
                has_data[sid] = False
                continue
            try:
                has_data[sid] = _section_has_data(section.collect())
            except Exception:
                has_data[sid] = False
        return has_data

    def _toggle_grid_overview(self) -> None:
        """Ctrl+T — heading map for rapid section jump (TUI's Ctrl+G,
        rebound — see grid_overview.py's module docstring for why). Toggles:
        a second press while the grid is showing closes it back to whatever
        section was active before, exactly like the TUI's own toggle_grid."""
        if self.stack.get_visible_child_name() == "grid_overview":
            self._close_grid_overview()
        else:
            self._open_grid_overview()

    def _open_grid_overview(self) -> None:
        self._pre_grid_stack_name = self.stack.get_visible_child_name()
        grid_data = OBJ_GRID_DATA if self._in_objective_mode else SUBJ_GRID_DATA
        has_data = self._collect_grid_has_data(grid_data)
        cursor = (
            self._grid_cursor if self._grid_cursor_set
            else section_to_cursor(self._current_section_id(), grid_data)
        )

        def on_selected(section_id: str, anchor_id: str) -> None:
            self._grid_cursor = self.grid_overview.current_cursor()
            self._grid_cursor_set = True
            # The SUBJ_GRID_DATA "04_objective" row is the one place
            # anchor_id is itself a section id (e.g. "02_active") rather
            # than an anchor within section_id — _show_section already
            # handles any objective section id directly regardless of
            # current mode, so no special-casing needed here.
            if section_id == "04_objective":
                self._show_section(anchor_id)
            elif section_id == "08_special":
                # OBJ_GRID_DATA's Special Tests row lists body regions, not
                # subsection anchors (Special Tests has no fixed layout of
                # its own — see grid_overview.py) — anchor_id is "st_<region>";
                # the region may not currently be mounted, unlike every other
                # row's target, so activate it first.
                self._show_section(section_id)
                self._jump_to_special_region(anchor_id)
            else:
                self._show_section(section_id)
                name = _SECTION_ID_TO_NAME.get(section_id)
                if name is not None:
                    self._scroll_section_to_anchor(name, anchor_id)

        self.grid_overview.open(grid_data, has_data, cursor, on_selected)
        self.stack.set_visible_child_name("grid_overview")

    def _scroll_section_to_anchor(self, name: str, anchor_id: str) -> None:
        """Scroll `name`'s stack page so the widget tagged with anchor_id
        (widgets.make_subsection_header's anchor_id, or an Outcome Measures
        Gtk.Expander's own .anchor_id) sits at the top of the viewport,
        instead of leaving whatever focus_first_field() already focused —
        which can leave the subsection's own header scrolled above the
        visible area. Deferred via GLib.timeout_add: GTK layout/allocation
        for a stack page just made visible isn't available synchronously
        right after set_visible_child_name (mirrors the TUI's own
        set_timer(0.05, ...) deferral in assessment_view.py's
        navigate_to_heading)."""
        scroll = self.stack.get_child_by_name(name)
        section = self._sections_by_name.get(name)
        if scroll is None or section is None:
            return

        def do_scroll() -> bool:
            target = find_by_anchor_id(section, anchor_id)
            if target is None:
                return False
            if isinstance(target, Gtk.Expander) and not target.get_expanded():
                # Outcome Measures blocks are collapsed by default —
                # compute_bounds would measure the collapsed height, so
                # expand first and re-measure next frame.
                target.set_expanded(True)
                GLib.timeout_add(50, do_scroll)
                return False
            ok, bounds = target.compute_bounds(scroll)
            if not ok:
                return False
            vadj = scroll.get_vadjustment()
            newval = max(
                vadj.get_lower(),
                min(vadj.get_value() + bounds.origin.y, vadj.get_upper() - vadj.get_page_size()),
            )
            vadj.set_value(newval)
            if target.get_can_focus():
                target.grab_focus()
            return False

        GLib.timeout_add(50, do_scroll)

    def _jump_to_special_region(self, anchor_id: str) -> None:
        """Special Tests row click: anchor_id is "st_<region>" — mount that
        region if it isn't already active, then scroll straight to its
        RegionContainer (the container itself is the target, no header
        text-matching needed — unlike every other row)."""
        region_id = anchor_id.removeprefix("st_")
        if region_id not in self._active_regions:
            self._sync_active_regions(self._active_regions + [region_id])

        scroll = self.stack.get_child_by_name("special_tests")
        if scroll is None:
            return

        def do_scroll() -> bool:
            container = self.special_tests.get_container(region_id)
            if container is None:
                return False
            ok, bounds = container.compute_bounds(scroll)
            if not ok:
                return False
            vadj = scroll.get_vadjustment()
            newval = max(
                vadj.get_lower(),
                min(vadj.get_value() + bounds.origin.y, vadj.get_upper() - vadj.get_page_size()),
            )
            vadj.set_value(newval)
            return False

        GLib.timeout_add(50, do_scroll)

    def _close_grid_overview(self) -> None:
        """Escape, or a second Ctrl+T — dismiss without navigating,
        remembering the cursor position exactly like the TUI does."""
        self._grid_cursor = self.grid_overview.current_cursor()
        self._grid_cursor_set = True
        if self._pre_grid_stack_name:
            self.stack.set_visible_child_name(self._pre_grid_stack_name)

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

    def _switch_to_bodychart(self) -> None:
        """Ctrl+B — raise bodychart's window instead of gpab's own, the
        dedicated-key half of "feels like one program" (2026-08-25; see
        bodychart/src/window.c's matching Ctrl+B handler, which raises
        gpab). Landed on Ctrl+B (no particular mnemonic — "for all I care"
        was the user's own bar) only after two failed attempts, both
        live-tested the same day: Ctrl+` (the user's original preference,
        from the old embedded-TUI setup) and then Ctrl+Tab both got
        silently intercepted before reaching either app's key handler at
        all — something below GNOME's own gsettings-visible keybindings
        (checked thoroughly: wm/mutter/shell schemas, no explicit binding
        for either combo found anywhere) reproducibly caught both as its
        own app/window-switcher gesture instead. Ctrl+B is a plain letter
        with no switcher-like semantics and wasn't already bound in either
        app (unlike Ctrl+A, which gpab already uses for select-all).
        `gapplication launch <app-id>` on an app that's already running
        doesn't spawn a second instance — it re-delivers "activate" to the
        existing one, which for bodychart just presents its window (single
        window, nothing to dedupe there, unlike gpab's own on_activate —
        see build_app's docstring on that). Best-effort: if bodychart isn't
        running, this silently does nothing rather than launching a fresh
        one with no session — matches how the reverse direction
        (bodychart's Ctrl+B) is scoped too."""
        try:
            subprocess.Popen(
                ["gapplication", "launch", "com.gpab.bodychart"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            logger.warning("_switch_to_bodychart: gapplication launch failed: %s", e)

    def _flush_and_quit(self) -> None:
        """Ctrl+Q — just closes the window; _on_close_request does the actual
        flush-then-report work, uniformly for every close path (this, the
        window's own close button, and window-manager close), not just this
        one. Kept as a separate method since Ctrl+Q's key handler already
        calls it by name."""
        self.close()

    def _on_close_request(self, *_a) -> bool:
        """Runs for every close path — window-manager close, the window's own
        close button, and Ctrl+Q's _flush_and_quit — not just one of them.

        Gap fixed 2026-08-23: previously only a "destroy" handler existed
        here, which just stopped the chart watcher / 60s report timer with no
        final flush or report regeneration at all. Confirmed live: text typed
        into a real session made it into *_assessment.json (autosave worked)
        but never into any report file, because nothing ever called the
        report generators on close — the periodic 60s timer only covers
        edits made at least 60s before the app closes. Mirrors
        assessment_view.py's AssessmentView.on_unmount() exactly: flush any
        pending debounced save first (same reasoning as _show_report's own
        flush — the report must reflect the latest edit, not whatever was
        last on disk before the debounce fired), stop the background
        watchers, then run a FINAL full regeneration (raw + markdown + clean
        + docx — the one format the periodic timer deliberately skips) in a
        non-daemon background thread so it keeps completing (including the
        slower pandoc/docx step) even after the window itself has closed.
        """
        if self._save_source_id is not None:
            GLib.source_remove(self._save_source_id)
            self._save_source_id = None
            self._do_save()
        if self._save_source_id_obj is not None:
            GLib.source_remove(self._save_source_id_obj)
            self._save_source_id_obj = None
            self._do_save_obj()

        self._chart_watcher.stop()
        self._report_timer.stop()
        self.session_timer_widget.stop()

        # "Close once" (2026-08-25): whichever of the two windows closes,
        # the other should too — best-effort, fire-and-forget, never blocks
        # this close. If bodychart isn't running this just fails silently
        # (no bus name to activate); if bodychart is ALSO mid-close right
        # now (the two closed each other within the same instant) this is
        # a harmless duplicate that no-ops against an already-vanishing
        # bus name, not a loop — bodychart's own quit action doesn't call
        # back into this one, it only runs bodychart's own close path.
        try:
            subprocess.Popen(
                ["gapplication", "action", "com.gpab.bodychart", "quit"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            logger.warning("_on_close_request: gapplication action quit failed: %s", e)

        session_file = self.session_file

        def _run() -> None:
            try:
                generate_all_reports_final(session_file)
            except Exception as e:
                logger.error("_on_close_request: generate_all_reports_final failed: %s", e)

        threading.Thread(target=_run, daemon=False).start()
        return False  # allow the close to proceed

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

    def _on_session_timer_alert(self, pulses: int) -> None:
        """20/40 min -> pulses=1 (one beep, one flash); 55 min -> pulses=2
        (two of each, TIMER_FLASH_PULSE_GAP_MS apart). Sound playback is
        fire-and-forget via a detached subprocess — never block the GTK
        main thread waiting on audio playback."""
        self._play_timer_alert_sound()
        self._flash_timer_alert()
        if pulses == 2:
            GLib.timeout_add(TIMER_FLASH_PULSE_GAP_MS, self._session_timer_second_pulse)

    def _session_timer_second_pulse(self) -> bool:
        self._play_timer_alert_sound()
        self._flash_timer_alert()
        return GLib.SOURCE_REMOVE

    def _play_timer_alert_sound(self) -> None:
        paplay_volume = int(65536 * (TIMER_ALERT_VOLUME_PCT / 100.0))
        try:
            subprocess.Popen(
                ["paplay", f"--volume={paplay_volume}", str(TIMER_ALERT_SOUND)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            try:
                subprocess.Popen(
                    ["aplay", str(TIMER_ALERT_SOUND)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError as e:
                logger.error("session timer: no audio player found (paplay/aplay): %s", e)

    def _flash_timer_alert(self) -> None:
        self._timer_flash_box.set_opacity(TIMER_FLASH_OPACITY)
        GLib.timeout_add(TIMER_FLASH_DURATION_MS, self._end_timer_flash)

    def _end_timer_flash(self) -> bool:
        self._timer_flash_box.set_opacity(0)
        return GLib.SOURCE_REMOVE

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
            muscle_data = self.muscle_testing.get_container(region_id).collect()
            special_data = self.special_tests.get_container(region_id).collect()
            if region_id == "lumbar":
                # SIJ Provocation Signs is collected from the Special Tests
                # widget (moved there 2026-08-24) using new st_sij_* field
                # ids — special_data keeps that real data untouched.
                # storage.py's report generator — reused unchanged, never
                # edited — hardcodes reading these 6 tests as one plain
                # boolean each from the region's "muscle" dict under their
                # OLD field ids (see lumbar_tables.py's module docstring),
                # so ADDITIONALLY merge in a derived summary under those old
                # ids purely for the report text to keep working.
                muscle_data.update(sij_report_compat(special_data))
            section_data[region_id] = {
                "active": self.active_movement.get_container(region_id).collect(),
                "passive": self.passive_movement.get_container(region_id).collect(),
                "muscle": muscle_data,
                "special": special_data,
            }

        ok = save_objective_sections(self.session_file, section_data, sections_complete)
        self.save_status.set_label("saved" if ok else "SAVE FAILED")
        if ok:
            self._push_region_tests_to_pain_classification()
        return GLib.SOURCE_REMOVE


def build_app(session_file: str) -> Gtk.Application:
    """Owns two 2026-08-25 additions on top of the plain single-window app,
    both in service of "feels like one program with bodychart" — see
    TrialWindow._switch_to_bodychart's docstring for the other half:

    1. on_activate now reuses an existing window instead of creating a new
       TrialWindow every time it fires. It used to always create one, which
       was harmless as long as nothing ever re-activated a running
       instance (the only real trigger was a second `gpab_assessment.main`
       launch, and that always got pkilled first by bodychart's
       kill_existing_gpab / ./gpab's own pkill, so on_activate only ever
       ran once per process in practice). That stops being true now that
       bodychart's Ctrl+B deliberately re-activates a still-running gpab on
       purpose (via `gapplication launch`) to raise its window — without
       this fix that would have popped a second, confusingly-blank
       TrialWindow on top of the real one instead.
    2. A "quit" GAction, activated remotely via
       `gapplication action com.gpab.assessment quit` — the half of "close
       once" that lets bodychart's own close handler ask gpab to close too.
       Just closes the window, same as any other close path — routes
       through TrialWindow._on_close_request as normal, no shortcuts on the
       flush/report-regeneration work that path does.
    """
    app = Gtk.Application(application_id="com.gpab.assessment")
    state = {"win": None}

    def on_quit_action(_action, _param) -> None:
        if state["win"] is not None:
            state["win"].close()

    quit_action = Gio.SimpleAction.new("quit", None)
    quit_action.connect("activate", on_quit_action)
    app.add_action(quit_action)

    def on_activate(app):
        if state["win"] is not None:
            state["win"].present()
            return

        display = Gdk.Display.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).with_name("style.css")))
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        win = TrialWindow(app, session_file)
        state["win"] = win

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

        # Default to fullscreen on startup — per direct user feedback
        # 2026-08-23: "full attention, no distraction" was the whole point
        # of this touch-first port, and opening windowed undercut that.
        # Deferred 200ms, not called immediately after present() — same
        # rationale, and the same proven fix, as bodychart's own
        # deferred_fullscreen in window.c: requesting fullscreen before the
        # compositor has finished the initial windowed configure round-trip
        # is exactly the kind of thing that's already needed a workaround
        # once on this machine's compositor. F11 (_toggle_fullscreen) still
        # works normally afterward since _is_fullscreen is set to match.
        def _start_fullscreen() -> bool:
            win.fullscreen()
            win._is_fullscreen = True
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(200, _start_fullscreen)

    app.connect("activate", on_activate)
    return app
