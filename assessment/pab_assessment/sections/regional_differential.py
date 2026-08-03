"""Regional differential panel for Pain Classification (section 05)."""

from __future__ import annotations
import re
import logging
from pathlib import Path

import yaml
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Collapsible, Static

from ..objective import kb_db
from ..objective.kb_loader import get_registry, is_db_backed_region, is_global_db_field, KBEntry

logger = logging.getLogger(__name__)

_YAML_DIR = Path(__file__).parent.parent / "objective" / "sections" / "yaml"

_BADGE_MAP: dict = {
    None:  ("  —  ", "badge_none"),
    "Yes": (" Pos ", "badge_pos"),
    "No":  (" Neg ", "badge_neg"),
}


def _short_sn_sp(raw: str) -> str:
    """Extract compact Sn/Sp: 'Sn 72–79% / Sp 56–66% (...)' → 'Sn 79% Sp 66%'."""
    m = re.search(r"Sn\s+(?:\d+[–-])?(\d+)%\s*/\s*Sp\s+(?:\d+[–-])?(\d+)%", raw)
    if m:
        return f"Sn {m.group(1)}% Sp {m.group(2)}%"
    return "—"


def _load_region_structure(region_id: str) -> dict:
    """Load special_tests groups from the region YAML."""
    yaml_path = _YAML_DIR / f"{region_id}.yaml"
    try:
        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}
        return data.get("special_tests", {})
    except Exception as e:
        logger.warning("Failed to load region YAML %s: %s", yaml_path, e)
        return {}


def _load_extra_clusters(region_id: str) -> list[dict]:
    """Load extra_clusters — DB clusters whose members don't live in this region's
    special_tests widgets at all (e.g. Cook Myelopathy's signs are Neurological UMN
    fields). Each entry is {label, cluster_id, db_cluster_name}, no 'rows:' — every
    member comes from the DB via db_cluster_name, there's no YAML-authored fallback
    list the way special_tests groups have."""
    yaml_path = _YAML_DIR / f"{region_id}.yaml"
    try:
        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}
        return data.get("extra_clusters", []) or []
    except Exception as e:
        logger.warning("Failed to load region YAML %s: %s", yaml_path, e)
        return []


def _cluster_note_for(group_def: dict, kb: dict) -> str:
    """Return first non-empty cluster note from this group's KB entries."""
    for row in group_def.get("rows", []):
        entry = kb.get(row["id"])
        if entry and entry.cluster:
            return entry.cluster
    return ""


def _load_db_cluster(group_def: dict, region_id: str) -> dict | None:
    """Real DB cluster membership for a group, if the group opts in via
    `db_cluster_name` and the region is DB-backed. Returns None (falls back to the
    group's plain YAML `rows` list) if not opted in, region isn't DB-backed, the
    named cluster doesn't exist, or the DB file isn't reachable — never crashes the
    panel over this."""
    name = group_def.get("db_cluster_name")
    if not name or not is_db_backed_region(region_id):
        return None
    try:
        return kb_db.load_cluster_by_name(name, region_id)
    except FileNotFoundError:
        return None


def _build_members(group_def: dict, region_id: str) -> tuple[list[tuple], int, dict | None]:
    """(members, boolean_total, db_cluster) for one special_tests group — real DB
    cluster membership if the group opts in (see _load_db_cluster), else the plain
    YAML rows list unchanged. Each member tuple: (kind, stem_or_None, label,
    field_l, field_r, field_na, hint). kind is "boolean" (renders _TestRow, tallies
    toward pos/total) or "value" (renders _ValueRow, informational only).

    A DB-backed group can still carry YAML-only rows the DB doesn't model at all
    (e.g. lat_trans has no DB test row) — any YAML row whose stem isn't already
    covered by a DB member is appended after the DB members, same as if the group
    weren't DB-backed."""
    db_cluster = _load_db_cluster(group_def, region_id)
    members: list[tuple] = []
    covered_stems: set[str] = set()
    if db_cluster is not None:
        for t in db_cluster["tests"]:
            fl, fr, fna = t["field_l"], t["field_r"], t["field_na"]
            if fna and is_global_db_field(fna):
                # Single-sided flag sourced from elsewhere in the Objective tab
                # (e.g. Neurological UMN signs) — not a special-tests st_ field.
                members.append(("flag", None, t["name"], None, None, fna, ""))
            elif any(f and f.startswith("st_") for f in (fl, fr, fna)):
                stem = (fl or fr or "").removeprefix("st_").removesuffix("_l").removesuffix("_r")
                members.append(("boolean", stem, t["name"], fl, fr, fna, ""))
                covered_stems.add(stem)
            else:
                members.append(("value", None, t["name"], fl, fr, fna,
                                 t.get("positive_finding") or ""))
    for row in group_def.get("rows", []):
        stem = row["id"]
        if stem in covered_stems:
            continue
        members.append(("boolean", stem, row.get("label", stem), None, None, None, ""))
    boolean_total = sum(1 for m in members if m[0] in ("boolean", "flag"))
    return members, boolean_total, db_cluster


