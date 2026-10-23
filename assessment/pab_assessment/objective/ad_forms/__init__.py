"""AD position-ordered examination forms — backend (no UI imports).

A form is one YAML spec (e.g. ad_lx_sij.yaml, see its header comment for the
cell vocabulary). This module is the only thing that interprets that spec
for data purposes:

  load_form(form_id)        parsed + side-expanded spec (cached)
  own_field_ids(form)       every AD-only field id (the form's own data)
  cell_value(obj, cell)     a cell's saved value from an _objective.json
                            "assessment" block — linked cells read the real
                            gpab field, AD-only cells read obj[data_key]
  tally(form_block, get)    an "n of N tests positive" count (SIJ 3/5)
  report_positions(obj, clean)  rows for storage.py's report renderers
  form_has_data(obj, form)  whether the form was used at all in this session

The GTK tab (assessment_gtk/.../objective/sections/ad_form.py) reads the same
spec through load_form(), so layout, labels and report wording can't drift.
Like storage.py, this stays free of UI imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

_FORMS_DIR = Path(__file__).parent

REGION_IDS = ("shoulder", "lumbar", "cervical", "hip", "knee", "ankle")
REGION_SUBKEYS = ("active", "passive", "muscle", "special")

# Saved alongside the AD-only fields: True once anything in the AD tab has
# been edited (linked or AD-only), so the report only grows an AD section
# for sessions where the AD form was actually used.
TOUCHED_KEY = "ad_touched"


@dataclass(frozen=True)
class Cell:
    link: str | None = None        # "<owner>.<field>" or "<region>.<sub>.<field>"
    id: str | None = None          # AD-only field id
    type: str | None = None        # AD-only: radio | cycle | entry | text | flag
    options: tuple = ()            # AD-only radio/cycle: ((label, variant), ...)
    unit: str = ""
    placeholder: str = ""

    @property
    def field_id(self) -> str:
        return self.id if self.id is not None else parse_path(self.link)[2]


@dataclass
class Row:
    label: str
    cells: list[Cell]
    hint: str = ""
    sides: tuple = ()              # () or ("l", "r"); cells are side-major when set


@dataclass
class Block:
    title: str
    rows: list[Row]
    id: str = ""
    note: str = ""
    wide: bool = False
    column: str = ""               # "left" | "right" — position laid out as two columns
    report: bool = True            # False: tab only, left out of the report
    columns: tuple = ()
    tally: dict | None = None      # {"label", "threshold", "tests": [(name, [paths])]}
    level_grid: dict | None = None  # {"levels", "modalities", "cells": {(mod, lvl, side): Cell}}


@dataclass
class Position:
    id: str
    label: str
    blocks: list[Block]


@dataclass
class Form:
    form_id: str
    data_key: str
    title: str
    report_title: str
    positions: list[Position] = field(default_factory=list)


def parse_path(path: str) -> tuple[str, str | None, str]:
    """"lumbar.special.st_slr_l" -> ("lumbar", "special", "st_slr_l");
    "neurological.nr_knee_l" -> ("neurological", None, "nr_knee_l")."""
    parts = path.split(".")
    if parts[0] in REGION_IDS:
        if len(parts) != 3 or parts[1] not in REGION_SUBKEYS:
            raise ValueError(f"bad region link path: {path!r}")
        return parts[0], parts[1], parts[2]
    if len(parts) != 2:
        raise ValueError(f"bad link path: {path!r}")
    return parts[0], None, parts[1]


def _cell(raw: dict, scales: dict, side: str | None) -> Cell:
    def sub(s):
        return s.replace("{side}", side) if (s and side) else s
    scale = raw.get("scale")
    options = tuple(tuple(o) for o in scales[scale]) if scale else ()
    return Cell(
        link=sub(raw.get("link")), id=sub(raw.get("id")), type=raw.get("type"),
        options=options, unit=raw.get("unit", ""), placeholder=raw.get("placeholder", ""),
    )


def _row(raw: dict, scales: dict) -> Row:
    sides = tuple(raw.get("sides", ()))
    if sides:
        cells = [_cell(c, scales, s) for s in sides for c in raw["cells"]]
    else:
        cells = [_cell(c, scales, None) for c in raw["cells"]]
    return Row(label=raw.get("label", ""), cells=cells, hint=raw.get("hint", ""), sides=sides)


def _level_grid(raw: dict, scales: dict) -> dict:
    options = tuple(tuple(o) for o in scales[raw["scale"]])
    cells = {}
    for mod, _ in raw["modalities"]:
        for lvl, _ in raw["levels"]:
            for side in ("l", "r"):
                fid = raw["id"].format(modality=mod, level=lvl, side=side)
                cells[(mod, lvl, side)] = Cell(id=fid, type="cycle", options=options)
    return {
        "levels": [tuple(x) for x in raw["levels"]],
        "modalities": [tuple(x) for x in raw["modalities"]],
        "cells": cells,
    }


_CACHE: dict[str, Form] = {}


def load_form(form_id: str) -> Form:
    if form_id in _CACHE:
        return _CACHE[form_id]
    spec = yaml.safe_load((_FORMS_DIR / f"{form_id}.yaml").read_text(encoding="utf-8"))
    scales = spec.get("scales", {})
    for name, opts in scales.items():
        # Unquoted Yes/No in YAML parse as booleans — the stored value IS
        # the label, so a non-string label is always a spec bug.
        if not all(isinstance(o[0], str) for o in opts):
            raise ValueError(f"{form_id}.yaml scale {name!r}: quote every option label")
    form = Form(
        form_id=spec["form_id"], data_key=spec["data_key"],
        title=spec["title"], report_title=spec["report_title"],
    )
    for pos in spec["positions"]:
        blocks = []
        for b in pos["blocks"]:
            tally = None
            if "tally" in b:
                t = b["tally"]
                tally = {"label": t["label"], "threshold": t["threshold"],
                         "tests": [(name, list(paths)) for name, paths in t["tests"]]}
            blocks.append(Block(
                title=b["title"], id=b.get("id", ""), note=b.get("note", ""),
                wide=bool(b.get("wide", False)), columns=tuple(b.get("columns", ())),
                column=b.get("column", ""), report=bool(b.get("report", True)),
                rows=[_row(r, scales) for r in b.get("rows", [])],
                tally=tally,
                level_grid=_level_grid(b["level_grid"], scales) if "level_grid" in b else None,
            ))
        # Columns are all-or-nothing per position: a block without one would
        # have nowhere to go in a two-column layout.
        cols = {b.column for b in blocks}
        if cols != {""} and cols - {"left", "right"}:
            raise ValueError(f"{form_id}.yaml position {pos['id']!r}: give every block "
                             f"column: left|right, or none")
        form.positions.append(Position(id=pos["id"], label=pos["label"], blocks=blocks))
    _CACHE[form_id] = form
    return form


def iter_cells(form: Form):
    for pos in form.positions:
        for block in pos.blocks:
            for row in block.rows:
                yield from row.cells
            if block.level_grid:
                yield from block.level_grid["cells"].values()


def own_field_ids(form: Form) -> list[str]:
    seen: list[str] = []
    for c in iter_cells(form):
        if c.id is not None and c.id not in seen:
            seen.append(c.id)
    return seen


def link_paths(form: Form) -> list[str]:
    seen: list[str] = []
    for c in iter_cells(form):
        if c.link is not None and c.link not in seen:
            seen.append(c.link)
    return seen


def path_value(obj: dict, path: str):
    owner, sub, fid = parse_path(path)
    data = obj.get(owner, {}) or {}
    if sub is not None:
        data = data.get(sub, {}) or {}
    return data.get(fid)


def cell_value(obj: dict, form: Form, cell: Cell):
    if cell.link is not None:
        return path_value(obj, cell.link)
    return (obj.get(form.data_key, {}) or {}).get(cell.id)


def form_has_data(obj: dict, form: Form) -> bool:
    own = obj.get(form.data_key, {}) or {}
    if own.get(TOUCHED_KEY):
        return True
    return any(not _empty(own.get(fid)) for fid in own_field_ids(form))


def tally(block: Block, get) -> tuple[int, int, list[str], bool]:
    """(positive, total, positive test names, any answered) for a block's
    tally, `get(path)` returning each linked field's current value. A test
    with two sides counts once if either side is "Yes" — the same rule
    lumbar_tables.sij_report_compat already applies to these tests."""
    t = block.tally
    positive: list[str] = []
    answered = False
    for name, paths in t["tests"]:
        values = [get(p) for p in paths]
        if any(v is not None for v in values):
            answered = True
        if any(v == "Yes" for v in values):
            positive.append(name)
    return len(positive), len(t["tests"]), positive, answered


def tally_text(block: Block, get) -> str:
    n, total, names, _ = tally(block, get)
    status = "met" if n >= block.tally["threshold"] else "not met"
    which = f" ({', '.join(names)})" if names else ""
    return f"{n}/{total}{which} — {block.tally['threshold']}/{total} rule {status}"


# ── report rows ──────────────────────────────────────────────────────────────

def _empty(v) -> bool:
    return v is None or v == [] or (isinstance(v, str) and not v.strip())


def fmt_value(v, unit: str = "") -> str:
    """"" for no value. Newlines are flattened so a multi-line note can't
    break a Markdown/plain-text table row."""
    if _empty(v):
        return ""
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    if isinstance(v, list):
        return " + ".join(str(x) for x in v)
    s = " / ".join(line.strip() for line in str(v).strip().splitlines() if line.strip())
    if unit and not s.endswith(unit.strip()):
        s = f"{s}{unit}"
    return s


def _join(values: list[str]) -> str:
    return " — ".join(v for v in values if v)


def report_positions(obj: dict, form: Form, clean: bool, empty: str) -> list[tuple[str, list[dict]]]:
    """[(position label, [block dict, ...]), ...] in the form's own order.

    Each block dict: {"title", "headers", "rows", "notes", "tally"} — "rows"
    are table rows (lists of str, first column the label), "notes" are
    (label, text) pairs for free-text rows with no label of their own,
    "tally" an optional summary line. `empty` is the renderer's own
    "no value" marker ("—" / "-"). clean=True drops empty rows, blocks and
    positions; otherwise every row is listed with `empty` for no value."""
    out: list[tuple[str, list[dict]]] = []
    for pos in form.positions:
        blocks_out: list[dict] = []
        for block in pos.blocks:
            if not block.report:
                continue
            b = _report_block(obj, form, block, clean, empty)
            if b is not None:
                blocks_out.append(b)
        if blocks_out or not clean:
            out.append((pos.label, blocks_out))
    return out


def _report_block(obj: dict, form: Form, block: Block, clean: bool, empty: str) -> dict | None:
    def val(cell: Cell) -> str:
        return fmt_value(cell_value(obj, form, cell), cell.unit)

    rows: list[list[str]] = []
    notes: list[tuple[str, str]] = []

    if block.level_grid:
        lg = block.level_grid
        headers = ["Level"] + [lbl for _, lbl in lg["modalities"]]
        for lvl, lvl_lbl in lg["levels"]:
            cells = []
            for mod, _ in lg["modalities"]:
                left = val(lg["cells"][(mod, lvl, "l")])
                right = val(lg["cells"][(mod, lvl, "r")])
                cells.append(f"L {left or empty} / R {right or empty}" if (left or right) else "")
            rows.append([lvl_lbl] + cells)
    elif block.columns:
        headers = list(block.columns)
        for row in block.rows:
            rows.append([row.label] + [val(c) for c in row.cells])
    else:
        sided = [r for r in block.rows if r.sides]
        all_sided = bool(block.rows) and len(sided) == len(block.rows)
        headers = ["", "L", "R"] if all_sided else ["", "Finding"]
        for row in block.rows:
            label = f"{row.label} ({row.hint})" if row.hint else row.label
            if row.sides:
                half = len(row.cells) // len(row.sides)
                per_side = [_join([val(c) for c in row.cells[i * half:(i + 1) * half]])
                            for i in range(len(row.sides))]
                if all_sided:
                    rows.append([label] + per_side)
                else:
                    text = " / ".join(f"{s.upper()} {v}" for s, v in zip(row.sides, per_side) if v)
                    rows.append([label, text])
            elif not row.label:
                text = _join([val(c) for c in row.cells])
                if text or not clean:
                    notes.append((block.title, text))
            else:
                rows.append([label, _join([val(c) for c in row.cells])])

    if clean:
        rows = [r for r in rows if any(c for c in r[1:])]
    else:
        rows = [[r[0]] + [c or empty for c in r[1:]] for r in rows]

    tally_line = ""
    if block.tally:
        _, _, _, answered = tally(block, lambda p: path_value(obj, p))
        if answered or not clean:
            tally_line = f"{block.tally['label']}: {tally_text(block, lambda p: path_value(obj, p))}"

    if clean and not rows and not notes and not tally_line:
        return None
    return {"title": block.title, "headers": headers, "rows": rows,
            "notes": notes, "tally": tally_line}
