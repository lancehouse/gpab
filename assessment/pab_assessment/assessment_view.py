"""Assessment view with section navigation."""

import asyncio
import json
import logging
import threading
from pathlib import Path

from textual.app import ComposeResult, on
from textual import events
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.widgets import Button, Label, Static, TextArea

from .sections.consent import ConsentSection
from .sections.subjective import SubjectiveSection
from .sections.medical import MedicalSection
from .sections.pain_classification import PainClassificationSection
from .sections.outcome_measures import OutcomeMeasuresSection
from .sections.diagnosis import DiagnosisSection
from .sections.barriers import BarriersSection
from .sections.rx_plan import RxPlanSection
from .objective.objective_view import ObjectiveAssessmentView, RegionTopbar
from .objective.kb_panel import KBPanel
from .objective.kb_loader import get_registry
from .sections.regional_differential import RequestKBEntry
from .grid_overview import GridOverview, SUBJ_GRID_DATA, _section_has_data, section_to_cursor
from .storage import (
    save_all_sections,
    save_raw_report,
    export_session_report,
    save_clean_reports,
    save_docx_report,
    assessment_path,
    load_objective,
)

_REPORT_INTERVAL = 60.0  # seconds between background report regeneration


def _flatten_region_fields(obj_assessment: dict, region_id: str) -> dict:
    """Flatten one region's objective dict (special/active_movement/muscle_testing/...)
    plus the generic Neurological section into a single field-id → value dict for
    the section 05 Regional Differential panel. Field ids are unique across
    sections, so a flat merge is safe — this is what lets that panel show DB
    cluster members that live outside special_tests (e.g. Cervical Rotation ROM,
    an Active Movement field; Cook Myelopathy's UMN signs, which live in
    Neurological — a top-level generic section, not nested per-region like
    special_tests is, so it has to be merged in explicitly rather than picked up
    by iterating obj_assessment[region_id])."""
    flat: dict = {}
    neurological = obj_assessment.get("neurological", {})
    if isinstance(neurological, dict):
        flat.update(neurological)
    region_data = obj_assessment.get(region_id, {})
    for section_data in region_data.values():
        if isinstance(section_data, dict):
            flat.update(section_data)
    return flat


def _exit_generate_all_reports(session_file: str) -> None:
    """Run all report generators serially — called in a non-daemon thread at exit."""
    save_raw_report(session_file)
    export_session_report(session_file)
    save_clean_reports(session_file)
    save_docx_report(session_file)


logger = logging.getLogger(__name__)


