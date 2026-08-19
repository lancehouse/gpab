"""
Physiotherapy Assessment TUI using Textual framework.

Integrates with GTK body chart via session JSON file watcher.
Ctrl+B  — focus body chart (signal file → GTK raises its own window)
Ctrl+E  — export session report to Markdown (full)
Ctrl+R  — report view  |  Ctrl+K — toggle KB panel
Ctrl+N  — toggle bottom notes overlay
Ctrl+S  — manual save
Ctrl+L  — return to session list
"""

import asyncio
import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from datetime import datetime

from rich.text import Text

from textual.app import ComposeResult, on
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.widgets import Header, Footer, Static, Label, Input, TextArea, Button, ListItem, ListView
from textual.binding import Binding

from .watcher import BodyChartWatcher
from .search import build_index
from .search_widget import SearchModal
from .report_modal import ReportModal
from .objective.kb_panel import KBPanel
from .storage import (
    load_assessment, save_assessment, list_sessions, create_new_session,
    read_gtk_pid, write_focus_signal, export_session_report,
    save_raw_report, save_clean_reports, save_docx_report,
)
from .assessment_view import AssessmentView, NotesOverlay
from .goniometer_import import importer as gonio_importer
from .goniometer_import.matcher import match_batch
from .goniometer_import.wizard_screen import GonioImportWizard



logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Window-focus helpers
# ---------------------------------------------------------------------------

