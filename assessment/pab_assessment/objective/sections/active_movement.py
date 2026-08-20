"""Active Movement section — 02 Objective Examination."""

from textual.app import ComposeResult, on
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Input, Label, Static, TextArea

from ...nav import escape_to_neighbor
from ...sections.base import BaseSection
from ...widgets import GridInput


# ---------------------------------------------------------------------------
# RangeCell — one grid cell: degree input (full width of the data column)
# ---------------------------------------------------------------------------

class RangeCell(Static):
    """Degree ° input, filling the full width of its data column."""

    class Changed(Message):
        pass

    DEFAULT_CSS = """
    RangeCell {
        layout: horizontal;
        height: 3;
        width: 1fr;
        padding: 0;
    }
    RangeCell .rc_input { width: 1fr; height: 3; padding: 0 1; border: solid $panel-lighten-3; }
    RangeCell .rc_input:focus { border: solid $accent; }
    """

    def __init__(self, prefix: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._prefix = prefix

    def compose(self) -> ComposeResult:
        yield GridInput(placeholder="°", id=f"{self._prefix}_range", classes="rc_input")

    def on_input_changed(self, event: Input.Changed) -> None:
        self.post_message(self.Changed())
        event.stop()

    def collect(self) -> dict:
        try:
            rng = self.query_one(f"#{self._prefix}_range", GridInput).value.strip()
        except Exception:
            rng = ""
        return {f"{self._prefix}_range": rng}

    def load(self, data: dict) -> None:
        try:
            self.query_one(f"#{self._prefix}_range", GridInput).value = data.get(f"{self._prefix}_range", "")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ROMRow — one table row: label + up to 4 RangeCells (bilateral rows have 2 empty slots)
# ---------------------------------------------------------------------------

class ROMRow(Static):
    """label | ax_l | ax_r — bilateral movements leave ax_r as an empty placeholder."""

    DEFAULT_CSS = """
    ROMRow { layout: horizontal; height: 3; width: 100%; margin-bottom: 0; }
    ROMRow .col_label { width: 12; height: 3; content-align: left middle; }
    ROMRow .col_cell  { width: 1fr; height: 3; }
    ROMRow .col_empty { width: 1fr; height: 3; }
    """

    def __init__(self, label: str, prefix: str, bilateral: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label     = label
        self._prefix    = prefix
        self._bilateral = bilateral

    def compose(self) -> ComposeResult:
        p = self._prefix
        yield Static(self._label, classes="col_label")
        yield RangeCell(f"{p}_ax_l",   classes="col_cell", id=f"rc_{p}_ax_l")
        if self._bilateral:
            yield Static("", classes="col_empty")
        else:
            yield RangeCell(f"{p}_ax_r",   classes="col_cell", id=f"rc_{p}_ax_r")

    def collect(self) -> dict:
        return {k: v for cell in self.query(RangeCell) for k, v in cell.collect().items()}

    def load(self, data: dict) -> None:
        for cell in self.query(RangeCell):
            cell.load(data)


# ---------------------------------------------------------------------------
# ActiveMovementSection
# ---------------------------------------------------------------------------

class ActiveMovementSection(BaseSection):
    """02 Active Movement — Lumbar + Thoracic ROM tables (Ax/ReAx, L/R) with arrow-key grid navigation."""

    class FieldChanged(Message):
        pass

    # (display label, data prefix, bilateral?)
    _LX_ROWS: list[tuple[str, str, bool]] = [
        ("Flexion",   "lx_flex", True),
        ("Extension", "lx_ext",  True),
        ("Lat Flex",  "lx_lf",   False),
        ("Rotation",  "lx_rot",  False),
    ]
    _TX_ROWS: list[tuple[str, str, bool]] = [
        ("Flexion",   "tx_flex", True),
        ("Extension", "tx_ext",  True),
        ("Rotation",  "tx_rot",  False),
    ]

    DEFAULT_CSS = """
    ActiveMovementSection {
        width: 100%;
        height: auto;
        padding: 0 1 2 1;
    }
    ActiveMovementSection .section_title     { text-style: bold; margin-bottom: 0; }


    /* Two-line Ax/ReAx header — hdr_group uses 2fr to span two 1fr sub-columns */
    ActiveMovementSection .hdr_major  { layout: horizontal; height: 1; width: 100%; color: $text-muted; margin-bottom: 0; }
    ActiveMovementSection .hdr_spacer { width: 12; }
    ActiveMovementSection .hdr_group  { width: 2fr; text-align: center; text-style: bold; }
    ActiveMovementSection .hdr_sub    { layout: horizontal; height: 1; width: 100%; color: $text-muted; margin-bottom: 0; }
    ActiveMovementSection .hdr_lr     { width: 1fr; text-align: center; }

    ActiveMovementSection TextArea { height: auto; min-height: 2; padding: 0 1; }
    ActiveMovementSection Label    { height: auto; margin-top: 0; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._grid:     list[list[str | None]] = []
        self._grid_pos: dict[str, tuple[int, int]] = {}

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def _rom_headers(self) -> ComposeResult:
        with Horizontal(classes="hdr_major"):
            yield Static("",     classes="hdr_spacer")
            yield Static("Ax",   classes="hdr_group")
            yield Static("ReAx", classes="hdr_group")
        with Horizontal(classes="hdr_sub"):
            yield Static("",      classes="hdr_spacer")
            yield Static("Left",  classes="hdr_lr")
            yield Static("Right", classes="hdr_lr")
            yield Static("Left",  classes="hdr_lr")
            yield Static("Right", classes="hdr_lr")

    def compose(self) -> ComposeResult:
        yield Label("02 Active Movement", classes="section_title")

        yield Label("Lumbar ROM", classes="subsection_header", id="am_lumbar")
        yield from self._rom_headers()
        for label, prefix, bilateral in self._LX_ROWS:
            yield ROMRow(label, prefix, bilateral, id=f"row_{prefix}")
        yield Label("Comment:")
        yield TextArea(id="am_lx_notes", language="plain")

        yield Label("Thoracic ROM", classes="subsection_header", id="am_thoracic")
        yield from self._rom_headers()
        for label, prefix, bilateral in self._TX_ROWS:
            yield ROMRow(label, prefix, bilateral, id=f"row_{prefix}")
        yield Label("Comment:")
        yield TextArea(id="am_tx_notes", language="plain")

    # ------------------------------------------------------------------
    # Grid build (after mount so all widgets exist)
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._build_grid()

    def _build_grid(self) -> None:
        """Populate _grid (2-D list of widget IDs) and _grid_pos (ID → row,col)."""
        for row_idx, (_, prefix, bilateral) in enumerate(self._LX_ROWS + self._TX_ROWS):
            if bilateral:
                cols: list[str | None] = [
                    f"{prefix}_ax_l_range",
                    None,
                    f"{prefix}_reax_l_range",
                    None,
                ]
            else:
                cols = [
                    f"{prefix}_ax_l_range",
                    f"{prefix}_ax_r_range",
                    f"{prefix}_reax_l_range",
                    f"{prefix}_reax_r_range",
                ]
            self._grid.append(cols)
            for col_idx, wid in enumerate(cols):
                if wid is not None:
                    self._grid_pos[wid] = (row_idx, col_idx)

    # ------------------------------------------------------------------
    # Grid navigation helpers
    # ------------------------------------------------------------------

    def _walk(self, row: int, col: int, step: int) -> str | None:
        """Walk col in step direction from col, returning the first non-None widget ID."""
        grid_row = self._grid[row]
        c = col
        while 0 <= c < len(grid_row):
            if grid_row[c] is not None:
                return grid_row[c]
            c += step
        return None

    def _focus_nearest(self, row: int, col: int) -> bool:
        """Focus the non-None cell in grid[row] nearest to col. Returns True if focused."""
        if row < 0 or row >= len(self._grid):
            return False
        grid_row = self._grid[row]
        n = len(grid_row)
        col = max(0, min(col, n - 1))
        for offset in range(n):
            for c in [col - offset, col + offset]:
                if 0 <= c < n and grid_row[c] is not None:
                    try:
                        self.query_one(f"#{grid_row[c]}").focus()
                        return True
                    except Exception:
                        pass
        return False

    def _nav(self, direction: str, focused_id: str) -> bool:
        """Navigate within the grid. Returns True if focus moved."""
        if focused_id not in self._grid_pos:
            return False
        row, col = self._grid_pos[focused_id]
        if direction == "up":
            return self._focus_nearest(row - 1, col)
        elif direction == "down":
            return self._focus_nearest(row + 1, col)
        elif direction == "left":
            wid = self._walk(row, col - 1, -1)
            if wid:
                self.query_one(f"#{wid}").focus()
                return True
            return False
        elif direction == "right":
            wid = self._walk(row, col + 1, +1)
            if wid:
                self.query_one(f"#{wid}").focus()
                return True
            return False
        return False

    # GridInput posts Navigate when it hits a boundary; KEY event already stopped by GridInput
    @on(GridInput.Navigate)
    def _on_grid_input_navigate(self, event: GridInput.Navigate) -> None:
        focused = self.app.focused
        if focused is not None:
            if not self._nav(event.direction, focused.id):
                escape_to_neighbor(self, focused, event.direction)
        event.stop()

    # ------------------------------------------------------------------
    # Field change → autosave
    # ------------------------------------------------------------------

    @on(RangeCell.Changed)
    @on(TextArea.Changed, selector="TextArea")
    def _on_field_changed(self) -> None:
        if not self._loading:
            self.post_message(self.FieldChanged())

    # ------------------------------------------------------------------
    # collect / load / is_complete
    # ------------------------------------------------------------------

    def collect(self) -> dict:
        data: dict = {}
        for _, prefix, _ in self._LX_ROWS + self._TX_ROWS:
            try:
                data.update(self.query_one(f"#row_{prefix}", ROMRow).collect())
            except Exception:
                pass
        for fid in ("am_lx_notes", "am_tx_notes"):
            try:
                data[fid] = self.query_one(f"#{fid}", TextArea).text
            except Exception:
                data[fid] = ""
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            for _, prefix, _ in self._LX_ROWS + self._TX_ROWS:
                try:
                    self.query_one(f"#row_{prefix}", ROMRow).load(data)
                except Exception:
                    pass
            for fid in ("am_lx_notes", "am_tx_notes"):
                try:
                    self.query_one(f"#{fid}", TextArea).text = data.get(fid, "")
                except Exception:
                    pass
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        try:
            return bool(self.query_one("#lx_flex_ax_l_range", GridInput).value.strip())
        except Exception:
            return False
