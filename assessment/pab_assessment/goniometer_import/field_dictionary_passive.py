"""Passive/OP ROM field dictionary for goniometer import — used only when the
spoken label explicitly says "passive" (see matcher.py). Everyday default is
field_dictionary_active.py instead.

Extracted directly from the *_tables.py OP (overpressure/passive ROM) row
definitions in objective/sections/ — NOT guessed. Only OP rows are included
(not accessory-glide/AC-SC/PAIVM/strength rows): those are joint mobility or
force-grading fields with a different clinical meaning (kg, grade) than a
goniometer angle reading, so importing into them would be a wrong-field match
even if the label text happened to be similar.

Each field's actual stored value lives in a free-text "findings" GridInput
whose id ends in "_txt" (paired with a separate "_norm" CycleButton that this
importer never touches). That "_txt" field is exactly where pab's own UI
already invites clinicians to type multiple values separated by " // "
(placeholder text is literally "findings / //").

Nesting inside _objective.json: data["assessment"][region_id]["passive"][field_id].
"""

from __future__ import annotations

from .rom_field import RomField

SECTION_KEY = "passive"

_SIDED = "{prefix}_{side}_txt"
_UNSIDED = "{prefix}_txt"


def _f(region: str, movement: str, prefix: str, bilateral: bool, synonyms: tuple[str, ...]) -> RomField:
    return RomField(region, movement, prefix, bilateral, synonyms, _SIDED, _UNSIDED)


ROM_FIELDS: list[RomField] = [
    # ── Ankle ──────────────────────────────────────────────────────────────
    _f("ankle", "dorsiflexion", "ak_op_df", True, ("ankle", "dorsiflexion", "dorsi flexion")),
    _f("ankle", "plantarflexion", "ak_op_pf", True, ("ankle", "plantarflexion", "plantar flexion")),
    _f("ankle", "inversion", "ak_op_inv", True, ("ankle", "inversion")),
    _f("ankle", "eversion", "ak_op_ev", True, ("ankle", "eversion")),

    # ── Cervical (flexion/extension unsided — whole-spine sagittal movement) ─
    _f("cervical", "flexion", "cx_op_flex", False, ("cervical", "neck", "flexion")),
    _f("cervical", "extension", "cx_op_ext", False, ("cervical", "neck", "extension")),
    _f("cervical", "lateral flexion", "cx_op_lf", True, ("cervical", "neck", "lateral flexion", "side flexion", "side bend")),
    _f("cervical", "rotation", "cx_op_rot", True, ("cervical", "neck", "rotation")),
    _f("cervical", "quadrant", "cx_op_quad", True, ("cervical", "neck", "quadrant")),

    # ── Hip ────────────────────────────────────────────────────────────────
    _f("hip", "flexion", "hp_op_flex", True, ("hip", "flexion")),
    _f("hip", "extension", "hp_op_ext", True, ("hip", "extension")),
    _f("hip", "abduction", "hp_op_abd", True, ("hip", "abduction")),
    _f("hip", "adduction", "hp_op_add", True, ("hip", "adduction")),
    _f("hip", "internal rotation", "hp_op_ir", True, ("hip", "internal rotation", "medial rotation")),
    _f("hip", "external rotation", "hp_op_er", True, ("hip", "external rotation", "lateral rotation")),

    # ── Knee ───────────────────────────────────────────────────────────────
    _f("knee", "flexion", "kn_op_flex", True, ("knee", "flexion")),
    _f("knee", "extension", "kn_op_ext", True, ("knee", "extension")),

    # ── Lumbar / Thoracic (flex/ext unsided; rotation + lateral flexion sided) ─
    _f("lumbar", "thoracic flexion", "op_tx_flex", False, ("thoracic", "tx", "flexion")),
    _f("lumbar", "thoracic extension", "op_tx_ext", False, ("thoracic", "tx", "extension")),
    _f("lumbar", "thoracic rotation", "op_tx_rot", True, ("thoracic", "tx", "rotation")),
    _f("lumbar", "lumbar flexion", "op_lx_flex", False, ("lumbar", "lx", "flexion")),
    _f("lumbar", "lumbar extension", "op_lx_ext", False, ("lumbar", "lx", "extension")),
    _f("lumbar", "lumbar lateral flexion", "op_lx_lf", True, ("lumbar", "lx", "lateral flexion", "side flexion", "side bend")),

    # ── Shoulder ───────────────────────────────────────────────────────────
    _f("shoulder", "flexion", "sh_op_flex", True, ("shoulder", "flexion")),
    _f("shoulder", "extension", "sh_op_ext", True, ("shoulder", "extension")),
    _f("shoulder", "abduction", "sh_op_abd", True, ("shoulder", "abduction")),
    _f("shoulder", "internal rotation", "sh_op_ir", True, ("shoulder", "internal rotation", "medial rotation")),
    _f("shoulder", "external rotation", "sh_op_er", True, ("shoulder", "external rotation", "lateral rotation")),
    _f("shoulder", "horizontal adduction", "sh_op_hadd", True, ("shoulder", "horizontal adduction", "horizontal add")),
    _f("shoulder", "horizontal abduction", "sh_op_habd", True, ("shoulder", "horizontal abduction", "horizontal abd")),
]