def _process_alive(pid: int | None) -> bool:
    """Return True if a process with this PID is currently running."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False



# ---------------------------------------------------------------------------
# Session list screen
# ---------------------------------------------------------------------------

class SessionListRow(Static):
    """Single session row in the session list."""

    class Selected(Message):
        def __init__(self, session_path: str) -> None:
            super().__init__()
            self.session_path = session_path

    def __init__(self, session: dict, **kwargs):
        super().__init__(**kwargs)
        self.session = session
        self.patient_id = session["patient_id"]
        self.session_label = session["session_label"]
        self.session_path = session["path"]
        self.sections_complete = session["sections_complete"]
        self.obj_sections_complete = session.get("obj_sections_complete", 0)
        self.body_chart_data = session["body_chart_data"]
        self.date = session["date"]

    def on_click(self) -> None:
        self.post_message(self.Selected(self.session_path))

    def render(self) -> str:
        if isinstance(self.date, str):
            try:
                dt = datetime.fromisoformat(self.date.replace("Z", "+00:00"))
                date_str = dt.strftime("%d %b %H:%M")
            except Exception:
                date_str = self.date[:10] if self.date else ""
        else:
            date_str = datetime.fromtimestamp(self.date).strftime("%d %b %H:%M")

        body_chart_indicator = "●" if self.body_chart_data else "○"
        top_line = f"{self.patient_id}   {date_str}   {body_chart_indicator}   S {self.sections_complete}/7  O {self.obj_sections_complete}/7"
        lines = [top_line]
        if self.session_label:
            lines.append(f"  {self.session_label}")
        return "\n".join(lines)


class SessionListScreen(Container):
    """Session list screen — primary entry point."""

    DEFAULT_CSS = """
    SessionListScreen {
        height: 100%; width: 100%;
        layout: vertical; padding: 1 2;
    }
    #session_list_title { width: 100%; height: auto; }
    #session_search { width: 100%; height: 1; margin-bottom: 1; }
    #sessions_view { width: 100%; height: 1fr; margin-bottom: 1; }
    #session_actions { width: 100%; height: auto; layout: horizontal; }
    Button { margin-right: 1; }
    """

    def __init__(self, on_session_selected: callable, **kwargs):
        super().__init__(**kwargs)
        self.on_session_selected = on_session_selected
        self.sessions = []
        self.filtered_sessions = []

    def compose(self) -> ComposeResult:
        yield Label("PhysioChart Assessment", id="session_list_title")
        yield Input(placeholder="Search patients...", id="session_search")
        yield ScrollableContainer(id="sessions_view")
        yield Button("Quit", id="quit_btn", variant="error")

    def on_mount(self) -> None:
        self.load_sessions()
        self.query_one("#session_search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "session_search":
            self._on_search_change(event.value)

    def load_sessions(self) -> None:
        self.sessions = list_sessions()
        self.filtered_sessions = self.sessions
        self.refresh_list()

    def _on_search_change(self, value: str) -> None:
        if not value:
            self.filtered_sessions = self.sessions
        else:
            q = value.lower()
            self.filtered_sessions = [
                s for s in self.sessions
                if q in s["patient_id"].lower() or q in s["session_label"].lower()
            ]
        self.refresh_list()

    def refresh_list(self) -> None:
        container = self.query_one("#sessions_view", ScrollableContainer)
        container.remove_children()
        if not self.filtered_sessions:
            container.mount(Label("No sessions found"))
            return

        today = datetime.now().date()
        buckets: dict[str, list] = {"Today": [], "This week": [], "Older": []}
        for session in self.filtered_sessions:
            d = session["date"]
            try:
                dt = (datetime.fromisoformat(d.replace("Z", "+00:00")) if isinstance(d, str)
                      else datetime.fromtimestamp(d)).date()
            except Exception:
                dt = None
            if dt == today:
                buckets["Today"].append(session)
            elif dt and (today - dt).days < 7:
                buckets["This week"].append(session)
            else:
                buckets["Older"].append(session)

        for label_text, group in buckets.items():
            if not group:
                continue
            container.mount(Label(label_text, classes="section_header"))
            for session in group:
                row = SessionListRow(session)
                row.styles.height = "auto"
                container.mount(row)

    def on_session_list_row_selected(self, event: SessionListRow.Selected) -> None:
        self.on_session_selected(event.session_path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit_btn":
            self.app.exit()


# ---------------------------------------------------------------------------
# Session header + body chart panel
# ---------------------------------------------------------------------------

class SessionHeader(Static):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.patient_id = ""
        self.session_label = ""
        self.session_file = ""

    def render(self) -> str:
        if not self.session_file:
            return "No active session"
        return f"{self.patient_id} · {self.session_label}"


class BodyChartPanel(Static):

    DEFAULT_CSS = """
    BodyChartPanel {
        width: auto;
        height: 2;
        color: $text-muted;
        padding: 0 1;
        content-align: left middle;
    }
    BodyChartPanel:hover { color: $text; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.symptom_types_used = []
        self.views_drawn = []

    def render(self) -> str:
        if not self.symptom_types_used:
            return "⌕ search"
        lines = ["Body Chart:"]
        if self.views_drawn:
            lines.append(f"Views: {', '.join(str(v) for v in self.views_drawn)}")
        if self.symptom_types_used:
            lines.append(f"Symptoms: {', '.join(str(s) for s in self.symptom_types_used)}")
        return "  ".join(lines)

    def on_click(self) -> None:
        try:
            self.app.query_one("PhysioAssessmentTUI").action_search()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main assessment container
# ---------------------------------------------------------------------------

class _NavChip(Static):
    """Clickable nav chip — plain Static avoids Button's unoverrideable CSS."""

    DEFAULT_CSS = """
    _NavChip {
        width: auto;
        height: 2;
        padding: 0 1;
        background: #2a4060;
        color: white;
        content-align: left middle;
    }
    _NavChip:hover {
        background: #4a7090;
    }
    """

    def __init__(self, label, anchor_id: str, section_widget_id: str, **kwargs) -> None:
        super().__init__(label, **kwargs)
        self._anchor_id = anchor_id
        self._section_widget_id = section_widget_id

    def on_click(self) -> None:
        try:
            self.app.query_one(self._section_widget_id)._jump_to(self._anchor_id)
        except Exception:
            pass


class SubsectionNavBar(Static):
    """Context-sensitive subsection jump bar — lives in the top chrome row.

    Hidden by default; shown when a section with sub-navigation is active.
    Call set_context(section_id) when switching sections to swap chips.
    Underlined character in Subjective chips shows the Alt+key shortcut.
    """

    CONSENT_SUBS = [
        ("Consent",  "cs_consent"),
        ("Framing",  "cs_framing"),
        ("ICE+",     "cs_ice"),
        ("Goals",    "consent_goals"),
        ("Beliefs",  "cs_beliefs"),
    ]

    # (before, underlined_key, after, anchor_id)  — Subjective has Alt+key shortcuts
    SUBJECTIVE_SUBS = [
        ("",      "S", "ymptoms",     "subj_symptoms"),
        ("",      "H", "istory",      "subj_history"),
        ("",      "B", "ehaviour",    "subj_behaviour"),
        ("",      "M", "gmt",         "subj_management"),
        ("",      "A", "ctivity",     "subj_activity"),
        ("",      "W", "ork",         "subj_work"),
        ("sl",    "E", "ep",          "subj_sleep"),
        ("",      "2", "4Hr",         "subj_24hr"),
        ("",      "P", "sychosocial", "subj_psychosocial"),
        ("",      "G", "oals",        "subj_goals"),
        ("",      "R", "isk",         "subj_suicide"),
    ]

    MEDICAL_SUBS = [
        ("Comorbid",     "med_comorbidities"),
        ("CVD Risk",     "med_cardiovascular"),
        ("Red Flags",    "med_red_flags"),
        ("Differential", "med_differential"),
        ("Medications",  "med_medications"),
    ]

    PAIN_CLASS_SUBS = [
        ("Inflamm",      "pc_inflammatory"),
        ("Nociceptive",  "pc_nociceptive"),
        ("Neuropathic",  "pc_neuropathic"),
        ("Nociplastic",  "pc_nociplastic"),
        ("Central Sens", "pc_central"),
        ("Fibro",        "pc_fibromyalgia"),
        ("BACPAP",       "pc_bacpap"),
        ("Summary",      "pc_summary"),
    ]

    OM_SUBS = [
        ("PSFS",       "om_psfs"),
        ("BPI",        "om_bpi"),
        ("DASS",       "om_dass"),
        ("PCS",        "om_pcs"),
        ("PSEQ/PCL",   "om_pseq"),
        ("Sleep",      "om_sleep"),
        ("Additional", "om_additional"),
        ("Hypothesis", "om_hypothesis"),
    ]

    DX_SUBS = [
        ("Overview",    "dx_overview"),
        ("Primary",     "dx_primary"),
        ("Post-Surg",   "dx_surgical"),
        ("Post-Trauma", "dx_traumatic"),
        ("MSK",         "dx_msk"),
        ("Neuro",       "dx_neuropathic"),
        ("Mixed",       "dx_mixed"),
    ]

    BR_SUBS = [
        ("Physical",   "br_physical"),
        ("Neuro",      "br_neuro"),
        ("Nocip",      "br_nocip"),
        ("Psych",      "br_psych"),
        ("Sleep/Soc",  "br_sleep"),
        ("Medical",    "br_medical"),
        ("Custom",     "br_custom"),
    ]

    RX_PLAN_SUBS = [
        ("Treatment",  "rp_treatment"),
        ("Session 1",  "rp_session1"),
        ("Day 1",      "rp_day1"),
        ("Follow-Up",  "rp_followup"),
    ]

    DEFAULT_CSS = """
    SubsectionNavBar {
        height: 2;
        width: 1fr;
        layout: horizontal;
        background: #1a2a3a;
        padding: 0;
    }
    """

    def _make_label(self, before: str, key: str, after: str) -> Text:
        t = Text()
        if before:
            t.append(before)
        t.append(key, style="underline bold")
        t.append(after)
        return t

    def compose(self) -> ComposeResult:
        # Intentionally empty — set_context() mounts chips on first navigation.
        # Composing chips here would register their IDs, then set_context's
        # remove_children() + mount() with the same IDs causes a silent collision.
        return
        yield  # make this a generator

    def set_context(self, section_id: str) -> None:
        """Swap chips to match the newly active section."""
        self.remove_children()
        if section_id == "01_consent":
            for label, anchor_id in self.CONSENT_SUBS:
                self.mount(_NavChip(
                    label,
                    anchor_id=anchor_id,
                    section_widget_id="#section_01_consent",
                ))
        elif section_id == "02_subjective":
            for before, key, after, anchor_id in self.SUBJECTIVE_SUBS:
                self.mount(_NavChip(
                    self._make_label(before, key, after),
                    anchor_id=anchor_id,
                    section_widget_id="#section_02_subjective",
                ))
        elif section_id == "03_medical":
            for label, anchor_id in self.MEDICAL_SUBS:
                self.mount(_NavChip(
                    label,
                    anchor_id=anchor_id,
                    section_widget_id="#section_03_medical",
                ))
        elif section_id == "04_pain_classification":
            for label, anchor_id in self.PAIN_CLASS_SUBS:
                self.mount(_NavChip(
                    label,
                    anchor_id=anchor_id,
                    section_widget_id="#section_04_pain_classification",
                ))
        elif section_id == "05_outcome_measures":
            for label, anchor_id in self.OM_SUBS:
                self.mount(_NavChip(
                    label,
                    anchor_id=anchor_id,
                    section_widget_id="#section_05_outcome_measures",
                ))
        elif section_id == "06_diagnosis":
            for label, anchor_id in self.DX_SUBS:
                self.mount(_NavChip(
                    label,
                    anchor_id=anchor_id,
                    section_widget_id="#section_06_diagnosis",
                ))
        elif section_id == "07_barriers":
            for label, anchor_id in self.BR_SUBS:
                self.mount(_NavChip(
                    label,
                    anchor_id=anchor_id,
                    section_widget_id="#section_07_barriers",
                ))
        elif section_id == "08_rx_plan":
            for label, anchor_id in self.RX_PLAN_SUBS:
                self.mount(_NavChip(
                    label,
                    anchor_id=anchor_id,
                    section_widget_id="#section_08_rx_plan",
                ))


class PhysioAssessmentTUI(Container):
    """Assessment form container — owns the watcher and all keyboard actions."""

    BINDINGS = [
        Binding("ctrl+s", "save",          "Save",       show=True),
        Binding("ctrl+u", "reload_chart",  "Reload Chart", show=True),

        Binding("ctrl+t", "toggle_grid",    "Overview",   show=True,  priority=True),
        Binding("ctrl+r", "view_report",     "Report",     show=True,  priority=True),
        Binding("ctrl+n", "toggle_notes",  "Notes",      show=True,  priority=True),
        Binding("ctrl+k", "toggle_kb",     "KB",         show=True,  priority=True),
        Binding("ctrl+f", "search",        "Search",     show=True,  priority=True),
        # Was ctrl+o — that's the classic termios VDISCARD special character
        # and can get swallowed by the kernel tty driver before an app ever
        # sees it, depending on how raw mode is configured. ctrl+g ("Gonio")
        # isn't one of the reserved special characters.
        Binding("ctrl+g", "import_gonio",  "Import ROM", show=True,  priority=True),
    ]

    DEFAULT_CSS = """
    PhysioAssessmentTUI {
        height: 100%; width: 100%; layout: vertical;
    }

    #top_bar {
        height: 2;
        width: 100%;
        background: $boost;
        padding: 0 1;
    }
    #session_header {
        width: 19;
        height: 2;
        color: $text;
        padding: 0 1 0 0;
        content-align: left middle;
    }
    #subsection_nav_bar {
        display: none;
        height: 2;
    }

    #tui_status {
        height: 1; width: 100%;
        background: $boost; color: $text-muted;
        padding: 0 1;
    }
    AssessmentView { height: 1fr; }
    """

    def __init__(self, session_path: str = "", **kwargs):
        super().__init__(**kwargs)
        self.watcher: BodyChartWatcher | None = None
        self.current_session_file = session_path
        self._status_timer = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="top_bar"):
            yield SessionHeader(id="session_header")
            yield SubsectionNavBar(id="subsection_nav_bar")
            yield BodyChartPanel(id="chart_panel")
        yield AssessmentView(id="assessment_view")
        yield Static("", id="tui_status")

    def on_mount(self) -> None:
        self.watcher = BodyChartWatcher(
            on_session_switch=self.on_session_switch,
            on_chart_update=self.on_chart_update,
        )
        self.watcher.start()

        if self.current_session_file:
            asyncio.create_task(self.load_session_from_path(self.current_session_file))
        else:
            from .storage import load_session_current
            current_data = load_session_current()
            if current_data and current_data.get("session_file"):
                self.current_session_file = current_data["session_file"]
                asyncio.create_task(self.load_session_from_path(self.current_session_file))

    def on_unmount(self) -> None:
        if self.watcher:
            self.watcher.stop()

    # ------------------------------------------------------------------
    # Session loading
    # ------------------------------------------------------------------

    async def load_session_from_path(self, session_file: str) -> None:
        try:
            p = Path(session_file)
            # File may not exist yet if GTK spawned us before its first save.
            # Use empty data so we can still set session_file and accept saves.
            data = json.loads(p.read_text()) if p.exists() else {}

            self.current_session_file = session_file

            header = self.query_one("#session_header", SessionHeader)
            header.patient_id    = data.get("patient_id", "")
            header.session_label = data.get("session_label", "")
            header.session_file  = session_file

            chart_panel = self.query_one("#chart_panel", BodyChartPanel)
            chart_panel.symptom_types_used = []
            chart_panel.views_drawn = []

            assessment_view = self.query_one("#assessment_view", AssessmentView)
            assessment_view.load_session(session_file, data)

            from .storage import write_tui_pid
            write_tui_pid(os.getpid())

        except Exception as e:
            logger.error(f"Failed to load session from {session_file}: {e}")

    async def on_session_switch(self, data: dict) -> None:
        self.current_session_file = data.get("session_file", "")
        header = self.query_one("#session_header", SessionHeader)
        header.patient_id    = data.get("session_id", "")
        header.session_label = data.get("session_label", "")
        header.session_file  = self.current_session_file

        body_chart = data.get("body_chart", {})
        chart_panel = self.query_one("#chart_panel", BodyChartPanel)
        chart_panel.symptom_types_used = body_chart.get("symptom_types_used", [])
        chart_panel.views_drawn        = body_chart.get("views_drawn", [])

        if self.current_session_file:
            try:
                p = Path(self.current_session_file)
                full_data = json.loads(p.read_text()) if p.exists() else {}
            except Exception as e:
                logger.error(f"on_session_switch: failed to read {self.current_session_file}: {e}")
                full_data = {}
            assessment_view = self.query_one("#assessment_view", AssessmentView)
            assessment_view.load_session(self.current_session_file, full_data)
            from .storage import write_tui_pid
            write_tui_pid(os.getpid())

    async def on_chart_update(self, data: dict) -> None:
        # Derive chart panel indicators from raw session JSON strokes (type 5 = tick/clear)
        strokes = data.get("subjective", {}).get("strokes", [])
        seen_types = sorted({s["type"] for s in strokes if "type" in s and s["type"] != 5})

        chart_panel = self.query_one("#chart_panel", BodyChartPanel)
        chart_panel.symptom_types_used = seen_types
        chart_panel.views_drawn        = sorted({s["view"] for s in strokes if "view" in s})
        chart_panel.refresh()

        # Refresh subjective note slots from updated body chart
        try:
            av = self.query_one("#assessment_view", AssessmentView)
            subj = av.sections.get("02_subjective")
            if subj is not None:
                subj.refresh_from_chart(data)
        except Exception:
            pass


    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _show_status(self, message: str, seconds: float = 2.5) -> None:
        try:
            self.query_one("#tui_status", Static).update(message)
            if self._status_timer:
                self._status_timer.cancel()
            self._status_timer = self.set_timer(seconds, self._clear_status)
        except Exception:
            pass

    def _clear_status(self) -> None:
        try:
            self.query_one("#tui_status", Static).update("")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Search (ctrl+f)
    # ------------------------------------------------------------------

    def action_search(self) -> None:
        """Open the jump-search modal."""
        index = build_index(self.app)

        def _callback(result) -> None:
            if result is not None:
                self._execute_jump(result)

        self.app.push_screen(SearchModal(index), _callback)

    def _execute_jump(self, entry) -> None:
        from .assessment_view import AssessmentView
        from .objective.objective_view import ObjectiveAssessmentView
        from textual.containers import ScrollableContainer
        try:
            av = self.query_one("#assessment_view", AssessmentView)

            # ── Objective sections (section_id prefixed with "obj:") ──────────
            if entry.section_id.startswith("obj:"):
                real_section = entry.section_id[4:]
                av._show_section("04_objective")
                obj_view = av._obj_view
                if obj_view is None:
                    return
                obj_view._show_section(real_section)
                if entry.widget_id:
                    try:
                        w = obj_view.query_one(f"#{entry.widget_id}")
                        w.focus()
                        sc = obj_view.query_one("#obj_section_content", ScrollableContainer)
                        sc.scroll_to_widget(w, animate=False)
                    except Exception:
                        pass
                return

            # ── Assessment sections ───────────────────────────────────────────
            av._show_section(entry.section_id)
            section = av.sections.get(entry.section_id)
            if section is None:
                return
            if entry.widget_id:
                # Jump directly to the specific widget; anchor only used as fallback
                try:
                    w = section.query_one(f"#{entry.widget_id}")
                    w.focus()
                    sc = self.app.query_one("#section_content", ScrollableContainer)
                    sc.scroll_to_widget(w, animate=False)
                except Exception:
                    if entry.anchor_id:
                        if hasattr(section, "_jump_to"):
                            section._jump_to(entry.anchor_id)
                        section._focus_first_after(entry.anchor_id)
            elif entry.anchor_id:
                if hasattr(section, "_jump_to"):
                    section._jump_to(entry.anchor_id)
                section._focus_first_after(entry.anchor_id)
            else:
                section.focus_first_field()
        except Exception as e:
            logger.error(f"Search jump failed: {e}")

    async def save_if_pending(self) -> None:
        """Flush pending debounced save before navigating away. Only saves if a save is queued."""
        assessment_view = self.query_one("#assessment_view", AssessmentView)
        task = assessment_view._save_task
        if task and not task.done():
            task.cancel()
            await assessment_view._do_save()

    def action_toggle_grid(self) -> None:
        """Ctrl+G — toggle grid overview for whichever mode is active."""
        try:
            av = self.query_one("#assessment_view", AssessmentView)
            if av._in_objective_mode:
                av._obj_view.toggle_grid()
            else:
                av.toggle_grid()
        except Exception:
            pass

    def action_save(self) -> None:
        assessment_view = self.query_one("#assessment_view", AssessmentView)

        async def _save_and_notify():
            await assessment_view._do_save()
            self._show_status("Saved")

        asyncio.create_task(_save_and_notify())

    def action_reload_chart(self) -> None:
        """Ctrl+U — force-reload body chart data from _session.json and refresh note slots."""
        if not self.current_session_file:
            self._show_status("No session loaded")
            return
        try:
            p = Path(self.current_session_file)
            if not p.exists():
                self._show_status("Session file not found")
                return
            data = json.loads(p.read_text())
            av = self.query_one("#assessment_view", AssessmentView)
            subj = av.sections.get("02_subjective")
            if subj is not None:
                subj.refresh_from_chart(data)
            self._show_status("Body chart reloaded")
        except Exception as e:
            self._show_status(f"Reload failed: {e}")

    def action_view_report(self) -> None:
        """Ctrl+R — save, regenerate reports in threads, show viewer, then run pandoc."""
        if not self.current_session_file:
            self._show_status("No session loaded")
            return

        async def _save_then_show():
            try:
                assessment_view = self.query_one("#assessment_view", AssessmentView)
                await assessment_view._do_save()
                sf = self.current_session_file
                # Generate raw + md + clean in threads (no pandoc yet)
                results = await asyncio.gather(
                    asyncio.to_thread(save_raw_report, sf),
                    asyncio.to_thread(export_session_report, sf, True, True),  # clean=True, dev=True → _clean.md
                    asyncio.to_thread(save_clean_reports, sf),
                    return_exceptions=True,
                )
                clean_path = results[1]
                if not clean_path or isinstance(clean_path, Exception):
                    self._show_status("Report generation failed — check logs")
                    return
                md_text = Path(clean_path).read_text(encoding="utf-8")
                await self.app.push_screen(ReportModal(md_text))
                # Pandoc runs after the modal is visible — daemon=True is fine here
                threading.Thread(target=save_docx_report, args=(sf,), daemon=True).start()
            except Exception as e:
                self._show_status(f"Report error: {e}")

        asyncio.create_task(_save_then_show())

    def action_import_gonio(self) -> None:
        """Ctrl+G — import goniometer ROM measurements for the open patient from
        ~/PAB/_inbox/goniometer/<code>/, via a fast review wizard, into the
        matching Active ROM fields (see goniometer_import/). If nothing new is
        pending, falls back to the most recently imported file so a mistake
        spotted after Apply (wrong field/side/angle) can be fixed by re-running
        the wizard and re-applying — safe, since Apply just overwrites the same
        field(s) again rather than appending."""
        if not self.current_session_file:
            self._show_status("No session loaded")
            return

        header = self.query_one("#session_header", SessionHeader)
        patient_code = header.patient_id.strip()
        if not patient_code:
            self._show_status("No patient code on this session")
            return

        files = gonio_importer.inbox_files_for(patient_code)
        reimporting = False
        if not files:
            files = gonio_importer.imported_files_for(patient_code)[:1]  # most recent only
            reimporting = True
        if not files:
            self._show_status(f"No goniometer data waiting for {patient_code}")
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
            self._show_status(f"Goniometer file(s) for {patient_code} had no measurements")
            return

        results = match_batch(combined)

        def _after_wizard(grouped) -> None:
            if not grouped:
                return  # cancelled — nothing written, files stay where they were
            sf = self.current_session_file
            gonio_importer.apply_grouped_values(sf, grouped)
            for f in files:
                gonio_importer.archive_imported_file(f)
            verb = "Re-imported" if reimporting else "Imported"
            self._show_status(f"{verb} {len(grouped)} ROM field(s) for {patient_code}")
            # Reload everything from disk so the new values show immediately,
            # same path used for a session switch.
            try:
                full_data = json.loads(Path(sf).read_text())
            except Exception as e:
                logger.error(f"import_gonio: failed to reload session after apply: {e}")
                return
            assessment_view = self.query_one("#assessment_view", AssessmentView)
            assessment_view.load_session(sf, full_data)

        self.app.push_screen(GonioImportWizard(results), _after_wizard)

    def action_toggle_notes(self) -> None:
        """Ctrl+N — toggle the bottom notes overlay."""
        try:
            av = self.query_one("#assessment_view", AssessmentView)
            overlay = av.query_one(NotesOverlay)
            if overlay.display:
                overlay.display = False
                # Return focus to active section so hotkeys work immediately
                def _refocus():
                    try:
                        section = av.sections.get(av.active_section_id)
                        if section:
                            section.focus_first_field()
                    except Exception:
                        self.set_focus(None)
                self.call_after_refresh(_refocus)
            else:
                overlay.display = True
                overlay.call_after_refresh(lambda: overlay.query_one(TextArea).focus())
        except Exception:
            pass

    def action_toggle_kb(self) -> None:
        """Ctrl+K — toggle KB panel (global; panel lives inside objective view)."""
        try:
            panel = self.query_one(KBPanel)
            panel.display = not panel.display
        except Exception:
            self._show_status("KB panel not available")

    # ------------------------------------------------------------------
    # Arrow-key scroll fallback — only when no widget is focused
    # ------------------------------------------------------------------

    def on_key(self, event) -> None:
        """Arrow keys scroll the section when no widget is focused."""
        if event.key not in ("up", "down"):
            return
        if self.app.focused is not None:
            return
        try:
            sc = self.query_one("#section_content", ScrollableContainer)
            if event.key == "up":
                sc.scroll_up(animate=False)
            else:
                sc.scroll_down(animate=False)
            event.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Save state indicator
    # ------------------------------------------------------------------

    def on_assessment_view_save_state_changed(
        self, event: AssessmentView.SaveStateChanged
    ) -> None:
        """Update status bar to reflect auto-save state."""
        if event.state == "pending":
            try:
                self.query_one("#tui_status", Static).update("Unsaved changes")
                if self._status_timer:
                    self._status_timer.cancel()
                    self._status_timer = None
            except Exception:
                pass
        elif event.state == "saving":
            try:
                self.query_one("#tui_status", Static).update("Saving…")
                if self._status_timer:
                    self._status_timer.cancel()
                    self._status_timer = None
            except Exception:
                pass
        elif event.state == "saved":
            now = datetime.now().strftime("%H:%M")
            self._show_status(f"Saved {now}", seconds=8.0)
