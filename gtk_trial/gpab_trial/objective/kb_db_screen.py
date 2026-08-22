"""Full-screen Clinical KB browser — GTK4 port of
pab_assessment.objective.kb_db_screen. Opened via Ctrl+D from anywhere in
the app (see app.py's _open_kb_browser).

Layout mirrors the TUI: left region list, centre condition -> cluster ->
test tree, right detail panel for the selected node. DB access (path
search, read-only connection) lives in kb_db.py, shared with kb_loader.py
and the Regional Differential panel.

Two things are rebuilt rather than ported verbatim, everything else (every
SQL query, the fuzzy search index/scorer, the formatting helpers) is
lifted unchanged:

- Textual's `Tree` widget -> `Gtk.TreeView` + `Gtk.TreeStore(str, object)`
  (the object column carries the same {"type": ..., "row"/"id": ...} data
  dict the TUI's `node.data` held). GTK's TreeView doesn't need — and
  doesn't show — a synthetic root node the way Textual's Tree always does,
  so the redundant root-labelled-as-region-name row is dropped; the region
  name is shown in a heading label above the tree instead, and top-level
  tree rows are conditions directly.
- Rich markup (`[bold]`, `[dim]`, `[red]`) in the detail-render functions
  -> Pango markup (`<b>`, `<span alpha="60%">`, `<span foreground="...">`),
  via the `_b`/`_dim`/`_italic_dim`/`_color` helpers below. All
  interpolated DB text is escaped with GLib.markup_escape_text — this
  panel renders live clinical reference text, some of it long-form
  free text, so unescaped markup injection is a real (if low-stakes)
  risk, not a hypothetical one.

Left/Right arrow keys are freed for cross-panel focus movement (region
list <-> tree <-> detail), same deliberate TUI choice — GtkTreeView's
built-in Left/Right (usually collapse/expand) never fires here because the
window-level key controller runs in the CAPTURE phase, ahead of the
TreeView's own handling; Enter is wired explicitly to toggle expand/collapse
instead (see _on_tree_key), matching the TUI's Tree subclass rebinding.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango  # noqa: E402

from . import kb_db

_find_db = kb_db.find_db
_open_db = kb_db.open_db


# ── Database queries — lifted verbatim from the TUI, zero UI imports ──────────

def _load_regions() -> list[sqlite3.Row]:
    conn = _open_db()
    try:
        return conn.execute(
            "SELECT pab_id, label FROM region ORDER BY body_area NULLS LAST, label"
        ).fetchall()
    finally:
        conn.close()


def _load_conditions_for_region(pab_region_id: str) -> list[sqlite3.Row]:
    conn = _open_db()
    try:
        return conn.execute(
            """
            SELECT co.id, co.name, co.short_name, co.condition_category,
                   co.context, co.reference,
                   COUNT(DISTINCT cl.id) AS cluster_count,
                   COUNT(DISTINCT cf.id) AS feature_count
            FROM condition co
            LEFT JOIN cluster cl ON cl.condition_id = co.id
                                 AND cl.pab_region_id = ?
            LEFT JOIN condition_feature cf ON cf.condition_id = co.id
            WHERE co.primary_region_id = (SELECT id FROM region WHERE pab_id = ?)
               OR EXISTS (
                   SELECT 1 FROM cluster cl2
                   WHERE cl2.condition_id = co.id AND cl2.pab_region_id = ?
               )
            GROUP BY co.id
            ORDER BY cluster_count DESC, co.display_priority, co.name
            """,
            (pab_region_id, pab_region_id, pab_region_id),
        ).fetchall()
    finally:
        conn.close()


def _load_clusters_for_condition(condition_id: int, pab_region_id: str) -> list[sqlite3.Row]:
    conn = _open_db()
    try:
        return conn.execute(
            """
            SELECT id, name, cluster_type, threshold,
                   sn, sp, plr, nlr, clinical_interpretation, notes, reference
            FROM cluster
            WHERE condition_id = ? AND pab_region_id = ?
            ORDER BY display_priority, plr DESC NULLS LAST
            """,
            (condition_id, pab_region_id),
        ).fetchall()
    finally:
        conn.close()


def _load_tests_for_cluster(cluster_id: int) -> list[sqlite3.Row]:
    conn = _open_db()
    try:
        return conn.execute(
            """
            SELECT t.id, t.name, t.also_known_as, t.domain,
                   t.sn, t.sp, t.plr, t.nlr
            FROM test t
            JOIN cluster_test ct ON ct.test_id = t.id
            WHERE ct.cluster_id = ?
            ORDER BY ct.display_order
            """,
            (cluster_id,),
        ).fetchall()
    finally:
        conn.close()


def _load_test_detail(test_id: int) -> sqlite3.Row | None:
    conn = _open_db()
    try:
        return conn.execute("SELECT * FROM test WHERE id = ?", (test_id,)).fetchone()
    finally:
        conn.close()


def _load_test_field_maps(test_id: int) -> list[sqlite3.Row]:
    conn = _open_db()
    try:
        return conn.execute(
            "SELECT pab_field_id, pab_json_file, pab_json_path, side "
            "FROM test_field_map WHERE test_id = ?",
            (test_id,),
        ).fetchall()
    finally:
        conn.close()


def _load_test_clusters(test_id: int) -> list[sqlite3.Row]:
    conn = _open_db()
    try:
        return conn.execute(
            """
            SELECT cl.name, cl.cluster_type, cl.plr, co.name AS condition
            FROM cluster cl
            JOIN cluster_test ct ON ct.cluster_id = cl.id
            JOIN condition co ON co.id = cl.condition_id
            WHERE ct.test_id = ?
            ORDER BY cl.plr DESC NULLS LAST
            """,
            (test_id,),
        ).fetchall()
    finally:
        conn.close()


def _load_condition_features(condition_id: int) -> list[sqlite3.Row]:
    conn = _open_db()
    try:
        return conn.execute(
            """
            SELECT feature_name, feature_value, feature_domain
            FROM condition_feature
            WHERE condition_id = ?
            ORDER BY feature_domain, feature_name
            """,
            (condition_id,),
        ).fetchall()
    finally:
        conn.close()


def _load_condition_differentiators(condition_name: str, pab_region_id: str) -> list[sqlite3.Row]:
    conn = _open_db()
    try:
        return conn.execute(
            """
            SELECT condition_a, condition_b, narrative, key_test, key_feature
            FROM differentiator
            WHERE region_id = (SELECT id FROM region WHERE pab_id = ?)
              AND (condition_a = ? OR condition_b = ?)
            ORDER BY condition_a
            """,
            (pab_region_id, condition_name, condition_name),
        ).fetchall()
    finally:
        conn.close()


def _load_condition_red_flags(condition_id: int, region_pab_id: str) -> list[sqlite3.Row]:
    conn = _open_db()
    try:
        return conn.execute(
            """
            SELECT flag_text, severity
            FROM red_flag
            WHERE condition_id = ?
               OR (region_id = (SELECT id FROM region WHERE pab_id = ?)
                   AND condition_id IS NULL)
            ORDER BY severity, flag_text
            """,
            (condition_id, region_pab_id),
        ).fetchall()
    finally:
        conn.close()


# ── Formatting helpers — lifted verbatim ───────────────────────────────────────

_fmt_lr = kb_db.fmt_lr
_fmt_snsp = kb_db.fmt_snsp


def _cluster_label(row: sqlite3.Row) -> str:
    lr = _fmt_lr(row["plr"], row["nlr"])
    suffix = f"  [{lr}]" if lr else ""
    return f"{row['name']}{suffix}"


def _test_label(row: sqlite3.Row) -> str:
    stats = _fmt_snsp(row["sn"], row["sp"])
    domain_tag = {"subjective": " ◆subj", "demographic": " ◆demog"}.get(row["domain"] or "", "")
    return f"{row['name']}{domain_tag}  ({stats})" if stats else f"{row['name']}{domain_tag}"


_SEVERITY_HEX = {"emergency": "#e53935", "urgent": "#f9a825", "refer": "#1565c0"}


def _severity_hex(severity: str | None) -> str:
    return _SEVERITY_HEX.get(severity or "", "#9e9e9e")


# ── Pango markup helpers ────────────────────────────────────────────────────────

def _esc(s: Any) -> str:
    return GLib.markup_escape_text(str(s)) if s is not None else ""


def _b(s: Any) -> str:
    return f"<b>{_esc(s)}</b>"


def _dim(s: Any) -> str:
    return f'<span alpha="60%">{_esc(s)}</span>'


def _italic_dim(s: Any) -> str:
    return f'<span alpha="60%" style="italic">{_esc(s)}</span>'


def _color(s: Any, hexcolor: str) -> str:
    return f'<span foreground="{hexcolor}">{_esc(s)}</span>'


# ── Detail panel rendering ──────────────────────────────────────────────────────

def _render_condition(row: sqlite3.Row, pab_region_id: str = "") -> str:
    lines = [_b(row["name"]), ""]

    has_clusters = (row["cluster_count"] > 0) if "cluster_count" in row.keys() else True
    if not has_clusters:
        lines.append(_italic_dim("◇ Reference condition — no CPR cluster data"))
        lines.append("")

    if row["condition_category"]:
        lines.append(f"{_dim('Category:')}  {_esc(row['condition_category'])}")
    if row["context"]:
        lines += ["", _dim("Context"), _esc(row["context"])]
    if row["reference"]:
        lines += ["", f"{_dim('Reference:')}  {_esc(row['reference'])}"]

    features = _load_condition_features(row["id"])
    if features:
        by_domain: dict[str, list] = {}
        for f in features:
            by_domain.setdefault(f["feature_domain"] or "other", []).append(f)
        domain_order = ["subjective", "history", "objective", "other"]
        domain_labels = {
            "subjective": "Subjective features",
            "history":    "History",
            "objective":  "Objective findings",
            "other":      "Other",
        }
        for domain in domain_order:
            if domain not in by_domain:
                continue
            lines += ["", _dim(domain_labels.get(domain, domain.title()))]
            for f in by_domain[domain]:
                lines.append(f"• {_dim(f['feature_name'] + ':')}  {_esc(f['feature_value'])}")

    if pab_region_id:
        diffs = _load_condition_differentiators(row["name"], pab_region_id)
        if diffs:
            lines += ["", _dim("Key differentiators")]
            for d in diffs:
                other = d["condition_b"] if d["condition_a"] == row["name"] else d["condition_a"]
                lines.append(f"{_dim('vs')} <i>{_esc(other)}</i>")
                if d["key_feature"]:
                    lines.append(f"  {_esc(d['key_feature'])}")

    flags = _load_condition_red_flags(row["id"], pab_region_id)
    condition_flags = [f for f in flags if f["flag_text"] and len(f["flag_text"]) < 200]
    if condition_flags:
        lines += ["", _dim("Red flags")]
        for f in condition_flags[:5]:
            hexcolor = _severity_hex(f["severity"])
            lines.append(f"{_color(chr(0x25b2), hexcolor)} {_esc(f['flag_text'][:120])}")

    return "\n".join(lines)


def _render_cluster(row: sqlite3.Row) -> str:
    lines = [
        _b(row["name"]),
        f"{_dim('Type:')}  {_esc(row['cluster_type'] or '—')}",
    ]
    if row["threshold"]:
        lines.append(f"{_dim('Threshold:')}  {_esc(row['threshold'])}")
    lines.append("")

    stats = []
    if row["sn"] is not None:
        stats.append(f"Sn {row['sn']:.2f}")
    if row["sp"] is not None:
        stats.append(f"Sp {row['sp']:.2f}")
    if stats:
        lines.append(_esc("  ".join(stats)))

    lr = _fmt_lr(row["plr"], row["nlr"])
    if lr:
        lines.append(_esc(lr))

    if row["clinical_interpretation"]:
        lines += ["", _dim("Interpretation"), _esc(row["clinical_interpretation"])]
    if row["notes"]:
        lines += ["", _dim("Notes"), _esc(row["notes"])]
    if row["reference"]:
        lines += ["", f"{_dim('Reference:')}  {_esc(row['reference'])}"]
    return "\n".join(lines)


def _render_test(test_id: int) -> str:
    row = _load_test_detail(test_id)
    if not row:
        return _esc("Test not found.")

    lines = [_b(row["name"])]
    if row["also_known_as"]:
        lines.append(f"{_dim('Also known as:')}  {_esc(row['also_known_as'])}")
    if row["test_type"]:
        lines.append(f"{_dim('Type:')}  {_esc(row['test_type'])}")
    domain_label = {"objective": "Objective", "subjective": "Subjective",
                     "demographic": "Demographic"}.get(row["domain"] or "objective", row["domain"] or "")
    lines.append(f"{_dim('Domain:')}  {_esc(domain_label)}")
    lines.append("")

    if row["patient_position"]:
        lines += [_dim("Patient position"), _esc(row["patient_position"]), ""]
    if row["procedure"]:
        lines += [_dim("Procedure"), _esc(row["procedure"]), ""]
    if row["positive_finding"]:
        lines += [_dim("Positive finding"), _esc(row["positive_finding"]), ""]

    stat_lines = []
    for val, ci, label in [
        (row["sn"],  row["sn_ci"],  "Sn "),
        (row["sp"],  row["sp_ci"],  "Sp "),
        (row["plr"], row["plr_ci"], "+LR"),
        (row["nlr"], row["nlr_ci"], "−LR"),
    ]:
        if val is not None:
            s = f"{label} {val:.2f}"
            if ci:
                s += f"  {ci}"
            stat_lines.append(_esc(s))
    if row["kappa"] is not None:
        stat_lines.append(_esc(f"κ   {row['kappa']:.2f}"))
    if stat_lines:
        lines += [_dim("Statistics")] + stat_lines + [""]

    if row["reference"]:
        lines += [f"{_dim('Reference:')}  {_esc(row['reference'])}", ""]
    if row["clinical_notes"]:
        lines += [_dim("Clinical notes"), _esc(row["clinical_notes"]), ""]

    if row["pitfalls"]:
        items = [p.strip() for p in row["pitfalls"].split("|") if p.strip()]
        lines += [_dim("Pitfalls")] + [f"• {_esc(p)}" for p in items] + [""]

    clusters = _load_test_clusters(test_id)
    if clusters:
        lines += [_dim("Cluster membership")]
        for cl in clusters:
            lr_str = f" +LR {cl['plr']:.2f}" if cl["plr"] is not None else ""
            lines.append(_esc(f"• {cl['condition']} → {cl['name']}{lr_str}"))
        lines.append("")

    maps = _load_test_field_maps(test_id)
    if maps:
        lines += [_dim("PAB field map")]
        for m in maps:
            side_str = f" [{m['side']}]" if m["side"] and m["side"] != "na" else ""
            path_str = f"  →  {m['pab_json_path']}" if m["pab_json_path"] else ""
            lines.append(_esc(f"• {m['pab_field_id']}{side_str}{path_str}"))
    else:
        lines += [_dim("PAB field map"), _italic_dim("not yet mapped")]

    return "\n".join(lines)


# ── Search index — lifted verbatim ──────────────────────────────────────────────

@dataclass
class KBSearchEntry:
    display: str
    match_text: str
    region_id: str
    condition_id: int | None = None
    cluster_id: int | None = None
    test_id: int | None = None
    kind: str = "region"


def _fuzzy_score(query: str, target: str) -> int:
    if not query:
        return 0
    q, t = query.lower(), target.lower()
    if q == t:
        return 1000
    if t.startswith(q):
        return 900
    if q in t:
        return 800 - t.index(q)
    idx = 0
    gaps = 0
    for ch in q:
        pos = t.find(ch, idx)
        if pos == -1:
            return 0
        gaps += pos - idx
        idx = pos + 1
    return max(1, 200 - gaps)


def _filter_entries(query: str, index: list[KBSearchEntry], max_results: int = 10) -> list[KBSearchEntry]:
    if not query.strip():
        return []
    scored: list[tuple[int, int, KBSearchEntry]] = []
    for i, entry in enumerate(index):
        score = _fuzzy_score(query, entry.match_text)
        if score > 0:
            scored.append((score, -i, entry))
    scored.sort(reverse=True)
    return [e for _, _, e in scored[:max_results]]


def _build_kb_index() -> list[KBSearchEntry]:
    entries: list[KBSearchEntry] = []
    conn = _open_db()
    try:
        for r in conn.execute(
            "SELECT pab_id, label FROM region ORDER BY body_area NULLS LAST, label"
        ).fetchall():
            entries.append(KBSearchEntry(
                display=f"[Region]  {r['label']}",
                match_text=f"{r['label']} {r['pab_id']} region",
                region_id=r["pab_id"],
                kind="region",
            ))

        for c in conn.execute("""
            SELECT c.id, c.name, c.short_name, c.icd_concept, r.pab_id, r.label
            FROM condition c JOIN region r ON c.primary_region_id = r.id
            ORDER BY r.label, c.name
        """).fetchall():
            match = " ".join(filter(None, [c["name"], c["short_name"], c["icd_concept"], c["label"]]))
            entries.append(KBSearchEntry(
                display=f"{c['label']} › {c['name']}",
                match_text=match,
                region_id=c["pab_id"],
                condition_id=c["id"],
                kind="condition",
            ))

        for cl in conn.execute("""
            SELECT cl.id, cl.name, cl.pab_region_id, cl.threshold,
                   co.name AS cond_name, r.label AS region_label
            FROM cluster cl
            JOIN condition co ON co.id = cl.condition_id
            JOIN region r ON r.pab_id = cl.pab_region_id
            ORDER BY r.label, co.name, cl.name
        """).fetchall():
            match = " ".join(filter(None, [cl["name"], cl["cond_name"], cl["region_label"], cl["threshold"]]))
            entries.append(KBSearchEntry(
                display=f"{cl['region_label']} › {cl['cond_name']} › {cl['name']}",
                match_text=match,
                region_id=cl["pab_region_id"],
                cluster_id=cl["id"],
                kind="cluster",
            ))

        for t in conn.execute("""
            SELECT t.id, t.name, t.also_known_as, t.test_type,
                   cl.id AS cluster_id, cl.pab_region_id,
                   co.name AS cond_name, r.label AS region_label
            FROM test t
            JOIN cluster_test ct ON ct.test_id = t.id
            JOIN cluster cl ON cl.id = ct.cluster_id
            JOIN condition co ON co.id = cl.condition_id
            JOIN region r ON r.pab_id = cl.pab_region_id
            ORDER BY r.label, co.name, t.name
        """).fetchall():
            match = " ".join(filter(None, [t["name"], t["also_known_as"], t["test_type"], t["cond_name"], t["region_label"]]))
            entries.append(KBSearchEntry(
                display=f"{t['region_label']} › {t['cond_name']} › {t['name']}",
                match_text=match,
                region_id=t["pab_region_id"],
                cluster_id=t["cluster_id"],
                test_id=t["id"],
                kind="test",
            ))
    finally:
        conn.close()
    return entries


# ── Region list row ──────────────────────────────────────────────────────────────

class _RegionRow(Gtk.ListBoxRow):
    def __init__(self, pab_id: str, label: str) -> None:
        super().__init__()
        self.pab_id = pab_id
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0.0)
        lbl.set_margin_start(4)
        lbl.set_margin_end(4)
        lbl.set_margin_top(3)
        lbl.set_margin_bottom(3)
        self.set_child(lbl)


# ── Search window ────────────────────────────────────────────────────────────────

class _KBSearchWindow(Gtk.Window):
    """Ctrl+F / F fuzzy jump-search — GTK4 port of the TUI's _KBSearchModal.
    Up/Down move selection, Enter confirms, Escape cancels.

    Keyboard nav is wired via Gtk.SearchEntry's own signals
    (next-match/previous-match/stop-search/activate), NOT a window-level
    Gtk.EventControllerKey — GtkSearchEntry has built-in class key bindings
    for exactly Down/Up/Escape/Enter, which consume those keys at the entry
    itself before they'd ever bubble to an ancestor controller. A first
    version of this window used a window-level key controller and none of
    the four ever fired, for this reason."""

    def __init__(self, parent: Gtk.Window, index: list[KBSearchEntry], on_selected) -> None:
        super().__init__(transient_for=parent, modal=True, decorated=False)
        self.set_default_size(480, 320)
        self._index = index
        self._entries: list[KBSearchEntry] = []
        self._selected_idx = -1
        self._on_selected = on_selected

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.add_css_class("kb-search-box")

        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text("⌕ type to search…")
        self.entry.connect("search-changed", self._on_changed)
        self.entry.connect("next-match", self._on_next_match)
        self.entry.connect("previous-match", self._on_previous_match)
        self.entry.connect("stop-search", self._on_stop_search)
        self.entry.connect("activate", self._on_activate)
        box.append(self.entry)

        self.results_box = Gtk.ListBox()
        self.results_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.results_box.connect("row-activated", self._on_row_activated)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(260)
        scroll.set_child(self.results_box)
        box.append(scroll)

        self.set_child(box)

        self.connect("show", lambda *_a: self.entry.grab_focus())

    def _on_changed(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text()
        results = _filter_entries(query, self._index) if query.strip() else []
        self._entries = results
        row = self.results_box.get_row_at_index(0)
        while row is not None:
            self.results_box.remove(row)
            row = self.results_box.get_row_at_index(0)
        for e in results:
            lbl = Gtk.Label(label=e.display)
            lbl.set_xalign(0.0)
            lbl.set_margin_start(6)
            lbl.set_margin_end(6)
            lbl.set_margin_top(3)
            lbl.set_margin_bottom(3)
            self.results_box.append(lbl)
        self._selected_idx = 0 if results else -1
        if results:
            self.results_box.select_row(self.results_box.get_row_at_index(0))

    def _on_next_match(self, _entry: Gtk.SearchEntry) -> None:
        if self._selected_idx < len(self._entries) - 1:
            self._selected_idx += 1
            self.results_box.select_row(self.results_box.get_row_at_index(self._selected_idx))

    def _on_previous_match(self, _entry: Gtk.SearchEntry) -> None:
        if self._selected_idx > 0:
            self._selected_idx -= 1
            self.results_box.select_row(self.results_box.get_row_at_index(self._selected_idx))

    def _on_activate(self, _entry: Gtk.SearchEntry) -> None:
        if 0 <= self._selected_idx < len(self._entries):
            self._finish(self._entries[self._selected_idx])

    def _on_stop_search(self, _entry: Gtk.SearchEntry) -> None:
        self._finish(None)

    def _on_row_activated(self, _box, row: Gtk.ListBoxRow) -> None:
        idx = row.get_index()
        if 0 <= idx < len(self._entries):
            self._finish(self._entries[idx])

    def _finish(self, result: KBSearchEntry | None) -> None:
        self._on_selected(result)
        self.close()


# ── Main browser window ──────────────────────────────────────────────────────────


# Column-width fractions of the window's own width, matching the reference
# screenshot's proportions (region list ~16%, tree ~36%, detail ~48% of the
# space left after the region list) — applied as literal pixel positions
# computed from _default_size() below, not from a live get_width() query
# (see the GTK layout lessons memory note: a Paned position computed from a
# live width can force the toplevel to grow if the window hasn't finished
# laying out yet; here the width is a python int this class already chose,
# so there's nothing stale to read).
_REGION_FRACTION = 0.16
_TREE_FRACTION = 0.44  # of the space remaining after the region column


def _default_size(window: Gtk.Window) -> tuple[int, int]:
    """~90% of the primary monitor's work area, echoing the reference
    screenshot (a large, nearly-fullscreen window with the main app's
    chrome still visible at the edges) rather than a fixed pixel guess that
    would be too small on a large monitor or too big on a small one."""
    display = window.get_display() or Gdk.Display.get_default()
    if display is not None:
        monitors = display.get_monitors()
        if monitors is not None and monitors.get_n_items() > 0:
            geo = monitors.get_item(0).get_geometry()
            width = round(geo.width * 0.9)
            height = round(geo.height * 0.88)
            return max(1100, min(width, 1900)), max(700, min(height, 1150))
    return 1500, 950


class KBDBWindow(Gtk.Window):
    """Full-screen-ish Clinical KB browser. Escape, q, or the Close button
    dismisses — GTK4 port of the TUI's KBDBScreen."""

    def __init__(self, parent: Gtk.Window) -> None:
        super().__init__(transient_for=parent, modal=True, title="Clinical KB")
        width, height = _default_size(self)
        self.set_default_size(width, height)
        self._region_width = round(width * _REGION_FRACTION)

        self._regions: list[sqlite3.Row] = []
        self._selected_region: str | None = None
        self._search_index: list[KBSearchEntry] = []
        self._db_available = _find_db() is not None

        header = Gtk.HeaderBar()
        search_btn = Gtk.Button(label="Search (F)")
        search_btn.connect("clicked", lambda _b: self._open_search())
        header.pack_start(search_btn)
        collapse_btn = Gtk.Button(label="Collapse (R)")
        collapse_btn.connect("clicked", lambda _b: self._collapse_all())
        header.pack_start(collapse_btn)
        close_btn = Gtk.Button(label="Close (Esc)")
        close_btn.connect("clicked", lambda _b: self.close())
        header.pack_end(close_btn)
        self.set_titlebar(header)

        if not self._db_available:
            msg = Gtk.Label(label=(
                "clinical_kb.db not found.\n\n"
                "Expected at:\n"
                "  ~/.local/share/pab/clinical_kb.db\n"
                "  ~/Projects/kb/output/clinical_kb.db\n\n"
                "Build the KB database from the kb/ project and deploy it."
            ))
            msg.set_wrap(True)
            msg.set_halign(Gtk.Align.START)
            msg.set_valign(Gtk.Align.START)
            msg.set_margin_top(24)
            msg.set_margin_start(24)
            msg.set_margin_end(24)
            self.set_child(msg)
            self._wire_keys()
            return

        # -- left: region list --------------------------------------------------
        region_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        region_box.set_size_request(self._region_width, -1)
        region_title = Gtk.Label(label="REGIONS")
        region_title.add_css_class("kb-db-heading")
        region_title.set_halign(Gtk.Align.START)
        region_box.append(region_title)
        self.region_list = Gtk.ListBox()
        self.region_list.connect("row-selected", self._on_region_row_selected)
        region_scroll = Gtk.ScrolledWindow()
        region_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        region_scroll.set_child(self.region_list)
        region_scroll.set_vexpand(True)
        region_box.append(region_scroll)

        # -- centre: condition/cluster/test tree ---------------------------------
        tree_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.tree_heading = Gtk.Label(label="Select a region")
        self.tree_heading.add_css_class("kb-db-heading")
        self.tree_heading.set_halign(Gtk.Align.START)
        tree_box.append(self.tree_heading)

        self.tree_store = Gtk.TreeStore(str, object)
        self.tree_view = Gtk.TreeView(model=self.tree_store)
        self.tree_view.set_headers_visible(False)
        col = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=0)
        self.tree_view.append_column(col)
        self.tree_view.get_selection().connect("changed", self._on_tree_selection_changed)
        tree_key_ctrl = Gtk.EventControllerKey()
        tree_key_ctrl.connect("key-pressed", self._on_tree_key)
        self.tree_view.add_controller(tree_key_ctrl)
        tree_scroll = Gtk.ScrolledWindow()
        tree_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        tree_scroll.set_child(self.tree_view)
        tree_scroll.set_vexpand(True)
        tree_scroll.set_hexpand(True)
        tree_box.append(tree_scroll)

        # -- right: detail panel --------------------------------------------------
        self.detail_label = Gtk.Label()
        self.detail_label.set_use_markup(True)
        self.detail_label.set_wrap(True)
        self.detail_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.detail_label.set_xalign(0.0)
        self.detail_label.set_yalign(0.0)
        self.detail_label.set_valign(Gtk.Align.START)
        self.detail_label.set_justify(Gtk.Justification.LEFT)
        self.detail_label.set_selectable(True)
        self.detail_label.set_margin_top(8)
        self.detail_label.set_margin_bottom(8)
        self.detail_label.set_margin_start(10)
        self.detail_label.set_margin_end(10)
        self.detail_label.set_markup(_dim("Select a condition, cluster, or test."))
        self.detail_scroll = Gtk.ScrolledWindow()
        self.detail_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.detail_scroll.set_child(self.detail_label)
        self.detail_scroll.set_size_request(420, -1)
        self.detail_scroll.set_vexpand(True)

        # -- panes: region | tree | detail, same nested-Paned pattern as
        # app.py's main_paned (content_column | kb_panel) — a Paned's
        # divider only enforces each side's own small natural minimum, so
        # neither pane can force the whole window wider than the screen the
        # way a plain Box honouring each child's literal minimum size can.
        center_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        center_paned.set_start_child(tree_box)
        center_paned.set_resize_start_child(True)
        center_paned.set_shrink_start_child(True)
        center_paned.set_end_child(self.detail_scroll)
        center_paned.set_resize_end_child(True)
        center_paned.set_shrink_end_child(True)

        outer_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        outer_paned.set_start_child(region_box)
        outer_paned.set_resize_start_child(False)
        outer_paned.set_shrink_start_child(True)
        outer_paned.set_end_child(center_paned)
        outer_paned.set_resize_end_child(True)
        outer_paned.set_shrink_end_child(True)

        # Initial divider positions, matching the reference screenshot's
        # proportions — safe to set from `width` (a value this class already
        # chose) before the window is realized, unlike deriving a position
        # from a live get_width() query (see module docstring / the GTK
        # layout lessons memory note on why that specific pattern is unsafe).
        outer_paned.set_position(self._region_width)
        center_paned.set_position(round((width - self._region_width) * _TREE_FRACTION))

        self.set_child(outer_paned)

        self._wire_keys()
        self._load_regions_ui()

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def _wire_keys(self) -> None:
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

    def _on_key(self, _ctrl, keyval, _keycode, state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        lname = name.lower()
        ctrl_held = bool(state & Gdk.ModifierType.CONTROL_MASK)

        if name == "Escape" or (lname == "q" and not ctrl_held):
            self.close()
            return True
        if lname == "f" and self._db_available:
            self._open_search()
            return True
        if lname == "r" and not ctrl_held and self._db_available:
            self._collapse_all()
            return True
        if name == "Page_Up":
            self._scroll_detail(-1)
            return True
        if name == "Page_Down":
            self._scroll_detail(1)
            return True
        if name in ("Left", "Right") and self._db_available:
            return self._handle_panel_nav(name)
        return False

    def _on_tree_key(self, _ctrl, keyval, _keycode, _state) -> bool:
        """Enter toggles expand/collapse — Tree's collapse binding, freed
        from Left/Right by the window-level capture-phase handler above."""
        name = Gdk.keyval_name(keyval) or ""
        if name in ("Return", "KP_Enter"):
            model, it = self.tree_view.get_selection().get_selected()
            if it is not None:
                path = model.get_path(it)
                if self.tree_view.row_expanded(path):
                    self.tree_view.collapse_row(path)
                else:
                    self.tree_view.expand_row(path, False)
            return True
        return False

    def _handle_panel_nav(self, name: str) -> bool:
        if name == "Right":
            if self.region_list.has_focus() or self.region_list.get_focus_child() is not None:
                self.tree_view.grab_focus()
                return True
            if self.tree_view.has_focus():
                self.detail_label.grab_focus()
                return True
        else:  # Left
            if self.detail_label.has_focus():
                self.tree_view.grab_focus()
                return True
            if self.tree_view.has_focus():
                self.region_list.grab_focus()
                return True
        return False

    def _scroll_detail(self, direction: int) -> None:
        adj = self.detail_scroll.get_vadjustment()
        page = adj.get_page_size()
        new_val = adj.get_value() + direction * page
        new_val = max(adj.get_lower(), min(new_val, adj.get_upper() - page))
        adj.set_value(new_val)

    # ------------------------------------------------------------------
    # Region list / tree loading
    # ------------------------------------------------------------------

    def _load_regions_ui(self) -> None:
        try:
            self._regions = _load_regions()
        except Exception as e:
            self.detail_label.set_markup(_color(f"DB error: {e}", "#e53935"))
            return
        for r in self._regions:
            self.region_list.append(_RegionRow(r["pab_id"], r["label"]))
        if self._regions:
            self.region_list.select_row(self.region_list.get_row_at_index(0))
        try:
            self._search_index = _build_kb_index()
        except Exception:
            pass

    def _on_region_row_selected(self, _listbox, row: _RegionRow | None) -> None:
        if row is None:
            return
        self._load_region(row.pab_id)

    def _load_region(self, pab_region_id: str) -> None:
        if pab_region_id == self._selected_region:
            return
        self._selected_region = pab_region_id
        self.tree_store.clear()

        label = next((r["label"] for r in self._regions if r["pab_id"] == pab_region_id), pab_region_id)
        self.tree_heading.set_label(label)

        try:
            conditions = _load_conditions_for_region(pab_region_id)
        except Exception as e:
            self.tree_store.append(None, [f"DB error: {e}", None])
            return

        if not conditions:
            self.tree_store.append(None, ["No conditions for this region yet", None])
            self.detail_label.set_markup(
                _dim(f"Select a condition, cluster, or test from the {label} region.")
            )
            return

        cpr_conditions = [c for c in conditions if c["cluster_count"] > 0]
        ref_conditions = [c for c in conditions if c["cluster_count"] == 0]

        expand_paths = []
        for cond in cpr_conditions:
            cond_iter = self.tree_store.append(
                None, [cond["name"], {"type": "condition", "row": cond, "region": pab_region_id}]
            )
            for cl in _load_clusters_for_condition(cond["id"], pab_region_id):
                cl_iter = self.tree_store.append(
                    cond_iter, [_cluster_label(cl), {"type": "cluster", "row": cl}]
                )
                for t in _load_tests_for_cluster(cl["id"]):
                    self.tree_store.append(
                        cl_iter, [_test_label(t), {"type": "test", "id": t["id"]}]
                    )
            expand_paths.append(self.tree_store.get_path(cond_iter))

        if ref_conditions:
            if cpr_conditions:
                self.tree_store.append(None, ["─── Reference ───────────────────────", None])
            for cond in ref_conditions:
                n = cond["feature_count"]
                suffix = f"  ({n} features)" if n else ""
                self.tree_store.append(
                    None, [f"◇ {cond['name']}{suffix}", {"type": "condition", "row": cond, "region": pab_region_id}]
                )

        for path in expand_paths:
            self.tree_view.expand_row(path, False)

        self.detail_label.set_markup(
            _dim(f"Select a condition, cluster, or test from the {label} region.")
        )

    def _on_tree_selection_changed(self, selection: Gtk.TreeSelection) -> None:
        model, it = selection.get_selected()
        if it is None:
            return
        data: dict[str, Any] | None = model.get_value(it, 1)
        if not data:
            return
        node_type = data.get("type")
        if node_type == "condition":
            self.detail_label.set_markup(_render_condition(data["row"], data.get("region", "")))
        elif node_type == "cluster":
            self.detail_label.set_markup(_render_cluster(data["row"]))
        elif node_type == "test":
            self.detail_label.set_markup(_render_test(data["id"]))
        else:
            return
        self.detail_scroll.get_vadjustment().set_value(0)

    def _collapse_all(self) -> None:
        it = self.tree_store.get_iter_first()
        while it is not None:
            self.tree_view.collapse_row(self.tree_store.get_path(it))
            it = self.tree_store.iter_next(it)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _open_search(self) -> None:
        def on_selected(entry: KBSearchEntry | None) -> None:
            if entry is not None:
                self._navigate_to(entry)
        _KBSearchWindow(self, self._search_index, on_selected).present()

    def _select_tree_iter(self, it: Gtk.TreeIter) -> None:
        path = self.tree_store.get_path(it)
        self.tree_view.expand_to_path(path)
        self.tree_view.set_cursor(path)
        self.tree_view.scroll_to_cell(path, None, True, 0.5, 0.0)
        self.tree_view.grab_focus()

    def _navigate_to(self, entry: KBSearchEntry) -> None:
        if entry.region_id != self._selected_region:
            self._load_region(entry.region_id)
            for i, r in enumerate(self._regions):
                if r["pab_id"] == entry.region_id:
                    row = self.region_list.get_row_at_index(i)
                    if row is not None:
                        self.region_list.select_row(row)
                    break

        if entry.kind == "region":
            self.tree_view.grab_focus()
            return

        it = self.tree_store.get_iter_first()
        while it is not None:
            data = self.tree_store.get_value(it, 1)
            if data and data.get("type") == "condition":
                if entry.kind == "condition" and data["row"]["id"] == entry.condition_id:
                    self._select_tree_iter(it)
                    return
                if entry.kind in ("cluster", "test"):
                    self.tree_view.expand_row(self.tree_store.get_path(it), False)
                    cl_it = self.tree_store.iter_children(it)
                    while cl_it is not None:
                        cl_data = self.tree_store.get_value(cl_it, 1)
                        if cl_data and cl_data.get("type") == "cluster" and cl_data["row"]["id"] == entry.cluster_id:
                            if entry.kind == "cluster":
                                self._select_tree_iter(cl_it)
                                return
                            self.tree_view.expand_row(self.tree_store.get_path(cl_it), False)
                            t_it = self.tree_store.iter_children(cl_it)
                            while t_it is not None:
                                t_data = self.tree_store.get_value(t_it, 1)
                                if t_data and t_data.get("type") == "test" and t_data["id"] == entry.test_id:
                                    self._select_tree_iter(t_it)
                                    return
                                t_it = self.tree_store.iter_next(t_it)
                        cl_it = self.tree_store.iter_next(cl_it)
            it = self.tree_store.iter_next(it)

        self.tree_view.grab_focus()
