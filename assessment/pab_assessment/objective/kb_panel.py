"""KBPanel — right-side knowledge base panel for the Objective TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widgets import Static

from .kb_loader import KBEntry, get_registry


class KBPanel(ScrollableContainer):
    """Toggleable right-panel showing KB info for the currently focused field.

    Width 48. Hidden by default; toggled via Ctrl+K in ObjectiveAssessmentView.
    Call update(region, field_id) whenever focused field changes.
    Last entry is preserved when a non-KB field is focused.
    """

    DEFAULT_CSS = """
    KBPanel {
        width: 48;
        height: 100%;
        border-left: solid $border;
        background: $panel-darken-1;
        padding: 0;
        display: none;
    }
    KBPanel #kb_content {
        width: 100%;
        height: auto;
        padding: 1;
        color: $text;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_region: str = ""
        self._current_field: str = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="kb_content")

    def _get_content(self) -> Static:
        return self.query_one("#kb_content", Static)

    def update(self, region: str, field_id: str) -> None:
        """Look up field_id in the KB and refresh panel text.

        If no entry is found, preserves the current content (no flicker on
        focus moving to notes/sidebar/non-KB fields).
        """
        entry = get_registry().resolve(region, field_id)
        if entry is None:
            return
        self._current_region = region
        self._current_field = field_id
        lines = entry.render_lines()
        self._get_content().update("\n".join(lines))

    def show_raw(self, text: str) -> None:
        """Set panel content directly from pre-rendered markup, bypassing the
        KB registry lookup. Used by callers that aren't part of the
        region/field KB (e.g. the CAL-CP diagnosis walker's per-node notes,
        appendix examples, and source footnote text)."""
        self._current_region = ""
        self._current_field = ""
        self._get_content().update(text)

    def show_placeholder(self) -> None:
        """Show a startup hint when no field is focused yet."""
        self._get_content().update(" Knowledge Base\n" + "─" * 36 + "\n\n Focus a test or\n field to see info.")
