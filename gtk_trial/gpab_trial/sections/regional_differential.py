"""Regional differential panel for Pain Classification — GTK4 port of
pab_assessment/sections/regional_differential.py.

Mounted into PainClassificationSection.diff_region_box, one panel per
active body region, mirroring the TUI's set_active_regions()/
set_region_test_data() mount/unmount + live-refresh pattern exactly (see
that section's own set_active_regions/set_region_test_data, and app.py's
_push_region_tests_to_pain_classification for how test data reaches here).

The pure data functions below (_short_sn_sp, _load_region_structure,
_load_extra_clusters, _cluster_note_for, _load_db_cluster, _build_members)
are lifted verbatim from the TUI file — no Textual imports, no logic
changes, only the KB module import paths repointed at this package's own
copies (objective/kb_db.py, objective/kb_loader.py — both already ported
unchanged). Only the widget layer is rebuilt: Gtk.Expander stands in for
Textual's Collapsible, and Textual's Message-bubbling (RequestKBEntry) is
replaced with a plain on_request_kb(region_id, field_id) callback passed
down through the widget tree from the top-level panel — GTK has no
message-bubbling equivalent, and every other cross-cutting callback in
this codebase (set_on_changed, etc.) already uses this same
callback-injection convention rather than GObject signals for something
this deeply nested.
"""

from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Callable

import yaml
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..objective import kb_db
from ..objective.kb_loader import get_registry, is_db_backed_region, is_global_db_field, KBEntry

logger = logging.getLogger(__name__)

_YAML_DIR = Path(__file__).resolve().parents[3] / "assessment" / "pab_assessment" / "objective" / "sections" / "yaml"

# (region_id, field_id) -> None
RequestKBCallback = Callable[[str, str], None]

_BADGE_TEXT = {None: "—", "Yes": "Pos", "No": "Neg"}
_BADGE_CLASS = {None: "rdp-badge-none", "Yes": "rdp-badge-pos", "No": "rdp-badge-neg"}


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
    field_l, field_r, field_na, hint). kind is "boolean" (renders a test row,
    tallies toward pos/total), "flag" (single-sided boolean sourced elsewhere,
    also tallies), or "value" (renders a value row, informational only).

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


# ── Badge ─────────────────────────────────────────────────────────────────────

class _ResultBadge(Gtk.Label):
    """Compact coloured badge: Pos / Neg / —."""

    def __init__(self) -> None:
        super().__init__(label="—")
        self.set_size_request(40, -1)
        self.add_css_class("rdp-badge")
        self.add_css_class("rdp-badge-none")

    def set_state(self, value) -> None:
        self.set_label(_BADGE_TEXT.get(value, "—"))
        for cls in ("rdp-badge-pos", "rdp-badge-neg", "rdp-badge-none"):
            self.remove_css_class(cls)
        self.add_css_class(_BADGE_CLASS.get(value, "rdp-badge-none"))


def _make_clickable(widget: Gtk.Widget, on_click) -> None:
    click = Gtk.GestureClick()
    click.connect("released", lambda *_a: on_click())
    widget.add_controller(click)
    widget.add_css_class("rdp-clickable")


# ── Test row ──────────────────────────────────────────────────────────────────

