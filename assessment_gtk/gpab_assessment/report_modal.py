"""Ctrl+R report viewer — GTK4 port of pab_assessment.report_modal.ReportModal.

The TUI renders clean.md through Textual's MarkdownViewer (with a
table-of-contents pane). GTK has no equivalent built-in markdown widget, so
this renders the same *_clean.md storage.py generates through a small
Markdown-subset -> Pango markup converter (`markdown_render.py`) into a
read-only TextView, rather than showing the raw *_report.md text. Per
CONVERSION_PLAN.md Phase 5, storage.py's report generation is already reused
unchanged — this is purely the trigger/preview surface.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

from .markdown_render import md_to_pango
from .storage_bridge import generate_clean_report


class ReportModal(Gtk.Window):
    """Escape or the Close button dismisses. Regenerate re-runs storage.py's
    export_session_report against the current session file (so edits saved
    since the modal was last opened are reflected) and reloads the text."""

    def __init__(self, parent: Gtk.Window, session_file: str) -> None:
        super().__init__(transient_for=parent, modal=True, title="Clinical Report")
        self.session_file = session_file
        self.set_default_size(820, 900)

        header = Gtk.HeaderBar()
        regen_btn = Gtk.Button(label="Regenerate")
        regen_btn.connect("clicked", self._on_regenerate)
        header.pack_start(regen_btn)
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda _b: self.close())
        header.pack_end(close_btn)
        self.set_titlebar(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_view.set_top_margin(12)
        self.text_view.set_bottom_margin(12)
        self.text_view.set_left_margin(16)
        self.text_view.set_right_margin(16)
        scroll.set_child(self.text_view)
        self.set_child(scroll)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        self._load_report()

    def _on_key(self, _ctrl, keyval, _keycode, _state) -> bool:
        if Gdk.keyval_name(keyval) == "Escape":
            self.close()
            return True
        return False

    def _on_regenerate(self, _btn) -> None:
        self._load_report()

    def _load_report(self) -> None:
        text = generate_clean_report(self.session_file)
        buf = self.text_view.get_buffer()
        buf.set_text("")
        if not text:
            buf.set_text("(report generation failed — see terminal log)")
            return
        try:
            markup = md_to_pango(text)
            buf.insert_markup(buf.get_end_iter(), markup, -1)
        except GLib.Error:
            # Malformed markup (shouldn't happen — inputs are escaped) —
            # fall back to showing the raw, unrendered text.
            buf.set_text(text)
