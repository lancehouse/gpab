"""Load KB YAML files and resolve field IDs to KBEntry objects.

Regions in _DB_BACKED_REGIONS resolve against clinical_kb.db first (see kb_db.py),
falling back to kb/*.yaml only for fields with no DB test mapped yet. Everything
else resolves purely from YAML, unchanged. This is how the cephalad DB rollout
stays incremental: cervical today, more regions added to the set as they're
migrated, no other region's behavior changes until it's added here.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import kb_db

logger = logging.getLogger(__name__)

# Reads the read-only reference clone's kb/*.yaml directly — this app has
# no copy of its own, same pattern as region_section.py's _YAML_DIR.
_KB_DIR = (
    Path(__file__).resolve().parents[3]
    / "assessment" / "pab_assessment" / "objective" / "kb"
)

_STRIP_SUFFIXES = ("_l", "_r", "_left", "_right")

_DB_BACKED_REGIONS = {"cervical", "shoulder"}

# Fields that are DB-resolvable regardless of which region is active — these
# aren't tied to a body-region tab (they're Neurological section UMN signs,
# part of the Cook Myelopathy Cluster), so gating on _DB_BACKED_REGIONS would
# wrongly depend on cervical happening to be one of the clinician's active
# regions. Not every _UMN_ITEMS field is here — only the ones with a DB test
# mapped (see kb_db.load_test_for_field).
#
# Sensory section fields are here for the same reason: pain-sensitisation
# screening (allodynia, hyperalgesia, PPT, CPM, nerve trunk palpation) applies
# regardless of active body region, not to any single region tab.
_GLOBAL_DB_FIELDS = {
    "nr_umn_hoffman", "nr_umn_tromner", "nr_umn_bab",
    "nr_umn_lhermitte", "nr_umn_inv_sup",
    "sn_static_allodynia", "sn_pin_prick", "sn_secondary_hyper",
    "sn_cold", "sn_cpm", "sn_nerve_palpation",
    # Lumbar SIJ Provocation Signs (objective/sections/lumbar_tables.py,
    # moved to Special Tests 2026-08-24) — wired here as individual fields
    # rather than adding "lumbar" to _DB_BACKED_REGIONS, deliberately:
    # lumbar's OTHER special-test fields (st_faber_l/_r) already have a
    # genuine pre-existing DB data-quality issue (two conflicting test rows,
    # different Sn/Sp, mapped to the same field id — test_id 36 vs 68,
    # found while wiring this) that a region-wide flip would have made
    # live/user-visible in an arbitrary way. Flagged to the user, not fixed
    # here — out of scope for the SIJ task. These 10 are all clean, single
    # DB mappings (confirmed 2026-08-24) so wiring just these is safe.
    "sij_sacral", "sij_dist",
    "sij_ptt_l", "sij_ptt_r",
    "sij_comp_l", "sij_comp_r",
    "sij_gaenslen_l", "sij_gaenslen_r",
    "sij_aslr_l", "sij_aslr_r",
    # CRPS section (objective/sections/crps.py) — Budapest/Valencia diagnostic
    # criteria checklist items. Not region-scoped (CRPS is assessed per-limb,
    # independent of which lumbar/cervical/etc. tabs are active), so global
    # like the Sensory/UMN fields above. Added 2026-08-24 with the matching
    # clinical_kb.db test_field_map rows (source/msk_clusters_pab.csv in
    # ~/Projects/kb, standalone tests — no condition/cluster — mirroring the
    # sn_ppt/sn_nerve_palpation pattern), sourced from Goebel et al. 2021
    # PAIN 162:2346-2348 (Valencia consensus, reproducing the Budapest
    # criteria table verbatim).
    "crps_disp_pain", "crps_no_alt_dx",
    "crps_sx_hyperesth", "crps_sx_hyperalg", "crps_sx_allodynia",
    "crps_sx_temp_asymm", "crps_sx_skin_colour", "crps_sx_colour_asymm",
    "crps_sx_oedema", "crps_sx_sweat_chng", "crps_sx_sweat_asymm",
    "crps_sx_rom_dec", "crps_sx_weakness", "crps_sx_tremor",
    "crps_sx_dystonia", "crps_sx_trophic",
    "crps_sg_hyperalg_pp", "crps_sg_allod_lt", "crps_sg_allod_press",
    "crps_sg_allod_jt", "crps_sg_temp_asymm", "crps_sg_skin_colour",
    "crps_sg_colour_asymm", "crps_sg_oedema", "crps_sg_sweat_chng",
    "crps_sg_sweat_asymm", "crps_sg_rom_dec", "crps_sg_weakness",
    "crps_sg_tremor", "crps_sg_dystonia", "crps_sg_trophic",
}


# Sensory's "Pressure Pain Threshold" button (field id sn_secondary_hyper —
# kept as-is for storage.py schema compatibility; it used to be labelled "2°
# hyperalgesia (algometer)") now carries the DB content that used to live
# under the removed sn_ppt severity radio group (test id 173, "Pressure Pain
# Threshold (Algometer)" — also_known_as "Pressure hyperalgesia"). Resolved
# here rather than in clinical_kb.db's test_field_map, since that DB is
# vendored from the separate ~/Projects/kb repo and out of scope to edit.
_FIELD_ALIASES = {"sn_secondary_hyper": "sn_ppt"}


def _bullet_list(text: str) -> str:
    """Reformat a "N sites: a; b; c" sentence as an intro line plus dot
    points, one per semicolon-separated clause — same clinical wording,
    just restructured out of a single run-on sentence for readability."""
    if ":" not in text:
        return text
    intro, _, rest = text.partition(":")
    items = [seg.strip() for seg in rest.split(";") if seg.strip()]
    if len(items) < 2:
        return text
    return intro.strip() + ":\n" + "\n".join(f"• {item}" for item in items)


def is_db_backed_region(region_id: str) -> bool:
    """Public accessor for other modules (e.g. regional_differential.py) that need
    to know whether a region is on the DB-backed rollout — avoids reaching into
    _DB_BACKED_REGIONS directly."""
    return region_id in _DB_BACKED_REGIONS


def is_global_db_field(field_id: str) -> bool:
    """Public accessor for other modules that need to know whether a field id is
    DB-resolvable regardless of active region (see _GLOBAL_DB_FIELDS) — e.g. the
    Regional Differential panel uses this to tell single-sided flag fields (like
    Neurological's UMN signs) apart from bilateral special-test fields."""
    return field_id in _GLOBAL_DB_FIELDS


@dataclass
class KBEntry:
    label: str = ""
    purpose: str = ""
    position: str = ""
    procedure: str = ""
    positive_finding: str = ""  # DB-backed entries only (test.positive_finding);
                                 # YAML-sourced entries have no equivalent column.
    assess: str = ""      # decision-criteria entries (non-test KB)
    sn_sp: str = ""
    variants: str = ""
    cluster: str = ""
    note: str = ""
    image_filename: str = ""  # bare filename (test.image_filename), DB-backed
                               # entries only — resolve via kb_db.resolve_image_path()
                               # before display. Empty for YAML-sourced entries
                               # (added 2026-08-23; YAML KB files have no image
                               # support yet — see kb_panel.py's module docstring).

    def render_lines(self) -> list[str]:
        """Return display lines for the KB panel."""
        lines: list[str] = []
        if self.label:
            lines += [f" {self.label}", "─" * 46]
        if self.purpose:
            lines += ["Purpose:", _wrap(self.purpose.strip(), 44), ""]
        if self.position:
            lines += ["Position:", _wrap(self.position.strip(), 44), ""]
        if self.procedure:
            lines += ["Procedure:", _wrap(self.procedure.strip(), 44), ""]
        if self.positive_finding:
            lines += ["Positive finding:", _wrap(self.positive_finding.strip(), 44), ""]
        if self.assess:
            lines += ["Assess:", _wrap(self.assess.strip(), 44), ""]
        if self.variants:
            lines += ["Variants:", _wrap(self.variants.strip(), 44), ""]
        if self.sn_sp:
            lines += ["Sn / Sp:", f"  {self.sn_sp}", ""]
        if self.cluster:
            lines += ["Cluster:", _wrap(self.cluster.strip(), 44), ""]
        if self.note:
            lines += ["Note:", _wrap(self.note.strip(), 44), ""]
        return lines


def _wrap(text: str, width: int) -> str:
    """Simple word-wrap to `width` chars, returns indented block."""
    words = text.split()
    lines: list[str] = []
    current = "  "
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = "  " + word
        else:
            current = current + (" " if len(current) > 2 else "") + word
    if current.strip():
        lines.append(current)
    return "\n".join(lines)


def _load_yaml_file(path: Path) -> dict[str, KBEntry]:
    """Parse one YAML file into a flat dict of id → KBEntry."""
    entries: dict[str, KBEntry] = {}
    try:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("KB YAML load failed %s: %s", path, e)
        return entries
    for key, data in raw.items():
        if not isinstance(data, dict):
            continue
        entries[key] = KBEntry(
            label=str(data.get("label", key)),
            purpose=str(data.get("purpose", "")),
            position=str(data.get("position", "")),
            procedure=str(data.get("procedure", "")),
            assess=str(data.get("assess", "")),
            sn_sp=str(data.get("sn_sp", "")),
            variants=str(data.get("variants", "")),
            cluster=str(data.get("cluster", "")),
            note=str(data.get("note", "")),
        )
    return entries


def _resolve_from_db(field_id: str) -> KBEntry | None:
    """Resolve a field_id against clinical_kb.db.

    Tries field_id as-is first (global fields like 'nr_umn_hoffman', which
    objective_view.py never strips a prefix from), then 'st_{field_id}' (the
    bilateral special-test convention, called with the 'st_' prefix already
    stripped, e.g. 'spurling_l').

    Returns None on any miss — no DB row for this field, or the DB file isn't
    reachable at all — so the caller falls back to YAML rather than showing
    nothing or crashing. Never fabricates content for an unmapped field.
    """
    db_field_id = _FIELD_ALIASES.get(field_id, field_id)
    try:
        row = kb_db.load_test_for_field(db_field_id)
        if row is None:
            row = kb_db.load_test_for_field(f"st_{db_field_id}")
    except FileNotFoundError:
        return None
    if row is None:
        return None

    stats = kb_db.fmt_snsp(row["sn"], row["sp"])
    lr = kb_db.fmt_lr(row["plr"], row["nlr"])
    sn_sp = "  ".join(p for p in (stats, lr) if p)

    cluster_lines: list[str] = []
    try:
        for c in kb_db.load_clusters_for_test(row["id"]):
            c_lr = kb_db.fmt_lr(c["plr"], c["nlr"])
            suffix = f" ({c_lr})" if c_lr else ""
            cluster_lines.append(f"{c['name']} — {c['condition']}{suffix}")
    except FileNotFoundError:
        pass

    note = row["clinical_notes"] or ""
    if row["pitfalls"]:
        note = f"{note}\nPitfalls: {row['pitfalls']}" if note else f"Pitfalls: {row['pitfalls']}"

    position = row["patient_position"] or ""
    if row["name"] == "Upper Limb Nerve Trunk Palpation":
        position = _bullet_list(position)

    return KBEntry(
        label=row["name"],
        position=position,
        procedure=row["procedure"] or "",
        positive_finding=row["positive_finding"] or "",
        sn_sp=sn_sp,
        cluster="; ".join(cluster_lines),
        note=note,
        image_filename=row["image_filename"] or "",
    )


class KBRegistry:
    """Holds all loaded KB entries, keyed by region then field ID."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, KBEntry]] = {}

    def load_all(self) -> None:
        """Load all YAML files found in the kb/ directory."""
        for yaml_path in sorted(_KB_DIR.glob("*.yaml")):
            region = yaml_path.stem
            self._data[region] = _load_yaml_file(yaml_path)
            logger.debug("KB loaded %s: %d entries", region, len(self._data[region]))

    def resolve_any(self, field_id: str) -> tuple[str, KBEntry] | None:
        """Search all loaded regions for field_id. Returns (region, entry) or None."""
        for region, data in self._data.items():
            if field_id in data:
                return region, data[field_id]
            for suffix in _STRIP_SUFFIXES:
                if field_id.endswith(suffix):
                    stem = field_id[: -len(suffix)]
                    if stem in data:
                        return region, data[stem]
        return None

    def resolve(self, region: str, field_id: str) -> KBEntry | None:
        """Resolve a field_id to a KBEntry for the given region.

        For DB-backed regions (cervical) or globally DB-resolvable fields
        (_GLOBAL_DB_FIELDS — Neurological UMN signs, not region-scoped), tries
        clinical_kb.db first and falls back to YAML for fields with no DB test
        mapped yet (or if the DB file isn't reachable). All other regions
        resolve from YAML only, unchanged.

        YAML lookup tries exact match first, then strips _l/_r suffixes.
        """
        if region in _DB_BACKED_REGIONS or field_id in _GLOBAL_DB_FIELDS:
            db_entry = _resolve_from_db(field_id)
            if db_entry is not None:
                return db_entry

        region_data = self._data.get(region, {})
        if not region_data:
            return None
        if field_id in region_data:
            return region_data[field_id]
        for suffix in _STRIP_SUFFIXES:
            if field_id.endswith(suffix):
                stem = field_id[: -len(suffix)]
                if stem in region_data:
                    return region_data[stem]
        return None


# Module-level singleton — loaded once at startup
_registry: KBRegistry | None = None


def get_registry() -> KBRegistry:
    global _registry
    if _registry is None:
        _registry = KBRegistry()
        _registry.load_all()
    return _registry
