"""Sensory — 05 Objective Examination.

Dermatomes have moved to 04 Neurological (NeurologicalSection).
This section covers reduced acuity and heightened sensitivity findings.
"""

from textual.app import ComposeResult, on
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Input, Label, Static, TextArea

from ...sections.base import BaseSection
from ...widgets import FlagButton, RadioGroup


# ---------------------------------------------------------------------------
# Gang option sets
# ---------------------------------------------------------------------------

_SEV4 = [("Norm", "success"), ("Mild", "warning"), ("Mod", "error"), ("Sev", "error")]
# 4 × 6 = 24 cols — used for PPT severity


# ---------------------------------------------------------------------------
# Row definitions
# ---------------------------------------------------------------------------

# (display label, data id, has detail Input?)
_HYPO_ITEMS: list[tuple[str, str, bool]] = [
    ("Sharp/blunt (Neuropen)",      "sn_sharp_blunt", True),
    ("Two-point discrimination",    "sn_tpd",         True),
    ("Light touch (hypoaesthesia)", "sn_lt",          True),
    ("Body perception impaired",    "sn_body",        False),
]
_HYPER_ITEMS: list[tuple[str, str, bool]] = [
    ("Static allodynia (monofilament)", "sn_static_allodynia",  True),
    ("Dynamic allodynia (brush)",       "sn_dynamic_allodynia", True),
    ("2° hyperalgesia (algometer)",     "sn_secondary_hyper",   True),
    ("Pin prick hyperalgesia",          "sn_pin_prick",         True),
    ("Cold hyperalgesia (ice 5 s)",     "sn_cold",              True),
    ("Heat hyperalgesia",               "sn_heat",              True),
    ("Temporal summation",              "sn_temporal_sum",      True),
    ("Conditioned pain modulation",     "sn_cpm",               True),
    ("Nerve trunk palpation",           "sn_nerve_palpation",   True),
]


# ---------------------------------------------------------------------------
# SensorySection
# ---------------------------------------------------------------------------

class SensorySection(BaseSection):
    """05 Sensory — reduced acuity and heightened sensitivity findings.

    Dermatomes are assessed in 04 Neurological.
    PPT (pressure pain threshold) is the first entry in Heightened Sensitivity
    and will be linked to objective body-chart findings in a future phase.
    """

    _nav_include_inputs = True  # include Input (detail/value fields) in arrow-key nav

    class FieldChanged(Message):
        pass

    DEFAULT_CSS = """
    SensorySection {
        width: 100%;
        height: auto;
        padding: 0 1 2 1;
    }
    SensorySection .section_title     { text-style: bold; margin-bottom: 0; }


    /* PPT row — label + gang + gap + detail input */
    SensorySection .ppt_row    { layout: horizontal; height: 3; width: 100%; margin-bottom: 0; }
    SensorySection .ppt_lbl    { width: 20; height: 3; content-align: left middle; }
    SensorySection .ppt_gap    { width: 2;  height: 3; }
    SensorySection .ppt_detail { height: 3; width: 1fr; }

    /* Sensory finding rows — FlagButton (≤25%) + optional detail Input (1fr) */
    SensorySection .sn_row     { layout: horizontal; height: 3; width: 100%; margin-bottom: 0; }
    SensorySection FlagButton  { width: 25%; height: 3; min-width: 0; }
    SensorySection .sn_detail  { width: 1fr; height: 3; padding: 0 1; }

    SensorySection TextArea { height: auto; min-height: 2; padding: 0 1; }
    SensorySection Label    { height: auto; margin-top: 0; }
    """

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Label("05 Sensory", classes="section_title")

        # ── Reduced Sensory Acuity ────────────────────────────────────────────
        yield Label("Reduced Sensory Acuity (hyposensitivity)", classes="subsection_header", id="sn_hyposensitivity")
        for label, sid, has_detail in _HYPO_ITEMS:
            with Horizontal(classes="sn_row"):
                yield FlagButton(label, id=sid)
                if has_detail:
                    yield Input(placeholder="region / detail",
                                id=f"{sid}_detail", classes="sn_detail")
            if sid == "sn_body":
                yield TextArea(id="sn_body_detail", language="plain")

        # ── Heightened Sensitivity ────────────────────────────────────────────
        yield Label("Heightened Sensitivity / Central Sensitisation",
                    classes="subsection_header", id="sn_hypersensitivity")

        # PPT — first entry; will link to body-chart findings in future phase
        with Horizontal(classes="ppt_row"):
            yield Static("PPT (algometer)", classes="ppt_lbl")
            yield RadioGroup(_SEV4, id="sn_ppt")
            yield Static("",               classes="ppt_gap")
            yield Input(placeholder="kPa / region / notes",
                        id="sn_ppt_detail", classes="ppt_detail")

        for label, sid, has_detail in _HYPER_ITEMS:
            with Horizontal(classes="sn_row"):
                yield FlagButton(label, id=sid)
                if has_detail:
                    yield Input(placeholder="region / value",
                                id=f"{sid}_detail", classes="sn_detail")

        # ── Notes ─────────────────────────────────────────────────────────────
        yield Label("Notes:")
        yield TextArea(id="sn_notes", language="plain")

    # ------------------------------------------------------------------
    # Field change → autosave
    # ------------------------------------------------------------------

    @on(RadioGroup.Changed)
    @on(FlagButton.Changed)
    @on(Input.Changed, selector="Input")
    @on(TextArea.Changed, selector="TextArea")
    def _on_field_changed(self) -> None:
        if not self._loading:
            self.post_message(self.FieldChanged())

    # ------------------------------------------------------------------
    # collect / load / is_complete
    # ------------------------------------------------------------------

    def collect(self) -> dict:
        data: dict = {}
        # PPT gang
        for rg in self.query(RadioGroup):
            data[rg.id] = rg.value
        # PPT detail input
        try:
            data["sn_ppt_detail"] = self.query_one("#sn_ppt_detail", Input).value
        except Exception:
            data["sn_ppt_detail"] = ""
        # FlagButton findings + detail inputs
        for items in (_HYPO_ITEMS, _HYPER_ITEMS):
            for _, sid, has_detail in items:
                try:
                    data[sid] = self.query_one(f"#{sid}", FlagButton).value
                except Exception:
                    data[sid] = None
                if has_detail:
                    try:
                        data[f"{sid}_detail"] = self.query_one(
                            f"#{sid}_detail", Input).value.strip()
                    except Exception:
                        data[f"{sid}_detail"] = ""
        for fid in ("sn_body_detail", "sn_notes"):
            try:
                data[fid] = self.query_one(f"#{fid}", TextArea).text
            except Exception:
                data[fid] = ""
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            for rg in self.query(RadioGroup):
                rg.set_value(data.get(rg.id))
            try:
                self.query_one("#sn_ppt_detail", Input).value = data.get(
                    "sn_ppt_detail", "")
            except Exception:
                pass
            for items in (_HYPO_ITEMS, _HYPER_ITEMS):
                for _, sid, has_detail in items:
                    try:
                        self.query_one(f"#{sid}", FlagButton).set_value(data.get(sid))
                    except Exception:
                        pass
                    if has_detail:
                        try:
                            self.query_one(f"#{sid}_detail", Input).value = data.get(
                                f"{sid}_detail", "")
                        except Exception:
                            pass
            for fid in ("sn_body_detail", "sn_notes"):
                try:
                    self.query_one(f"#{fid}", TextArea).text = data.get(fid, "")
                except Exception:
                    pass
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        try:
            return self.query_one("#sn_ppt", RadioGroup).value is not None
        except Exception:
            return False
