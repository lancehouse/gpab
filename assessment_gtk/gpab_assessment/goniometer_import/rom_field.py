"""Shared RomField type for both the Active (default) and Passive/OP field
dictionaries. Field-id construction is templated because the two field
families use different suffix conventions (Active: "{prefix}_ax_{side}_range",
Passive: "{prefix}_{side}_txt") — see field_dictionary_active.py /
field_dictionary_passive.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RomField:
    region: str  # region_id as used in REGION_EXTRAS / active_regions, e.g. "shoulder"
    movement: str  # canonical movement key, e.g. "flexion"
    field_prefix: str  # e.g. "sh_flex"
    bilateral: bool  # True = needs a side (L/R); False = single unsided field
    synonyms: tuple[str, ...]
    id_template_sided: str  # "{prefix}" and "{side}" placeholders, e.g. "{prefix}_ax_{side}_range"
    id_template_unsided: str  # "{prefix}" placeholder only, e.g. "{prefix}_ax_l_range"

    def field_id(self, side: str | None) -> str:
        """side is 'l', 'r', or None. Raises if a side is given for a unilateral field or omitted for a bilateral one."""
        if self.bilateral:
            if side not in ("l", "r"):
                raise ValueError(f"{self.region} {self.movement} is bilateral — needs a side")
            return self.id_template_sided.format(prefix=self.field_prefix, side=side)
        if side is not None:
            raise ValueError(f"{self.region} {self.movement} is not sided — side should not be set")
        return self.id_template_unsided.format(prefix=self.field_prefix)
