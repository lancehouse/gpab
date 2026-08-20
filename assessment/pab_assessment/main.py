"""Textual TUI main entry point."""

import sys
import asyncio
import faulthandler
import logging
import signal
import subprocess
import time as _time
from pathlib import Path
from textual.app import ComposeResult, App, NoScreen
from textual.binding import Binding
from textual.widgets import Header, Footer
from textual.containers import Container
from .tui import PhysioAssessmentTUI, SessionListScreen
from .assessment_view import AssessmentView
from .storage import load_assessment, load_session_current, clear_tui_pid
from .objective.kb_db_screen import KBDBScreen


class PhysioAssessment(App):
    """Main Textual application for PhysioChart assessment system."""

    TITLE = "PhysioChart Assessment System"
    SUB_TITLE = "Specialist Physiotherapy Assessment & Report Generator"

    BINDINGS = [
        ("ctrl+q", "quit",              "Quit"),
        Binding("ctrl+a", "textarea_select_all", show=False, priority=True),
        Binding("ctrl+d", "open_kb_db", "KB DB", show=True, priority=True),
        # Section tab navigation — F1-F9 (priority=True overrides any focused widget)
        Binding("f1", "section_consent",          show=False, priority=True),
        Binding("f2", "section_subjective",       show=False, priority=True),
        Binding("f3", "section_medical",          show=False, priority=True),
        Binding("f4", "section_objective",        show=False, priority=True),
        Binding("f5", "section_pain",             show=False, priority=True),
        Binding("f6", "section_outcomes",         show=False, priority=True),
        Binding("f7", "section_diagnosis",        show=False, priority=True),
        Binding("f8", "section_barriers",         show=False, priority=True),
        Binding("f9", "section_rx_plan",          show=False, priority=True),
        Binding("f10", "toggle_notes",            show=False, priority=True),
        # Objective section jump — Ctrl+F1-F8 (priority=True overrides any focused widget)
        Binding("ctrl+f1", "obj_general",       show=False, priority=True),
        Binding("ctrl+f2", "obj_functional",    show=False, priority=True),
        Binding("ctrl+f3", "obj_active",        show=False, priority=True),
        Binding("ctrl+f4", "obj_passive",       show=False, priority=True),
        Binding("ctrl+f5", "obj_neurological",  show=False, priority=True),
        Binding("ctrl+f6", "obj_sensory",       show=False, priority=True),
        Binding("ctrl+f7", "obj_muscle",        show=False, priority=True),
        Binding("ctrl+f8", "obj_special",       show=False, priority=True),
        # Subjective subsection jump — Alt+letter (priority=True overrides TextArea)
        Binding("alt+s", "sub_symptoms",             show=False, priority=True),
        Binding("alt+h", "sub_history",              show=False, priority=True),
        Binding("alt+b", "sub_behaviour",            show=False, priority=True),
        Binding("alt+m", "sub_management",           show=False, priority=True),
        Binding("alt+a", "sub_activity",             show=False, priority=True),
        Binding("alt+w", "sub_work",                 show=False, priority=True),
        Binding("alt+e", "sub_sleep",                show=False, priority=True),
        Binding("alt+4", "sub_24hr",                 show=False, priority=True),
        Binding("alt+p", "sub_psychosocial",         show=False, priority=True),
        Binding("alt+g", "sub_goals",                show=False, priority=True),
        Binding("alt+r", "sub_risk",                 show=False, priority=True),
    ]

    CSS = """
    Screen { background: $surface; }
    """

    def __init__(self, session_path: str = "", **kwargs):
        super().__init__(**kwargs)
        self.current_session_path = session_path
        self.assessment_screen = None

    _last_app_focus_time: float = 0.0

    async def _on_app_focus(self, event) -> None:
        self._last_app_focus_time = _time.monotonic()
        await super()._on_app_focus(event)

    async def _on_app_blur(self, event) -> None:
        if _time.monotonic() - self._last_app_focus_time < 0.25:
            return  # Suppress spurious AppBlur from GNOME (<250ms after AppFocus)
        await super()._on_app_blur(event)

    def _watch_app_focus(self, focus: bool) -> None:
        # Skip update_node_styles() — it's O(n_widgets) and takes 3s with 2662
        # mounted widgets. We have no app-level :focus/:blur CSS so it's wasted work.
        if focus:
            try:
                if (
                    self._last_focused_on_app_blur is not None
                    and self._last_focused_on_app_blur.screen is self.screen
                    and self.screen.focused is None
                ):
                    self.screen.set_focus(
                        self._last_focused_on_app_blur,
                        scroll_visible=False,
                        from_app_focus=True,
                    )
            except NoScreen:
                pass
            self._last_focused_on_app_blur = None
        else:
            self._last_focused_on_app_blur = self.screen.focused
            self.screen.set_focus(None)

    # ------------------------------------------------------------------
    # System clipboard bridge (wl-copy / wl-paste)
    # ------------------------------------------------------------------

    @property
    def clipboard(self) -> str:
        """Read from system clipboard via wl-paste, falling back to internal."""
        try:
            result = subprocess.run(
                ["wl-paste", "--no-newline"],
                capture_output=True, text=True, timeout=0.5,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass
        return self._clipboard

    def copy_to_clipboard(self, text: str) -> None:
        """Write to both internal clipboard and system clipboard via wl-copy."""
        self._clipboard = text
        try:
            subprocess.run(
                ["wl-copy"],
                input=text, text=True, timeout=0.5,
            )
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container()
        yield Footer()

    def on_mount(self) -> None:
        if self.current_session_path:
            asyncio.create_task(self.show_assessment_form())
            return

        current_data = load_session_current()
        if current_data and current_data.get("session_file"):
            self.current_session_path = current_data["session_file"]
            asyncio.create_task(self.show_assessment_form())
        else:
            self.show_session_list()

    async def _flush_pending_saves(self) -> None:
        """Flushes any debounced (not-yet-written) edits before teardown.

        Must run BEFORE anything starts unmounting: on_unmount fires too late
        — by then the widget's own children are already gone, so collect()
        (which walks those children to read current field values) returns
        empty and the flush silently writes nothing. Confirmed by direct
        testing: calling _do_save() during on_unmount produced an empty
        section; calling it here, before remove_children()/exit(), produces
        the full data. This is what was silently dropping fields (e.g. a
        manually-typed ROM value) typed within ~2s of quitting or switching
        sessions — not a report-generation bug, a lost-write bug.
        """
        try:
            av = self.query_one("#assessment_view", AssessmentView)
        except Exception:
            return
        save_task = getattr(av, "_save_task", None)
        if save_task is not None and not save_task.done():
            save_task.cancel()
            await av._do_save()
        obj_view = getattr(av, "_obj_view", None)
        if obj_view is not None:
            obj_save_task = getattr(obj_view, "_save_task", None)
            if obj_save_task is not None and not obj_save_task.done():
                obj_save_task.cancel()
                await obj_view._do_save()

    async def action_quit(self) -> None:
        """Ctrl+Q — flush before exiting (see _flush_pending_saves)."""
        await self._flush_pending_saves()
        self.exit()

    def show_session_list(self) -> None:
        main = self.query_one(Container)
        main.remove_children()
        session_list = SessionListScreen(on_session_selected=self.on_session_selected)
        main.mount(session_list)

    async def on_session_selected(self, session_path: str) -> None:
        await self._flush_pending_saves()
        self.current_session_path = session_path
        await self.show_assessment_form()

    async def show_assessment_form(self) -> None:
        main = self.query_one(Container)
        main.remove_children()
        assessment = PhysioAssessmentTUI(session_path=self.current_session_path)
        self.assessment_screen = assessment
        main.mount(assessment)

    def on_unmount(self) -> None:
        clear_tui_pid()

    def action_textarea_select_all(self) -> None:
        from textual.widgets import TextArea
        focused = self.focused
        if isinstance(focused, TextArea):
            focused.action_select_all()

    def action_open_kb_db(self) -> None:
        """Ctrl+D — open the full Clinical KB database browser."""
        self.push_screen(KBDBScreen())


    # ------------------------------------------------------------------
    # Section navigation (Alt+1-7, Alt+N) — on App so they're global
    # ------------------------------------------------------------------

    def _goto_section(self, section_id: str) -> None:
        try:
            av = self.query_one("#assessment_view", AssessmentView)
            av._show_section(section_id)
            section = av.sections.get(section_id)
            if section:
                section.focus_first_field()
        except Exception:
            pass

    def action_section_consent(self):    self._goto_section("01_consent")
    def action_section_subjective(self): self._goto_section("02_subjective")
    def action_section_medical(self):    self._goto_section("03_medical")
    def action_section_objective(self):  self._goto_section("04_objective")
    def action_section_pain(self):       self._goto_section("04_pain_classification")
    def action_section_outcomes(self):   self._goto_section("05_outcome_measures")
    def action_section_diagnosis(self):  self._goto_section("06_diagnosis")
    def action_section_barriers(self):   self._goto_section("07_barriers")
    def action_section_rx_plan(self):    self._goto_section("08_rx_plan")
    def action_toggle_notes(self) -> None:
        try:
            from .tui import PhysioAssessmentTUI
            tui = self.query_one(PhysioAssessmentTUI)
            tui.action_toggle_notes()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Subjective subsection jump (Alt+S/H/F/M/A/W/E/B/P/R) — global
    # ------------------------------------------------------------------

    def _goto_subjective_sub(self, anchor_id: str) -> None:
        try:
            self.query_one("#section_02_subjective")._jump_to(anchor_id)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Objective section jump (Ctrl+F1-F8) — global
    # ------------------------------------------------------------------

    def _goto_objective_section(self, section_id: str) -> None:
        try:
            av = self.query_one("#assessment_view")
            av._enter_objective_mode()
            av._obj_view._show_section(section_id)
        except Exception:
            pass

    def action_obj_general(self):      self._goto_objective_section("01_general")
    def action_obj_functional(self):   self._goto_objective_section("07_functional")
    def action_obj_active(self):       self._goto_objective_section("02_active")
    def action_obj_passive(self):      self._goto_objective_section("03_passive")
    def action_obj_neurological(self): self._goto_objective_section("04_neurological")
    def action_obj_sensory(self):      self._goto_objective_section("05_sensory")
    def action_obj_muscle(self):       self._goto_objective_section("06_muscle")
    def action_obj_special(self):      self._goto_objective_section("08_special")

    def action_sub_symptoms(self):     self._goto_subjective_sub("subj_symptoms")
    def action_sub_history(self):      self._goto_subjective_sub("subj_history")
    def action_sub_behaviour(self):    self._goto_subjective_sub("subj_behaviour")
    def action_sub_management(self):   self._goto_subjective_sub("subj_management")
    def action_sub_activity(self):     self._goto_subjective_sub("subj_activity")
    def action_sub_work(self):         self._goto_subjective_sub("subj_work")
    def action_sub_sleep(self):        self._goto_subjective_sub("subj_sleep")
    def action_sub_24hr(self):         self._goto_subjective_sub("subj_24hr")
    def action_sub_psychosocial(self): self._goto_subjective_sub("subj_psychosocial")
    def action_sub_goals(self):        self._goto_subjective_sub("subj_goals")
    def action_sub_risk(self):         self._goto_subjective_sub("subj_suicide")


def main():
    """Entry point — accepts optional --session <path> argument."""
    logging.basicConfig(
        level=logging.DEBUG,
        filename="/tmp/pab.log",
        filemode="w",
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    session_path = ""
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--session" and i + 1 < len(args):
            session_path = args[i + 1]
            break

    # Diagnostics for a crash that leaves no Python traceback anywhere (the
    # _exception check below covers Textual's own exception handling, but
    # not a hang or a hard/segfault-level exit — both are still invisible
    # otherwise since bodychart/src/integration.c destroys the VTE window
    # the instant this process exits, before any output could be read).
    # faulthandler.enable() dumps a real traceback to this file on a
    # segfault/fatal signal; dump_traceback_later dumps one if the process
    # is still alive-but-stuck 5s from now (cancelled below on any normal
    # exit, so a healthy run leaves this file empty).
    fault_log = open("/tmp/pab_fault.log", "w")
    faulthandler.enable(file=fault_log)
    faulthandler.dump_traceback_later(5, file=fault_log)
    # Also dump on an external signal-based kill (SIGTERM/SIGHUP) — these
    # skip faulthandler.enable()'s fatal-signal handler (that only covers
    # SIGSEGV/SIGABRT/SIGBUS/SIGFPE/SIGILL) and skip Python exception
    # handling entirely, so without this a kill from outside the process
    # (e.g. the GTK/VTE side) would look identical to a clean exit here.
    faulthandler.register(signal.SIGTERM, file=fault_log)
    faulthandler.register(signal.SIGHUP, file=fault_log)

    app = PhysioAssessment(session_path=session_path)
    try:
        app.run()
    except Exception:
        # Belt-and-braces: exceptions escaping run() itself (rare — see the
        # _exception check below for the actual common case).
        logging.getLogger(__name__).exception("Unhandled exception, app exiting")
        raise
    finally:
        faulthandler.cancel_dump_traceback_later()
    if app._exception is not None:
        # Textual's App._handle_exception() (any unhandled exception in a
        # message handler or worker) sets self._exception and exits the app
        # WITHOUT raising it back to run() — that re-raise only happens
        # inside run_test(), for test frameworks (see textual/app.py's
        # run_test(), "so test frameworks are aware"). Production run() just
        # returns normally, so this was previously invisible here. It's also
        # invisible in the terminal itself: bodychart/src/integration.c
        # destroys the VTE window the instant this process exits
        # (on_tui_child_exited), before anyone could read the printed
        # traceback off it. Log it explicitly so it survives.
        logging.getLogger(__name__).error(
            "App exited via unhandled exception (return_code=%s): %r",
            app.return_code, app._exception, exc_info=app._exception,
        )


if __name__ == "__main__":
    main()
