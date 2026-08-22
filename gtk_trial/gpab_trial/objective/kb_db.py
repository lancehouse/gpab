"""Shared read-only access to clinical_kb.db.

DB path search order:
  1. ~/.local/share/pab/clinical_kb.db  (deployed — symlinked to the standalone
     ~/Projects/kb project's build output, so a rebuild there is live here with no
     extra deploy step)
  2. ~/Projects/kb/output/clinical_kb.db (dev fallback, used if the symlink above
     hasn't been set up)

Connection is always read-only (mode=ro). Every query function opens and closes its
own connection — nothing is cached, so callers always see the latest rebuilt DB.

Consumers: kb_db_screen.py (Ctrl+D browser), kb_loader.py (Ctrl+K panel, DB-backed
for the cervical region; other regions still read kb/*.yaml).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_DB_CANDIDATES = [
    Path.home() / ".local/share/pab/clinical_kb.db",
    Path.home() / "Projects/kb/output/clinical_kb.db",
]


def find_db() -> Path | None:
    for p in _DB_CANDIDATES:
        if p.exists():
            return p
    return None


def open_db() -> sqlite3.Connection:
    path = find_db()
    if path is None:
        raise FileNotFoundError(
            "clinical_kb.db not found in ~/.local/share/pab/ or ~/Projects/kb/output/"
        )
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ── Formatting helpers ─────────────────────────────────────────────────────────

def fmt_lr(plr, nlr) -> str:
    parts = []
    if plr is not None:
        parts.append(f"+LR {plr:.2f}")
    if nlr is not None:
        parts.append(f"−LR {nlr:.2f}")
    return "  ".join(parts)


def fmt_snsp(sn, sp) -> str:
    parts = []
    if sn is not None:
        parts.append(f"Sn {sn:.2f}")
    if sp is not None:
        parts.append(f"Sp {sp:.2f}")
    return "  ".join(parts)


# ── Queries ─────────────────────────────────────────────────────────────────────

def load_tests_for_pab_region(pab_region_id: str) -> list[sqlite3.Row]:
    """Tests wired to widget fields for a PAB region's special-tests panel.

    Keyed off test_field_map.pab_json_path, which already matches the JSON paths
    BilateralGridSpecialTestsWidget/SpecialTestsWidget write to _objective.json
    (e.g. 'cervical.special.st_spurling_l'). One row per side (l/r/na).
    """
    conn = open_db()
    try:
        return conn.execute(
            """
            SELECT t.id, t.name, t.also_known_as, t.procedure, t.positive_finding,
                   t.patient_position, t.sn, t.sp, t.plr, t.nlr, t.clinical_notes,
                   t.pitfalls, tfm.pab_field_id, tfm.side, tfm.pab_json_path
            FROM test_field_map tfm
            JOIN test t ON t.id = tfm.test_id
            WHERE tfm.pab_json_path LIKE ?
            ORDER BY tfm.pab_field_id, tfm.side
            """,
            (f"{pab_region_id}.special.%",),
        ).fetchall()
    finally:
        conn.close()


def load_test_for_field(pab_field_id: str) -> sqlite3.Row | None:
    """Single test row (with l/r-specific field mapping) for an exact widget field id
    (e.g. 'st_spurling_l'). Returns None if this field has no DB test mapped yet."""
    conn = open_db()
    try:
        return conn.execute(
            """
            SELECT t.id, t.name, t.also_known_as, t.procedure, t.positive_finding,
                   t.patient_position, t.sn, t.sp, t.plr, t.nlr, t.clinical_notes,
                   t.pitfalls, tfm.pab_field_id, tfm.side
            FROM test_field_map tfm
            JOIN test t ON t.id = tfm.test_id
            WHERE tfm.pab_field_id = ?
            """,
            (pab_field_id,),
        ).fetchone()
    finally:
        conn.close()


def load_cluster_by_name(cluster_name: str, pab_region_id: str) -> dict | None:
    """Full membership of one named DB cluster, for the Regional Differential panel.

    Returns the real cluster composition (via cluster_test), not a YAML layout
    grouping — e.g. for Wainner CPR this includes Cervical Rotation ROM, which
    lives in Active Movement, not the special-tests widget. Each member test
    includes its widget field id(s) if `test_field_map` has one (None if the DB
    tracks this test but no pab widget captures it yet — surfaced as-is so the
    caller can show real coverage gaps rather than hiding them).

    Returns None if no cluster with this exact name exists for this region.
    """
    conn = open_db()
    try:
        cluster = conn.execute(
            """
            SELECT cl.id, cl.name, cl.threshold, cl.sn, cl.sp, cl.plr, cl.nlr,
                   cl.clinical_interpretation, co.name AS condition
            FROM cluster cl
            JOIN condition co ON co.id = cl.condition_id
            WHERE cl.name = ? AND cl.pab_region_id = ?
            """,
            (cluster_name, pab_region_id),
        ).fetchone()
        if cluster is None:
            return None
        test_rows = conn.execute(
            """
            SELECT t.id, t.name, t.positive_finding
            FROM cluster_test ct
            JOIN test t ON t.id = ct.test_id
            WHERE ct.cluster_id = ?
            ORDER BY ct.display_order
            """,
            (cluster["id"],),
        ).fetchall()
        tests = []
        for t in test_rows:
            fields = conn.execute(
                "SELECT pab_field_id, side FROM test_field_map WHERE test_id = ?",
                (t["id"],),
            ).fetchall()
            field_l = next((f["pab_field_id"] for f in fields if f["side"] == "l"), None)
            field_r = next((f["pab_field_id"] for f in fields if f["side"] == "r"), None)
            field_na = next((f["pab_field_id"] for f in fields if f["side"] == "na"), None)
            tests.append({
                "id": t["id"], "name": t["name"], "positive_finding": t["positive_finding"],
                "field_l": field_l, "field_r": field_r, "field_na": field_na,
            })
        return {
            "id": cluster["id"], "name": cluster["name"], "threshold": cluster["threshold"],
            "sn": cluster["sn"], "sp": cluster["sp"], "plr": cluster["plr"], "nlr": cluster["nlr"],
            "clinical_interpretation": cluster["clinical_interpretation"],
            "condition": cluster["condition"], "tests": tests,
        }
    finally:
        conn.close()


def load_clusters_for_test(test_id: int) -> list[sqlite3.Row]:
    """Clusters (CPRs) a test participates in, for contextual display alongside a
    single-test KB lookup."""
    conn = open_db()
    try:
        return conn.execute(
            """
            SELECT cl.name, cl.plr, cl.nlr, co.name AS condition
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
