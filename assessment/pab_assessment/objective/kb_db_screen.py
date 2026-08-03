"""Full-screen Clinical KB browser — opened via Ctrl+D from anywhere in the app.

Layout mirrors kb_viewer.py (separate kb/ project):
  Left   — region selector
  Centre — condition → cluster → test tree
  Right  — detail panel for selected node

DB access (path search, read-only connection) lives in kb_db.py, shared with
kb_loader.py and the special-test widgets.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Input, Label, ListItem, ListView, Static, Tree

from . import kb_db

_find_db = kb_db.find_db
_open_db = kb_db.open_db


# ── Database queries ───────────────────────────────────────────────────────────

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


# ── Formatting helpers ─────────────────────────────────────────────────────────

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


def _severity_colour(severity: str | None) -> str:
    return {"emergency": "red", "urgent": "yellow", "refer": "blue"}.get(severity or "", "dim")


# ── Detail panel rendering ─────────────────────────────────────────────────────

def _render_condition(row: sqlite3.Row, pab_region_id: str = "") -> str:
    lines = [f"[bold]{row['name']}[/bold]", ""]

    has_clusters = (row["cluster_count"] > 0) if "cluster_count" in row.keys() else True
    if not has_clusters:
        lines.append("[dim italic]◇ Reference condition — no CPR cluster data[/dim italic]")
        lines.append("")

    if row["condition_category"]:
        lines.append(f"[dim]Category:[/dim]  {row['condition_category']}")
    if row["context"]:
        lines += ["", "[dim]Context[/dim]", row["context"]]
    if row["reference"]:
        lines += ["", f"[dim]Reference:[/dim]  {row['reference']}"]

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
            lines += ["", f"[dim]{domain_labels.get(domain, domain.title())}[/dim]"]
            for f in by_domain[domain]:
                lines.append(f"• [dim]{f['feature_name']}:[/dim]  {f['feature_value']}")

    if pab_region_id:
        diffs = _load_condition_differentiators(row["name"], pab_region_id)
        if diffs:
            lines += ["", "[dim]Key differentiators[/dim]"]
            for d in diffs:
                other = d["condition_b"] if d["condition_a"] == row["name"] else d["condition_a"]
                lines.append(f"[dim]vs[/dim] [italic]{other}[/italic]")
                if d["key_feature"]:
                    lines.append(f"  {d['key_feature']}")

    flags = _load_condition_red_flags(row["id"], pab_region_id)
    condition_flags = [f for f in flags if f["flag_text"] and len(f["flag_text"]) < 200]
    if condition_flags:
        lines += ["", "[dim]Red flags[/dim]"]
        for f in condition_flags[:5]:
            col = _severity_colour(f["severity"])
            lines.append(f"[{col}]▲[/{col}] {f['flag_text'][:120]}")

    return "\n".join(lines)


def _render_cluster(row: sqlite3.Row) -> str:
    lines = [
        f"[bold]{row['name']}[/bold]",
        f"[dim]Type:[/dim]  {row['cluster_type'] or '—'}",
    ]
    if row["threshold"]:
        lines.append(f"[dim]Threshold:[/dim]  {row['threshold']}")
    lines.append("")

    stats = []
    if row["sn"] is not None:
        stats.append(f"Sn {row['sn']:.2f}")
    if row["sp"] is not None:
        stats.append(f"Sp {row['sp']:.2f}")
    if stats:
        lines.append("  ".join(stats))

    lr = _fmt_lr(row["plr"], row["nlr"])
    if lr:
        lines.append(lr)

    if row["clinical_interpretation"]:
        lines += ["", "[dim]Interpretation[/dim]", row["clinical_interpretation"]]
    if row["notes"]:
        lines += ["", "[dim]Notes[/dim]", row["notes"]]
    if row["reference"]:
        lines += ["", f"[dim]Reference:[/dim]  {row['reference']}"]
    return "\n".join(lines)


def _render_test(test_id: int) -> str:
    row = _load_test_detail(test_id)
    if not row:
        return "Test not found."

    lines = [f"[bold]{row['name']}[/bold]"]
    if row["also_known_as"]:
        lines.append(f"[dim]Also known as:[/dim]  {row['also_known_as']}")
    if row["test_type"]:
        lines.append(f"[dim]Type:[/dim]  {row['test_type']}")
    domain_label = {"objective": "Objective", "subjective": "Subjective",
                    "demographic": "Demographic"}.get(row["domain"] or "objective", row["domain"] or "")
    lines.append(f"[dim]Domain:[/dim]  {domain_label}")
    lines.append("")

    if row["patient_position"]:
        lines += ["[dim]Patient position[/dim]", row["patient_position"], ""]
    if row["procedure"]:
        lines += ["[dim]Procedure[/dim]", row["procedure"], ""]
    if row["positive_finding"]:
        lines += ["[dim]Positive finding[/dim]", row["positive_finding"], ""]

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
            stat_lines.append(s)
    if row["kappa"] is not None:
        stat_lines.append(f"κ   {row['kappa']:.2f}")
    if stat_lines:
        lines += ["[dim]Statistics[/dim]"] + stat_lines + [""]

    if row["reference"]:
        lines += [f"[dim]Reference:[/dim]  {row['reference']}", ""]
    if row["clinical_notes"]:
        lines += ["[dim]Clinical notes[/dim]", row["clinical_notes"], ""]

    if row["pitfalls"]:
        items = [p.strip() for p in row["pitfalls"].split("|") if p.strip()]
        lines += ["[dim]Pitfalls[/dim]"] + [f"• {p}" for p in items] + [""]

    clusters = _load_test_clusters(test_id)
    if clusters:
        lines += ["[dim]Cluster membership[/dim]"]
        for cl in clusters:
            lr_str = f" +LR {cl['plr']:.2f}" if cl["plr"] is not None else ""
            lines.append(f"• {cl['condition']} → {cl['name']}{lr_str}")
        lines.append("")

    maps = _load_test_field_maps(test_id)
    if maps:
        lines += ["[dim]PAB field map[/dim]"]
        for m in maps:
            side_str = f" [{m['side']}]" if m["side"] and m["side"] != "na" else ""
            path_str = f"  →  {m['pab_json_path']}" if m["pab_json_path"] else ""
            lines.append(f"• {m['pab_field_id']}{side_str}{path_str}")
    else:
        lines += ["[dim]PAB field map[/dim]", "[dim italic]not yet mapped[/dim italic]"]

    return "\n".join(lines)


# ── Search index ──────────────────────────────────────────────────────────────

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


# ── Search modal ──────────────────────────────────────────────────────────────

class _KBSearchResultRow(Static):
    DEFAULT_CSS = """
    _KBSearchResultRow {
        width: 100%;
        height: 1;
        padding: 0 1;
        color: $text;
        display: none;
    }
    _KBSearchResultRow.--selected {
        height: 3;
        border: solid $accent;
        color: $accent;
        background: transparent;
        padding: 0 1;
    }
    _KBSearchResultRow:hover { color: $text; background: $surface; }
    _KBSearchResultRow.--selected:hover {
        border: solid $accent;
        color: $accent;
        background: transparent;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._entry: KBSearchEntry | None = None

    def on_click(self) -> None:
        if self._entry is not None:
            self.screen.dismiss(self._entry)


class _KBSearchModal(ModalScreen):
    DEFAULT_CSS = """
    _KBSearchModal { background: transparent; align: center middle; }
    #kb_modal_box {
        width: 60;
        height: auto;
        max-height: 22;
        background: $boost;
        border: solid $primary;
    }
    #kb_modal_input {
        width: 100%;
        height: 1;
        padding: 0 1;
        background: $accent 30%;
        border: none;
        color: $text;
    }
    #kb_modal_input:focus { border: none; background: $accent 45%; }
    """

    def __init__(self, index: list[KBSearchEntry], **kwargs) -> None:
        super().__init__(**kwargs)
        self._index = index
        self._entries: list[KBSearchEntry] = []
        self._selected_idx: int = -1

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical as _V
        with _V(id="kb_modal_box"):
            yield Input(placeholder="⌕ type to search…", id="kb_modal_input")
            for _ in range(10):
                yield _KBSearchResultRow()

    def on_mount(self) -> None:
        self.query_one("#kb_modal_input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        results = _filter_entries(event.value, self._index) if event.value.strip() else []
        self._entries = results
        self._selected_idx = 0 if results else -1
        rows = list(self.query(_KBSearchResultRow))
        for i, row in enumerate(rows):
            if i < len(results):
                row._entry = results[i]
                row.update(results[i].display)
                row.display = True
                row.set_class(i == 0, "--selected")
            else:
                row._entry = None
                row.update("")
                row.display = False

    def on_key(self, event: events.Key) -> None:
        if event.key == "down":
            if self._selected_idx < len(self._entries) - 1:
                self._move_selection(self._selected_idx + 1)
            event.stop()
        elif event.key == "up":
            if self._selected_idx > 0:
                self._move_selection(self._selected_idx - 1)
            event.stop()
        elif event.key == "enter":
            if 0 <= self._selected_idx < len(self._entries):
                self.dismiss(self._entries[self._selected_idx])
            event.stop()
        elif event.key == "escape":
            self.dismiss(None)
            event.stop()

    def _move_selection(self, idx: int) -> None:
        rows = list(self.query(_KBSearchResultRow))
        if 0 <= self._selected_idx < len(rows):
            rows[self._selected_idx].remove_class("--selected")
        self._selected_idx = idx
        if 0 <= idx < len(rows):
            rows[idx].add_class("--selected")


# ── Tree subclass ─────────────────────────────────────────────────────────────

class _KBTree(Tree):
    """Tree with Enter = toggle and left/right freed for panel navigation."""
    BINDINGS = [
        *(b for b in Tree.BINDINGS if b.key != "enter"),
        Binding("enter", "toggle_node", show=False),
    ]


# ── Main screen ───────────────────────────────────────────────────────────────

class KBDBScreen(Screen):
    """Full-screen Clinical KB browser. Dismiss with Escape or q."""

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Dismiss", show=True),
        Binding("q",      "dismiss_screen", "Dismiss", show=False),
        Binding("f",      "search",         "Search",  show=True),
        Binding("ctrl+f", "search",         "Search",  show=False),
        Binding("r",      "collapse_all",   "Collapse", show=True),
        Binding("right",  "focus_next_panel",     show=False, priority=True),
        Binding("left",   "focus_prev_panel",     show=False, priority=True),
        Binding("pageup",   "detail_page_up",   "Scroll ↑", show=True),
        Binding("pagedown", "detail_page_down", "Scroll ↓", show=True),
    ]

    CSS = """
    KBDBScreen {
        layout: vertical;
    }

    #kb_title_bar {
        height: 1;
        width: 100%;
        background: $boost;
        color: $text-muted;
        padding: 0 1;
        text-style: bold;
    }

    #kb_main {
        layout: horizontal;
        height: 1fr;
    }

    #kb_region_panel {
        width: 22;
        border-right: solid $primary-darken-2;
        padding: 0 1;
    }

    #kb_region_title {
        text-style: bold;
        color: $primary;
        padding: 0 0 1 0;
    }

    #kb_tree_panel {
        width: 1fr;
        border-right: solid $primary-darken-2;
    }

    #kb_detail_scroll { width: 50; }
    #kb_detail_panel  { padding: 1 2; }

    KBDBScreen ListView { height: 1fr; border: none; }
    KBDBScreen ListItem { padding: 0 1; }
    KBDBScreen Tree     { height: 1fr; padding: 0 1; }
    """

    def __init__(self, start_at: tuple[str, int] | None = None, **kwargs) -> None:
        """
        start_at: optional (pab_region_id, condition_id) to pre-navigate on open.
        Reserved for future linked mode from Pain Classification section.
        """
        super().__init__(**kwargs)
        self._start_at = start_at
        self._regions: list[sqlite3.Row] = []
        self._selected_region: str | None = None
        self._search_index: list[KBSearchEntry] = []
        self._db_available = _find_db() is not None

    def compose(self) -> ComposeResult:
        yield Static("Clinical KB  [dim]Esc/q[/dim] dismiss  [dim]f[/dim] search  [dim]r[/dim] collapse  [dim]PgUp/Dn[/dim] scroll detail", id="kb_title_bar", markup=True)
        if not self._db_available:
            yield Static(
                "\n[bold red]clinical_kb.db not found.[/bold red]\n\n"
                "Expected at:\n"
                "  ~/.local/share/pab/clinical_kb.db\n"
                "  ~/Projects/kb/output/clinical_kb.db\n\n"
                "Build the KB database from the kb/ project and deploy it.",
                markup=True,
            )
            yield Footer()
            return
        with Horizontal(id="kb_main"):
            with Vertical(id="kb_region_panel"):
                yield Label("REGIONS", id="kb_region_title")
                yield ListView(id="kb_region_list")
            with Vertical(id="kb_tree_panel"):
                yield _KBTree("Select a region", id="kb_tree")
            with ScrollableContainer(id="kb_detail_scroll"):
                yield Static("", id="kb_detail_panel", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        if not self._db_available:
            return
        try:
            self._regions = _load_regions()
        except Exception as e:
            self.query_one("#kb_detail_panel", Static).update(f"[red]DB error: {e}[/red]")
            return

        region_list = self.query_one("#kb_region_list", ListView)
        for r in self._regions:
            region_list.append(ListItem(Label(r["label"]), id=f"kbr-{r['pab_id']}"))

        if self._regions:
            initial_region = self._regions[0]["pab_id"]
            if self._start_at:
                initial_region = self._start_at[0]
            self._load_region(initial_region)
            for i, r in enumerate(self._regions):
                if r["pab_id"] == initial_region:
                    region_list.index = i
                    break

        try:
            self._search_index = _build_kb_index()
        except Exception:
            pass

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        item_id = event.item.id or ""
        if item_id.startswith("kbr-"):
            self._load_region(item_id[len("kbr-"):])

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        data: dict[str, Any] | None = event.node.data
        if not data:
            return
        detail = self.query_one("#kb_detail_panel", Static)
        node_type = data.get("type")
        if node_type == "condition":
            detail.update(_render_condition(data["row"], data.get("region", "")))
        elif node_type == "cluster":
            detail.update(_render_cluster(data["row"]))
        elif node_type == "test":
            detail.update(_render_test(data["id"]))
        self.query_one("#kb_detail_scroll").scroll_home(animate=False)

    def action_dismiss_screen(self) -> None:
        self.app.pop_screen()

    def action_search(self) -> None:
        def on_dismiss(result: KBSearchEntry | None) -> None:
            if result is not None:
                self._navigate_to(result)
        self.app.push_screen(_KBSearchModal(self._search_index), on_dismiss)

    def action_detail_page_up(self) -> None:
        try:
            self.query_one("#kb_detail_scroll", ScrollableContainer).scroll_page_up(animate=False)
        except Exception:
            pass

    def action_detail_page_down(self) -> None:
        try:
            self.query_one("#kb_detail_scroll", ScrollableContainer).scroll_page_down(animate=False)
        except Exception:
            pass

    def action_collapse_all(self) -> None:
        try:
            for node in self.query_one("#kb_tree", Tree).root.children:
                node.collapse()
        except Exception:
            pass

    def action_focus_next_panel(self) -> None:
        focused = self.focused
        try:
            region_list = self.query_one("#kb_region_list", ListView)
            tree = self.query_one("#kb_tree", _KBTree)
            detail = self.query_one("#kb_detail_scroll", ScrollableContainer)
            if focused is region_list:
                tree.focus()
            elif focused is tree:
                detail.focus()
        except Exception:
            pass

    def action_focus_prev_panel(self) -> None:
        focused = self.focused
        try:
            region_list = self.query_one("#kb_region_list", ListView)
            tree = self.query_one("#kb_tree", _KBTree)
            detail = self.query_one("#kb_detail_scroll", ScrollableContainer)
            if focused is tree:
                region_list.focus()
            elif focused is detail:
                tree.focus()
        except Exception:
            pass

    def _load_region(self, pab_region_id: str) -> None:
        if pab_region_id == self._selected_region:
            return
        self._selected_region = pab_region_id

        tree = self.query_one("#kb_tree", Tree)
        tree.clear()
        label = next((r["label"] for r in self._regions if r["pab_id"] == pab_region_id), pab_region_id)
        tree.root.set_label(label)
        tree.root.expand()

        try:
            conditions = _load_conditions_for_region(pab_region_id)
        except Exception as e:
            tree.root.add_leaf(f"[red]DB error: {e}[/red]")
            return

        if not conditions:
            tree.root.add_leaf("[dim]No conditions for this region yet[/dim]")
            return

        cpr_conditions = [c for c in conditions if c["cluster_count"] > 0]
        ref_conditions = [c for c in conditions if c["cluster_count"] == 0]

        for cond in cpr_conditions:
            cond_node = tree.root.add(
                cond["name"],
                data={"type": "condition", "row": cond, "region": pab_region_id},
            )
            clusters = _load_clusters_for_condition(cond["id"], pab_region_id)
            for cl in clusters:
                cl_node = cond_node.add(
                    _cluster_label(cl),
                    data={"type": "cluster", "row": cl},
                )
                for t in _load_tests_for_cluster(cl["id"]):
                    cl_node.add_leaf(
                        _test_label(t),
                        data={"type": "test", "id": t["id"]},
                    )

        if ref_conditions:
            if cpr_conditions:
                tree.root.add_leaf("[dim]─── Reference ─────────────────────[/dim]")
            for cond in ref_conditions:
                n = cond["feature_count"]
                suffix = f"  ({n} features)" if n else ""
                tree.root.add_leaf(
                    f"◇ {cond['name']}{suffix}",
                    data={"type": "condition", "row": cond, "region": pab_region_id},
                )

        for node in tree.root.children:
            if node.data and node.data.get("type") == "condition":
                if node.data["row"]["cluster_count"] > 0:
                    node.expand()

        self.query_one("#kb_detail_panel", Static).update(
            f"[dim]Select a condition, cluster, or test from the {label} region.[/dim]"
        )

    def _navigate_to(self, entry: KBSearchEntry) -> None:
        if entry.region_id != self._selected_region:
            self._load_region(entry.region_id)
            for i, r in enumerate(self._regions):
                if r["pab_id"] == entry.region_id:
                    self.query_one("#kb_region_list", ListView).index = i
                    break

        tree = self.query_one("#kb_tree", Tree)

        if entry.kind == "region":
            tree.focus()
            return

        for node in tree.root.children:
            data = node.data
            if not data or data.get("type") != "condition":
                continue

            if entry.kind == "condition":
                if data["row"]["id"] == entry.condition_id:
                    tree.move_cursor(node)
                    tree.focus()
                    return

            if entry.kind in ("cluster", "test"):
                node.expand()
                for cl_node in node.children:
                    cl_data = cl_node.data
                    if not cl_data or cl_data.get("type") != "cluster":
                        continue
                    if cl_data["row"]["id"] == entry.cluster_id:
                        if entry.kind == "cluster":
                            tree.move_cursor(cl_node)
                            tree.focus()
                            return
                        cl_node.expand()
                        for t_node in cl_node.children:
                            t_data = t_node.data
                            if t_data and t_data.get("type") == "test" and t_data["id"] == entry.test_id:
                                tree.move_cursor(t_node)
                                tree.focus()
                                return

        tree.focus()