# ── Message ───────────────────────────────────────────────────────────────────

class RequestKBEntry(Message):
    """Bubbles when user clicks a test row — show its KB entry in the side panel."""
    def __init__(self, region_id: str, stem: str) -> None:
        super().__init__()
        self.region_id = region_id
        self.stem = stem


# ── Badge ─────────────────────────────────────────────────────────────────────

class _ResultBadge(Static):
    """Compact coloured badge: Pos / Neg / —."""

    DEFAULT_CSS = """
    _ResultBadge {
        width: 5; height: 1;
        content-align: center middle;
        text-align: center;
    }
    _ResultBadge.badge_pos  { background: $error;   color: white; }
    _ResultBadge.badge_neg  { background: $success; color: white; }
    _ResultBadge.badge_none { background: $surface; color: $text-muted; }
    """

    def __init__(self, badge_id: str, **kwargs) -> None:
        super().__init__("  —  ", id=badge_id, **kwargs)
        self.add_class("badge_none")

    def set_state(self, value) -> None:
        text, css_class = _BADGE_MAP.get(value, _BADGE_MAP[None])
        self.update(text)
        for cls in ("badge_pos", "badge_neg", "badge_none"):
            self.remove_class(cls)
        self.add_class(css_class)


# ── Test row ──────────────────────────────────────────────────────────────────

