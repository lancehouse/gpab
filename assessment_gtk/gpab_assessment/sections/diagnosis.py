"""Clinical Impression & ICD-11 Diagnosis — GTK4 port of
pab_assessment/sections/diagnosis.py (CAL-CP walker).

Workup (cal_cp_model.py) is pure data/logic with zero Textual imports — it's
this section's actual source of truth, exactly as in the TUI: collect()/load()
serialize/deserialize Workup objects directly via to_dict()/from_dict(), not
via widget values. That reuse is unchanged here.

What's genuinely simpler in this port, not just stylistically different: the
TUI's rebuild logic (_schedule_rebuild/_rebuild_loop/_schedule_tab_sync) exists
entirely to work around Textual's async mount semantics — a naive rebuild
could be cancelled mid-mutation by a second rebuild request, corrupting the
DOM with no catchable exception (see that file's docstring for the real crash
this caused). GTK has no equivalent hazard: widget construction and
Gtk.Notebook page add/remove are synchronous, so a state change just clears
and rebuilds a workup's page body directly, in-line, with none of that
coalescing-worker machinery.

Deferred, flagged rather than faked:
- Ctrl+K KB-panel push (_push_kb_notes in the TUI) — objective/kb_panel.py
  doesn't exist in this GTK port yet (Phase 4). Notes/appendix/footnote text
  (render_notes_panel) isn't surfaced anywhere yet as a result.
- Cross-reference badges are a no-op here exactly as they are in the TUI
  itself — dropped project-wide in the CAL-CP rebuild, not a gap this port
  introduces.

Rich markup tags ([b]...[/b], [dim]...[/dim] etc.) that the TUI's own
render_hint()/breadcrumb() functions inject are stripped rather than
translated to Pango markup — confirmed via `grep -o '\\[[^]]*\\]'` against
data/cal-cp-trunk.json that no real node text contains square brackets, so
stripping can't eat clinical content. Cosmetic bold/dim emphasis is lost;
the text itself is not.
"""

from __future__ import annotations

import re

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GObject  # noqa: E402

from .. import pab_path_bootstrap  # noqa: F401  (sys.path side effect)
from ..section_base import SectionBase
from ..widgets import TouchEntry
from pab_assessment.cal_cp_model import (  # noqa: E402
    INTRO_FORM, TEMPORAL_PATTERN_OPTIONS, Workup,
    effective_view, is_answerable, render_hint,
)

_TAG_RE = re.compile(r"\[/?\w+\]")

_LINE_RGBA = (0.35, 0.35, 0.38, 0.9)   # flowchart connector lines
_CURVE_RGBA = (0.09, 0.40, 0.75, 1.0)  # temporal-pattern sparkline curves


class BranchConnector(Gtk.DrawingArea):
    """Draws a small flowchart branch: one vertical stem from the parent
    down to a midpoint, then n evenly-spaced branches out to each child's
    x-position and down into it. n=1 draws a plain straight vertical line.
    Purely decorative (Cairo drawing, no interaction) — sits between a node
    box and its children in the lookahead-tree preview, replacing the TUI's
    plain "│" connector characters now that GTK isn't limited to terminal
    cells.
    """

    def __init__(self, n: int = 2, height: int = 26) -> None:
        super().__init__()
        self._n = max(1, n)
        self.set_content_height(height)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, width, height) -> None:
        cr.set_source_rgba(*_LINE_RGBA)
        cr.set_line_width(2)
        cx = width / 2
        if self._n == 1:
            cr.move_to(cx, 0)
            cr.line_to(cx, height)
            cr.stroke()
            return
        mid_y = height * 0.45
        cr.move_to(cx, 0)
        cr.line_to(cx, mid_y)
        cr.stroke()
        for i in range(self._n):
            x = width * (i + 1) / (self._n + 1)
            cr.move_to(cx, mid_y)
            cr.line_to(x, mid_y)
            cr.line_to(x, height)
            cr.stroke()


