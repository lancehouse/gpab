"""Active ROM field dictionary for goniometer import — the DEFAULT target.
Only switches to field_dictionary_passive.py's fields when the spoken label
explicitly says "passive" (see matcher.py).

Extracted from objective/sections/yaml/<region>.yaml's `active_movement.groups`
— NOT guessed. Each row's actual stored value is the "Ax" (assessment) column
of a ROMGroupWidget/ROMRow — a free-text GridInput (confirmed: despite the "°"
placeholder it behaves like any other text field, so the same " // " joined-
repeats convention used for Passive fields works here too). The "ReAx"
(re-assessment) column is deliberately never written by this importer — it
carries a real clinical before/after-treatment meaning, not "second capture,"
and per instruction it's being removed from the UI as rarely used anyway.

IMPORTANT — polarity warning: pab's own YAML uses `bilateral: true` to mean
"single midline field, L-only, no R column" (e.g. cervical/lumbar/thoracic
flexion-extension) — the OPPOSITE of what "bilateral" means in the Passive/OP
tables (there, bilateral=True means "both L and R exist"). RomField.bilateral
below is normalized to this codebase's own convention throughout: True always
means "needs a side (L or R)," matching field_dictionary_passive.py. Do not
copy pab's YAML bilateral flags directly without inverting them — this is the
single easiest way to get this dictionary backwards.

Thoracic rotation/flexion/extension exist under THREE separate YAML files
(lumbar.yaml, cervical.yaml, shoulder.yaml — each assessed from a different
regional context). Only the lumbar.yaml copy (tx_flex/tx_ext/tx_rot) is
included as a matchable synonym here — the cervical- and shoulder-embedded
duplicates are deliberately left out to avoid an unresolvable three-way
ambiguity from a label as generic as "thoracic rotation."

Nesting inside _objective.json: data["assessment"][region_id]["active"][field_id].
"""

from __future__ import annotations

from .rom_field import RomField

SECTION_KEY = "active"

_SIDED = "{prefix}_ax_{side}_range"
_UNSIDED = "{prefix}_ax_l_range"  # ROMRow always emits the "_l" slot even for unsided/midline movements


def _f(region: str, movement: str, prefix: str, bilateral: bool, synonyms: tuple[str, ...]) -> RomField:
    return RomField(region, movement, prefix, bilateral, synonyms, _SIDED, _UNSIDED)


ROM_FIELDS: list[RomField] = [
    # ── Ankle ──────────────────────────────────────────────────────────────
    _f("ankle", "dorsiflexion", "ak_df", True, ("ankle", "dorsiflexion", "dorsi flexion")),
    _f("ankle", "plantarflexion", "ak_pf", True, ("ankle", "plantarflexion", "plantar flexion")),
    _f("ankle", "inversion", "ak_inv", True, ("ankle", "inversion")),
    _f("ankle", "eversion", "ak_ev", True, ("ankle", "eversion")),
    _f("ankle", "weight bearing dorsiflexion", "ak_wbdf", True, ("weight bearing", "lunge", "dorsiflexion")),

    # ── Cervical (flexion/extension unsided — whole-spine sagittal movement) ─
    _f("cervical", "flexion", "cx_flex", False, ("cervical", "neck", "flexion")),
    _f("cervical", "extension", "cx_ext", False, ("cervical", "neck", "extension")),
    _f("cervical", "lateral flexion", "cx_lf", True, ("cervical", "neck", "lateral flexion", "side flexion", "side bend")),
    _f("cervical", "rotation", "cx_rot", True, ("cervical", "neck", "rotation")),

    # ── Hip ────────────────────────────────────────────────────────────────
    _f("hip", "flexion", "hp_flex", True, ("hip", "flexion")),
    _f("hip", "extension", "hp_ext", True, ("hip", "extension")),
    _f("hip", "abduction", "hp_abd", True, ("hip", "abduction")),
    _f("hip", "adduction", "hp_add", True, ("hip", "adduction")),
    _f("hip", "internal rotation", "hp_ir", True, ("hip", "internal rotation", "medial rotation")),
    _f("hip", "external rotation", "hp_er", True, ("hip", "external rotation", "lateral rotation")),

    # ── Knee ───────────────────────────────────────────────────────────────
    _f("knee", "flexion", "kn_flex", True, ("knee", "flexion")),
    _f("knee", "extension", "kn_ext", True, ("knee", "extension")),

    # ── Lumbar / Thoracic (flex/ext unsided; rotation + lateral flexion sided) ─
    _f("lumbar", "lumbar flexion", "lx_flex", False, ("lumbar", "lx", "flexion")),
    _f("lumbar", "lumbar extension", "lx_ext", False, ("lumbar", "lx", "extension")),
    _f("lumbar", "lumbar lateral flexion", "lx_lf", True, ("lumbar", "lx", "lateral flexion", "side flexion", "side bend")),
    _f("lumbar", "lumbar rotation", "lx_rot", True, ("lumbar", "lx", "rotation")),
    _f("lumbar", "thoracic flexion", "tx_flex", False, ("thoracic", "tx", "flexion")),
    _f("lumbar", "thoracic extension", "tx_ext", False, ("thoracic", "tx", "extension")),
    _f("lumbar", "thoracic rotation", "tx_rot", True, ("thoracic", "tx", "rotation")),

    # ── Shoulder ───────────────────────────────────────────────────────────
    _f("shoulder", "flexion", "sh_flex", True, ("shoulder", "flexion")),
    _f("shoulder", "extension", "sh_ext", True, ("shoulder", "extension")),
    _f("shoulder", "abduction", "sh_abd", True, ("shoulder", "abduction")),
    _f("shoulder", "internal rotation", "sh_ir", True, ("shoulder", "internal rotation", "medial rotation")),
    _f("shoulder", "external rotation", "sh_er", True, ("shoulder", "external rotation", "lateral rotation")),
    _f("shoulder", "horizontal adduction", "sh_hadd", True, ("shoulder", "horizontal adduction", "horizontal add")),
    _f("shoulder", "hand behind back", "sh_hbb", True, ("hand behind back", "hand bk back")),
]
