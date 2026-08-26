"""Minimal Markdown -> Pango markup renderer for the report viewer.

GTK has no built-in Markdown widget (unlike Textual's MarkdownViewer, which the
TUI uses for its report screen). Rather than pull in a full CommonMark engine
for one read-only view, this hand-rolls just the subset storage.py's clean
report actually emits: `#`..`######` headings, `**bold**`, `---` rules,
`- ` list items, and pipe tables (header + `---` separator row).

Output is Pango markup meant for Gtk.TextBuffer.insert_markup(), not
Gtk.Label.set_markup() — multi-paragraph text with embedded newlines.
"""

from __future__ import annotations

import re

from gi.repository import GLib

_HEADING_SIZES = {
    1: "xx-large",
    2: "x-large",
    3: "large",
    4: "medium",
    5: "medium",
    6: "small",
}

_BOLD_RE = re.compile(r"(\*\*.+?\*\*)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_RE = re.compile(r"^(\s*)-\s+(.*)$")
_TABLE_SEP_CELL_RE = re.compile(r"^:?-+:?$")


def _inline(text: str) -> str:
    """Escape a line for markup, translating **bold** spans to <b>."""
    parts = _BOLD_RE.split(text)
    out = []
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) >= 4:
            out.append(f"<b>{GLib.markup_escape_text(part[2:-2])}</b>")
        else:
            out.append(GLib.markup_escape_text(part))
    return "".join(out)


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _render_table(rows: list[str]) -> str:
    parsed = [_split_row(r) for r in rows]
    if len(parsed) >= 2 and all(_TABLE_SEP_CELL_RE.match(c) for c in parsed[1]):
        header, data = parsed[0], parsed[2:]
    else:
        header, data = parsed[0], parsed[1:]

    ncols = len(header)
    widths = [len(header[i]) for i in range(ncols)]
    for row in data:
        for i in range(min(ncols, len(row))):
            widths[i] = max(widths[i], len(row[i]))

    def fmt_row(cells: list[str]) -> str:
        padded = [(cells[i] if i < len(cells) else "").ljust(widths[i]) for i in range(ncols)]
        return "  ".join(padded)

    lines = [
        f"<b>{GLib.markup_escape_text(fmt_row(header))}</b>",
        GLib.markup_escape_text("  ".join("-" * w for w in widths)),
    ]
    lines.extend(GLib.markup_escape_text(fmt_row(row)) for row in data)
    return '<span font_family="monospace">' + "\n".join(lines) + "</span>"


def md_to_pango(md: str) -> str:
    """Render a Markdown document (storage.py's clean-report subset) to Pango markup."""
    lines = md.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("|"):
            block = []
            while i < n and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(_render_table(block))
            continue

        if stripped in ("---", "***", "___"):
            out.append('<span alpha="40%">' + "─" * 70 + "</span>")
            i += 1
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            size = _HEADING_SIZES.get(level, "medium")
            out.append(f'<span size="{size}" weight="bold">{_inline(heading.group(2))}</span>')
            i += 1
            continue

        item = _LIST_RE.match(line)
        if item:
            out.append(f"{item.group(1)}• {_inline(item.group(2))}")
            i += 1
            continue

        out.append(_inline(line))
        i += 1

    return "\n".join(out)