class _TemporalDiagram(Gtk.DrawingArea):
    """Small schematic pain-intensity-over-time sparkline for one of the p6
    specifier's three standard temporal-pattern categories. Deliberately a
    plain, idealised curve — not real patient data — illustrating each
    option's own definition literally (persistent = flat continuous line;
    recurring = returns fully to a pain-free baseline between episodes;
    persistent with attacks = a continuous elevated baseline with sharper
    spikes on top), the standard shapes used in pain-education material for
    exactly these three ICD-11 CAL-CP categories.
    """

    def __init__(self, kind: str, width: int = 110, height: int = 40) -> None:
        super().__init__()
        self._kind = kind
        self.set_content_width(width)
        self.set_content_height(height)
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, w, h) -> None:
        pad = 5
        x0, x1 = pad, w - pad
        top, bottom = pad, h - pad
        cr.set_line_width(2.2)
        cr.set_source_rgba(*_CURVE_RGBA)

        if self._kind == "persistent":
            y = top + (bottom - top) * 0.5
            cr.move_to(x0, y)
            cr.line_to(x1, y)

        elif self._kind == "recurring":
            n = 3
            seg = (x1 - x0) / n
            cr.move_to(x0, bottom)
            for i in range(n):
                sx = x0 + i * seg
                cr.line_to(sx + seg * 0.15, bottom)
                cr.line_to(sx + seg * 0.5, top)
                cr.line_to(sx + seg * 0.85, bottom)
            cr.line_to(x1, bottom)

        elif self._kind == "persistent_with_attacks":
            baseline = top + (bottom - top) * 0.65
            cr.move_to(x0, baseline)
            for frac in (0.3, 0.65):
                sx = x0 + (x1 - x0) * frac
                cr.line_to(sx - (x1 - x0) * 0.04, baseline)
                cr.line_to(sx, top)
                cr.line_to(sx + (x1 - x0) * 0.04, baseline)
            cr.line_to(x1, baseline)

        cr.stroke()


class _TemporalPatternPicker(Gtk.Box):
    """Exclusive-select picker for the p6 specifier's temporal-pattern field:
    one toggle button per option, each showing its _TemporalDiagram above the
    option label. Kept local to this section (not promoted to widgets.py)
    since the diagram+label card layout is specific to this one CAL-CP field,
    unlike RadioGroup's general chip-gang shape used across many sections.
    """

    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, options: list[dict]) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._options = options
        self._buttons: list[Gtk.ToggleButton] = []
        self._selected: int | None = None

        for opt in options:
            btn = Gtk.ToggleButton()
            btn.add_css_class("dx-temporal-btn")
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            card.append(_TemporalDiagram(opt["value"]))
            lbl = Gtk.Label(label=opt["label"])
            lbl.set_wrap(True)
            lbl.set_justify(Gtk.Justification.CENTER)
            lbl.set_max_width_chars(14)
            card.append(lbl)
            btn.set_child(card)
            btn.connect("toggled", self._on_toggled)
            self._buttons.append(btn)
            self.append(btn)

    @property
    def value(self) -> str | None:
        return self._options[self._selected]["value"] if self._selected is not None else None

    def set_value(self, value: str | None) -> None:
        idx = None
        for i, opt in enumerate(self._options):
            if opt["value"] == value:
                idx = i
                break
        self._select(idx, emit=False)

    def _select(self, idx: int | None, emit: bool = True) -> None:
        self._selected = idx
        for i, btn in enumerate(self._buttons):
            btn.handler_block_by_func(self._on_toggled)
            btn.set_active(i == idx)
            btn.handler_unblock_by_func(self._on_toggled)
        if emit:
            self.emit("changed")

    def _on_toggled(self, btn: Gtk.ToggleButton) -> None:
        idx = self._buttons.index(btn)
        if btn.get_active():
            for i, other in enumerate(self._buttons):
                if other is not btn and other.get_active():
                    other.handler_block_by_func(self._on_toggled)
                    other.set_active(False)
                    other.handler_unblock_by_func(self._on_toggled)
            self._selected = idx
        else:
            self._selected = None
        self.emit("changed")


def _plain(text: str) -> str:
    return _TAG_RE.sub("", text or "")