class _TestRow(Gtk.Box):
    """One test: label (click → KB panel) + Sn/Sp + L/R result badges."""

    def __init__(self, stem: str, label: str, kb_entry: "KBEntry | None",
                 region_id: str, on_request_kb: RequestKBCallback | None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.stem = stem
        self.add_css_class("rdp-row")

        sn_sp = _short_sn_sp(kb_entry.sn_sp) if (kb_entry and kb_entry.sn_sp) else "—"

        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        lbl.set_xalign(0.0)
        self.append(lbl)

        snsp_lbl = Gtk.Label(label=sn_sp)
        snsp_lbl.add_css_class("rdp-snsp")
        snsp_lbl.set_size_request(120, -1)
        snsp_lbl.set_xalign(1.0)
        self.append(snsp_lbl)

        self.append(self._side_label("L"))
        self.badge_l = _ResultBadge()
        self.append(self.badge_l)
        self.append(self._side_label("R"))
        self.badge_r = _ResultBadge()
        self.append(self.badge_r)

        if on_request_kb is not None:
            _make_clickable(self, lambda: on_request_kb(region_id, stem))

    @staticmethod
    def _side_label(text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("rdp-side-label")
        return lbl

    def set_results(self, l_val, r_val) -> None:
        self.badge_l.set_state(l_val)
        self.badge_r.set_state(r_val)


# ── Value row ─────────────────────────────────────────────────────────────────

class _ValueRow(Gtk.Box):
    """One cluster member that isn't a boolean special test — shows the raw entered
    value (e.g. a ROM degree measurement) instead of a Pos/Neg badge. Rendered for
    DB cluster members whose widget field id doesn't use the special-tests 'st_'
    convention. If the DB tracks a test with no pab field mapped to it at all,
    shows "not wired to pab yet" instead — a real coverage gap, not hidden."""

    def __init__(self, label: str, hint: str, field_l: str | None, field_r: str | None,
                 field_na: str | None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._field_l = field_l
        self._field_r = field_r
        self._field_na = field_na
        self._value_labels: dict[str, Gtk.Label] = {}

        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        lbl.set_xalign(0.0)
        self.append(lbl)

        if hint:
            hint_lbl = Gtk.Label(label=hint)
            hint_lbl.add_css_class("rdp-hint")
            hint_lbl.set_size_request(160, -1)
            hint_lbl.set_xalign(1.0)
            hint_lbl.set_wrap(True)
            self.append(hint_lbl)

        if field_l or field_r:
            for side, fid in (("L", field_l), ("R", field_r)):
                if not fid:
                    continue
                self.append(_TestRow._side_label(side))
                val_lbl = Gtk.Label(label="—")
                val_lbl.add_css_class("rdp-value")
                val_lbl.set_size_request(40, -1)
                self._value_labels[fid] = val_lbl
                self.append(val_lbl)
        elif field_na:
            val_lbl = Gtk.Label(label="—")
            val_lbl.add_css_class("rdp-value")
            val_lbl.set_size_request(40, -1)
            self._value_labels[field_na] = val_lbl
            self.append(val_lbl)
        else:
            unwired = Gtk.Label(label="not wired to pab yet")
            unwired.add_css_class("rdp-unwired")
            unwired.set_hexpand(True)
            unwired.set_xalign(1.0)
            self.append(unwired)

    def set_results(self, tests: dict) -> None:
        for fid, lbl in self._value_labels.items():
            val = tests.get(fid)
            lbl.set_label(str(val) if val else "—")


# ── Flag row ──────────────────────────────────────────────────────────────────

class _FlagRow(Gtk.Box):
    """One single-sided boolean cluster member sourced from elsewhere in the
    Objective tab (e.g. Neurological's UMN FlagButtons) rather than a special-tests
    L/R pair. No side columns — one label, one badge. Tallies toward pos/total like
    _TestRow, unlike _ValueRow's numeric members."""

    def __init__(self, label: str, region_id: str, field_id: str,
                 on_request_kb: RequestKBCallback | None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.field_id = field_id
        self.add_css_class("rdp-row")

        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        lbl.set_xalign(0.0)
        self.append(lbl)

        self.badge = _ResultBadge()
        self.append(self.badge)

        if on_request_kb is not None:
            _make_clickable(self, lambda: on_request_kb(region_id, field_id))

    def set_results(self, tests: dict) -> None:
        val = tests.get(self.field_id)
        # FlagButton.value is True/False/None (Python bool), unlike CycleField's
        # "Yes"/"No"/None strings that _ResultBadge expects — normalize.
        badge_val = "Yes" if val is True else "No" if val is False else None
        self.badge.set_state(badge_val)


# ── Cluster block ─────────────────────────────────────────────────────────────

class _ClusterBlock(Gtk.Box):
    """One cluster group wrapped in a Gtk.Expander (collapsed by default)."""

    def __init__(self, group_def: dict, kb: dict, region_id: str,
                 on_request_kb: RequestKBCallback | None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._group_def = group_def
        self._members, self._boolean_total, self._db_cluster = _build_members(group_def, region_id)
        self._test_rows: list[_TestRow] = []
        self._flag_rows: list[_FlagRow] = []
        self._value_rows: list[_ValueRow] = []

        group_label = group_def.get("label", "")
        self._expander = Gtk.Expander(label=f"{group_label}  0/{self._boolean_total}")
        self._expander.add_css_class("rdp-cluster-expander")
        self.append(self._expander)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        body.set_margin_start(12)
        body.set_margin_top(4)
        for kind, stem, label, fl, fr, fna, hint in self._members:
            if kind == "boolean":
                kb_entry = kb.get(stem)
                row = _TestRow(stem, label, kb_entry, region_id, on_request_kb)
                self._test_rows.append(row)
                body.append(row)
            elif kind == "flag":
                row = _FlagRow(label, region_id, fna, on_request_kb)
                self._flag_rows.append(row)
                body.append(row)
            else:
                row = _ValueRow(label, hint, fl, fr, fna)
                self._value_rows.append(row)
                body.append(row)

        if self._db_cluster is not None:
            cluster_note = self._db_cluster.get("clinical_interpretation") or ""
        else:
            cluster_note = _cluster_note_for(group_def, kb)
        if cluster_note:
            note_lbl = Gtk.Label(label=cluster_note)
            note_lbl.add_css_class("rdp-cluster-note")
            note_lbl.set_wrap(True)
            note_lbl.set_xalign(0.0)
            note_lbl.set_halign(Gtk.Align.START)
            body.append(note_lbl)

        self._expander.set_child(body)

    def set_tests(self, tests: dict) -> tuple[int, int]:
        """Update rows; return (pos_count, total) for parent to sum. Boolean and
        flag members count toward the tally — value rows (e.g. a ROM measurement)
        are shown for reference but can't be auto-scored pass/fail from free text."""
        pos_count = 0
        for row in self._test_rows:
            l_val = tests.get(f"st_{row.stem}_l")
            r_val = tests.get(f"st_{row.stem}_r")
            row.set_results(l_val, r_val)
            if l_val == "Yes" or r_val == "Yes":
                pos_count += 1
        for row in self._flag_rows:
            row.set_results(tests)
            if tests.get(row.field_id) is True:
                pos_count += 1
        for row in self._value_rows:
            row.set_results(tests)
        group_label = self._group_def.get("label", "")
        self._expander.set_label(f"{group_label}  {pos_count}/{self._boolean_total}")
        return pos_count, self._boolean_total


# ── Regional panel ────────────────────────────────────────────────────────────

class RegionalDifferentialPanel(Gtk.Box):
    """Region-level Gtk.Expander containing cluster-level Gtk.Expanders."""

    def __init__(self, region_id: str, on_request_kb: RequestKBCallback | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.region_id = region_id
        self._blocks: list[_ClusterBlock] = []

        structure = _load_region_structure(region_id)
        extra_clusters = _load_extra_clusters(region_id)
        kb: dict = dict(get_registry()._data.get(region_id, {}))
        all_groups = structure.get("groups", []) + extra_clusters
        self._total_stems = sum(_build_members(g, region_id)[1] for g in all_groups)

        region_label = region_id.capitalize()
        self._expander = Gtk.Expander(label=f"◆ {region_label}  0/{self._total_stems}")
        self._expander.add_css_class("rdp-region-expander")
        self.append(self._expander)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        body.set_margin_start(8)
        body.set_margin_top(4)

        for group in structure.get("groups", []):
            block = _ClusterBlock(group, kb, region_id, on_request_kb)
            self._blocks.append(block)
            body.append(block)

        for group in extra_clusters:
            # extra_clusters have no YAML rows fallback — if the named DB
            # cluster isn't found (typo, or DB unreachable), _build_members
            # returns no members at all. Skip rendering an empty "0/0" block
            # rather than showing a broken-looking group.
            members, _, _ = _build_members(group, region_id)
            if not members:
                continue
            block = _ClusterBlock(group, kb, region_id, on_request_kb)
            self._blocks.append(block)
            body.append(block)

        self._expander.set_child(body)

    def set_tests(self, tests: dict) -> None:
        total_pos = 0
        for block in self._blocks:
            pos, _ = block.set_tests(tests)
            total_pos += pos
        region_label = self.region_id.capitalize()
        self._expander.set_label(f"◆ {region_label}  {total_pos}/{self._total_stems}")