class NotesOverlay(Vertical):
    """Bottom quick-notes panel, toggled with Ctrl+N. Fits within content_column."""

    class Changed(Message):
        pass

    DEFAULT_CSS = """
    NotesOverlay {
        height: 10;
        width: 100%;
        display: none;
        border-top: thick $primary;
    }
    NotesOverlay TextArea {
        height: 1fr;
        border: none;
        padding: 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield TextArea(id="notes_textarea")

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.post_message(self.Changed())

    @property
    def text(self) -> str:
        try:
            return self.query_one("#notes_textarea", TextArea).text
        except Exception:
            return ""

    def load_text(self, notes: str) -> None:
        try:
            self.query_one("#notes_textarea", TextArea).load_text(notes)
        except Exception:
            pass


class SectionNav(Static):
    """Left sidebar with section navigation buttons."""

    DEFAULT_CSS = """
    SectionNav {
        width: 20;
        height: 100%;
        border-right: solid $border;
        background: $panel;
        layout: vertical;
        padding: 1 0;
    }

    SectionNav Button {
        width: 100%;
        height: auto;
        border: none;
        background: $panel;
        margin: 0;
        padding: 0 1;
    }

    SectionNav Button:hover {
        background: $boost;
    }

    SectionNav Button.active {
        background: $accent;
        text-style: bold;
    }

    """

    SECTION_LABELS = {
        "01_consent": "01 Consent",
        "02_subjective": "02 Subjective",
        "03_medical": "03 Medical",
        "04_objective": "04 Objective →",
        "04_pain_classification": "05 Pain Class",
        "05_outcome_measures": "06 Outcomes",
        "06_diagnosis": "07 Diagnosis",
        "07_barriers": "08 Barriers",
        "08_rx_plan":  "09 Rx & Plan",
    }

    def __init__(self, on_section_selected: callable, **kwargs):
        super().__init__(**kwargs)
        self.on_section_selected = on_section_selected
        self.active_section = "01_consent"
        self.section_indicators = {}  # section_id -> completion bool

    def compose(self) -> ComposeResult:
        """Create navigation buttons for all sections."""
        for section_id in [
            "01_consent",
            "02_subjective",
            "03_medical",
            "04_objective",
            "04_pain_classification",
            "05_outcome_measures",
            "06_diagnosis",
            "07_barriers",
            "08_rx_plan",
        ]:
            label = self.SECTION_LABELS.get(section_id, section_id)
            btn = Button(label, id=f"nav_{section_id}")
            if section_id == "01_consent":
                btn.add_class("active")
            yield btn

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle section button clicks."""
        button_id = event.button.id
        if button_id.startswith("nav_"):
            section_id = button_id[4:]  # Remove "nav_" prefix
            self.set_active(section_id)
            self.on_section_selected(section_id)

    def set_active(self, section_id: str) -> None:
        """Highlight the active section button."""
        # Remove active class from all buttons
        for btn in self.query(Button):
            btn.remove_class("active")

        # Add active class to the selected button
        try:
            active_btn = self.query_one(f"#nav_{section_id}", Button)
            active_btn.add_class("active")
            self.active_section = section_id
        except Exception:
            pass

    def set_indicator(self, section_id: str, complete: bool) -> None:
        """Update the completion indicator (●/○) for a section.

        Currently just marks in our dict; rendering happens via button label.
        """
        self.section_indicators[section_id] = complete

    def refresh_indicators(self, sections: dict[str, bool]) -> None:
        """Update all section indicators based on completion dict."""
        for section_id, complete in sections.items():
            self.set_indicator(section_id, complete)

    def set_tab_status(self, section_id: str, status: str) -> None:
        """Set visual status on a section button via variant: 'pending', 'clear', or 'positive'."""
        variant_map = {"pending": "warning", "positive": "error", "clear": "success"}
        try:
            btn = self.query_one(f"#nav_{section_id}", Button)
            btn.variant = variant_map.get(status, "default")
        except Exception:
            pass