class DiagnosisSection(Gtk.Box, SectionBase):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None

        self._workups: dict[str, Workup] = {}
        self._counter = 0
        self._legacy_dx: dict = {}
        self._pages: dict[str, Gtk.Box] = {}

        title = Gtk.Label(label="Clinical Impression & ICD-11 Diagnosis")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        ref = Gtk.Label(label="Korwisi et al 2021, PAIN — CAL-CP: ICD-11 Chronic Pain Classification Algorithm")
        ref.add_css_class("reference-note")
        ref.set_halign(Gtk.Align.START)
        self.append(ref)

        add_btn = Gtk.Button(label="+ New workup")
        add_btn.set_halign(Gtk.Align.START)
        add_btn.connect("clicked", self._on_add_workup)
        self.append(add_btn)

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.set_vexpand(True)
        self.append(self.notebook)

        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("save-status")
        self.status_label.set_halign(Gtk.Align.START)
        self.append(self.status_label)

        self._add_workup_model()
        self._sync_notebook()

    # ------------------------------------------------------------------
    # Workup lifecycle
    # ------------------------------------------------------------------

    def _add_workup_model(self) -> str:
        self._counter += 1
        wid = f"w{self._counter}"
        self._workups[wid] = Workup(id=wid, label=f"Site {self._counter}")
        return wid

    def _on_add_workup(self, _btn) -> None:
        wid = self._add_workup_model()
        self._sync_notebook()
        idx = self.notebook.page_num(self._pages[wid])
        self.notebook.set_current_page(idx)
        self._notify_changed()

    def select_workup(self, wid: str) -> None:
        """Switch the notebook to a given workup's tab — used by Ctrl+F
        search jump (search.py's dynamic CAL-CP entries)."""
        page = self._pages.get(wid)
        if page is not None:
            self.notebook.set_current_page(self.notebook.page_num(page))

    def _sync_notebook(self) -> None:
        """Add/remove notebook pages to match self._workups exactly, then
        rebuild every remaining page's body. Called after load() (which may
        replace self._workups wholesale) and after adding a workup."""
        existing = set(self._pages.keys())
        wanted = set(self._workups.keys())

        for wid in existing - wanted:
            page = self._pages.pop(wid)
            idx = self.notebook.page_num(page)
            if idx != -1:
                self.notebook.remove_page(idx)

        for wid in wanted - existing:
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            self._pages[wid] = body
            tab_label = Gtk.Label(label=self._workups[wid].label)
            self.notebook.append_page(body, tab_label)

        for wid in wanted:
            self._rebuild_workup_body(wid)
            self._update_tab_label(wid)

    def _update_tab_label(self, wid: str) -> None:
        w = self._workups.get(wid)
        page = self._pages.get(wid)
        if w is None or page is None:
            return
        text = f"{w.label} · {w.result_summary}" if w.finished else w.label
        self.notebook.set_tab_label_text(page, text)

    # ------------------------------------------------------------------
    # Control — mirrors the TUI's workup_answer/workup_confirm/etc exactly
    # ------------------------------------------------------------------

    def workup_answer(self, wid: str, ans: str) -> None:
        w = self._workups.get(wid)
        if w is None or w.finished or not is_answerable(w.current_node()):
            return
        w.answer(ans)
        self._after_state_change(wid)

    def workup_confirm(self, wid: str) -> None:
        w = self._workups.get(wid)
        if w is None or w.finished or is_answerable(w.current_node()):
            return
        if w.can_continue():
            w.continue_step()
        elif w.can_finish():
            w.finish()
        else:
            return
        self._after_state_change(wid)

    def workup_stop_as_level(self, wid: str) -> None:
        w = self._workups.get(wid)
        if w is None or w.finished:
            return
        if not (w.can_continue() and w.can_finish()):
            return
        w.finish()
        self._after_state_change(wid)

    def workup_go_back(self, wid: str) -> None:
        w = self._workups.get(wid)
        if w is None:
            return
        w.go_back()
        self._after_state_change(wid)

    def apply_click_answers(self, wid: str, answers: list[str]) -> None:
        w = self._workups.get(wid)
        if w is None or w.finished:
            return
        for ans in answers:
            if not is_answerable(w.current_node()):
                return
            w.answer(ans)
        self._after_state_change(wid)

    def _after_state_change(self, wid: str) -> None:
        self._update_tab_label(wid)
        self._notify_changed()
        self._rebuild_workup_body(wid)

    def _notify_changed(self) -> None:
        if self._loading:
            return
        if self._on_changed:
            self._on_changed()

    # ------------------------------------------------------------------
    # Body rendering
    # ------------------------------------------------------------------

    def _clear_box(self, box: Gtk.Box) -> None:
        child = box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    def _rebuild_workup_body(self, wid: str) -> None:
        body = self._pages.get(wid)
        w = self._workups.get(wid)
        if body is None or w is None:
            return
        self._clear_box(body)
        if not w.intro_done:
            self._build_intro(body, wid)
        else:
            self._build_trunk(body, wid)

    def _build_trunk(self, body: Gtk.Box, wid: str) -> None:
        w = self._workups[wid]

        if w.path:
            breadcrumb = Gtk.Label(label=_plain(w.breadcrumb(markup=False)))
            breadcrumb.set_wrap(True)
            breadcrumb.set_halign(Gtk.Align.START)
            breadcrumb.add_css_class("reference-note")
            body.append(breadcrumb)

        if w.finished:
            banner = Gtk.Label(label=f"Result: {w.result_summary}")
            banner.set_wrap(True)
            banner.set_halign(Gtk.Align.START)
            banner.add_css_class("dx-result-banner")
            body.append(banner)

        view = effective_view(w.current_node_id)
        current_text = "\n".join(view["texts"])
        if view.get("criteria"):
            current_text += "\n" + "\n".join(f"• {c}" for c in view["criteria"])

        node_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        node_box.add_css_class("dx-node-box")
        node_box.set_can_focus(True)
        node_box.set_focusable(True)
        node_label = Gtk.Label(label=current_text)
        node_label.set_wrap(True)
        node_label.set_halign(Gtk.Align.START)
        node_label.set_xalign(0.0)
        node_box.append(node_label)
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_node_key, wid)
        node_box.add_controller(key_ctrl)
        body.append(node_box)

        answerable = not w.finished and is_answerable(w.current_node())
        if answerable:
            # Centered so it sits directly above the branch fork's stem
            # (BranchConnector), which is itself centered under this row —
            # visually "Yes/No choice -> fork" rather than left-hugging.
            btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            btn_row.set_halign(Gtk.Align.CENTER)
            yes_btn = Gtk.Button(label="Yes")
            yes_btn.connect("clicked", lambda _b: self.workup_answer(wid, "yes"))
            no_btn = Gtk.Button(label="No")
            no_btn.connect("clicked", lambda _b: self.workup_answer(wid, "no"))
            btn_row.append(yes_btn)
            btn_row.append(no_btn)
            body.append(btn_row)
        elif not w.finished:
            can_c = w.can_continue()
            can_f = w.can_finish()
            btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            if can_c:
                cont_btn = Gtk.Button(label="Continue to next level" if can_f else "Continue")
                cont_btn.connect("clicked", lambda _b: self.workup_confirm(wid))
                btn_row.append(cont_btn)
            if can_f:
                label = "Stop, code as this level" if can_c else "Finish this workup"
                finish_btn = Gtk.Button(label=label)
                finish_btn.connect("clicked", lambda _b: (
                    self.workup_stop_as_level(wid) if can_c else self.workup_confirm(wid)
                ))
                btn_row.append(finish_btn)
            if btn_row.get_first_child() is not None:
                body.append(btn_row)

        if not w.finished and view["kind"] == "decision":
            shown: dict[str, str] = {rid: "current" for rid in view["raw_ids"]}
            body.append(BranchConnector(n=2))
            families_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, homogeneous=True)
            families_row.append(self._build_family(wid, "Yes", view["yes"], shown, "yes"))
            families_row.append(self._build_family(wid, "No", view["no"], shown, "no"))
            body.append(families_row)

        hint = Gtk.Label(label=_plain(render_hint(w)))
        hint.set_wrap(True)
        hint.set_halign(Gtk.Align.START)
        hint.add_css_class("reference-note")
        body.append(hint)

        bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        if w.path:
            back_btn = Gtk.Button(label="◀ Back")
            back_btn.connect("clicked", lambda _b: self.workup_go_back(wid))
            bottom_row.append(back_btn)
        restart_btn = Gtk.Button(label="Restart")
        restart_btn.connect("clicked", lambda _b: self._on_restart(wid))
        bottom_row.append(restart_btn)
        body.append(bottom_row)

        if self._pages.get(wid) is not None:
            idx = self.notebook.page_num(self._pages[wid])
            if idx == self.notebook.get_current_page():
                node_box.grab_focus()

    def _on_restart(self, wid: str) -> None:
        w = self._workups.get(wid)
        if w is None:
            return
        w.restart()
        self._after_state_change(wid)

    def _on_node_key(self, _ctrl, keyval, _keycode, _state, wid: str) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name in ("y", "Y"):
            self.workup_answer(wid, "yes")
            return True
        if name in ("n", "N"):
            self.workup_answer(wid, "no")
            return True
        if name in ("Return", "KP_Enter"):
            self.workup_confirm(wid)
            return True
        if name in ("f", "F"):
            self.workup_stop_as_level(wid)
            return True
        if name == "BackSpace":
            self.workup_go_back(wid)
            return True
        return False

    # ------------------------------------------------------------------
    # Lookahead tree — ported from the TUI's _build_box/_build_family/
    # _build_grandchildren, same algorithm, Gtk widgets instead of Textual.
    # ------------------------------------------------------------------

    def _build_box(
        self, wid: str, rel_label: str, target_id: str, shown: dict[str, str],
        css_class: str, click_answers: list[str] | None = None,
    ) -> tuple[Gtk.Widget, dict]:
        view = effective_view(target_id)
        note = ""
        for rid in view["raw_ids"]:
            if rid in shown:
                note = f"\n(= {shown[rid]}, above)"
                break
        for rid in view["raw_ids"]:
            shown.setdefault(rid, rel_label)
        text = "\n".join(view["texts"])
        if view.get("criteria"):
            text += "\n" + "\n".join(f"• {c}" for c in view["criteria"])
        if view["kind"] == "diagnosis":
            text = "→ Diagnosis:\n" + text
        box_text = f"{rel_label}: {text}{note}"

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class(css_class)
        lbl = Gtk.Label(label=box_text)
        lbl.set_wrap(True)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_xalign(0.0)
        box.append(lbl)
        if click_answers:
            box.add_css_class("clickable")
            click = Gtk.GestureClick()
            click.connect("released", lambda _g, _n, _x, _y: self.apply_click_answers(wid, click_answers))
            box.add_controller(click)
        return box, view

    def _build_grandchildren(self, wid: str, parent_view: dict, shown: dict[str, str], first_answer: str) -> list[Gtk.Widget]:
        if parent_view["kind"] == "decision":
            yb, _ = self._build_box(wid, "Yes", parent_view["yes"], shown, "dx-grandchild-box", click_answers=[first_answer, "yes"])
            nb, _ = self._build_box(wid, "No", parent_view["no"], shown, "dx-grandchild-box", click_answers=[first_answer, "no"])
            return [yb, nb]
        if parent_view["kind"] == "diagnosis":
            msg = "— continues to next level, see next screen —" if parent_view.get("next") \
                else "— diagnosis reached, no further branching —"
        elif parent_view["kind"] == "terminal":
            msg = "— pathway ends here —"
        elif parent_view.get("next"):
            msg = "— continues automatically, see next screen —"
        else:
            msg = "—"
        lbl = Gtk.Label(label=msg)
        lbl.add_css_class("dx-pathway-end")
        lbl.set_wrap(True)
        return [lbl]

    def _build_family(self, wid: str, rel_label: str, target_id: str, shown: dict[str, str], first_answer: str) -> Gtk.Box:
        daughter_box, view = self._build_box(wid, rel_label, target_id, shown, "dx-daughter-box", click_answers=[first_answer])
        children = self._build_grandchildren(wid, view, shown, first_answer)
        family = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        family.append(daughter_box)
        family.append(BranchConnector(n=len(children)))
        grandkids_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, homogeneous=True)
        for c in children:
            grandkids_row.append(c)
        family.append(grandkids_row)
        return family

    # ------------------------------------------------------------------
    # Intro form (p6 chronic pain specifier)
    # ------------------------------------------------------------------

    def _labeled_col(self, label: str, widget: Gtk.Widget) -> Gtk.Box:
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl = Gtk.Label(label=label)
        lbl.add_css_class("field-label")
        lbl.set_halign(Gtk.Align.START)
        col.append(lbl)
        col.append(widget)
        return col

    @staticmethod
    def _nrs_placeholder(field: dict) -> str:
        return f"0={field.get('anchor_low', '')}, 10={field.get('anchor_high', '')}"

    def _build_intro(self, body: Gtk.Box, wid: str) -> None:
        w = self._workups[wid]
        spec = INTRO_FORM.get("chronic_pain_specifier", {})
        fields = {f["id"]: f for f in spec.get("fields", []) if f.get("id")}

        header = Gtk.Label(label="Chronic Pain Specifier (assess separately per pain site)")
        header.add_css_class("field-label")
        header.set_halign(Gtk.Align.START)
        body.append(header)

        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        site_entry = TouchEntry(f"dx_intro_label__{wid}")
        site_entry.text = w.label
        site_entry.connect("changed", self._on_intro_entry_changed, wid, "label")
        row1.append(self._labeled_col("Site label", site_entry))

        onset_entry = TouchEntry(f"dx_intro_onset_date__{wid}", placeholder="MM/YYYY")
        onset_entry.text = w.intro.get("onset_date", "")
        onset_entry.connect("changed", self._on_intro_entry_changed, wid, "onset_date")
        row1.append(self._labeled_col("Onset (MM/YYYY)", onset_entry))
        body.append(row1)

        note = Gtk.Label(label="Pain must be present >3 months to count as chronic.")
        note.add_css_class("reference-note")
        note.set_halign(Gtk.Align.START)
        body.append(note)

        nrs_i = fields.get("nrs_intensity", {})
        distress = fields.get("distress", {})
        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        intensity_entry = TouchEntry(f"dx_intro_nrs_intensity__{wid}", placeholder=self._nrs_placeholder(nrs_i))
        intensity_entry.text = w.intro.get("nrs_intensity", "")
        intensity_entry.connect("changed", self._on_intro_entry_changed, wid, "nrs_intensity")
        row2.append(self._labeled_col("Intensity, last wk (0-10)", intensity_entry))

        distress_entry = TouchEntry(f"dx_intro_distress__{wid}", placeholder=self._nrs_placeholder(distress))
        distress_entry.text = w.intro.get("distress", "")
        distress_entry.connect("changed", self._on_intro_entry_changed, wid, "distress")
        row2.append(self._labeled_col("Distress, last wk (0-10)", distress_entry))
        body.append(row2)

        interference = fields.get("interference", {})
        temporal = fields.get("temporal_pattern", {})
        temporal_options = temporal.get("options") or TEMPORAL_PATTERN_OPTIONS
        row3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        interference_entry = TouchEntry(f"dx_intro_interference__{wid}", placeholder=self._nrs_placeholder(interference))
        interference_entry.text = w.intro.get("interference", "")
        interference_entry.connect("changed", self._on_intro_entry_changed, wid, "interference")
        row3.append(self._labeled_col("Interference, last wk (0-10)", interference_entry))

        temporal_picker = _TemporalPatternPicker(temporal_options)
        temporal_picker.set_value(w.intro.get("temporal_pattern"))
        temporal_picker.connect("changed", self._on_temporal_changed, wid)
        row3.append(self._labeled_col("Temporal pattern", temporal_picker))
        body.append(row3)

        start_btn = Gtk.Button(label="Start decision trunk →")
        start_btn.set_halign(Gtk.Align.START)
        start_btn.connect("clicked", self._on_intro_start, wid)
        body.append(start_btn)

    def _on_intro_entry_changed(self, entry: TouchEntry, wid: str, field_id: str) -> None:
        if self._loading:
            return
        w = self._workups.get(wid)
        if w is None:
            return
        value = entry.text
        if field_id == "label":
            w.label = value or w.label
            self._update_tab_label(wid)
        else:
            w.intro[field_id] = value
        self._notify_changed()

    def _on_temporal_changed(self, picker: "_TemporalPatternPicker", wid: str) -> None:
        if self._loading:
            return
        w = self._workups.get(wid)
        if w is None:
            return
        w.intro["temporal_pattern"] = picker.value
        self._notify_changed()

    def _on_intro_start(self, _btn, wid: str) -> None:
        w = self._workups.get(wid)
        if w is None:
            return
        w.intro_done = True
        self._after_state_change(wid)

    # ------------------------------------------------------------------
    # Cross-reference badges — no-op, matching the TUI exactly (dropped
    # project-wide in the CAL-CP rebuild, not a gap introduced by this port).
    # ------------------------------------------------------------------

    def update_cross_refs(self, assessment: dict | None = None) -> None:
        pass

    # ------------------------------------------------------------------
    # Change events
    # ------------------------------------------------------------------

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def collect(self) -> dict:
        data = {"workups": [w.to_dict() for w in self._workups.values()]}
        if self._legacy_dx:
            data["legacy"] = self._legacy_dx
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            dx = data if isinstance(data, dict) else {}
            workups_data = dx.get("workups")
            if workups_data:
                self._workups = {}
                max_n = 0
                for wd in workups_data:
                    w = Workup.from_dict(wd)
                    self._workups[w.id] = w
                    if w.id.startswith("w") and w.id[1:].isdigit():
                        max_n = max(max_n, int(w.id[1:]))
                self._counter = max_n
            else:
                self._workups = {}
                self._counter = 0
                self._add_workup_model()
            legacy = dx.get("legacy") or {
                k: v for k, v in dx.items() if k not in ("workups", "legacy")
            }
            self._legacy_dx = legacy
            self._sync_notebook()
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        return any(w.finished for w in self._workups.values())

    def focus_first_field(self) -> None:
        self.notebook.grab_focus()
