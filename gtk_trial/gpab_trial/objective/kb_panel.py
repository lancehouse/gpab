"""KBPanel — GTK4 port of pab_assessment.objective.kb_panel.KBPanel.

Right-side knowledge base panel, toggled via Ctrl+K, shown across every
tab (assessment and objective alike — matches the TUI, where this panel
is mounted once at the AssessmentView level, not per-section). Call
update(region, field_id) whenever the focused field changes; a resolve
miss preserves whatever's currently shown (no flicker moving focus to
notes/sidebar/non-KB fields).

Reference images (added 2026-08-23, no reference-TUI equivalent — this
was one of the original motivations for moving off Textual, which can't
render images at all): a Gtk.Picture above the text label, shown only
when the resolved KBEntry has an image_filename that actually resolves to
a real file (kb_db.resolve_image_path) — no reference image today just
means the Picture stays hidden, not an error. DB-backed entries only
(currently cervical/shoulder); YAML-sourced entries never have one.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango  # noqa: E402

from . import kb_db
from .kb_loader import get_registry, KBEntry


def _render_entry(entry: KBEntry) -> str:
    """Build free-flowing display text for one KBEntry — deliberately NOT
    KBEntry.render_lines(): that method hard-wraps every field to 44
    characters (via kb_loader._wrap()), sized for the TUI's fixed-width
    terminal columns. Rendered verbatim here, that hard wrap fought this
    Label's own wrap=True, producing text that looked wrapped/cut off at a
    narrow fixed column no matter how wide the panel actually was — the
    Label's wrapping should be the only wrapping, reflowing naturally to
    whatever width the panel is actually given (confirmed against the
    TUI's own behaviour: Textual's Static widget wraps its own text to the
    render width the same way, with no separate hard-wrap step either)."""
    parts: list[str] = []
    if entry.label:
        parts.append(entry.label)
    for heading, text in (
        ("Purpose", entry.purpose),
        ("Position", entry.position),
        ("Procedure", entry.procedure),
        ("Assess", entry.assess),
        ("Variants", entry.variants),
        ("Sn / Sp", entry.sn_sp),
        ("Cluster", entry.cluster),
        ("Note", entry.note),
    ):
        if text:
            parts.append(f"{heading}:\n{text.strip()}")
    return "\n\n".join(parts)


class KBPanel(Gtk.ScrolledWindow):
    def __init__(self) -> None:
        super().__init__()
        # Width comes entirely from wherever app.py's Gtk.Paned puts the
        # divider — a Paned assigns each side a real pixel allocation
        # directly (unlike a plain Box, which negotiates from each child's
        # own natural/minimum size), so nothing here needs to request or
        # float a width of its own. hexpand=True just means "use all of
        # whatever the Paned gives you" instead of collapsing to the
        # Label's own small natural size and leaving dead space.
        self.set_hexpand(True)
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.add_css_class("kb-panel")
        self.set_visible(False)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content.set_margin_top(8)
        content.set_margin_bottom(8)
        content.set_margin_start(10)
        content.set_margin_end(10)

        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.set_size_request(-1, 220)
        self.picture.set_visible(False)
        content.append(self.picture)

        self.label = Gtk.Label()
        self.label.set_hexpand(True)
        self.label.set_wrap(True)
        self.label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.label.set_xalign(0.0)
        self.label.set_yalign(0.0)
        self.label.set_valign(Gtk.Align.START)
        self.label.set_justify(Gtk.Justification.LEFT)
        self.label.set_selectable(True)
        content.append(self.label)

        self.set_child(content)

        self.show_placeholder()

    def _set_image(self, image_filename: str) -> None:
        path = kb_db.resolve_image_path(image_filename)
        if path is None:
            self.picture.set_visible(False)
            self.picture.set_paintable(None)
        else:
            self.picture.set_filename(str(path))
            self.picture.set_visible(True)

    def update(self, region: str, field_id: str) -> None:
        """Look up field_id in the KB and refresh panel text.

        If no entry is found, preserves the current content — same
        no-flicker behaviour as the TUI's KBPanel.update().
        """
        entry = get_registry().resolve(region, field_id)
        if entry is None:
            return
        self.label.set_label(_render_entry(entry))
        self._set_image(entry.image_filename)

    def show_raw(self, text: str) -> None:
        """Set panel content directly, bypassing the KB registry lookup."""
        self.label.set_label(text)
        self._set_image("")

    def show_placeholder(self) -> None:
        self.label.set_label("Knowledge Base\n\nFocus a test or field to see info.")
        self._set_image("")