class AssessmentView(Container):
    """Main assessment view with section navigation and content area."""

    DEFAULT_CSS = """
    AssessmentView {
        width: 100%;
        height: 100%;
        layout: horizontal;
    }

    #content_column {
        width: 1fr;
        height: 100%;
        layout: vertical;
    }

    #section_content {
        width: 100%;
        height: 1fr;
    }

    #section_content_inner {
        width: 100%;
        height: auto;
    }

    #obj_view {
        width: 1fr;
        height: 100%;
    }
    """

    def __init__(self, session_file: str = "", **kwargs):
        super().__init__(**kwargs)
        self.session_file = session_file
        self.sections = {}
        self.active_section_id = "01_consent"
        self._save_task: asyncio.Task | None = None
        self._report_interval = None
        self._mounted = False
        self._pending_load: dict | None = None
        self._in_objective_mode = False
        self._last_assessment_section_id = "01_consent"
        self._obj_view: ObjectiveAssessmentView | None = None
        self._active_regions: list[str] = ["lumbar"]  # session-level region context
        self._grid_visible = False
        self._grid_cursor: tuple[int, int] = (0, 0)
        self._grid_cursor_set = False   # False until first navigation anchors it
        self._pre_grid_section: str = "01_consent"

    def compose(self) -> ComposeResult:
        """Create sidebar nav + content area."""
        yield SectionNav(on_section_selected=self._show_section, id="section_nav")
        with Vertical(id="content_column"):
            yield ScrollableContainer(Vertical(id="section_content_inner"), id="section_content")
            yield GridOverview(SUBJ_GRID_DATA, id="subj_grid_overview")
            yield NotesOverlay(id="notes_overlay")
        yield ObjectiveAssessmentView(id="obj_view")
        yield KBPanel(id="kb_panel")

    def on_mount(self) -> None:
        """Initialize after mounting."""
        self.sections = {
            "01_consent":             ConsentSection(id="section_01_consent"),
            "02_subjective":          SubjectiveSection(id="section_02_subjective"),
            "03_medical":             MedicalSection(id="section_03_medical"),
            "04_pain_classification": PainClassificationSection(id="section_04_pain_classification"),
            "05_outcome_measures":    OutcomeMeasuresSection(id="section_05_outcome_measures"),
            "06_diagnosis":           DiagnosisSection(id="section_06_diagnosis"),
            "07_barriers":            BarriersSection(id="section_07_barriers"),
            "08_rx_plan":             RxPlanSection(id="section_08_rx_plan"),
        }

        content = self.query_one("#section_content_inner", Vertical)
        for section_id, section in self.sections.items():
            if section_id != self.active_section_id:
                section.display = False
            content.mount(section)

        # Objective view — hidden until entering objective mode
        self._obj_view = self.query_one("#obj_view", ObjectiveAssessmentView)
        self._obj_view.display = False

        self._mounted = True
        if self._pending_load:
            data = self._pending_load
            self._pending_load = None
            self.load_session(self.session_file, data)

    def on_unmount(self) -> None:
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
        if self._report_interval is not None:
            self._report_interval.stop()
            self._report_interval = None
        if self.session_file:
            # daemon=False — process waits for all reports + pandoc before exit
            threading.Thread(
                target=_exit_generate_all_reports, args=(self.session_file,), daemon=False
            ).start()

    def load_session(self, session_file: str, data: dict) -> None:
        """Load session data into all sections."""
        if not self._mounted:
            # Defer load until mounted
            self._pending_load = data
            self.session_file = session_file
            return

        self.session_file = session_file

        # Prefer TUI-owned _assessment.json; fall back to embedded assessment block
        # for old sessions that predate the split architecture.
        assess_p = assessment_path(session_file)
        if assess_p.exists():
            try:
                assess_file = json.loads(assess_p.read_text())
                assessment = assess_file.get("assessment", {})
                nav_data = assess_file  # sections_complete lives here
            except Exception:
                assessment = data.get("assessment", {})
                nav_data = data
        else:
            assessment = data.get("assessment", {})
            nav_data = data

        # Load consent section
        consent_data = assessment.get("consent", {})
        if "01_consent" in self.sections:
            consent_section = self.sections["01_consent"]
            consent_section.session_file = session_file
            consent_section.load(consent_data)

        # Load subjective section
        subjective_data = assessment.get("subjective", {})
        # Migration: goals moved from diagnosis → subjective (existing sessions)
        if not any(subjective_data.get(f"goal_{i}") for i in range(1, 5)):
            for i in range(1, 5):
                k = f"goal_{i}"
                v = assessment.get("diagnosis", {}).get(k)
                if v:
                    subjective_data.setdefault(k, v)
        if "02_subjective" in self.sections:
            subjective_section = self.sections["02_subjective"]
            subjective_section.session_file = session_file
            subjective_section.load(subjective_data)

        # Mirror goals into consent section
        if "01_consent" in self.sections:
            self.sections["01_consent"].load_goals(subjective_data)

        # Load medical section
        medical_data = assessment.get("medical", {})
        if "03_medical" in self.sections:
            medical_section = self.sections["03_medical"]
            medical_section.session_file = session_file
            medical_section.load(medical_data)

        # Load pain classification section
        pain_data = assessment.get("pain_classification", {})
        if "04_pain_classification" in self.sections:
            pain_section = self.sections["04_pain_classification"]
            pain_section.session_file = session_file
            pain_section.load(pain_data)

        # Load outcome measures section
        om_data = assessment.get("outcome_measures", {})
        if "05_outcome_measures" in self.sections:
            om_section = self.sections["05_outcome_measures"]
            om_section.session_file = session_file
            om_section.load(om_data)

        # Load barriers section
        br_data = assessment.get("barriers", {})
        if "07_barriers" in self.sections:
            br_section = self.sections["07_barriers"]
            br_section.session_file = session_file
            if isinstance(br_data, dict):
                br_section.load(br_data)

        # Load rx_plan section
        rp_data = assessment.get("rx_plan", {})
        if "08_rx_plan" in self.sections:
            rp_section = self.sections["08_rx_plan"]
            rp_section.session_file = session_file
            if isinstance(rp_data, dict):
                rp_section.load(rp_data)

        # Load diagnosis section
        dx_data = assessment.get("diagnosis", {})
        if "06_diagnosis" in self.sections:
            dx_section = self.sections["06_diagnosis"]
            dx_section.session_file = session_file
            if isinstance(dx_data, dict):
                dx_section.load(dx_data)

        # Load notes overlay
        sp_data = assessment.get("scratchpad", {})
        notes_text = sp_data.get("notes", "") if isinstance(sp_data, dict) else ""
        try:
            self.query_one("#notes_overlay", NotesOverlay).load_text(notes_text)
        except Exception:
            pass

        # Load objective sections via ObjectiveAssessmentView
        obj_file_data = load_objective(session_file)
        if self._obj_view is not None:
            self._obj_view.load_session(session_file, obj_file_data)
            self._obj_view.load_goals(subjective_data)

        # Push active regions and test data to section 05 regional panels
        section_05 = self.sections.get("04_pain_classification")
        if section_05:
            obj_assessment = obj_file_data.get("assessment", {})
            obj_regions = obj_assessment.get("active_regions", [])
            self._active_regions = list(obj_regions)   # sync session-level context
            section_05.set_active_regions(obj_regions)
            for rid in obj_regions:
                tests = _flatten_region_fields(obj_assessment, rid)
                section_05.set_region_test_data(rid, tests)

        # Update nav indicators and medical tab color
        self._refresh_nav_indicators(nav_data)
        self._update_medical_tab_color()

        # (Re)start 60s background report timer now that a session is loaded
        if self._report_interval is not None:
            self._report_interval.stop()
        self._report_interval = self.set_interval(
            _REPORT_INTERVAL,
            lambda: asyncio.create_task(self._generate_reports()),
        )

    def _collect_assessment_for_xref(self) -> dict:
        """Collect in-memory section data for cross-reference badge updates.

        Reads widget values — no disk I/O. Called before update_cross_refs()
        on section switch so badges never need to re-read the JSON file.
        """
        result = {}
        for section_id, json_key in (
            ("02_subjective",          "subjective"),
            ("03_medical",             "medical"),
            ("04_pain_classification", "pain_classification"),
            ("05_outcome_measures",    "outcome_measures"),
            ("06_diagnosis",           "diagnosis"),
        ):
            s = self.sections.get(section_id)
            if s is not None:
                try:
                    result[json_key] = s.collect()
                except Exception:
                    result[json_key] = {}
        return result

    def _show_section(self, section_id: str) -> None:
        """Switch to an assessment section; exits objective mode if needed."""
        if section_id == "04_objective":
            self._enter_objective_mode()
            return

        # Any assessment F-key while in objective mode exits it first
        coming_from_objective = self._in_objective_mode
        if self._in_objective_mode:
            self._exit_objective_mode_silent()

        self._last_assessment_section_id = section_id

        # Skip redraw only when staying within assessment mode on the same section.
        # If we just exited objective mode, active_section_id was never updated while
        # there, so the guard would incorrectly suppress the show() call.
        if not coming_from_objective and section_id == self.active_section_id:
            return

        if self.active_section_id == "03_medical":
            self._update_medical_tab_color()

        current = self.sections.get(self.active_section_id)
        if current:
            current.display = False
        new = self.sections.get(section_id)
        if new:
            new.display = True
            self.active_section_id = section_id

        try:
            self.query_one("#section_nav", SectionNav).set_active(section_id)
        except Exception:
            pass

        # Cross-reference refresh (assessment sections only) — use in-memory data
        if section_id in ("04_pain_classification", "05_outcome_measures",
                          "06_diagnosis", "07_barriers"):
            s = self.sections.get(section_id)
            if s:
                s.update_cross_refs(self._collect_assessment_for_xref())

        # Subsection nav bar: only for certain assessment sections
        has_subnav = section_id in (
            "01_consent", "02_subjective", "03_medical", "04_pain_classification",
            "05_outcome_measures", "06_diagnosis", "07_barriers", "08_rx_plan",
        )
        try:
            nav_bar = self.app.query_one("#subsection_nav_bar")
            nav_bar.display = has_subnav
            if has_subnav:
                nav_bar.set_context(section_id)
        except Exception:
            pass

    # ── Grid overview ─────────────────────────────────────────────────────────

    def toggle_grid(self) -> None:
        if self._grid_visible:
            # Escape without navigating — remember where cursor was in grid
            self._grid_cursor = self.query_one("#subj_grid_overview", GridOverview).current_cursor()
            self._grid_cursor_set = True
            self.query_one("#subj_grid_overview", GridOverview).close()
            self.query_one("#section_content").display = True
            self._grid_visible = False
        else:
            self._pre_grid_section = self.active_section_id
            # First open (or no prior navigation): cursor at current section's row
            if not self._grid_cursor_set:
                self._grid_cursor = section_to_cursor(self.active_section_id, SUBJ_GRID_DATA)
            has_data = {sid: _section_has_data(s.collect()) for sid, s in self.sections.items()}
            self.query_one("#section_content").display = False
            self.query_one("#subj_grid_overview", GridOverview).open(has_data, self._grid_cursor)
            self._grid_visible = True

    def navigate_to_heading(self, section_id: str, anchor_id: str) -> None:
        """Close grid and jump to section + anchor."""
        self._grid_cursor = section_to_cursor(self._pre_grid_section, SUBJ_GRID_DATA)
        self._grid_cursor_set = True
        self.query_one("#subj_grid_overview", GridOverview).close()
        self.query_one("#section_content").display = True
        self._grid_visible = False

        if section_id == "04_objective":
            # anchor_id is an objective section_id — switch mode then show it
            self._enter_objective_mode()
            if self._obj_view:
                self.set_timer(0.05, lambda: self._obj_view._show_section(anchor_id))
            return

        self._show_section(section_id)
        section = self.sections.get(section_id)
        if section and hasattr(section, "_jump_to"):
            self.set_timer(0.05, lambda: section._jump_to(anchor_id))
        else:
            try:
                sc = self.query_one("#section_content", ScrollableContainer)
                target = self.query_one(f"#{anchor_id}")
                self.set_timer(0.05, lambda: sc.scroll_to_widget(target, top=True, animate=False))
            except Exception:
                pass

    @on(GridOverview.HeadingSelected)
    def _on_grid_heading_selected(self, event: GridOverview.HeadingSelected) -> None:
        if not self._in_objective_mode:
            self.navigate_to_heading(event.section_id, event.anchor_id)

    @on(GridOverview.Dismissed)
    def _on_grid_dismissed(self, event: GridOverview.Dismissed) -> None:
        if not self._in_objective_mode:
            self.toggle_grid()

    # ── Objective mode ────────────────────────────────────────────────────────

    def _enter_objective_mode(self) -> None:
        """Show ObjectiveAssessmentView, hide assessment content."""
        if self._in_objective_mode:
            return

        self._in_objective_mode = True

        # Hide assessment sidebar + content column (includes notes overlay)
        current = self.sections.get(self.active_section_id)
        if current:
            current.display = False
        try:
            self.query_one("#section_nav", SectionNav).display = False
            self.query_one("#content_column", Vertical).display = False
        except Exception:
            pass
        try:
            self.app.query_one("#subsection_nav_bar").display = False
        except Exception:
            pass

        # Show objective view
        if self._obj_view is not None:
            self._obj_view.display = True

    def _exit_objective_mode_silent(self) -> None:
        """Exit objective mode without triggering _show_section recursion."""
        self._in_objective_mode = False
        if self._obj_view is not None:
            self._obj_view.display = False
        try:
            self.query_one("#section_nav", SectionNav).display = True
            self.query_one("#content_column", Vertical).display = True
        except Exception:
            pass

    def _exit_objective_mode(self) -> None:
        """Return to assessment mode — called by ← back in objective view."""
        self._exit_objective_mode_silent()
        target = self._last_assessment_section_id or "01_consent"
        current = self.sections.get(self.active_section_id)
        if current:
            current.display = False
        new = self.sections.get(target)
        if new:
            new.display = True
            self.active_section_id = target
        try:
            self.query_one("#section_nav", SectionNav).set_active(target)
        except Exception:
            pass

    def _update_medical_tab_color(self) -> None:
        """Update the 03 Medical nav button to orange/green/red based on urgent red flag review."""
        try:
            medical_section = self.sections.get("03_medical")
            if medical_section is None:
                return
            status = medical_section.urgent_red_flag_status()
            nav = self.query_one("#section_nav", SectionNav)
            nav.set_tab_status("03_medical", status)
        except Exception:
            pass

    def _refresh_nav_indicators(self, data: dict) -> None:
        """Update all section completion indicators from stored sections_complete dict."""
        sections_complete = data.get("sections_complete", {})
        nav = self.query_one("#section_nav", SectionNav)
        nav.refresh_indicators(sections_complete)

    def _schedule_save(self) -> None:
        """Schedule a debounced save after 2 seconds of inactivity."""
        if self._save_task:
            self._save_task.cancel()
        self.post_message(self.SaveStateChanged("pending"))

        save_for = self.session_file  # capture — don't save if session switches before timer fires

        async def delayed_save():
            await asyncio.sleep(2.0)
            if self.session_file == save_for:
                await self._do_save()

        self._save_task = asyncio.create_task(delayed_save())

    async def _do_save(self) -> None:
        """Collect ALL sections and write the complete assessment in one atomic pass."""
        if not self.session_file:
            return

        self.post_message(self.SaveStateChanged("saving"))

        # Section ID → key used in assessment JSON block
        _SEC_KEYS = [
            ("01_consent",           "consent"),
            ("02_subjective",        "subjective"),
            ("03_medical",           "medical"),
            ("04_pain_classification", "pain_classification"),
            ("05_outcome_measures",  "outcome_measures"),
            ("06_diagnosis",         "diagnosis"),
            ("07_barriers",          "barriers"),
            ("08_rx_plan",           "rx_plan"),
        ]

        assessment_data: dict = {}
        sections_complete: dict[str, bool] = {}

        for section_id, json_key in _SEC_KEYS:
            section = self.sections.get(section_id)
            if section is None:
                continue
            assessment_data[json_key] = section.collect()
            sections_complete[section_id] = section.is_complete()

        # Notes overlay — saved under the legacy "scratchpad" key for backward compat
        try:
            notes_text = self.query_one("#notes_overlay", NotesOverlay).text
        except Exception:
            notes_text = ""
        assessment_data["scratchpad"] = {"notes": notes_text}

        save_all_sections(self.session_file, assessment_data, sections_complete)
        # Objective sections save themselves via ObjectiveAssessmentView autosave.

        # Update nav indicators directly from the in-memory dict — no round-trip read
        self._refresh_nav_indicators({"sections_complete": sections_complete})
        self._update_medical_tab_color()

        self.post_message(self.SaveStateChanged("saved"))

    async def _generate_reports(self) -> None:
        """Regenerate raw + markdown reports in background threads.

        Called by the 60s interval timer and by Ctrl+R before showing the modal.
        Pandoc (docx) is NOT run here — only on Ctrl+R and at session close.
        """
        if not self.session_file:
            return
        sf = self.session_file
        try:
            await asyncio.gather(
                asyncio.to_thread(save_raw_report, sf),
                asyncio.to_thread(export_session_report, sf),
                asyncio.to_thread(save_clean_reports, sf),
            )
        except Exception as e:
            logger.error(f"_generate_reports failed: {e}")

    @on(ObjectiveAssessmentView.GoalsEdited)
    def _on_obj_goals_edited(self, event: ObjectiveAssessmentView.GoalsEdited) -> None:
        """Goals edited in Functional — sync to Consent and Subjective, then save."""
        from textual.widgets import TextArea
        goals   = event.goals
        focused = self.app.focused
        for section_key, widget_prefix in (
            ("02_subjective", "goal_"),
            ("01_consent",    "consent_goal_"),
        ):
            section = self.sections.get(section_key)
            if not section:
                continue
            section._loading = True
            try:
                for i in range(1, 5):
                    try:
                        w = section.query_one(f"#{widget_prefix}{i}", TextArea)
                        if w is focused:
                            continue
                        val = goals.get(f"goal_{i}", "")
                        if w.text != val:
                            w.text = val
                    except Exception:
                        pass
            finally:
                section._loading = False
        self._schedule_save()

    @on(ObjectiveAssessmentView.ExitRequested)
    def _on_obj_exit_requested(self) -> None:
        self._exit_objective_mode()

    @on(ObjectiveAssessmentView.SaveStateChanged)
    def _on_obj_save_state(self, event: ObjectiveAssessmentView.SaveStateChanged) -> None:
        self.post_message(self.SaveStateChanged(event.state))
        if event.state == "saved":
            self._push_region_tests_to_section05()

    @on(RegionTopbar.RegionToggled)
    def _on_region_topbar_toggled_05(self, event: RegionTopbar.RegionToggled) -> None:
        logger.debug("RDP broker: RegionToggled %s active=%s", event.region_id, event.active)
        section_05 = self.sections.get("04_pain_classification")
        if section_05 and self._obj_view:
            active = list(self._obj_view._active_regions)
            self._active_regions = active              # sync session-level context
            logger.debug("RDP broker: calling set_active_regions(%s)", active)
            section_05.set_active_regions(active)
            self._push_region_tests_to_section05()
        else:
            logger.debug("RDP broker: skipped — section_05=%s _obj_view=%s",
                         section_05, self._obj_view)

    def _push_region_tests_to_section05(self) -> None:
        section_05 = self.sections.get("04_pain_classification")
        if not section_05 or not self.session_file:
            return
        try:
            obj = load_objective(self.session_file).get("assessment", {})
            logger.debug("RDP push: active_regions=%s", self._active_regions)
            for rid in self._active_regions:
                tests = _flatten_region_fields(obj, rid)
                logger.debug("RDP push: %s tests sample=%s", rid, dict(list(tests.items())[:3]))
                section_05.set_region_test_data(rid, tests)
        except Exception as e:
            logger.warning("Failed to push region tests to section 05: %s", e)

    class SaveStateChanged(Message):
        """Posted when save state changes: 'pending', 'saving', or 'saved'."""
        def __init__(self, state: str) -> None:
            super().__init__()
            self.state = state

    @on(RequestKBEntry)
    def _on_request_kb_entry(self, event: RequestKBEntry) -> None:
        try:
            kb = self.query_one("#kb_panel", KBPanel)
            kb.update(event.region_id, event.stem)
            kb.display = True
        except Exception:
            pass

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """Update KB panel when any assessment-section field is focused."""
        try:
            panel = self.query_one("#kb_panel", KBPanel)
        except Exception:
            return
        if not panel.display:
            return
        wid = event.widget.id or ""
        if not wid:
            return
        if wid.endswith("_btn"):
            wid = wid[:-4]
        result = get_registry().resolve_any(wid)
        if result is not None:
            region, _ = result
            panel.update(region, wid)

    def _sync_goals_consent_to_subj(self) -> None:
        from textual.widgets import TextArea
        consent = self.sections.get("01_consent")
        subj    = self.sections.get("02_subjective")
        if not consent or not subj:
            return
        focused = self.app.focused
        subj._loading = True
        try:
            for i in range(1, 5):
                try:
                    val = consent.query_one(f"#consent_goal_{i}", TextArea).text
                    w   = subj.query_one(f"#goal_{i}", TextArea)
                    if w is focused:
                        continue
                    if w.text != val:
                        w.text = val
                except Exception:
                    pass
        finally:
            subj._loading = False

    def _sync_goals_subj_to_consent(self) -> None:
        from textual.widgets import TextArea
        subj    = self.sections.get("02_subjective")
        consent = self.sections.get("01_consent")
        if not subj or not consent:
            return
        focused = self.app.focused
        consent._loading = True
        try:
            for i in range(1, 5):
                try:
                    val = subj.query_one(f"#goal_{i}", TextArea).text
                    w   = consent.query_one(f"#consent_goal_{i}", TextArea)
                    if w is focused:
                        continue
                    if w.text != val:
                        w.text = val
                except Exception:
                    pass
        finally:
            consent._loading = False

    def on_consent_section_field_changed(self) -> None:
        self._sync_goals_consent_to_subj()
        self._schedule_save()

    def on_subjective_section_field_changed(self) -> None:
        self._sync_goals_subj_to_consent()
        self._schedule_save()

    def on_medical_section_field_changed(self) -> None:
        self._schedule_save()
        self._update_medical_tab_color()

    def on_pain_classification_section_field_changed(self) -> None:
        self._schedule_save()

    def on_outcome_measures_section_field_changed(self) -> None:
        self._schedule_save()

    def on_diagnosis_section_field_changed(self) -> None:
        self._schedule_save()

    def on_barriers_section_field_changed(self) -> None:
        self._schedule_save()

    def on_rx_plan_section_field_changed(self) -> None:
        self._schedule_save()

    def on_notes_overlay_changed(self) -> None:
        self._schedule_save()

    def on_active_movement_section_field_changed(self) -> None:
        self._schedule_save()

    def on_general_section_field_changed(self) -> None:
        self._schedule_save()

    def on_neurological_section_field_changed(self) -> None:
        self._schedule_save()

    def on_sensory_section_field_changed(self) -> None:
        self._schedule_save()

    def on_muscle_section_field_changed(self) -> None:
        self._schedule_save()

    def on_functional_section_field_changed(self) -> None:
        self._schedule_save()