class _TestRow(Horizontal):
    """One test: label (click → KB panel) + Sn/Sp + L/R result badges."""

    DEFAULT_CSS = """
    _TestRow {
        height: 1; width: 100%;
    }
    _TestRow:hover { background: $boost; }
    _TestRow .tr_label {
        width: 1fr; height: 1;
        padding: 0 1 0 0;
        color: $text;
    }
    _TestRow .tr_snsp {
        width: 18; height: 1;
        color: $text-muted;
        text-align: right;
    }
    _TestRow .tr_side_label {
        width: 2; height: 1;
        color: $text-muted;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, stem: str, label: str, kb: "KBEntry | None",
                 region_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stem = stem
        self._label = label
        self._kb = kb
        self._region_id = region_id
        self._badge_l_id = f"rdp_{region_id}_{stem}_l"
        self._badge_r_id = f"rdp_{region_id}_{stem}_r"

    def compose(self) -> ComposeResult:
        sn_sp = _short_sn_sp(self._kb.sn_sp) if (self._kb and self._kb.sn_sp) else "—"
        yield Static(self._label, classes="tr_label")
        yield Static(sn_sp, classes="tr_snsp")
        yield Static("L", classes="tr_side_label")
        yield _ResultBadge(self._badge_l_id)
        yield Static("R", classes="tr_side_label")
        yield _ResultBadge(self._badge_r_id)

    def on_click(self) -> None:
        self.post_message(RequestKBEntry(self._region_id, self._stem))

    def set_results(self, l_val, r_val) -> None:
        try:
            self.query_one(f"#{self._badge_l_id}", _ResultBadge).set_state(l_val)
        except Exception:
            pass
        try:
            self.query_one(f"#{self._badge_r_id}", _ResultBadge).set_state(r_val)
        except Exception:
            pass


# ── Value row ─────────────────────────────────────────────────────────────────

class _ValueRow(Horizontal):
    """One cluster member that isn't a boolean special test — shows the raw entered
    value (e.g. a ROM degree measurement) instead of a Pos/Neg badge. Rendered for
    DB cluster members whose widget field id doesn't use the special-tests 'st_'
    convention. If the DB tracks a test with no pab field mapped to it at all,
    shows "not wired to pab yet" instead — a real coverage gap, not hidden."""

    DEFAULT_CSS = """
    _ValueRow { height: 1; width: 100%; }
    _ValueRow .tr_label   { width: 1fr; height: 1; padding: 0 1 0 0; color: $text; }
    _ValueRow .tr_hint    { width: 30; height: 1; color: $text-muted; }
    _ValueRow .tr_side_label { width: 2; height: 1; color: $text-muted; margin: 0 0 0 1; }
    _ValueRow .tr_value   { width: 6; height: 1; color: $text; text-align: right; }
    _ValueRow .tr_unwired { width: 1fr; height: 1; color: $text-muted; text-align: right; }
    """

    def __init__(self, label: str, hint: str, field_l: str | None, field_r: str | None,
                 field_na: str | None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._hint = hint
        self._field_l = field_l
        self._field_r = field_r
        self._field_na = field_na

    def compose(self) -> ComposeResult:
        yield Static(self._label, classes="tr_label")
        yield Static(self._hint, classes="tr_hint")
        if self._field_l or self._field_r:
            if self._field_l:
                yield Static("L", classes="tr_side_label")
                yield Static("—", classes="tr_value", id=f"rdpval_{self._field_l}")
            if self._field_r:
                yield Static("R", classes="tr_side_label")
                yield Static("—", classes="tr_value", id=f"rdpval_{self._field_r}")
        elif self._field_na:
            yield Static("—", classes="tr_value", id=f"rdpval_{self._field_na}")
        else:
            yield Static("not wired to pab yet", classes="tr_unwired")

    def set_results(self, tests: dict) -> None:
        for fid in (self._field_l, self._field_r, self._field_na):
            if not fid:
                continue
            try:
                widget = self.query_one(f"#rdpval_{fid}", Static)
            except Exception:
                continue
            val = tests.get(fid)
            widget.update(str(val) if val else "—")


# ── Flag row ──────────────────────────────────────────────────────────────────

class _FlagRow(Horizontal):
    """One single-sided boolean cluster member sourced from elsewhere in the
    Objective tab (e.g. Neurological's UMN FlagButtons) rather than a special-tests
    L/R pair. No side columns — one label, one badge. Tallies toward pos/total like
    _TestRow, unlike _ValueRow's numeric members."""

    DEFAULT_CSS = """
    _FlagRow { height: 1; width: 100%; }
    _FlagRow:hover { background: $boost; }
    _FlagRow .tr_label { width: 1fr; height: 1; padding: 0 1 0 0; color: $text; }
    """

    def __init__(self, label: str, region_id: str, field_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._region_id = region_id
        self._field_id = field_id
        self._badge_id = f"rdpflag_{field_id}"

    def compose(self) -> ComposeResult:
        yield Static(self._label, classes="tr_label")
        yield _ResultBadge(self._badge_id)

    def on_click(self) -> None:
        self.post_message(RequestKBEntry(self._region_id, self._field_id))

    def set_results(self, tests: dict) -> None:
        val = tests.get(self._field_id)
        # FlagButton.value is True/False/None (Python bool), unlike CycleButton's
        # "Yes"/"No"/None strings that _ResultBadge/_BADGE_MAP expect — normalize.
        badge_val = "Yes" if val is True else "No" if val is False else None
        try:
            self.query_one(f"#{self._badge_id}", _ResultBadge).set_state(badge_val)
        except Exception:
            pass


# ── Cluster block ─────────────────────────────────────────────────────────────

class _ClusterBlock(Vertical):
    """One cluster group wrapped in a collapsible (collapsed by default)."""

    DEFAULT_CSS = """
    _ClusterBlock {
        height: auto; width: 100%;
        margin-bottom: 0;
    }
    _ClusterBlock Collapsible {
        height: auto;
        border: none;
        padding: 0; margin: 0;
    }
    _ClusterBlock .cb_cluster_note {
        width: 100%; height: auto;
        color: $accent;
        padding: 0 0 0 2;
        margin: 0;
    }
    """

    def __init__(self, group_def: dict, kb: dict, region_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._group_def = group_def
        self._kb = kb
        self._region_id = region_id
        self._collapsible: Collapsible | None = None
        # _members: list of (kind, stem_or_None, label, field_l, field_r, field_na, hint)
        # kind is "boolean" (renders _TestRow, tallies toward pos/total) or "value"
        # (renders _ValueRow, informational only — see set_tests()).
        self._members, self._boolean_total, self._db_cluster = _build_members(group_def, region_id)

    def compose(self) -> ComposeResult:
        group_label = self._group_def.get("label", "")
        n = self._boolean_total
        if self._db_cluster is not None:
            cluster_note = self._db_cluster.get("clinical_interpretation") or ""
        else:
            cluster_note = _cluster_note_for(self._group_def, self._kb)
        with Collapsible(title=f"{group_label}  0/{n}", collapsed=True) as c:
            self._collapsible = c
            for kind, stem, label, fl, fr, fna, hint in self._members:
                if kind == "boolean":
                    kb_entry = self._kb.get(stem)
                    yield _TestRow(stem, label, kb_entry, self._region_id)
                elif kind == "flag":
                    yield _FlagRow(label, self._region_id, fna)
                else:
                    yield _ValueRow(label, hint, fl, fr, fna)
            if cluster_note:
                yield Static(cluster_note, classes="cb_cluster_note")

    def set_tests(self, tests: dict) -> tuple[int, int]:
        """Update rows; return (pos_count, total) for parent to sum. Boolean and
        flag members count toward the tally — value rows (e.g. a ROM measurement)
        are shown for reference but can't be auto-scored pass/fail from free text."""
        pos_count = 0
        total = self._boolean_total
        for row_widget in self.query(_TestRow):
            stem = row_widget._stem
            l_val = tests.get(f"st_{stem}_l")
            r_val = tests.get(f"st_{stem}_r")
            row_widget.set_results(l_val, r_val)
            if l_val == "Yes" or r_val == "Yes":
                pos_count += 1
        for flag_widget in self.query(_FlagRow):
            flag_widget.set_results(tests)
            if tests.get(flag_widget._field_id) is True:
                pos_count += 1
        for value_widget in self.query(_ValueRow):
            value_widget.set_results(tests)
        if self._collapsible is not None:
            group_label = self._group_def.get("label", "")
            self._collapsible.title = f"{group_label}  {pos_count}/{total}"
        return pos_count, total


# ── Regional panel ────────────────────────────────────────────────────────────

class RegionalDifferentialPanel(Vertical):
    """Region-level collapsible containing cluster-level collapsibles."""

    DEFAULT_CSS = """
    RegionalDifferentialPanel {
        height: auto; width: 100%;
        margin-bottom: 0;
    }
    RegionalDifferentialPanel > Collapsible {
        height: auto;
        border: none;
        padding: 0; margin: 0;
    }
    """

    def __init__(self, region_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._region_id = region_id
        self._pending_tests: dict = {}
        self._structure = _load_region_structure(region_id)
        self._extra_clusters = _load_extra_clusters(region_id)
        self._kb: dict = dict(get_registry()._data.get(region_id, {}))
        self._collapsible: Collapsible | None = None
        all_groups = self._structure.get("groups", []) + self._extra_clusters
        self._total_stems = sum(_build_members(g, region_id)[1] for g in all_groups)
        logger.debug("RDP panel: created for region=%s groups=%d extra_clusters=%d kb_entries=%d",
                     region_id, len(self._structure.get("groups", [])),
                     len(self._extra_clusters), len(self._kb))

    def compose(self) -> ComposeResult:
        region_label = self._region_id.capitalize()
        logger.debug("RDP panel: compose() for %s", self._region_id)
        with Collapsible(
            title=f"◆ {region_label}  0/{self._total_stems}", collapsed=True
        ) as c:
            self._collapsible = c
            for group in self._structure.get("groups", []):
                cid = group.get("cluster_id", "")
                yield _ClusterBlock(
                    group, self._kb, self._region_id,
                    id=f"rdp_cb_{self._region_id}_{cid}"
                )
            for group in self._extra_clusters:
                # extra_clusters have no YAML rows fallback — if the named DB
                # cluster isn't found (typo, or DB unreachable), _build_members
                # returns no members at all. Skip rendering an empty "0/0" block
                # rather than showing a broken-looking group.
                members, _, _ = _build_members(group, self._region_id)
                if not members:
                    continue
                cid = group.get("cluster_id", "")
                yield _ClusterBlock(
                    group, self._kb, self._region_id,
                    id=f"rdp_cb_{self._region_id}_{cid}"
                )

    def on_mount(self) -> None:
        logger.debug("RDP panel: on_mount() for %s pending=%s",
                     self._region_id, bool(self._pending_tests))
        if self._pending_tests:
            self.set_tests(self._pending_tests)
            self._pending_tests = {}

    def set_tests(self, tests: dict) -> None:
        blocks = list(self.query(_ClusterBlock))
        if not blocks:
            self._pending_tests = dict(tests)
            return
        total_pos = 0
        for block in blocks:
            pos, _ = block.set_tests(tests)
            total_pos += pos
        if self._collapsible is not None:
            region_label = self._region_id.capitalize()
            self._collapsible.title = f"◆ {region_label}  {total_pos}/{self._total_stems}"
