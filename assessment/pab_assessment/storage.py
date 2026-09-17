"""
Session storage — read/write assessment data to session JSON files.

Handles atomic writes via temp file + rename to prevent JSON corruption.
Preserves GTK-owned sections (subjective, objective) while updating
Python-owned assessment block.
"""

import json
import re
import subprocess
import time
import logging
from itertools import zip_longest
from pathlib import Path
from typing import Optional

from .cal_cp_model import Workup as _CalCpWorkup


logger = logging.getLogger(__name__)


def load_assessment(session_file: str) -> dict:
    """
    Load assessment block from session JSON file.

    Returns empty dict if file doesn't exist or can't be parsed.
    """
    path = Path(session_file)
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text())
        return data.get("assessment", {})
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse session file {session_file}: {e}")
        return {}


def save_assessment(session_file: str, assessment: dict) -> bool:
    """
    Merge assessment block into session JSON, preserving all GTK sections.

    Uses atomic write (temp file + rename) to prevent corruption.
    Returns True on success, False on error.
    """
    path = Path(session_file)

    try:
        # Read current file if it exists
        if path.exists():
            data = json.loads(path.read_text())
        else:
            data = {}

        # Update assessment block with timestamp
        if "assessment" not in data:
            data["assessment"] = {}

        data["assessment"].update(assessment)
        data["assessment"]["modified"] = int(time.time())

        # Atomic write: temp file, then rename
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)  # atomic on POSIX

        logger.debug(f"Saved assessment to {session_file}")
        return True

    except Exception as e:
        logger.error(f"Failed to save assessment to {session_file}: {e}")
        return False


def load_session_current() -> Optional[dict]:
    """
    Load the active session pointer from session_current.json.

    Returns None if file doesn't exist or can't be parsed.
    """
    session_current = Path.home() / ".local/share/pab/session_current.json"

    if not session_current.exists():
        return None

    try:
        return json.loads(session_current.read_text())
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse session_current.json: {e}")
        return None


def assessment_path(session_file: str) -> Path:
    """Return the TUI-owned _assessment.json path for a given GTK _session.json path."""
    p = Path(session_file)
    return p.parent / p.name.replace("_session.json", "_assessment.json")


def objective_path(session_file: str) -> Path:
    """Return the Objective TUI-owned _objective.json path for a given _session.json path."""
    p = Path(session_file)
    return p.parent / p.name.replace("_session.json", "_objective.json")


def load_objective(session_file: str) -> dict:
    """Load objective data from _objective.json. Returns empty dict if absent."""
    path = objective_path(session_file)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse objective file {path}: {e}")
        return {}


def save_objective(
    session_file: str,
    assessment: dict,
    sections_complete: dict[str, bool],
) -> bool:
    """Save all objective sections to _objective.json atomically."""
    path = objective_path(session_file)
    try:
        data = json.loads(path.read_text()) if path.exists() else {}

        if "assessment" not in data:
            data["assessment"] = {}
        for key, val in assessment.items():
            data["assessment"][key] = val
        data["assessment"]["modified"] = int(time.time())

        # Purge stale flat-schema keys once the new region schema is present
        if "active_regions" in data["assessment"]:
            for _stale in ("active", "passive", "muscle"):
                data["assessment"].pop(_stale, None)

        if "sections_complete" not in data:
            data["sections_complete"] = {}
        for section_id, complete in sections_complete.items():
            data["sections_complete"][section_id] = complete

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)

        logger.debug(f"Saved objective to {path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save objective to {path}: {e}")
        return False


def write_objective_pid(pid: int) -> None:
    """Write the Objective TUI process PID into session_current.json."""
    path = Path.home() / ".local/share/pab/session_current.json"
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
        data["objective_pid"] = pid
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)
    except Exception as e:
        logger.warning(f"write_objective_pid: {e}")


def read_objective_pid() -> int | None:
    """Read the Objective TUI PID from session_current.json."""
    path = Path.home() / ".local/share/pab/session_current.json"
    try:
        data = json.loads(path.read_text())
        pid = data.get("objective_pid")
        return int(pid) if pid else None
    except Exception:
        return None


def get_objective_sections_complete(session_file: str) -> dict[str, bool]:
    """Read sections_complete from _objective.json."""
    path = objective_path(session_file)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data.get("sections_complete", {})
    except Exception:
        return {}


def count_objective_complete_sections(session_file: str) -> int:
    """Count how many objective sections are marked complete in _objective.json."""
    sections = get_objective_sections_complete(session_file)
    return sum(1 for v in sections.values() if v)


def list_sessions() -> list[dict]:
    """
    List all assessment sessions from GTK storage directory.

    Returns list of session dicts with: path, patient_id, session_label,
    date, regions, body_chart_data, sections_complete
    """
    sessions = []
    physio_root = Path.home() / "Physio-Bodychart"

    if not physio_root.exists():
        return sessions

    # Scan all session directories
    for session_dir in sorted(physio_root.iterdir(), reverse=True):
        if not session_dir.is_dir():
            continue

        # Look for session.json in this directory
        session_file = session_dir / f"{session_dir.name}_session.json"
        if not session_file.exists():
            continue

        try:
            data = json.loads(session_file.read_text())

            # Merge TUI assessment data from separate _assessment.json if present
            assess_p = assessment_path(str(session_file))
            if assess_p.exists():
                try:
                    assess_data = json.loads(assess_p.read_text())
                    data["assessment"] = assess_data.get("assessment", data.get("assessment", {}))
                    data["sections_complete"] = assess_data.get("sections_complete", {})
                    data["sections_last_modified"] = assess_data.get("sections_last_modified", {})
                except Exception:
                    pass

            # Extract session metadata
            session = {
                "path": str(session_file),
                "patient_id": data.get("patient_id", "XX"),
                "session_label": data.get("session_label", ""),
                "date": data.get("date") or data.get("created", 0),
                "regions": data.get("regions", []),
                "body_chart_data": bool(
                    data.get("subjective", {}).get("strokes") or
                    data.get("subjective", {}).get("notes") or
                    data.get("objective", {}).get("zones") or
                    data.get("objective", {}).get("points")
                ),
                "sections_complete": sum(1 for v in data.get("sections_complete", {}).values() if v),
                "obj_sections_complete": count_objective_complete_sections(str(session_file)),
            }
            sessions.append(session)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to read session {session_file}: {e}")
            continue

    return sessions


def write_tui_pid(pid: int) -> None:
    """Write the TUI process PID into session_current.json."""
    path = Path.home() / ".local/share/pab/session_current.json"
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
        data["tui_pid"] = pid
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)
    except Exception as e:
        logger.warning(f"write_tui_pid: {e}")


def clear_tui_pid() -> None:
    """Remove tui_pid from session_current.json on clean TUI exit."""
    path = Path.home() / ".local/share/pab/session_current.json"
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
        data.pop("tui_pid", None)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)
    except Exception as e:
        logger.warning(f"clear_tui_pid: {e}")


def read_gtk_pid() -> int | None:
    """Read the GTK process PID from session_current.json. Returns None if absent."""
    path = Path.home() / ".local/share/pab/session_current.json"
    try:
        data = json.loads(path.read_text())
        pid = data.get("gtk_pid")
        return int(pid) if pid else None
    except Exception:
        return None



def focus_signal_path(session_file: str, target: str) -> Path:
    """Return path to a focus signal file (.focus_gtk or .focus_tui) in the session dir."""
    return Path(session_file).parent / f".focus_{target}"


def write_focus_signal(session_file: str, target: str) -> None:
    """Write a focus signal file. The other app watches for this and raises its window."""
    try:
        focus_signal_path(session_file, target).touch()
    except Exception as e:
        logger.warning(f"write_focus_signal({target}): {e}")


# ---------------------------------------------------------------------------
# Session report export
# ---------------------------------------------------------------------------

# Markdown heading level offset for *_report.md / *_clean.md.
# 0 = original sizes (H1/H2/H3/H4).
# 1 = one level smaller (H2/H3/H4/H5) — current setting.
# Change back to 0 to restore original heading sizes.
_MD_H_OFFSET: int = 1


def _shift_md_heading(line: str, offset: int) -> str:
    """Shift a Markdown heading down by `offset` levels (caps at H6)."""
    if not line.startswith('#'):
        return line
    i = 0
    while i < len(line) and line[i] == '#':
        i += 1
    if i < len(line) and line[i] == ' ':   # only valid headings (must have space)
        return '#' * min(i + offset, 6) + line[i:]
    return line


def _yn(val) -> str:
    if val is True:  return "Yes"
    if val is False: return "No"
    return ""


def _row(*pairs) -> str:
    """Format key-value pairs on one line, skipping empty values."""
    parts = [f"**{k}:** {v}" for k, v in pairs if v not in (None, "", [])]
    return "  ".join(parts) if parts else ""


# ─────────────────────────────────────────────────────────────────────────────
# Objective section report rendering
# ─────────────────────────────────────────────────────────────────────────────

def _md_table(headers: list, rows: list) -> list:
    """Return Markdown table as a list of strings. Returns [] when all value cols are blank."""
    if not rows:
        return []
    n = len(headers)
    rows = [[str(r[i]) if i < len(r) else "" for i in range(n)] for r in rows]
    col_w = [len(str(headers[i])) for i in range(n)]
    for r in rows:
        for i, v in enumerate(r):
            col_w[i] = max(col_w[i], len(v))
    # Separator widths control pandoc's proportional column allocation in DOCX.
    # Cap at 40 so very long cells don't steal all the width from label columns;
    # floor at 15 so short-label columns (Aspect, Denies, etc.) get a fair share.
    sep_w = [max(min(w, 40), 20) for w in col_w]
    def _fmt(cells):
        return "| " + " | ".join(str(v).ljust(col_w[i]) for i, v in enumerate(cells)) + " |"
    sep = "| " + " | ".join("-" * w for w in sep_w) + " |"
    return [_fmt(headers), sep] + [_fmt(r) for r in rows]


def _raw_table(headers: list, rows: list) -> list:
    """Return fixed-width plain-text table lines."""
    if not rows:
        return []
    n = len(headers)
    rows = [[str(r[i]) if i < len(r) else "" for i in range(n)] for r in rows]
    col_w = [len(str(headers[i])) for i in range(n)]
    for r in rows:
        for i, v in enumerate(r):
            col_w[i] = max(col_w[i], len(v))
    def _fmt(cells, sep=" | "):
        return "  " + sep.join(str(v).ljust(col_w[i]) for i, v in enumerate(cells))
    divider = "  " + "-+-".join("-" * w for w in col_w)
    return [_fmt(headers), divider] + [_fmt(r) for r in rows]


# All body-region ids ever used as a top-level key under assessment[region_id]
# — duplicated here rather than imported from objective/sections/ because
# storage.py must stay free of UI imports (CLAUDE.md: "No UI logic in
# storage"). Used only for defensive inclusion in _merged_region_data below;
# if a new region is added and this list isn't updated, the worst case is
# that region's report inclusion falls back to being active_regions-gated
# only (the old behavior), not a new failure mode.
_KNOWN_REGION_IDS = ("shoulder", "lumbar", "cervical", "hip", "knee", "ankle")


def _merged_region_data(obj: dict, active_regions) -> tuple[dict, dict, dict, dict]:
    """Merges active/passive/muscle/special dicts across every region that's
    either currently active OR simply has data recorded under it.

    Data-purity fix: a region toggled off in the UI *after* data was entered
    (or never marked active for some other reason) must not make that data
    silently vanish from every report output — previously this only walked
    obj.get("active_regions", []), so a deactivated-but-populated region's
    entire ROM table (not just one field) disappeared from every report with
    no indication anything was omitted.
    """
    region_ids = set(active_regions or []) | (set(_KNOWN_REGION_IDS) & set(obj.keys()))
    act: dict = {}
    pas: dict = {}
    mus: dict = {}
    spl: dict = {}
    for rid in region_ids:
        rdata = obj.get(rid, {}) or {}
        act.update(rdata.get("active", {}) or {})
        pas.update(rdata.get("passive", {}) or {})
        mus.update(rdata.get("muscle", {}) or {})
        spl.update(rdata.get("special", {}) or {})
    return act, pas, mus, spl


def _render_objective_md(obj: dict, clean: bool = False) -> list:
    """Render all objective sections as Markdown.

    clean=False: all fields shown; empty values shown as — / *(not answered)*.
    clean=True: only sections/tables/rows with real data are included.
    """
    lines: list = []

    gen  = obj.get("general",      {}) or {}
    neu  = obj.get("neurological", {}) or {}
    sen  = obj.get("sensory",      {}) or {}
    func = obj.get("functional",   {}) or {}
    crps = obj.get("crps",         {}) or {}

    # Support both old flat schema and new region-based schema
    active_regions = obj.get("active_regions")
    if active_regions is not None:
        act, pas, mus, spl = _merged_region_data(obj, active_regions)
    else:
        act  = obj.get("active",  {}) or {}
        pas  = obj.get("passive", {}) or {}
        mus  = obj.get("muscle",  {}) or {}
        spl  = {}

    if not any([gen, act, pas, neu, sen, mus, func, spl, crps]):
        return []

    # ── clean-mode helpers ────────────────────────────────────────────────────

    _EMPTY = frozenset(["—", "*(not answered)*", "*(not recorded)*", "*(empty)*", ""])

    def _nodata(v) -> bool:
        return v is None or str(v).strip() in _EMPTY

    def _filter_rows(rows: list, data_from: int = 1) -> list:
        if not clean:
            return rows
        return [r for r in rows if not all(_nodata(c) for c in r[data_from:])]

    def _maybe_table(sl: list, title: str, headers: list, rows: list, data_from: int = 1) -> None:
        rows = _filter_rows(rows, data_from)
        if not rows:
            return
        if clean and sl and sl[-1] != "":
            sl.append("")
        if title:
            sl.append(f"#### {title}")
        sl.extend(_md_table(headers, rows))
        if clean:
            sl.append("")

    def _maybe_note(sl: list, lbl: str, v: str) -> None:
        if v:
            # Data-purity fix: embedded "\n"s used to be joined straight into
            # the output list, which CommonMark then renders as a *soft*
            # break (collapses to a space) — a clinician's multi-paragraph
            # note visually merged into one run-on paragraph in every
            # Markdown/docx report, in both clean and full mode. Each line
            # but the last now gets the standard Markdown hard-break marker
            # (two trailing spaces) so the line breaks the practitioner
            # actually typed survive rendering.
            note_lines = v.split("\n")
            last = len(note_lines) - 1
            sl.append(f"{lbl}: {note_lines[0]}" + ("  " if last > 0 else ""))
            for i, extra in enumerate(note_lines[1:], start=1):
                sl.append(extra + ("" if i == last else "  "))
            if clean:
                sl.append("")
        elif not clean:
            sl.append(f"{lbl}: *(empty)*")

    def _flush_section(header: str, sl: list) -> None:
        if sl:
            if clean:
                header = re.sub(r'^(#{1,3})\s*\d{2}\s+', r'\1 ', header)
            lines.append(header)
            lines.extend(sl)
            lines.append("")

    # ── 01 General Observation ────────────────────────────────────────────────
    if gen:
        sl: list[str] = []
        _maybe_note(sl, "*General observations*", gen.get("go_general_notes", "").strip())
        _maybe_note(sl, "*General mobility*", gen.get("go_transfer_cmt", "").strip())
        _posture_def = [("Lumbar lordosis","go_lx_lord"),("Thoracic kyphosis","go_tx_kyph"),
                        ("Antalgic lean","go_lean"),("Sway posture","go_sway"),
                        ("Breathing","go_breath"),("Scapular L","go_scap_l"),
                        ("Scapular R","go_scap_r"),("Muscle wasting","go_wasting")]
        posture_rows = []
        for lbl, key in _posture_def:
            raw = gen.get(key)
            if key == "go_lean" and isinstance(raw, list):
                v = " + ".join(raw) if raw else "—"
            else:
                v = raw or "—"
            cmt = gen.get(f"{key}_cmt", "").strip()
            posture_rows.append([lbl, f"{v} — {cmt}" if cmt else v])
        _maybe_table(sl, "Posture", ["", "Finding"], posture_rows)
        _maybe_note(sl, "*Posture notes*", gen.get("go_posture_notes", "").strip())
        _flush_section("### 01 General Observation", sl)

    # ── 02 Active Movement ────────────────────────────────────────────────────
    if act:
        sl = []
        lx_rows_def = [("Flexion","lx_flex",True),("Extension","lx_ext",True),
                       ("Lat Flex","lx_lf",False),("Rotation","lx_rot",False)]
        tx_rows_def = [("Flexion","tx_flex",True),("Extension","tx_ext",True),
                       ("Rotation","tx_rot",False)]
        for title, rows_def in [("Lumbar ROM", lx_rows_def), ("Thoracic ROM", tx_rows_def)]:
            tbl_rows = []
            for label, prefix, bilateral in rows_def:
                def _cell(p, s):
                    v   = act.get(f"{p}_{s}_range", "") or ""
                    txt = f"{v}°" if v else "—"
                    return txt
                ax_l = _cell(prefix, "ax_l")
                if bilateral:
                    tbl_rows.append([label, ax_l, "—"])
                else:
                    ax_r = _cell(prefix, "ax_r")
                    tbl_rows.append([label, ax_l, ax_r])
            _maybe_table(sl, title, ["", "Ax L", "Ax R"], tbl_rows)
        for key, lbl in [("am_lx_notes","*Lumbar notes*"),("am_tx_notes","*Thoracic notes*")]:
            _maybe_note(sl, lbl, act.get(key, "").strip())
        if any(k.startswith("cx_") or k.startswith("tx_cx_") for k in act):
            def _cx_cell(p, s):
                v  = act.get(f"{p}_{s}_range","") or ""
                txt = f"{v}°" if v else "—"
                return txt
            for cx_title, cx_rows_def in [
                ("Cervical ROM", [("Flexion","cx_flex",True),("Extension","cx_ext",True),
                                  ("Lat Flex","cx_lf",False),("Rotation","cx_rot",False)]),
                ("Thoracic ROM (Cx)", [("Flexion","tx_cx_flex",True),("Extension","tx_cx_ext",True),
                                       ("Rotation","tx_cx_rot",False)]),
            ]:
                cx_tbl = []
                for cx_lbl, cx_pfx, cx_bil in cx_rows_def:
                    ax_l = _cx_cell(cx_pfx,"ax_l")
                    if cx_bil:
                        cx_tbl.append([cx_lbl, ax_l, "—"])
                    else:
                        cx_tbl.append([cx_lbl, ax_l, _cx_cell(cx_pfx,"ax_r")])
                _maybe_table(sl, cx_title, ["","Ax L","Ax R"], cx_tbl)
            for key, lbl in [("am_cx_notes","*Cervical notes*"),
                              ("am_tx_cx_notes","*Thoracic (Cx) notes*")]:
                _maybe_note(sl, lbl, act.get(key, "").strip())
        if any(k.startswith("sh_") or k.startswith("tx_sh_") for k in act):
            def _sh_cell(p, s):
                v  = act.get(f"{p}_{s}_range", "") or ""
                txt = f"{v}°" if v else "—"
                return txt
            sh_rom_def = [("Flexion","sh_flex"),("Extension","sh_ext"),
                          ("Abduction","sh_abd"),("Int Rotation","sh_ir"),
                          ("Ext Rotation","sh_er"),("Horiz Add","sh_hadd"),
                          ("Hand Bk Back","sh_hbb")]
            sh_tbl = [[lbl, _sh_cell(p,"ax_l"), _sh_cell(p,"ax_r")]
                      for lbl, p in sh_rom_def]
            _maybe_table(sl, "Shoulder ROM", ["","Ax L","Ax R"], sh_tbl)
            tx_sh_def = [("Flexion","tx_sh_flex",True),("Extension","tx_sh_ext",True),
                         ("Rotation","tx_sh_rot",False)]
            tx_sh_tbl = []
            for sh_lbl, sh_pfx, sh_bil in tx_sh_def:
                ax_l = _sh_cell(sh_pfx,"ax_l")
                if sh_bil:
                    tx_sh_tbl.append([sh_lbl, ax_l, "—"])
                else:
                    tx_sh_tbl.append([sh_lbl, ax_l, _sh_cell(sh_pfx,"ax_r")])
            _maybe_table(sl, "Thoracic ROM (Sh)", ["","Ax L","Ax R"], tx_sh_tbl)
            for key, lbl in [("am_sh_notes","*Shoulder notes*"),
                              ("am_tx_sh_notes","*Thoracic (Sh) notes*")]:
                _maybe_note(sl, lbl, act.get(key, "").strip())
        if any(k.startswith("hp_") for k in act):
            def _hp_cell(p, s):
                v  = act.get(f"{p}_{s}_range", "") or ""
                txt = f"{v}°" if v else "—"
                return txt
            hp_rom_def = [("Flexion","hp_flex"),("Extension","hp_ext"),
                          ("Abduction","hp_abd"),("Adduction","hp_add"),
                          ("Int Rotation","hp_ir"),("Ext Rotation","hp_er")]
            hp_tbl = [[lbl, _hp_cell(p,"ax_l"), _hp_cell(p,"ax_r")]
                      for lbl, p in hp_rom_def]
            _maybe_table(sl, "Hip ROM", ["","Ax L","Ax R"], hp_tbl)
            _maybe_note(sl, "*Hip notes*", act.get("am_hp_notes", "").strip())
        if any(k.startswith("kn_") for k in act):
            def _kn_cell(p, s):
                v  = act.get(f"{p}_{s}_range", "") or ""
                txt = f"{v}°" if v else "—"
                return txt
            kn_rom_def = [("Flexion","kn_flex"),("Extension","kn_ext")]
            kn_tbl = [[lbl, _kn_cell(p,"ax_l"), _kn_cell(p,"ax_r")]
                      for lbl, p in kn_rom_def]
            _maybe_table(sl, "Knee ROM", ["","Ax L","Ax R"], kn_tbl)
            _maybe_note(sl, "*Knee notes*", act.get("am_kn_notes", "").strip())
        if any(k.startswith("ak_") for k in act):
            def _ak_cell(p, s):
                v  = act.get(f"{p}_{s}_range", "") or ""
                txt = f"{v}°" if v else "—"
                return txt
            ak_rom_def = [("Dorsiflexion","ak_df"),("Plantarflexion","ak_pf"),
                          ("Inversion","ak_inv"),("Eversion","ak_ev"),
                          ("WB DF (lunge)","ak_wbdf")]
            ak_tbl = [[lbl, _ak_cell(p,"ax_l"), _ak_cell(p,"ax_r")]
                      for lbl, p in ak_rom_def]
            _maybe_table(sl, "Ankle ROM", ["","Ax L","Ax R"], ak_tbl)
            _maybe_note(sl, "*Ankle notes*", act.get("am_ak_notes", "").strip())
        _flush_section("### 02 Active Movement", sl)

    # ── 03 Passive Movement ───────────────────────────────────────────────────
    def _fmt_pas(norm: str | None, txt: str | None) -> str:
        n = norm == "Norm"
        t = (txt or "").strip()
        if n and t:
            return f"Normal; {t}"
        if n:
            return "Normal"
        return t or "—"

    def _bi_pas(p: str, d: dict) -> str | None:
        l = _fmt_pas(d.get(f"{p}_l_norm"), d.get(f"{p}_l_txt"))
        r = _fmt_pas(d.get(f"{p}_r_norm"), d.get(f"{p}_r_txt"))
        if l == "—" and r == "—":
            return None
        return f"L: {l} / R: {r}"

    if pas:
        sl = []
        # (label, prefix, bilateral)
        _lx_op = [("Tx Flexion","op_tx_flex",False),("Tx Extension","op_tx_ext",False),
                  ("Tx Rotation","op_tx_rot",True),
                  ("Lx Flexion","op_lx_flex",False),("Lx Extension","op_lx_ext",False),
                  ("Lx Lat Flex","op_lx_lf",True)]
        op_rows = [[lbl, _bi_pas(p, pas) if bi else _fmt_pas(pas.get(f"{p}_norm"), pas.get(f"{p}_txt"))]
                   for lbl, p, bi in _lx_op]
        _maybe_table(sl, "Overpressure", ["Movement", "Findings"], op_rows)
        paivm_levels = ["T8","T9","T10","T11","T12","L1","L2","L3","L4","L5"]
        paivm_rows = [[lv,
                       _fmt_pas(pas.get(f"pm_{lv}_l_norm"), None),
                       _fmt_pas(pas.get(f"pm_{lv}_c_norm"), None),
                       _fmt_pas(pas.get(f"pm_{lv}_r_norm"), None),
                       (pas.get(f"pm_{lv}_txt") or "").strip() or "—"]
                      for lv in paivm_levels]
        _maybe_table(sl, "PAIVMs", ["Level", "L", "C", "R", "Notes"], paivm_rows)
        for key, lbl in [("pm_op_notes","*OP notes*"),("pm_paivm_notes","*PAIVM notes*")]:
            _maybe_note(sl, lbl, pas.get(key, "").strip())
        if any(k.startswith("cx_op_") or k.startswith("cx_pm_") for k in pas):
            _cx_op = [("Flexion","cx_op_flex",False),("Extension","cx_op_ext",False),
                      ("Lat Flex","cx_op_lf",True),("Rotation","cx_op_rot",True),
                      ("Quadrant","cx_op_quad",True)]
            cx_op_rows = [[lbl, _bi_pas(p, pas) if bi else _fmt_pas(pas.get(f"{p}_norm"), pas.get(f"{p}_txt"))]
                          for lbl, p, bi in _cx_op]
            _maybe_table(sl, "Cervical OP", ["Movement","Findings"], cx_op_rows)
            cx_paivm_levels = [("C0/1","C0_1"),("C1/2","C1_2"),("C2","C2"),("C3","C3"),
                               ("C4","C4"),("C5","C5"),("C6","C6"),("C7","C7"),
                               ("T1","T1"),("T2","T2"),("T3","T3"),("T4","T4")]
            cx_paivm_rows = [[lv,
                               _fmt_pas(pas.get(f"cx_pm_{k}_l_norm"), None),
                               _fmt_pas(pas.get(f"cx_pm_{k}_c_norm"), None),
                               _fmt_pas(pas.get(f"cx_pm_{k}_r_norm"), None),
                               (pas.get(f"cx_pm_{k}_txt") or "").strip() or "—"]
                             for lv, k in cx_paivm_levels]
            _maybe_table(sl, "Cervical PAIVMs", ["Level","L","C","R","Notes"], cx_paivm_rows)
            for key, lbl in [("cx_pm_op_notes","*Cervical OP notes*"),
                              ("cx_pm_paivm_notes","*Cervical PAIVM notes*")]:
                _maybe_note(sl, lbl, pas.get(key, "").strip())
        if any(k.startswith("sh_op_") or k.startswith("sh_acc_") or
               k.startswith("sh_ac_pm") or k.startswith("sh_sc_pm") for k in pas):
            sh_op_def = [("Flexion","sh_op_flex"),("Extension","sh_op_ext"),
                         ("Abduction","sh_op_abd"),("Int Rot","sh_op_ir"),
                         ("Ext Rot","sh_op_er"),("Horiz Add","sh_op_hadd"),
                         ("Horiz Abd","sh_op_habd")]
            sh_op_rows = [[lbl,
                           _fmt_pas(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                           _fmt_pas(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                          for lbl, p in sh_op_def]
            _maybe_table(sl, "Shoulder OP", ["Movement","Left","Right"], sh_op_rows)
            for side, side_lbl in (("l","Left"),("r","Right")):
                acc_rows = [[dir_lbl,
                             _fmt_pas(pas.get(f"sh_acc_{dk}_{side}_norm"),
                                      pas.get(f"sh_acc_{dk}_{side}_txt"))]
                            for dir_lbl, dk in (("Inferior","inf"),("Posterior","post"),("Anterior","ant"))]
                _maybe_table(sl, f"GH Accessory — {side_lbl}", ["Direction","Findings"], acc_rows)
            acsc_rows = [[lbl,
                          _fmt_pas(pas.get(f"{pfx}_l_norm"), pas.get(f"{pfx}_l_txt")),
                          _fmt_pas(pas.get(f"{pfx}_r_norm"), pas.get(f"{pfx}_r_txt"))]
                         for lbl, pfx in (("AC Stress","sh_ac_pm_stress"),
                                          ("AC Palp","sh_ac_pm_palp"),
                                          ("SC Stress","sh_sc_pm_stress"))]
            _maybe_table(sl, "AC / SC Joint", ["Test","Left","Right"], acsc_rows)
            for key, lbl in [("sh_pm_op_notes","*Shoulder OP notes*"),
                              ("sh_pm_acc_notes","*Accessory notes*")]:
                _maybe_note(sl, lbl, pas.get(key, "").strip())
        if any(k.startswith("hp_op_") or k.startswith("hp_acc_") for k in pas):
            hp_op_def = [("Flexion","hp_op_flex"),("Extension","hp_op_ext"),
                         ("Abduction","hp_op_abd"),("Adduction","hp_op_add"),
                         ("Int Rot","hp_op_ir"),("Ext Rot","hp_op_er")]
            hp_op_rows = [[lbl,
                           _fmt_pas(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                           _fmt_pas(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                          for lbl, p in hp_op_def]
            _maybe_table(sl, "Hip OP", ["Movement","Left","Right"], hp_op_rows)
            hp_acc_def = [("Distraction","hp_acc_dist"),("Lateral","hp_acc_lat")]
            hp_acc_rows = [[lbl,
                            _fmt_pas(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                            _fmt_pas(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                           for lbl, p in hp_acc_def]
            _maybe_table(sl, "Hip Accessory", ["Direction","Left","Right"], hp_acc_rows)
            _maybe_note(sl, "*Hip OP notes*", pas.get("hp_op_notes", "").strip())
        if any(k.startswith("kn_op_") or k.startswith("kn_acc_") for k in pas):
            kn_op_def = [("Flexion","kn_op_flex"),("Extension","kn_op_ext")]
            kn_op_rows = [[lbl,
                           _fmt_pas(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                           _fmt_pas(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                          for lbl, p in kn_op_def]
            _maybe_table(sl, "Knee OP", ["Movement","Left","Right"], kn_op_rows)
            kn_acc_def = [("AP Glide","kn_acc_ap"),("Patella Med","kn_acc_pmed"),
                          ("Patella Lat","kn_acc_plat")]
            kn_acc_rows = [[lbl,
                            _fmt_pas(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                            _fmt_pas(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                           for lbl, p in kn_acc_def]
            _maybe_table(sl, "Knee Accessory", ["Direction","Left","Right"], kn_acc_rows)
            _maybe_note(sl, "*Knee OP notes*", pas.get("kn_op_notes", "").strip())
        if any(k.startswith("ak_op_") or k.startswith("ak_acc_") for k in pas):
            ak_op_def = [("Dorsiflexion","ak_op_df"),("Plantarflexion","ak_op_pf"),
                         ("Inversion","ak_op_inv"),("Eversion","ak_op_ev")]
            ak_op_rows = [[lbl,
                           _fmt_pas(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                           _fmt_pas(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                          for lbl, p in ak_op_def]
            _maybe_table(sl, "Ankle OP", ["Movement","Left","Right"], ak_op_rows)
            ak_acc_def = [("AP Glide","ak_acc_ap"),("Subtalar","ak_acc_st")]
            ak_acc_rows = [[lbl,
                            _fmt_pas(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                            _fmt_pas(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                           for lbl, p in ak_acc_def]
            _maybe_table(sl, "Ankle Accessory", ["Direction","Left","Right"], ak_acc_rows)
            _maybe_note(sl, "*Ankle OP notes*", pas.get("ak_op_notes", "").strip())
        _flush_section("### 03 Passive Movement & Overpressure", sl)

    # ── 04 Neurological ───────────────────────────────────────────────────────
    if neu:
        sl = []
        ul_reflex_def = [("Biceps C5/6","nr_biceps"),("Brachiorad C6","nr_brad"),
                         ("Triceps C7","nr_triceps")]
        ul_reflex_rows = [[lbl, neu.get(f"{p}_l") or "—", neu.get(f"{p}_r") or "—"]
                          for lbl, p in ul_reflex_def]
        _maybe_table(sl, "UL Reflexes", ["Test", "Left", "Right"], ul_reflex_rows)
        _maybe_note(sl, "*UL Reflex Notes:*", neu.get("nr_ul_reflex_notes", "").strip())
        ul_myotome_def = [("C5 Shldr abd","nr_c5"),("C6 Wrist ext","nr_c6"),
                          ("C7 Elbow ext","nr_c7"),("C8 Finger flx","nr_c8"),
                          ("T1 Finger abd","nr_t1")]
        ul_myotome_rows = [[lbl, neu.get(f"{p}_l") or "—", neu.get(f"{p}_r") or "—"]
                           for lbl, p in ul_myotome_def]
        _maybe_table(sl, "UL Myotomes", ["Level", "Left", "Right"], ul_myotome_rows)
        _maybe_note(sl, "*UL Myotome Notes:*", neu.get("nr_ul_myotome_notes", "").strip())
        ul_derm_def = [("C5 Lat arm/delt","sn_c5"),("C6 Thumb & index","sn_c6"),
                       ("C7 Middle finger","sn_c7"),("C8 Little/ulnar","sn_c8"),
                       ("T1 Med forearm","sn_t1")]
        ul_derm_rows = [[lbl, neu.get(f"{p}_l") or "—", neu.get(f"{p}_r") or "—"]
                        for lbl, p in ul_derm_def]
        _maybe_table(sl, "UL Dermatomes", ["Level", "Left", "Right"], ul_derm_rows)
        _maybe_note(sl, "*UL Dermatome Notes:*", neu.get("nr_ul_derm_notes", "").strip())
        ulnt_def = [("ULNT1","nr_ulnt1"),("ULNT2a","nr_ulnt2a"),("ULNT3","nr_ulnt3")]
        ulnt_rows = [[lbl, neu.get(f"{p}_l_resp","") or "—", neu.get(f"{p}_r_resp","") or "—"]
                     for lbl, p in ulnt_def]
        _maybe_table(sl, "Upper Limb Neurodynamics", ["Test", "L Response", "R Response"], ulnt_rows)
        _maybe_note(sl, "*UL Neurodynamics Notes:*", neu.get("nr_ul_nd_notes", "").strip())
        neuro_def = [
            ("Knee jerk L3/4","nr_knee"),("Ankle jerk S1","nr_ankle"),
            ("L2 Hip flex","nr_l2"),("L3 Knee ext","nr_l3"),("L4 Ankle DF","nr_l4"),
            ("L5 GT ext/EHL","nr_l5"),("S1 PF/evert","nr_s1"),("S2 Ham/KF","nr_s2"),
        ]
        neuro_rows = [[lbl, neu.get(f"{p}_l") or "—", neu.get(f"{p}_r") or "—"]
                      for lbl, p in neuro_def]
        _maybe_table(sl, "LL Reflexes & Myotomes", ["Test", "Left", "Right"], neuro_rows)
        _maybe_note(sl, "*LL Reflex Notes:*", neu.get("nr_ll_reflex_notes", "").strip())
        _maybe_note(sl, "*LL Myotome Notes:*", neu.get("nr_ll_myotome_notes", "").strip())
        _derm_def_nr = [("L2 Ant thigh","sn_l2"),("L3 Med knee","sn_l3"),
                        ("L4 Med leg","sn_l4"),("L5 Lat leg/GT","sn_l5"),
                        ("S1 Lat foot","sn_s1"),("S2 Post thigh","sn_s2")]
        derm_rows_nr = [[lbl, neu.get(f"{p}_l") or "—", neu.get(f"{p}_r") or "—"]
                        for lbl, p in _derm_def_nr]
        _maybe_table(sl, "LL Dermatomes", ["Level", "Left", "Right"], derm_rows_nr)
        _maybe_note(sl, "*LL Dermatome Notes:*", neu.get("nr_ll_derm_notes", "").strip())
        nd_def = [("SLR","nr_slr"),("Slump","nr_slump"),("PKF","nr_pkf")]
        nd_rows = []
        for lbl, p in nd_def:
            ld = neu.get(f"{p}_l_deg","") or ""; lr = neu.get(f"{p}_l_resp","") or "—"
            rd = neu.get(f"{p}_r_deg","") or ""; rr = neu.get(f"{p}_r_resp","") or "—"
            nd_rows.append([lbl, f"{ld}°" if ld else "—", lr,
                                  f"{rd}°" if rd else "—", rr])
        _maybe_table(sl, "LL Neurodynamics", ["Test", "L °", "L Resp", "R °", "R Resp"], nd_rows)
        _maybe_note(sl, "*LL Neurodynamics Notes:*", neu.get("nr_ll_nd_notes", "").strip())
        umn_items = [("Hyperreflexia","nr_umn_hyper"),("Babinski +","nr_umn_bab"),
                     ("Clonus","nr_umn_clonus"),("Romberg +","nr_umn_romberg"),
                     ("Coord impaired","nr_umn_coord"),
                     ("Hoffman's","nr_umn_hoffman"),("Tromner","nr_umn_tromner"),
                     ("Lhermitte's","nr_umn_lhermitte"),("Inv Supinator","nr_umn_inv_sup")]
        umn_rows = [[lbl, "Yes" if neu.get(uid) is True else "No" if neu.get(uid) is False else "*(not answered)*"]
                    for lbl, uid in umn_items]
        _maybe_table(sl, "UMN Signs", ["Sign", "Result"], umn_rows)
        _maybe_note(sl, "*UMN Notes:*", neu.get("nr_umn_notes", "").strip())
        _maybe_note(sl, "*Notes:*", neu.get("nr_notes", "").strip())
        _flush_section("### 04 Neurological", sl)

    # ── 05 Sensory ────────────────────────────────────────────────────────────
    if sen:
        sl = []
        ppt = (sen.get("sn_ppt") or "").strip()
        ppt_detail = sen.get("sn_ppt_detail", "").strip()
        if ppt:
            sl.append(f"**PPT (algometer):** {ppt}" + (f" — {ppt_detail}" if ppt_detail else ""))
        elif not clean:
            sl.append("**PPT (algometer):** *(not recorded)*")
        hypo_items = [("Sharp/blunt","sn_sharp_blunt",True),("Two-point discrim","sn_tpd",True),
                      ("Light touch","sn_lt",True),("Body perception","sn_body",True)]
        hyper_items = [("Static allodynia","sn_static_allodynia",True),
                       ("Dynamic allodynia","sn_dynamic_allodynia",True),
                       ("2° hyperalgesia PPT","sn_secondary_hyper",True),
                       ("Pin prick hyper","sn_pin_prick",True),
                       ("Cold hyperalgesia","sn_cold",True),
                       ("Heat hyperalgesia","sn_heat",True),
                       ("Temporal summation","sn_temporal_sum",True),
                       ("Conditioned pain modulation","sn_cpm",True),
                       ("Nerve trunk palpation","sn_nerve_palpation",True)]
        for sec_lbl, items in [("Hyposensitivity", hypo_items), ("Hypersensitivity", hyper_items)]:
            rows = []
            for lbl, sid, has_detail in items:
                v = sen.get(sid)
                if clean and v is None:
                    continue
                state = "Yes" if v is True else "No" if v is False else "*(not answered)*"
                detail = sen.get(f"{sid}_detail", "").strip() if has_detail and v is True else ""
                rows.append([lbl, f"{state} — {detail}" if detail else state])
            if rows:
                if clean and sl and sl[-1] != "":
                    sl.append("")
                sl.append(f"**{sec_lbl}:**")
                if clean:
                    sl.append("")
                sl.extend(_md_table(["Test", "Result"], rows))
                if clean:
                    sl.append("")
        _maybe_note(sl, "*Notes:*", sen.get("sn_notes", "").strip())
        _flush_section("### 05 Sensory", sl)

    # ── 06 Muscle Testing ─────────────────────────────────────────────────────
    _lower_regions = set(active_regions or [])
    if mus or _lower_regions & {"hip", "knee", "ankle"}:
        sl = []
        ml_def = [("QL (side sit)","ml_ql"),("Thomas test","ml_thomas"),
                  ("Hamstrings SLR","ml_ham")]
        ml_rows = [[lbl, mus.get(f"{p}_l") or "—", mus.get(f"{p}_r") or "—"]
                   for lbl, p in ml_def]
        _maybe_table(sl, "Muscle Length", ["Test", "Left", "Right"], ml_rows)
        ma_def = [("Tx erector spinae","ma_tx_es"),("Transversus abd","ma_tva"),
                  ("Lumbar multifidus","ma_lmf")]
        ma_rows = [[lbl, mus.get(mid) or "—"] for lbl, mid in ma_def]
        _maybe_table(sl, "Muscle Activation", ["Test", "Finding"], ma_rows)
        for key, lbl, unit in [("st_flex","Trunk flexion","reps/min"),
                                ("st_ext","Trunk extension","raises/min")]:
            v = (mus.get(key) or "").strip()
            if v:
                sl.append(f"**{lbl}:** {v} {unit}")
            elif not clean:
                sl.append(f"**{lbl}:** *(not recorded)* {unit}")
        hip_def = [("Hip flexion","sh_hip_flex"),("Hip extension","sh_hip_ext"),
                   ("Hip abduction","sh_hip_abd"),("Hip adduction","sh_hip_add"),
                   ("Hip int rotation","sh_hip_ir"),("Hip ext rotation","sh_hip_er")]
        hip_rows = [[lbl, mus.get(f"{p}_l") or "—", mus.get(f"{p}_r") or "—"]
                    for lbl, p in hip_def]
        _maybe_table(sl, "Hip Strength (Wagner FPX kg)", ["Movement", "Left kg", "Right kg"], hip_rows)
        sij_items = [("Sacral thrust","sij_sacral"),("Post thigh thrust","sij_ptt"),
                     ("Distraction supine","sij_dist"),("Compression s/l","sij_comp"),
                     ("Gaenslen","sij_gaenslen"),("ASLR compression","sij_aslr")]
        sij_rows = [[lbl, "Yes" if mus.get(sid) is True else "No" if mus.get(sid) is False else "*(not answered)*"]
                    for lbl, sid in sij_items]
        _maybe_table(sl, "SIJ Provocation", ["Test", "Result"], sij_rows)
        cx_ml_def = [("Upper trapezius","ml_ut"),("Levator scapulae","ml_ls"),
                     ("Pectorals","ml_pec"),("Scalenes","ml_scal")]
        cx_ml_rows = [[lbl, mus.get(f"{p}_l") or "—", mus.get(f"{p}_r") or "—"]
                      for lbl, p in cx_ml_def]
        _maybe_table(sl, "Cervical Muscle Length", ["Test", "Left", "Right"], cx_ml_rows)
        cx_ma_def = [("Deep cerv flexors","ma_dcf"),("Cervical extensors","ma_cx_ext"),
                     ("Serratus anterior","ma_sa")]
        cx_ma_rows = [[lbl, mus.get(mid) or "—"] for lbl, mid in cx_ma_def]
        _maybe_table(sl, "Cervical Muscle Activation", ["Test", "Finding"], cx_ma_rows)
        dcf_end = (mus.get("st_dcf_end") or "").strip()
        if dcf_end:
            sl.append(f"**DCF endurance:** {dcf_end} s")
        elif not clean:
            sl.append("**DCF endurance:** *(not recorded)* s")
        if any(k.startswith("cx_neck_") for k in mus):
            cx_neck_def = [("Neck flexion","cx_neck_flex"),("Neck extension","cx_neck_ext"),
                           ("Neck lat flex","cx_neck_lf"),("Neck rotation","cx_neck_rot")]
            cx_neck_rows = [[lbl, mus.get(f"{p}_l") or "—", mus.get(f"{p}_r") or "—"]
                            for lbl, p in cx_neck_def]
            _maybe_table(sl, "Neck Strength (kg)", ["Movement","Left","Right"], cx_neck_rows)
        _maybe_note(sl, "*Cervical muscle notes:*", mus.get("mu_cx_notes", "").strip())
        _maybe_note(sl, "*Notes:*", mus.get("mu_notes", "").strip())
        if any(k.startswith("sh_str_") or k.startswith("ml_pec_") or
               k.startswith("ml_post_cap") or k.startswith("ma_lt_") or
               k.startswith("ma_er_fc") for k in mus):
            sh_ml_def = [("Pec minor","ml_pec_min"),("Pec maj sternal","ml_pec_st"),
                         ("Pec maj clav","ml_pec_cl"),("Latissimus","ml_lat"),
                         ("Post capsule","ml_post_cap")]
            sh_ml_rows = [[lbl, mus.get(f"{p}_l") or "—", mus.get(f"{p}_r") or "—"]
                          for lbl, p in sh_ml_def]
            _maybe_table(sl, "Shoulder Muscle Length", ["Test","Left","Right"], sh_ml_rows)
            sh_ma_def = [("Lower trap","ma_lt"),("Serratus ant","ma_sa"),
                         ("ER force couple","ma_er_fc")]
            sh_ma_rows = [[lbl, mus.get(f"{p}_l") or "—", mus.get(f"{p}_r") or "—"]
                          for lbl, p in sh_ma_def]
            _maybe_table(sl, "Shoulder Muscle Activation", ["Test","Left","Right"], sh_ma_rows)
            sh_str_def = [("Flexion","sh_str_flex"),("Abduction","sh_str_abd"),
                          ("Int Rot","sh_str_ir"),("Ext Rot","sh_str_er"),
                          ("Scaption","sh_str_scap")]
            sh_str_rows = [[lbl, mus.get(f"{p}_l") or "—", mus.get(f"{p}_r") or "—"]
                           for lbl, p in sh_str_def]
            _maybe_table(sl, "Shoulder Strength (kg or 0–5)", ["Movement","Left","Right"], sh_str_rows)
            _maybe_note(sl, "*Shoulder muscle notes*", mus.get("mu_sh_notes", "").strip())
        if "hip" in _lower_regions or any(k.startswith("hp_str_") for k in mus):
            hp_str_def = [("Flexion","hp_str_flex"),("Extension","hp_str_ext"),
                          ("Abduction","hp_str_abd"),("Adduction","hp_str_add"),
                          ("Int Rot","hp_str_ir"),("Ext Rot","hp_str_er")]
            hp_str_rows = [[lbl, mus.get(f"{p}_l") or "—", mus.get(f"{p}_r") or "—"]
                           for lbl, p in hp_str_def]
            _maybe_table(sl, "Hip Strength (kg or 0–5)", ["Movement","Left","Right"], hp_str_rows)
            _maybe_note(sl, "*Hip muscle notes*", mus.get("mu_hp_notes", "").strip())
        if "knee" in _lower_regions or any(k.startswith("kn_str_") for k in mus):
            kn_str_def = [("Extension (quads)","kn_str_ext"),
                          ("Flexion (hamstring)","kn_str_flex"),
                          ("Calf (heel raise)","kn_str_calf")]
            kn_str_rows = [[lbl, mus.get(f"{p}_l") or "—", mus.get(f"{p}_r") or "—"]
                           for lbl, p in kn_str_def]
            _maybe_table(sl, "Knee/Calf Strength (kg or 0–5)", ["Movement","Left","Right"], kn_str_rows)
            _maybe_note(sl, "*Knee muscle notes*", mus.get("mu_kn_notes", "").strip())
        if "ankle" in _lower_regions or any(k.startswith("ak_str_") for k in mus):
            ak_str_def = [("Dorsiflexion (TA)","ak_str_df"),
                          ("Plantarflexion (GS)","ak_str_pf"),
                          ("Eversion (peroneals)","ak_str_ev")]
            ak_str_rows = [[lbl, mus.get(f"{p}_l") or "—", mus.get(f"{p}_r") or "—"]
                           for lbl, p in ak_str_def]
            _maybe_table(sl, "Ankle Strength (kg or 0–5)", ["Movement","Left","Right"], ak_str_rows)
            _maybe_note(sl, "*Ankle muscle notes*", mus.get("mu_ak_notes", "").strip())
        _flush_section("### 06 Muscle Testing", sl)

    # ── 02 Functional ─────────────────────────────────────────────────────────
    if func:
        sl = []
        obs_def = [
            ("Gait",         "ft_gait",  "ft_gait_obs"),
            ("Sit-to-stand", "ft_sts_q", "ft_sts_obs"),
            ("Squat",        "ft_squat", "ft_squat_obs"),
            ("Lunge",        "ft_lunge", "ft_lunge_obs"),
            ("Lifting",      "ft_lift",  "ft_lift_obs"),
            ("Carrying",     "ft_carry", "ft_carry_obs"),
            ("Reaching",     "ft_reach", "ft_reach_obs"),
        ]
        obs_rows = []
        for lbl, rid, iid in obs_def:
            parts = [p for p in [func.get(rid) or "", func.get(iid, "").strip()] if p]
            obs_rows.append([lbl, " — ".join(parts) if parts else "—"])
        _maybe_table(sl, "Movement Observation", ["Test", "Finding"], obs_rows)
        bal_def = [("Both legs",["ft_bal_both"]),("Feet together",["ft_bal_feet"]),
                   ("Tandem",["ft_bal_tandem"]),
                   ("SLS eyes open",["ft_sls_eo_l","ft_sls_eo_r"]),
                   ("SLS eyes closed",["ft_sls_ec_l","ft_sls_ec_r"]),
                   ("SLS foam 10cm",["ft_sls_foam_l","ft_sls_foam_r"])]
        bal_rows = []
        for lbl, ids in bal_def:
            vals = [func.get(i,"") or "—" for i in ids]
            if len(ids) == 1:
                vals = [vals[0], "—"]
            bal_rows.append([lbl] + vals)
        _maybe_table(sl, "Balance (Steffen 2002)", ["Test", "Left s", "Right s"], bal_rows)
        cap_def = [("TUG (3m)","ft_tug","s"),("5× Sit-to-Stand","ft_sts5","s"),
                   ("10m comfortable","ft_10m_e","m/s"),("10m fast","ft_10m_f","m/s"),
                   ("2 min walk","ft_2mw","m")]
        cap_rows = [[lbl, f"{func.get(fid,'') or '—'} {unit}".strip() if func.get(fid,"") else "—"]
                    for lbl, fid, unit in cap_def]
        _maybe_table(sl, "Timed Capability", ["Test", "Result"], cap_rows)
        _maybe_note(sl, "*Functional obs:*",    func.get("ft_fm_obs", "").strip())
        _maybe_note(sl, "*Custom Func test:*",  func.get("ft_fm_custom", "").strip())
        _maybe_note(sl, "*Notes:*",             func.get("ft_notes", "").strip())
        _flush_section("### 02 Functional", sl)

    # ── 08 Special Tests ──────────────────────────────────────────────────────
    if spl:
        sl = []
        _LX_ST_GROUPS = [
            ("Disc/Herniation",[("SLR","st_slr"),("Crossed SLR","st_crossed_slr")]),
            ("Neurodynamics",  [("Slump","st_slump"),("Femoral","st_femoral")]),
            ("Hip Screen",     [("FABER","st_faber"),("FADIR","st_fadir")]),
            ("Instability",    [("Prone Inst","st_prone_inst")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _LX_ST_GROUPS for _, sid in rows):
            for grp_lbl, rows in _LX_ST_GROUPS:
                lx_st_rows = [[lbl, spl.get(f"{sid}_l") or "—", spl.get(f"{sid}_r") or "—"]
                              for lbl, sid in rows]
                _maybe_table(sl, f"Lumbar — {grp_lbl}", ["Test","Left","Right"], lx_st_rows)
        _CX_ST_GROUPS = [
            ("Radiculopathy",  [("Spurling","st_spurling"),("Distraction","st_distraction")]),
            ("Neurodynamics",  [("ULNT1","st_ulnt1"),("ULNT2a","st_ulnt2a"),("ULNT3","st_ulnt3")]),
            ("CGH",            [("FRT","st_frt")]),
            ("Sharp-Purser",   [("Sharp-Purser","st_sharp_purser")]),
            ("Alar Ligament",  [("Ant Shear","st_ant_shear"),("Alar Lig SF","st_alar_sf"),
                                ("Alar Lig Rot","st_alar_rot"),("Lat Trans","st_lat_trans")]),
            ("VBI",            [("VBI Sus Rot","st_vbi_sus_rot")]),
            ("Motor Control",  [("CCFT","st_ccft")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _CX_ST_GROUPS for _, sid in rows):
            for grp_lbl, rows in _CX_ST_GROUPS:
                cx_st_rows = [[lbl, spl.get(f"{sid}_l") or "—", spl.get(f"{sid}_r") or "—"]
                              for lbl, sid in rows]
                _maybe_table(sl, f"Cervical — {grp_lbl}", ["Test","Left","Right"], cx_st_rows)
        for key, lbl in [("st_lx_notes","*Lumbar notes:*"),("st_cx_notes","*Cervical notes:*"),
                          ("st_ccft_notes","*CCFT notes (Lean angle · Nod · Lift · Hover):*")]:
            _maybe_note(sl, lbl, spl.get(key, "").strip())
        _SH_ST_GROUPS = [
            ("Impingement",  [("Hawkins","st_hawkins"),("Neer","st_neer"),
                              ("Painful Arc","st_painful_arc"),("ER Resist","st_er_resist")]),
            ("Rotator Cuff", [("Empty Can","st_empty_can"),("Full Can","st_full_can"),
                              ("ER Lag","st_er_lag"),("Lift-off","st_lift_off"),
                              ("Belly Press","st_belly_press"),("Drop Arm","st_drop_arm"),
                              ("IR Lag","st_irls"),("Drop Sign (IS)","st_drop_is"),
                              ("Hornblower","st_hornblower")]),
            ("AC Joint",     [("Cross-body","st_cross_body"),("AC Stress","st_ac_stress"),
                              ("AC Resist Ext","st_ac_ext")]),
            ("Biceps/SLAP",  [("Speed's","st_speeds"),("Yergason","st_yergason"),
                              ("O'Brien","st_obrien"),("Passive Comp","st_pass_comp"),
                              ("Bicip Groove","st_bicip_groove")]),
            ("Instability",  [("Apprehension","st_apprehension"),("Relocation","st_relocation")]),
            ("Sulcus",       [("Sulcus","st_sulcus")]),
            ("Scapular Assistance", [("Scap Assist","st_scap_assist")]),
            ("Serratus Anterior",   [("Wall Pushup","st_wall_pushup")]),
            ("TOS",          [("Adson's","st_adson"),("Roos/EAST","st_roos"),
                              ("Wright's","st_wright"),("CRLF","st_crlf")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _SH_ST_GROUPS for _, sid in rows):
            for grp_lbl, rows in _SH_ST_GROUPS:
                sh_st_rows = [[lbl, spl.get(f"{sid}_l") or "—", spl.get(f"{sid}_r") or "—"]
                              for lbl, sid in rows]
                _maybe_table(sl, f"Shoulder — {grp_lbl}", ["Test","Left","Right"], sh_st_rows)
            _maybe_note(sl, "*Shoulder test notes*", spl.get("st_sh_notes", "").strip())
        _HP_ST_GROUPS = [
            ("FAI/Impingement", [("FADIR","st_hp_fadir"),("Ant Impingement","st_hp_ant_imp")]),
            ("Hip OA",          [("FABER","st_hp_faber"),("Hip Scour","st_hp_hip_scour"),
                                 ("Log Roll","st_hp_log_roll")]),
            ("GTPS",            [("Ober","st_hp_ober"),("Trendelenburg","st_hp_trendelenburg"),
                                 ("SLS","st_hp_sls_hip")]),
            ("Hamstring Origin",[("Puranen-Orava","st_hp_puranen_orava"),("BKS","st_hp_bks")]),
            ("Adductor",        [("Squeeze","st_hp_squeeze")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _HP_ST_GROUPS for _, sid in rows):
            for grp_lbl, rows in _HP_ST_GROUPS:
                hp_st_rows = [[lbl, spl.get(f"{sid}_l") or "—", spl.get(f"{sid}_r") or "—"]
                              for lbl, sid in rows]
                _maybe_table(sl, f"Hip — {grp_lbl}", ["Test","Left","Right"], hp_st_rows)
            _maybe_note(sl, "*Hip test notes*", spl.get("st_hp_notes", "").strip())
        _KN_ST_GROUPS = [
            ("ACL",     [("Lachman","st_kn_lachman"),("Ant Drawer","st_kn_ant_draw"),
                         ("Pivot Shift","st_kn_pivot")]),
            ("PCL",     [("Post Drawer","st_kn_post_draw"),("Post Sag","st_kn_post_sag")]),
            ("Meniscus",[("McMurray","st_kn_mcmurray"),("Thessaly","st_kn_thessaly"),
                         ("JLT","st_kn_jlt")]),
            ("MCL",     [("Valgus 0°","st_kn_valgus_0"),("Valgus 30°","st_kn_valgus_30")]),
            ("LCL",     [("Varus 0°","st_kn_varus_0"),("Varus 30°","st_kn_varus_30")]),
            ("PFJ",     [("Clarke's","st_kn_clarkes"),("Pat Tilt","st_kn_pat_tilt"),
                         ("Pat Grind","st_kn_pat_grind")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _KN_ST_GROUPS for _, sid in rows):
            for grp_lbl, rows in _KN_ST_GROUPS:
                kn_st_rows = [[lbl, spl.get(f"{sid}_l") or "—", spl.get(f"{sid}_r") or "—"]
                              for lbl, sid in rows]
                _maybe_table(sl, f"Knee — {grp_lbl}", ["Test","Left","Right"], kn_st_rows)
            _maybe_note(sl, "*Knee test notes*", spl.get("st_kn_notes", "").strip())
        _AK_ST_GROUPS = [
            ("Lateral Lig",  [("Ant Drawer","st_ak_ant_draw"),("Talar Tilt","st_ak_talar_tilt")]),
            ("Achilles",     [("Thompson","st_ak_thompson"),("Royal London","st_ak_royal_london"),
                              ("Heel Raise","st_ak_heel_raise")]),
            ("Syndesmosis",  [("Squeeze","st_ak_squeeze"),("ER Stress","st_ak_er_stress"),
                              ("Cotton","st_ak_cotton")]),
            ("Ottawa Rules", [("Lat Malleolus","st_ak_ott_lat_mal"),("Med Malleolus","st_ak_ott_med_mal"),
                              ("Navicular","st_ak_ott_nav"),("5th Met Base","st_ak_ott_5mt")]),
            ("Peroneal",     [("Peroneal Prov","st_ak_per_prov")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _AK_ST_GROUPS for _, sid in rows):
            for grp_lbl, rows in _AK_ST_GROUPS:
                ak_st_rows = [[lbl, spl.get(f"{sid}_l") or "—", spl.get(f"{sid}_r") or "—"]
                              for lbl, sid in rows]
                _maybe_table(sl, f"Ankle — {grp_lbl}", ["Test","Left","Right"], ak_st_rows)
            _maybe_note(sl, "*Ankle test notes*", spl.get("st_ak_notes", "").strip())
        _flush_section("### 08 Special Tests", sl)

    # ── 09 CRPS ───────────────────────────────────────────────────────────────
    _crps_all_flag_ids = [
        "crps_disp_pain",
        "crps_sx_hyperesth","crps_sx_hyperalg","crps_sx_allodynia",
        "crps_sx_temp_asymm","crps_sx_skin_colour","crps_sx_colour_asymm",
        "crps_sx_oedema","crps_sx_sweat_chng","crps_sx_sweat_asymm",
        "crps_sx_rom_dec","crps_sx_weakness","crps_sx_tremor","crps_sx_dystonia","crps_sx_trophic",
        "crps_sg_hyperalg_pp","crps_sg_allod_lt","crps_sg_allod_press","crps_sg_allod_jt",
        "crps_sg_temp_asymm","crps_sg_skin_colour","crps_sg_colour_asymm",
        "crps_sg_oedema","crps_sg_sweat_chng","crps_sg_sweat_asymm",
        "crps_sg_rom_dec","crps_sg_weakness","crps_sg_tremor","crps_sg_dystonia","crps_sg_trophic",
        "crps_no_alt_dx",
    ]
    _crps_all_ta_ids = [
        "crps_disp_pain_notes","crps_sx_notes","crps_sg_notes",
        "crps_no_alt_dx_notes","crps_subtype_notes","crps_notes",
        "crps_tpd_notes","crps_vis_notes","crps_lat_notes",
    ]
    _crps_lat_field_ids = [
        f"crps_lat_{r}_{c}"
        for r in ("quick","vanilla","context","abstract")
        for c in ("l_acc","l_speed","r_acc","r_speed")
    ]
    _crps_has_data = (
        any(crps.get(f) is not None for f in _crps_all_flag_ids) or
        any(crps.get(t, "").strip() for t in _crps_all_ta_ids) or
        any(crps.get(lid, "") for lid in _crps_lat_field_ids) or
        bool(crps.get("crps_subtype"))
    )
    if crps and (not clean or _crps_has_data):
        sl = []
        def _crps_flag(v) -> str:
            return "Yes" if v is True else "No" if v is False else "—"
        _crps_sx_domains = [
            ("Sensory",          [("crps_sx_hyperesth","Hyperesthesia"),("crps_sx_hyperalg","Hyperalgesia"),("crps_sx_allodynia","Allodynia")]),
            ("Vasomotor",        [("crps_sx_temp_asymm","Temp asymm"),("crps_sx_skin_colour","Skin colour"),("crps_sx_colour_asymm","Colour asymm")]),
            ("Sudomotor/Oedema", [("crps_sx_oedema","Oedema"),("crps_sx_sweat_chng","Sweat chng"),("crps_sx_sweat_asymm","Sweat asymm")]),
            ("Motor/Trophic",    [("crps_sx_rom_dec","Decr ROM"),("crps_sx_weakness","Weakness"),("crps_sx_tremor","Tremor"),("crps_sx_dystonia","Dystonia"),("crps_sx_trophic","Trophic")]),
        ]
        _crps_sg_domains = [
            ("Sensory",          [("crps_sg_hyperalg_pp","Hyperalg PP"),("crps_sg_allod_lt","Allod LT"),("crps_sg_allod_press","Allod Pres"),("crps_sg_allod_jt","Allod Joint")]),
            ("Vasomotor",        [("crps_sg_temp_asymm","Temp asymm"),("crps_sg_skin_colour","Skin colour"),("crps_sg_colour_asymm","Colour asymm")]),
            ("Sudomotor/Oedema", [("crps_sg_oedema","Oedema"),("crps_sg_sweat_chng","Sweat chng"),("crps_sg_sweat_asymm","Sweat asymm")]),
            ("Motor/Trophic",    [("crps_sg_rom_dec","Decr ROM"),("crps_sg_weakness","Weakness"),("crps_sg_tremor","Tremor"),("crps_sg_dystonia","Dystonia"),("crps_sg_trophic","Trophic")]),
        ]
        _crps_subtype_full = {
            "T-I":   "Type I — no discrete nerve injury",
            "T-II":  "Type II — confirmed discrete nerve injury; signs extend beyond nerve territory",
            "Remit": "CRPS with Remission of Some Features",
            "NOS":   "CRPS Not Otherwise Specified",
        }
        if not clean or crps.get("crps_disp_pain") is not None:
            sl.append(f"**Rule 1 — Disproportionate pain:** {_crps_flag(crps.get('crps_disp_pain'))}")
        _maybe_note(sl, "*Disp. pain notes*", crps.get("crps_disp_pain_notes", "").strip())

        sx_t = crps.get("crps_sx_domains_triggered", 0)
        sx_rows = []
        for dom_lbl, dom_items in _crps_sx_domains:
            triggered = any(crps.get(fid) is True for fid, _ in dom_items)
            if clean and not triggered:
                continue
            present   = ", ".join(lbl for fid, lbl in dom_items if crps.get(fid) is True) or "—"
            sx_rows.append([dom_lbl, "Yes" if triggered else "No", present])
        _maybe_table(sl, f"Rule 2 — Symptoms ({sx_t}/4 domains; need ≥ 3)",
                     ["Domain", "Triggered", "Items present"], sx_rows, data_from=0)
        _maybe_note(sl, "*Symptom notes*", crps.get("crps_sx_notes", "").strip())

        sg_t = crps.get("crps_sg_domains_triggered", 0)
        sg_rows = []
        for dom_lbl, dom_items in _crps_sg_domains:
            triggered = any(crps.get(fid) is True for fid, _ in dom_items)
            if clean and not triggered:
                continue
            present   = ", ".join(lbl for fid, lbl in dom_items if crps.get(fid) is True) or "—"
            sg_rows.append([dom_lbl, "Yes" if triggered else "No", present])
        _maybe_table(sl, f"Rule 3 — Signs ({sg_t}/4 domains; need ≥ 2)",
                     ["Domain", "Triggered", "Items present"], sg_rows, data_from=0)
        _maybe_note(sl, "*Sign notes*", crps.get("crps_sg_notes", "").strip())

        if not clean or crps.get("crps_no_alt_dx") is not None:
            sl.append(f"**Rule 4 — No other diagnosis:** {_crps_flag(crps.get('crps_no_alt_dx'))}")
        _maybe_note(sl, "*No-alt-dx notes*", crps.get("crps_no_alt_dx_notes", "").strip())

        _crps_flags_answered = any(crps.get(f) is not None for f in ("crps_disp_pain", "crps_no_alt_dx"))
        if not clean or _crps_flags_answered or crps.get("crps_criteria_met"):
            verdict = "**CRITERIA MET**" if crps.get("crps_criteria_met") else "*Criteria not met*"
            sl.append(f"\n**Budapest/Valencia Clinical Criteria:** {verdict}")

        subtype_val = crps.get("crps_subtype")
        if subtype_val:
            sl.append(f"**Subtype:** {_crps_subtype_full.get(subtype_val, subtype_val)}")
        _maybe_note(sl, "*Subtype notes*", crps.get("crps_subtype_notes", "").strip())
        _maybe_note(sl, "*General notes*", crps.get("crps_notes", "").strip())

        tpd = crps.get("crps_tpd_notes", "").strip()
        if tpd:
            sl.append(f"**Two-Point Discrimination:** {tpd}")
        elif not clean:
            sl.append("**Two-Point Discrimination:** *(empty)*")

        vis = crps.get("crps_vis_notes", "").strip()
        if vis:
            sl.append(f"**Visualisation:** {vis}")
        elif not clean:
            sl.append("**Visualisation:** *(empty)*")

        def _lat_fmt(v: str, unit: str) -> str:
            v = (v or "").strip()
            if not v:
                return "—"
            if unit == "%" and not v.endswith("%"):
                return f"{v}%"
            if unit == "s" and not v.endswith("s"):
                return f"{v}s"
            return v
        _lat_row_labels = {"quick":"Quick","vanilla":"Vanilla","context":"Context","abstract":"Abstract"}
        _lat_rows_md = [
            [
                _lat_row_labels[row],
                _lat_fmt(crps.get(f"crps_lat_{row}_l_acc",  ""), "%"),
                _lat_fmt(crps.get(f"crps_lat_{row}_l_speed",""), "s"),
                _lat_fmt(crps.get(f"crps_lat_{row}_r_acc",  ""), "%"),
                _lat_fmt(crps.get(f"crps_lat_{row}_r_speed",""), "s"),
            ]
            for row in ("quick","vanilla","context","abstract")
        ]
        _maybe_table(sl, "Laterality", ["Task","L acc","L speed","R acc","R speed"],
                     _lat_rows_md, data_from=1)
        _maybe_note(sl, "*Laterality notes*", crps.get("crps_lat_notes", "").strip())
        _flush_section("### 09 CRPS (Budapest / Valencia Criteria)", sl)

    if not lines:
        return []

    return lines


def _render_objective_raw(obj: dict, lines: list, SEP: str, SEP2: str,
                          clean: bool = False) -> None:
    """Append objective sections in plain-text format to lines list.

    clean=True: omit sections/tables/rows with no real data.
    """
    gen  = obj.get("general",      {}) or {}
    neu  = obj.get("neurological", {}) or {}
    sen  = obj.get("sensory",      {}) or {}
    func = obj.get("functional",   {}) or {}
    crps = obj.get("crps",         {}) or {}

    # Support both old flat schema and new region-based schema
    active_regions = obj.get("active_regions")
    if active_regions is not None:
        act, pas, mus, spl = _merged_region_data(obj, active_regions)
    else:
        act  = obj.get("active",  {}) or {}
        pas  = obj.get("passive", {}) or {}
        mus  = obj.get("muscle",  {}) or {}
        spl  = {}

    if not any([gen, act, pas, neu, sen, mus, func, spl, crps]):
        return

    # ── clean-mode helpers ────────────────────────────────────────────────────
    _EMPTY_RAW = frozenset(["-", "(not answered)", "(not recorded)", "(empty)", ""])

    def _nodata(v) -> bool:
        return v is None or str(v).strip() in _EMPTY_RAW

    def _filter_rows(rows: list, data_from: int = 1) -> list:
        if not clean:
            return rows
        return [r for r in rows if not all(_nodata(c) for c in r[data_from:])]

    def _maybe_table(sl: list, headers: list, rows: list, data_from: int = 1) -> None:
        rows = _filter_rows(rows, data_from)
        if not rows:
            return
        sl.extend(_raw_table(headers, rows))

    def _flush_section(header: str, sl: list) -> None:
        if sl:
            lines.extend(["", f"  — {header} —"])
            lines.extend(sl)

    # ── 01 General Observation ────────────────────────────────────────────────
    if gen:
        sl: list[str] = []
        for key, lbl in [("go_general_notes","General observations"),
                          ("go_transfer_cmt","General mobility")]:
            v = gen.get(key, "").strip()
            if v:
                sl.append(f"  {lbl}: {v}")
            elif not clean:
                sl.append(f"  {lbl}: (empty)")
        _posture_raw = [("Lumbar lordosis","go_lx_lord"),("Thoracic kyphosis","go_tx_kyph"),
                        ("Antalgic lean","go_lean"),("Sway posture","go_sway"),
                        ("Breathing","go_breath"),("Scapular L","go_scap_l"),
                        ("Scapular R","go_scap_r"),("Muscle wasting","go_wasting")]
        p_rows = []
        for lbl, key in _posture_raw:
            raw = gen.get(key)
            if key == "go_lean" and isinstance(raw, list):
                v = " + ".join(raw) if raw else "(not recorded)"
            else:
                v = raw or "(not recorded)"
            p_rows.append([lbl, v, gen.get(f"{key}_cmt", "")])
        _maybe_table(sl, ["Posture", "Finding", "Comment"], p_rows)
        v = gen.get("go_posture_notes", "").strip()
        if v:
            sl.append(f"  Posture notes: {v}")
        elif not clean:
            sl.append(f"  Posture notes: (empty)")
        _flush_section("01 General Observation", sl)

    # ── 02 Active Movement ────────────────────────────────────────────────────
    if act:
        sl = []
        lx_rows_def = [("Flexion","lx_flex",True),("Extension","lx_ext",True),
                       ("Lat Flex","lx_lf",False),("Rotation","lx_rot",False)]
        tx_rows_def = [("Flexion","tx_flex",True),("Extension","tx_ext",True),
                       ("Rotation","tx_rot",False)]
        for title, rows_def in [("Lumbar ROM", lx_rows_def), ("Thoracic ROM", tx_rows_def)]:
            tbl_rows = []
            for lbl, prefix, bilateral in rows_def:
                def _cell(p, s):
                    v  = act.get(f"{p}_{s}_range", "") or ""
                    t  = f"{v}°" if v else "-"
                    return t
                ax_l = _cell(prefix,"ax_l")
                if bilateral:
                    tbl_rows.append([lbl, ax_l, "-"])
                else:
                    ax_r = _cell(prefix,"ax_r")
                    tbl_rows.append([lbl, ax_l, ax_r])
            filtered = _filter_rows(tbl_rows)
            if filtered:
                sl.append(f"  {title}:")
                sl.extend(_raw_table(["", "Ax L", "Ax R"], filtered))
            elif not clean:
                sl.append(f"  {title}:")
                sl.extend(_raw_table(["", "Ax L", "Ax R"], tbl_rows))
        for key, lbl in [("am_lx_notes","Lumbar notes"),("am_tx_notes","Thoracic notes")]:
            v = act.get(key, "").strip()
            if v:
                sl.append(f"  {lbl}: {v}")
            elif not clean:
                sl.append(f"  {lbl}: (empty)")
        if any(k.startswith("cx_") or k.startswith("tx_cx_") for k in act):
            def _cx_cell_r(p, s):
                v  = act.get(f"{p}_{s}_range","") or ""
                t  = f"{v}°" if v else "-"
                return t
            for cx_title, cx_rows_def in [
                ("Cervical ROM", [("Flexion","cx_flex",True),("Extension","cx_ext",True),
                                  ("Lat Flex","cx_lf",False),("Rotation","cx_rot",False)]),
                ("Thoracic ROM (Cx)", [("Flexion","tx_cx_flex",True),("Extension","tx_cx_ext",True),
                                       ("Rotation","tx_cx_rot",False)]),
            ]:
                cx_tbl = []
                for cx_lbl, cx_pfx, cx_bil in cx_rows_def:
                    ax_l = _cx_cell_r(cx_pfx,"ax_l")
                    if cx_bil:
                        cx_tbl.append([cx_lbl, ax_l, "-"])
                    else:
                        cx_tbl.append([cx_lbl, ax_l, _cx_cell_r(cx_pfx,"ax_r")])
                filtered = _filter_rows(cx_tbl)
                if filtered:
                    sl.append(f"  {cx_title}:")
                    sl.extend(_raw_table(["", "Ax L", "Ax R"], filtered))
                elif not clean:
                    sl.append(f"  {cx_title}:")
                    sl.extend(_raw_table(["", "Ax L", "Ax R"], cx_tbl))
            for key, lbl in [("am_cx_notes","Cervical notes"),
                              ("am_tx_cx_notes","Thoracic (Cx) notes")]:
                v = act.get(key, "").strip()
                if v:
                    sl.append(f"  {lbl}: {v}")
                elif not clean:
                    sl.append(f"  {lbl}: (empty)")
        if any(k.startswith("sh_") or k.startswith("tx_sh_") for k in act):
            def _sh_cell_r(p, s):
                v  = act.get(f"{p}_{s}_range", "") or ""
                t  = f"{v}°" if v else "-"
                return t
            sh_rom_def_r = [("Flexion","sh_flex"),("Extension","sh_ext"),
                            ("Abduction","sh_abd"),("Int Rotation","sh_ir"),
                            ("Ext Rotation","sh_er"),("Horiz Add","sh_hadd"),
                            ("Hand Bk Back","sh_hbb")]
            sh_tbl_r = [[lbl, _sh_cell_r(p,"ax_l"), _sh_cell_r(p,"ax_r")]
                        for lbl, p in sh_rom_def_r]
            filtered = _filter_rows(sh_tbl_r)
            if filtered:
                sl.append("  Shoulder ROM:")
                sl.extend(_raw_table(["","Ax L","Ax R"], filtered))
            elif not clean:
                sl.append("  Shoulder ROM:")
                sl.extend(_raw_table(["","Ax L","Ax R"], sh_tbl_r))
            tx_sh_def_r = [("Flexion","tx_sh_flex",True),("Extension","tx_sh_ext",True),
                           ("Rotation","tx_sh_rot",False)]
            tx_sh_tbl_r = []
            for sh_lbl, sh_pfx, sh_bil in tx_sh_def_r:
                ax_l = _sh_cell_r(sh_pfx,"ax_l")
                if sh_bil:
                    tx_sh_tbl_r.append([sh_lbl, ax_l, "-"])
                else:
                    tx_sh_tbl_r.append([sh_lbl, ax_l, _sh_cell_r(sh_pfx,"ax_r")])
            filtered = _filter_rows(tx_sh_tbl_r)
            if filtered:
                sl.append("  Thoracic ROM (Sh):")
                sl.extend(_raw_table(["","Ax L","Ax R"], filtered))
            elif not clean:
                sl.append("  Thoracic ROM (Sh):")
                sl.extend(_raw_table(["","Ax L","Ax R"], tx_sh_tbl_r))
            for key, lbl in [("am_sh_notes","Shoulder notes"),
                              ("am_tx_sh_notes","Thoracic (Sh) notes")]:
                v = act.get(key, "").strip()
                if v:
                    sl.append(f"  {lbl}: {v}")
                elif not clean:
                    sl.append(f"  {lbl}: (empty)")
        if any(k.startswith("hp_") for k in act):
            def _hp_cell_r(p, s):
                v  = act.get(f"{p}_{s}_range", "") or ""
                t  = f"{v}°" if v else "-"
                return t
            hp_rom_def_r = [("Flexion","hp_flex"),("Extension","hp_ext"),
                            ("Abduction","hp_abd"),("Adduction","hp_add"),
                            ("Int Rotation","hp_ir"),("Ext Rotation","hp_er")]
            hp_tbl_r = [[lbl, _hp_cell_r(p,"ax_l"), _hp_cell_r(p,"ax_r")]
                        for lbl, p in hp_rom_def_r]
            filtered = _filter_rows(hp_tbl_r)
            if filtered:
                sl.append("  Hip ROM:")
                sl.extend(_raw_table(["","Ax L","Ax R"], filtered))
            elif not clean:
                sl.append("  Hip ROM:")
                sl.extend(_raw_table(["","Ax L","Ax R"], hp_tbl_r))
            v = act.get("am_hp_notes", "").strip()
            if v:
                sl.append(f"  Hip notes: {v}")
            elif not clean:
                sl.append("  Hip notes: (empty)")
        if any(k.startswith("kn_") for k in act):
            def _kn_cell_r(p, s):
                v  = act.get(f"{p}_{s}_range", "") or ""
                t  = f"{v}°" if v else "-"
                return t
            kn_rom_def_r = [("Flexion","kn_flex"),("Extension","kn_ext")]
            kn_tbl_r = [[lbl, _kn_cell_r(p,"ax_l"), _kn_cell_r(p,"ax_r")]
                        for lbl, p in kn_rom_def_r]
            filtered = _filter_rows(kn_tbl_r)
            if filtered:
                sl.append("  Knee ROM:")
                sl.extend(_raw_table(["","Ax L","Ax R"], filtered))
            elif not clean:
                sl.append("  Knee ROM:")
                sl.extend(_raw_table(["","Ax L","Ax R"], kn_tbl_r))
            v = act.get("am_kn_notes", "").strip()
            if v:
                sl.append(f"  Knee notes: {v}")
            elif not clean:
                sl.append("  Knee notes: (empty)")
        if any(k.startswith("ak_") for k in act):
            def _ak_cell_r(p, s):
                v  = act.get(f"{p}_{s}_range", "") or ""
                t  = f"{v}°" if v else "-"
                return t
            ak_rom_def_r = [("Dorsiflexion","ak_df"),("Plantarflexion","ak_pf"),
                            ("Inversion","ak_inv"),("Eversion","ak_ev"),
                            ("WB DF (lunge)","ak_wbdf")]
            ak_tbl_r = [[lbl, _ak_cell_r(p,"ax_l"), _ak_cell_r(p,"ax_r")]
                        for lbl, p in ak_rom_def_r]
            filtered = _filter_rows(ak_tbl_r)
            if filtered:
                sl.append("  Ankle ROM:")
                sl.extend(_raw_table(["","Ax L","Ax R"], filtered))
            elif not clean:
                sl.append("  Ankle ROM:")
                sl.extend(_raw_table(["","Ax L","Ax R"], ak_tbl_r))
            v = act.get("am_ak_notes", "").strip()
            if v:
                sl.append(f"  Ankle notes: {v}")
            elif not clean:
                sl.append("  Ankle notes: (empty)")
        _flush_section("02 Active Movement", sl)

    # ── 03 Passive Movement ───────────────────────────────────────────────────
    def _fmt_pas_r(norm: str | None, txt: str | None) -> str:
        n = norm == "Norm"
        t = (txt or "").strip()
        if n and t:
            return f"Normal; {t}"
        if n:
            return "Normal"
        return t or "-"

    if pas:
        sl = []
        _lx_op_r = [("Tx Flexion","op_tx_flex",False),("Tx Extension","op_tx_ext",False),
                    ("Tx Rotation","op_tx_rot",True),
                    ("Lx Flexion","op_lx_flex",False),("Lx Extension","op_lx_ext",False),
                    ("Lx Lat Flex","op_lx_lf",True)]
        op_rows = [[lbl,
                    (f"L: {_fmt_pas_r(pas.get(f'{p}_l_norm'),pas.get(f'{p}_l_txt'))} / "
                     f"R: {_fmt_pas_r(pas.get(f'{p}_r_norm'),pas.get(f'{p}_r_txt'))}")
                    if bi else _fmt_pas_r(pas.get(f"{p}_norm"), pas.get(f"{p}_txt"))]
                   for lbl, p, bi in _lx_op_r]
        _maybe_table(sl, ["Overpressure", "Findings"], op_rows)
        paivm_levels = ["T8","T9","T10","T11","T12","L1","L2","L3","L4","L5"]
        paivm_rows = [[lv,
                       _fmt_pas_r(pas.get(f"pm_{lv}_l_norm"), None),
                       _fmt_pas_r(pas.get(f"pm_{lv}_c_norm"), None),
                       _fmt_pas_r(pas.get(f"pm_{lv}_r_norm"), None),
                       (pas.get(f"pm_{lv}_txt") or "").strip() or "-"]
                      for lv in paivm_levels]
        _maybe_table(sl, ["PAIVM", "L", "C", "R", "Notes"], paivm_rows)
        for key, lbl in [("pm_op_notes","OP notes"),("pm_paivm_notes","PAIVM notes")]:
            v = pas.get(key, "").strip()
            if v:
                sl.append(f"  {lbl}: {v}")
            elif not clean:
                sl.append(f"  {lbl}: (empty)")
        if any(k.startswith("cx_op_") or k.startswith("cx_pm_") for k in pas):
            _cx_op_r = [("Flexion","cx_op_flex",False),("Extension","cx_op_ext",False),
                        ("Lat Flex","cx_op_lf",True),("Rotation","cx_op_rot",True),
                        ("Quadrant","cx_op_quad",True)]
            cx_op_rows_r = [[lbl,
                             (f"L: {_fmt_pas_r(pas.get(f'{p}_l_norm'),pas.get(f'{p}_l_txt'))} / "
                              f"R: {_fmt_pas_r(pas.get(f'{p}_r_norm'),pas.get(f'{p}_r_txt'))}")
                             if bi else _fmt_pas_r(pas.get(f"{p}_norm"), pas.get(f"{p}_txt"))]
                            for lbl, p, bi in _cx_op_r]
            _maybe_table(sl, ["Cervical OP","Findings"], cx_op_rows_r)
            cx_paivm_levels_r = [("C0/1","C0_1"),("C1/2","C1_2"),("C2","C2"),("C3","C3"),
                                 ("C4","C4"),("C5","C5"),("C6","C6"),("C7","C7"),
                                 ("T1","T1"),("T2","T2"),("T3","T3"),("T4","T4")]
            cx_paivm_rows_r = [[lv,
                                 _fmt_pas_r(pas.get(f"cx_pm_{k}_l_norm"), None),
                                 _fmt_pas_r(pas.get(f"cx_pm_{k}_c_norm"), None),
                                 _fmt_pas_r(pas.get(f"cx_pm_{k}_r_norm"), None),
                                 (pas.get(f"cx_pm_{k}_txt") or "").strip() or "-"]
                                for lv, k in cx_paivm_levels_r]
            _maybe_table(sl, ["Cervical PAIVMs","L","C","R","Notes"], cx_paivm_rows_r)
            for key, lbl in [("cx_pm_op_notes","Cervical OP notes"),
                              ("cx_pm_paivm_notes","Cervical PAIVM notes")]:
                v = pas.get(key, "").strip()
                if v:
                    sl.append(f"  {lbl}: {v}")
                elif not clean:
                    sl.append(f"  {lbl}: (empty)")
        if any(k.startswith("sh_op_") or k.startswith("sh_acc_") or
               k.startswith("sh_ac_pm") or k.startswith("sh_sc_pm") for k in pas):
            sh_op_def_r = [("Flexion","sh_op_flex"),("Extension","sh_op_ext"),
                           ("Abduction","sh_op_abd"),("Int Rot","sh_op_ir"),
                           ("Ext Rot","sh_op_er"),("Horiz Add","sh_op_hadd"),
                           ("Horiz Abd","sh_op_habd")]
            sh_op_rows_r = [[lbl,
                             _fmt_pas_r(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                             _fmt_pas_r(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                            for lbl, p in sh_op_def_r]
            _maybe_table(sl, ["Shoulder OP","Left","Right"], sh_op_rows_r)
            for side, side_lbl in (("l","Left"),("r","Right")):
                acc_rows_r = [[dir_lbl,
                               _fmt_pas_r(pas.get(f"sh_acc_{dk}_{side}_norm"),
                                          pas.get(f"sh_acc_{dk}_{side}_txt"))]
                              for dir_lbl, dk in (("Inferior","inf"),("Posterior","post"),("Anterior","ant"))]
                _maybe_table(sl, [f"GH Accessory {side_lbl}","Findings"], acc_rows_r)
            acsc_rows_r = [[lbl,
                            _fmt_pas_r(pas.get(f"{pfx}_l_norm"), pas.get(f"{pfx}_l_txt")),
                            _fmt_pas_r(pas.get(f"{pfx}_r_norm"), pas.get(f"{pfx}_r_txt"))]
                           for lbl, pfx in (("AC Stress","sh_ac_pm_stress"),
                                            ("AC Palp","sh_ac_pm_palp"),
                                            ("SC Stress","sh_sc_pm_stress"))]
            _maybe_table(sl, ["AC / SC Joint","Left","Right"], acsc_rows_r)
            for key, lbl in [("sh_pm_op_notes","Shoulder OP notes"),
                              ("sh_pm_acc_notes","Accessory notes")]:
                v = pas.get(key, "").strip()
                if v:
                    sl.append(f"  {lbl}: {v}")
                elif not clean:
                    sl.append(f"  {lbl}: (empty)")
        if any(k.startswith("hp_op_") or k.startswith("hp_acc_") for k in pas):
            hp_op_def_r = [("Flexion","hp_op_flex"),("Extension","hp_op_ext"),
                           ("Abduction","hp_op_abd"),("Adduction","hp_op_add"),
                           ("Int Rot","hp_op_ir"),("Ext Rot","hp_op_er")]
            hp_op_rows_r = [[lbl,
                             _fmt_pas_r(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                             _fmt_pas_r(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                            for lbl, p in hp_op_def_r]
            _maybe_table(sl, ["Hip OP","Left","Right"], hp_op_rows_r)
            hp_acc_def_r = [("Distraction","hp_acc_dist"),("Lateral","hp_acc_lat")]
            hp_acc_rows_r = [[lbl,
                              _fmt_pas_r(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                              _fmt_pas_r(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                             for lbl, p in hp_acc_def_r]
            _maybe_table(sl, ["Hip Accessory","Left","Right"], hp_acc_rows_r)
            v = pas.get("hp_op_notes", "").strip()
            if v:
                sl.append(f"  Hip OP notes: {v}")
            elif not clean:
                sl.append("  Hip OP notes: (empty)")
        if any(k.startswith("kn_op_") or k.startswith("kn_acc_") for k in pas):
            kn_op_def_r = [("Flexion","kn_op_flex"),("Extension","kn_op_ext")]
            kn_op_rows_r = [[lbl,
                             _fmt_pas_r(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                             _fmt_pas_r(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                            for lbl, p in kn_op_def_r]
            _maybe_table(sl, ["Knee OP","Left","Right"], kn_op_rows_r)
            kn_acc_def_r = [("AP Glide","kn_acc_ap"),("Patella Med","kn_acc_pmed"),
                            ("Patella Lat","kn_acc_plat")]
            kn_acc_rows_r = [[lbl,
                              _fmt_pas_r(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                              _fmt_pas_r(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                             for lbl, p in kn_acc_def_r]
            _maybe_table(sl, ["Knee Accessory","Left","Right"], kn_acc_rows_r)
            v = pas.get("kn_op_notes", "").strip()
            if v:
                sl.append(f"  Knee OP notes: {v}")
            elif not clean:
                sl.append("  Knee OP notes: (empty)")
        if any(k.startswith("ak_op_") or k.startswith("ak_acc_") for k in pas):
            ak_op_def_r = [("Dorsiflexion","ak_op_df"),("Plantarflexion","ak_op_pf"),
                           ("Inversion","ak_op_inv"),("Eversion","ak_op_ev")]
            ak_op_rows_r = [[lbl,
                             _fmt_pas_r(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                             _fmt_pas_r(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                            for lbl, p in ak_op_def_r]
            _maybe_table(sl, ["Ankle OP","Left","Right"], ak_op_rows_r)
            ak_acc_def_r = [("AP Glide","ak_acc_ap"),("Subtalar","ak_acc_st")]
            ak_acc_rows_r = [[lbl,
                              _fmt_pas_r(pas.get(f"{p}_l_norm"), pas.get(f"{p}_l_txt")),
                              _fmt_pas_r(pas.get(f"{p}_r_norm"), pas.get(f"{p}_r_txt"))]
                             for lbl, p in ak_acc_def_r]
            _maybe_table(sl, ["Ankle Accessory","Left","Right"], ak_acc_rows_r)
            v = pas.get("ak_op_notes", "").strip()
            if v:
                sl.append(f"  Ankle OP notes: {v}")
            elif not clean:
                sl.append("  Ankle OP notes: (empty)")
        _flush_section("03 Passive Movement & Overpressure", sl)

    # ── 04 Neurological ───────────────────────────────────────────────────────
    if neu:
        sl = []
        ul_reflex_def = [("Biceps C5/6","nr_biceps"),("Brachiorad C6","nr_brad"),
                         ("Triceps C7","nr_triceps")]
        ul_reflex_rows = [[lbl, neu.get(f"{p}_l") or "-", neu.get(f"{p}_r") or "-"]
                          for lbl, p in ul_reflex_def]
        _maybe_table(sl, ["UL Reflexes", "Left", "Right"], ul_reflex_rows)
        v = neu.get("nr_ul_reflex_notes", "").strip()
        if v: sl.append(f"  UL Reflex notes: {v}")
        elif not clean: sl.append("  UL Reflex notes: (empty)")
        ul_myotome_def = [("C5 Shldr abd","nr_c5"),("C6 Wrist ext","nr_c6"),
                          ("C7 Elbow ext","nr_c7"),("C8 Finger flx","nr_c8"),
                          ("T1 Finger abd","nr_t1")]
        ul_myotome_rows = [[lbl, neu.get(f"{p}_l") or "-", neu.get(f"{p}_r") or "-"]
                           for lbl, p in ul_myotome_def]
        _maybe_table(sl, ["UL Myotomes", "Left", "Right"], ul_myotome_rows)
        v = neu.get("nr_ul_myotome_notes", "").strip()
        if v: sl.append(f"  UL Myotome notes: {v}")
        elif not clean: sl.append("  UL Myotome notes: (empty)")
        ul_derm_def = [("C5 Lat arm/delt","sn_c5"),("C6 Thumb & index","sn_c6"),
                       ("C7 Middle finger","sn_c7"),("C8 Little/ulnar","sn_c8"),
                       ("T1 Med forearm","sn_t1")]
        ul_derm_rows = [[lbl, neu.get(f"{p}_l") or "-", neu.get(f"{p}_r") or "-"]
                        for lbl, p in ul_derm_def]
        _maybe_table(sl, ["UL Dermatomes", "Left", "Right"], ul_derm_rows)
        v = neu.get("nr_ul_derm_notes", "").strip()
        if v: sl.append(f"  UL Dermatome notes: {v}")
        elif not clean: sl.append("  UL Dermatome notes: (empty)")
        ulnt_def = [("ULNT1","nr_ulnt1"),("ULNT2a","nr_ulnt2a"),("ULNT3","nr_ulnt3")]
        ulnt_rows = [[lbl, neu.get(f"{p}_l_resp","") or "-", neu.get(f"{p}_r_resp","") or "-"]
                     for lbl, p in ulnt_def]
        _maybe_table(sl, ["UL Neurodynamics", "L Response", "R Response"], ulnt_rows)
        v = neu.get("nr_ul_nd_notes", "").strip()
        if v: sl.append(f"  UL Neurodynamics notes: {v}")
        elif not clean: sl.append("  UL Neurodynamics notes: (empty)")
        neuro_def = [("Knee jerk L3/4","nr_knee"),("Ankle jerk S1","nr_ankle"),
                     ("L2 Hip flex","nr_l2"),("L3 Knee ext","nr_l3"),
                     ("L4 Ankle DF","nr_l4"),("L5 GT ext/EHL","nr_l5"),
                     ("S1 PF/evert","nr_s1"),("S2 Ham/KF","nr_s2")]
        neuro_rows = [[lbl, neu.get(f"{p}_l") or "-", neu.get(f"{p}_r") or "-"]
                      for lbl, p in neuro_def]
        _maybe_table(sl, ["LL Reflexes & Myotomes", "Left", "Right"], neuro_rows)
        v = neu.get("nr_ll_reflex_notes", "").strip()
        if v: sl.append(f"  LL Reflex notes: {v}")
        elif not clean: sl.append("  LL Reflex notes: (empty)")
        v = neu.get("nr_ll_myotome_notes", "").strip()
        if v: sl.append(f"  LL Myotome notes: {v}")
        elif not clean: sl.append("  LL Myotome notes: (empty)")
        _derm_raw = [("L2 Ant thigh","sn_l2"),("L3 Med knee","sn_l3"),
                     ("L4 Med leg","sn_l4"),("L5 Lat leg/GT","sn_l5"),
                     ("S1 Lat foot","sn_s1"),("S2 Post thigh","sn_s2")]
        derm_raw_rows = [[lbl, neu.get(f"{p}_l") or "-", neu.get(f"{p}_r") or "-"]
                         for lbl, p in _derm_raw]
        _maybe_table(sl, ["LL Dermatomes", "Left", "Right"], derm_raw_rows)
        v = neu.get("nr_ll_derm_notes", "").strip()
        if v: sl.append(f"  LL Dermatome notes: {v}")
        elif not clean: sl.append("  LL Dermatome notes: (empty)")
        nd_def = [("SLR","nr_slr"),("Slump","nr_slump"),("PKF","nr_pkf")]
        nd_rows = []
        for lbl, p in nd_def:
            ld = neu.get(f"{p}_l_deg","") or ""; lr = neu.get(f"{p}_l_resp","") or "-"
            rd = neu.get(f"{p}_r_deg","") or ""; rr = neu.get(f"{p}_r_resp","") or "-"
            nd_rows.append([lbl, f"{ld}°" if ld else "-", lr,
                                  f"{rd}°" if rd else "-", rr])
        _maybe_table(sl, ["LL Neurodynamics","L°","L Resp","R°","R Resp"], nd_rows)
        v = neu.get("nr_ll_nd_notes", "").strip()
        if v: sl.append(f"  LL Neurodynamics notes: {v}")
        elif not clean: sl.append("  LL Neurodynamics notes: (empty)")
        umn_items = [("Hyperreflexia","nr_umn_hyper"),("Babinski +","nr_umn_bab"),
                     ("Clonus","nr_umn_clonus"),("Romberg +","nr_umn_romberg"),
                     ("Coord impaired","nr_umn_coord"),
                     ("Hoffman's","nr_umn_hoffman"),("Tromner","nr_umn_tromner"),
                     ("Lhermitte's","nr_umn_lhermitte"),("Inv Supinator","nr_umn_inv_sup")]
        for lbl, uid in umn_items:
            v = neu.get(uid)
            if clean and v is None:
                continue
            sl.append(f"  {lbl}: {'✓ Yes' if v is True else '✗ No' if v is False else '(not answered)'}")
        v = neu.get("nr_umn_notes", "").strip()
        if v: sl.append(f"  UMN notes: {v}")
        elif not clean: sl.append("  UMN notes: (empty)")
        v = neu.get("nr_notes", "").strip()
        if v:
            sl.append(f"  Notes: {v}")
        elif not clean:
            sl.append("  Notes: (empty)")
        _flush_section("04 Neurological", sl)

    # ── 05 Sensory ────────────────────────────────────────────────────────────
    if sen:
        sl = []
        ppt_raw = (sen.get("sn_ppt") or "").strip()
        ppt_detail_raw = sen.get("sn_ppt_detail", "").strip()
        if ppt_raw:
            sl.append(f"  PPT (algometer): {ppt_raw}" + (f" — {ppt_detail_raw}" if ppt_detail_raw else ""))
        elif not clean:
            sl.append("  PPT (algometer): (not recorded)")
        hypo_items = [("Sharp/blunt","sn_sharp_blunt",True),
                      ("Two-point discrim","sn_tpd",True),
                      ("Light touch","sn_lt",True),
                      ("Body perception","sn_body",False)]
        hyper_items = [("Static allodynia","sn_static_allodynia",True),
                       ("Dynamic allodynia","sn_dynamic_allodynia",True),
                       ("2° hyperalgesia PPT","sn_secondary_hyper",True),
                       ("Pin prick hyper","sn_pin_prick",True),
                       ("Cold hyperalgesia","sn_cold",True),
                       ("Heat hyperalgesia","sn_heat",True),
                       ("Temporal summation","sn_temporal_sum",True),
                       ("Conditioned pain modulation","sn_cpm",True),
                       ("Nerve trunk palpation","sn_nerve_palpation",True)]
        for items in (hypo_items, hyper_items):
            for lbl, sid, has_detail in items:
                v = sen.get(sid)
                if clean and v is None:
                    continue
                detail = sen.get(f"{sid}_detail", "").strip() if has_detail else ""
                state = "✓ Yes" if v is True else "✗ No" if v is False else "(not answered)"
                sl.append(f"  {lbl}: {state}" + (f" — {detail}" if detail and v is True else ""))
        v = sen.get("sn_notes", "").strip()
        if v:
            sl.append(f"  Notes: {v}")
        elif not clean:
            sl.append("  Notes: (empty)")
        _flush_section("05 Sensory", sl)

    # ── 06 Muscle Testing ─────────────────────────────────────────────────────
    _lower_regions_r = set(active_regions or [])
    if mus or _lower_regions_r & {"hip", "knee", "ankle"}:
        sl = []
        ml_def = [("QL (side sit)","ml_ql"),("Thomas test","ml_thomas"),
                  ("Hamstrings SLR","ml_ham")]
        ml_rows = [[lbl, mus.get(f"{p}_l") or "-", mus.get(f"{p}_r") or "-"]
                   for lbl, p in ml_def]
        _maybe_table(sl, ["Muscle Length", "Left", "Right"], ml_rows)
        ma_def = [("Tx erector spinae","ma_tx_es"),("Transversus abd","ma_tva"),
                  ("Lumbar multifidus","ma_lmf")]
        ma_rows = [[lbl, mus.get(mid) or "-"] for lbl, mid in ma_def]
        _maybe_table(sl, ["Activation", "Finding"], ma_rows)
        for key, lbl, unit in [("st_flex","Trunk flexion","reps/min"),
                                ("st_ext","Trunk extension","raises/min")]:
            v = (mus.get(key) or "").strip()
            if v:
                sl.append(f"  {lbl}: {v} {unit}")
            elif not clean:
                sl.append(f"  {lbl}: (not recorded) {unit}")
        hip_def = [("Hip flexion","sh_hip_flex"),("Hip extension","sh_hip_ext"),
                   ("Hip abduction","sh_hip_abd"),("Hip adduction","sh_hip_add"),
                   ("Hip int rotation","sh_hip_ir"),("Hip ext rotation","sh_hip_er")]
        hip_rows = [[lbl, mus.get(f"{p}_l") or "-", mus.get(f"{p}_r") or "-"]
                    for lbl, p in hip_def]
        _maybe_table(sl, ["Hip Strength (kg)", "Left", "Right"], hip_rows)
        sij_items = [("Sacral thrust","sij_sacral"),("Post thigh thrust","sij_ptt"),
                     ("Distraction supine","sij_dist"),("Compression s/l","sij_comp"),
                     ("Gaenslen","sij_gaenslen"),("ASLR compression","sij_aslr")]
        for lbl, sid in sij_items:
            v = mus.get(sid)
            if clean and v is None:
                continue
            sl.append(f"  SIJ {lbl}: {'✓ Yes' if v is True else '✗ No' if v is False else '(not answered)'}")
        cx_ml_def = [("Upper trapezius","ml_ut"),("Levator scapulae","ml_ls"),
                     ("Pectorals","ml_pec"),("Scalenes","ml_scal")]
        cx_ml_rows = [[lbl, mus.get(f"{p}_l") or "-", mus.get(f"{p}_r") or "-"]
                      for lbl, p in cx_ml_def]
        _maybe_table(sl, ["Cervical Muscle Length", "Left", "Right"], cx_ml_rows)
        cx_ma_def = [("Deep cerv flexors","ma_dcf"),("Cervical extensors","ma_cx_ext"),
                     ("Serratus anterior","ma_sa")]
        cx_ma_rows = [[lbl, mus.get(mid) or "-"] for lbl, mid in cx_ma_def]
        _maybe_table(sl, ["Cervical Activation", "Finding"], cx_ma_rows)
        dcf_end = (mus.get("st_dcf_end") or "").strip()
        if dcf_end:
            sl.append(f"  DCF endurance: {dcf_end} s")
        elif not clean:
            sl.append("  DCF endurance: (not recorded) s")
        if any(k.startswith("cx_neck_") for k in mus):
            cx_neck_def_r = [("Neck flexion","cx_neck_flex"),("Neck extension","cx_neck_ext"),
                             ("Neck lat flex","cx_neck_lf"),("Neck rotation","cx_neck_rot")]
            cx_neck_rows_r = [[lbl, mus.get(f"{p}_l") or "-", mus.get(f"{p}_r") or "-"]
                              for lbl, p in cx_neck_def_r]
            _maybe_table(sl, ["Neck Strength (kg)","Left","Right"], cx_neck_rows_r)
        for key, lbl in [("mu_cx_notes","Cervical muscle notes"),("mu_notes","Notes")]:
            v = mus.get(key, "").strip()
            if v:
                sl.append(f"  {lbl}: {v}")
            elif not clean:
                sl.append(f"  {lbl}: (empty)")
        if any(k.startswith("sh_str_") or k.startswith("ml_pec_") or
               k.startswith("ml_post_cap") or k.startswith("ma_lt_") or
               k.startswith("ma_er_fc") for k in mus):
            sh_ml_def_r = [("Pec minor","ml_pec_min"),("Pec maj sternal","ml_pec_st"),
                           ("Pec maj clav","ml_pec_cl"),("Latissimus","ml_lat"),
                           ("Post capsule","ml_post_cap")]
            sh_ml_rows_r = [[lbl, mus.get(f"{p}_l") or "-", mus.get(f"{p}_r") or "-"]
                            for lbl, p in sh_ml_def_r]
            _maybe_table(sl, ["Shoulder Muscle Length","Left","Right"], sh_ml_rows_r)
            sh_ma_def_r = [("Lower trap","ma_lt"),("Serratus ant","ma_sa"),
                           ("ER force couple","ma_er_fc")]
            sh_ma_rows_r = [[lbl, mus.get(f"{p}_l") or "-", mus.get(f"{p}_r") or "-"]
                            for lbl, p in sh_ma_def_r]
            _maybe_table(sl, ["Shoulder Activation","Left","Right"], sh_ma_rows_r)
            sh_str_def_r = [("Flexion","sh_str_flex"),("Abduction","sh_str_abd"),
                            ("Int Rot","sh_str_ir"),("Ext Rot","sh_str_er"),
                            ("Scaption","sh_str_scap")]
            sh_str_rows_r = [[lbl, mus.get(f"{p}_l") or "-", mus.get(f"{p}_r") or "-"]
                             for lbl, p in sh_str_def_r]
            _maybe_table(sl, ["Shoulder Strength (kg/0-5)","Left","Right"], sh_str_rows_r)
            v = mus.get("mu_sh_notes", "").strip()
            if v:
                sl.append(f"  Shoulder muscle notes: {v}")
            elif not clean:
                sl.append("  Shoulder muscle notes: (empty)")
        if "hip" in _lower_regions_r or any(k.startswith("hp_str_") for k in mus):
            hp_str_def_r = [("Flexion","hp_str_flex"),("Extension","hp_str_ext"),
                            ("Abduction","hp_str_abd"),("Adduction","hp_str_add"),
                            ("Int Rot","hp_str_ir"),("Ext Rot","hp_str_er")]
            hp_str_rows_r = [[lbl, mus.get(f"{p}_l") or "-", mus.get(f"{p}_r") or "-"]
                             for lbl, p in hp_str_def_r]
            _maybe_table(sl, ["Hip Strength (kg/0-5)","Left","Right"], hp_str_rows_r)
            v = mus.get("mu_hp_notes", "").strip()
            if v:
                sl.append(f"  Hip muscle notes: {v}")
            elif not clean:
                sl.append("  Hip muscle notes: (empty)")
        if "knee" in _lower_regions_r or any(k.startswith("kn_str_") for k in mus):
            kn_str_def_r = [("Extension (quads)","kn_str_ext"),
                            ("Flexion (hamstring)","kn_str_flex"),
                            ("Calf (heel raise)","kn_str_calf")]
            kn_str_rows_r = [[lbl, mus.get(f"{p}_l") or "-", mus.get(f"{p}_r") or "-"]
                             for lbl, p in kn_str_def_r]
            _maybe_table(sl, ["Knee/Calf Strength (kg/0-5)","Left","Right"], kn_str_rows_r)
            v = mus.get("mu_kn_notes", "").strip()
            if v:
                sl.append(f"  Knee muscle notes: {v}")
            elif not clean:
                sl.append("  Knee muscle notes: (empty)")
        if "ankle" in _lower_regions_r or any(k.startswith("ak_str_") for k in mus):
            ak_str_def_r = [("Dorsiflexion (TA)","ak_str_df"),
                            ("Plantarflexion (GS)","ak_str_pf"),
                            ("Eversion (peroneals)","ak_str_ev")]
            ak_str_rows_r = [[lbl, mus.get(f"{p}_l") or "-", mus.get(f"{p}_r") or "-"]
                             for lbl, p in ak_str_def_r]
            _maybe_table(sl, ["Ankle Strength (kg/0-5)","Left","Right"], ak_str_rows_r)
            v = mus.get("mu_ak_notes", "").strip()
            if v:
                sl.append(f"  Ankle muscle notes: {v}")
            elif not clean:
                sl.append("  Ankle muscle notes: (empty)")
        _flush_section("06 Muscle Testing", sl)

    # ── 02 Functional ─────────────────────────────────────────────────────────
    if func:
        sl = []
        obs_def = [
            ("Gait",         "ft_gait",  "ft_gait_obs"),
            ("Sit-to-stand", "ft_sts_q", "ft_sts_obs"),
            ("Squat",        "ft_squat", "ft_squat_obs"),
            ("Lunge",        "ft_lunge", "ft_lunge_obs"),
            ("Lifting",      "ft_lift",  "ft_lift_obs"),
            ("Carrying",     "ft_carry", "ft_carry_obs"),
            ("Reaching",     "ft_reach", "ft_reach_obs"),
        ]
        obs_rows = []
        for lbl, rid, iid in obs_def:
            parts = [p for p in [func.get(rid) or "", func.get(iid, "").strip()] if p]
            obs_rows.append([lbl, " - ".join(parts) if parts else "-"])
        _maybe_table(sl, ["Movement Obs", "Finding"], obs_rows)
        bal_def = [("Both legs",["ft_bal_both"],"s"),("Feet together",["ft_bal_feet"],"s"),
                   ("Tandem",["ft_bal_tandem"],"s"),
                   ("SLS eyes open",["ft_sls_eo_l","ft_sls_eo_r"],"s"),
                   ("SLS eyes closed",["ft_sls_ec_l","ft_sls_ec_r"],"s"),
                   ("SLS foam 10cm",["ft_sls_foam_l","ft_sls_foam_r"],"s")]
        bal_rows = []
        for lbl, ids, _ in bal_def:
            vals = [func.get(i,"") or "-" for i in ids]
            if len(ids) == 1:
                vals = [vals[0], "-"]
            bal_rows.append([lbl] + vals)
        _maybe_table(sl, ["Balance (Steffen)", "Left s", "Right s"], bal_rows)
        cap_def = [("TUG (3m)","ft_tug","s"),("5× STS","ft_sts5","s"),
                   ("10m comfortable","ft_10m_e","m/s"),("10m fast","ft_10m_f","m/s"),
                   ("2 min walk","ft_2mw","m")]
        cap_rows = [[lbl, f"{func.get(fid,'') or '-'} {unit}".strip()]
                    for lbl, fid, unit in cap_def]
        _maybe_table(sl, ["Timed Capability", "Result"], cap_rows)
        v = func.get("ft_fm_obs", "").strip()
        if v:
            sl.append(f"  Functional obs: {v}")
        elif not clean:
            sl.append("  Functional obs: (empty)")
        v = func.get("ft_fm_custom", "").strip()
        if v:
            sl.append(f"  Custom Func test: {v}")
        elif not clean:
            sl.append("  Custom Func test: (empty)")
        v = func.get("ft_notes", "").strip()
        if v:
            sl.append(f"  Notes: {v}")
        elif not clean:
            sl.append("  Notes: (empty)")
        _flush_section("02 Functional", sl)

    # ── 08 Special Tests ──────────────────────────────────────────────────────
    if spl:
        sl = []
        _LX_ST_GROUPS_R = [
            ("Disc/Herniation",[("SLR","st_slr"),("Crossed SLR","st_crossed_slr")]),
            ("Neurodynamics",  [("Slump","st_slump"),("Femoral","st_femoral")]),
            ("Hip Screen",     [("FABER","st_faber"),("FADIR","st_fadir")]),
            ("Instability",    [("Prone Inst","st_prone_inst")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _LX_ST_GROUPS_R for _, sid in rows):
            for grp_lbl, rows in _LX_ST_GROUPS_R:
                lx_st_rows_r = [[lbl, spl.get(f"{sid}_l") or "-", spl.get(f"{sid}_r") or "-"]
                                for lbl, sid in rows]
                _maybe_table(sl, [f"Lumbar {grp_lbl}","Left","Right"], lx_st_rows_r)
        _CX_ST_GROUPS_R = [
            ("Radiculopathy",  [("Spurling","st_spurling"),("Distraction","st_distraction")]),
            ("Neurodynamics",  [("ULNT1","st_ulnt1"),("ULNT2a","st_ulnt2a"),("ULNT3","st_ulnt3")]),
            ("CGH",            [("FRT","st_frt")]),
            ("Sharp-Purser",   [("Sharp-Purser","st_sharp_purser")]),
            ("Alar Ligament",  [("Ant Shear","st_ant_shear"),("Alar Lig SF","st_alar_sf"),
                                ("Alar Lig Rot","st_alar_rot"),("Lat Trans","st_lat_trans")]),
            ("VBI",            [("VBI Sus Rot","st_vbi_sus_rot")]),
            ("Motor Control",  [("CCFT","st_ccft")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _CX_ST_GROUPS_R for _, sid in rows):
            for grp_lbl, rows in _CX_ST_GROUPS_R:
                cx_st_rows_r = [[lbl, spl.get(f"{sid}_l") or "-", spl.get(f"{sid}_r") or "-"]
                                for lbl, sid in rows]
                _maybe_table(sl, [f"Cervical {grp_lbl}","Left","Right"], cx_st_rows_r)
        for key, lbl in [("st_lx_notes","Lumbar notes"),("st_cx_notes","Cervical notes"),
                          ("st_ccft_notes","CCFT notes (Lean angle / Nod / Lift / Hover)")]:
            v = spl.get(key, "").strip()
            if v:
                sl.append(f"  {lbl}: {v}")
            elif not clean:
                sl.append(f"  {lbl}: (empty)")
        _SH_ST_GROUPS_R = [
            ("Impingement",  [("Hawkins","st_hawkins"),("Neer","st_neer"),
                              ("Painful Arc","st_painful_arc"),("ER Resist","st_er_resist")]),
            ("Rotator Cuff", [("Empty Can","st_empty_can"),("Full Can","st_full_can"),
                              ("ER Lag","st_er_lag"),("Lift-off","st_lift_off"),
                              ("Belly Press","st_belly_press"),("Drop Arm","st_drop_arm"),
                              ("IR Lag","st_irls"),("Drop Sign (IS)","st_drop_is"),
                              ("Hornblower","st_hornblower")]),
            ("AC Joint",     [("Cross-body","st_cross_body"),("AC Stress","st_ac_stress"),
                              ("AC Resist Ext","st_ac_ext")]),
            ("Biceps/SLAP",  [("Speed's","st_speeds"),("Yergason","st_yergason"),
                              ("O'Brien","st_obrien"),("Passive Comp","st_pass_comp"),
                              ("Bicip Groove","st_bicip_groove")]),
            ("Instability",  [("Apprehension","st_apprehension"),("Relocation","st_relocation")]),
            ("Sulcus",       [("Sulcus","st_sulcus")]),
            ("Scapular Assistance", [("Scap Assist","st_scap_assist")]),
            ("Serratus Anterior",   [("Wall Pushup","st_wall_pushup")]),
            ("TOS",          [("Adson's","st_adson"),("Roos/EAST","st_roos"),
                              ("Wright's","st_wright"),("CRLF","st_crlf")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _SH_ST_GROUPS_R for _, sid in rows):
            for grp_lbl, rows in _SH_ST_GROUPS_R:
                sh_st_rows_r = [[lbl, spl.get(f"{sid}_l") or "-", spl.get(f"{sid}_r") or "-"]
                                for lbl, sid in rows]
                _maybe_table(sl, [f"Shoulder {grp_lbl}","Left","Right"], sh_st_rows_r)
            v = spl.get("st_sh_notes", "").strip()
            if v:
                sl.append(f"  Shoulder test notes: {v}")
            elif not clean:
                sl.append("  Shoulder test notes: (empty)")
        _HP_ST_GROUPS_R = [
            ("FAI/Impingement", [("FADIR","st_hp_fadir"),("Ant Impingement","st_hp_ant_imp")]),
            ("Hip OA",          [("FABER","st_hp_faber"),("Hip Scour","st_hp_hip_scour"),
                                 ("Log Roll","st_hp_log_roll")]),
            ("GTPS",            [("Ober","st_hp_ober"),("Trendelenburg","st_hp_trendelenburg"),
                                 ("SLS","st_hp_sls_hip")]),
            ("Hamstring Origin",[("Puranen-Orava","st_hp_puranen_orava"),("BKS","st_hp_bks")]),
            ("Adductor",        [("Squeeze","st_hp_squeeze")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _HP_ST_GROUPS_R for _, sid in rows):
            for grp_lbl, rows in _HP_ST_GROUPS_R:
                hp_st_rows_r = [[lbl, spl.get(f"{sid}_l") or "-", spl.get(f"{sid}_r") or "-"]
                                for lbl, sid in rows]
                _maybe_table(sl, [f"Hip {grp_lbl}","Left","Right"], hp_st_rows_r)
            v = spl.get("st_hp_notes", "").strip()
            if v:
                sl.append(f"  Hip test notes: {v}")
            elif not clean:
                sl.append("  Hip test notes: (empty)")
        _KN_ST_GROUPS_R = [
            ("ACL",     [("Lachman","st_kn_lachman"),("Ant Drawer","st_kn_ant_draw"),
                         ("Pivot Shift","st_kn_pivot")]),
            ("PCL",     [("Post Drawer","st_kn_post_draw"),("Post Sag","st_kn_post_sag")]),
            ("Meniscus",[("McMurray","st_kn_mcmurray"),("Thessaly","st_kn_thessaly"),
                         ("JLT","st_kn_jlt")]),
            ("MCL",     [("Valgus 0°","st_kn_valgus_0"),("Valgus 30°","st_kn_valgus_30")]),
            ("LCL",     [("Varus 0°","st_kn_varus_0"),("Varus 30°","st_kn_varus_30")]),
            ("PFJ",     [("Clarke's","st_kn_clarkes"),("Pat Tilt","st_kn_pat_tilt"),
                         ("Pat Grind","st_kn_pat_grind")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _KN_ST_GROUPS_R for _, sid in rows):
            for grp_lbl, rows in _KN_ST_GROUPS_R:
                kn_st_rows_r = [[lbl, spl.get(f"{sid}_l") or "-", spl.get(f"{sid}_r") or "-"]
                                for lbl, sid in rows]
                _maybe_table(sl, [f"Knee {grp_lbl}","Left","Right"], kn_st_rows_r)
            v = spl.get("st_kn_notes", "").strip()
            if v:
                sl.append(f"  Knee test notes: {v}")
            elif not clean:
                sl.append("  Knee test notes: (empty)")
        _AK_ST_GROUPS_R = [
            ("Lateral Lig",  [("Ant Drawer","st_ak_ant_draw"),("Talar Tilt","st_ak_talar_tilt")]),
            ("Achilles",     [("Thompson","st_ak_thompson"),("Royal London","st_ak_royal_london"),
                              ("Heel Raise","st_ak_heel_raise")]),
            ("Syndesmosis",  [("Squeeze","st_ak_squeeze"),("ER Stress","st_ak_er_stress"),
                              ("Cotton","st_ak_cotton")]),
            ("Ottawa Rules", [("Lat Malleolus","st_ak_ott_lat_mal"),("Med Malleolus","st_ak_ott_med_mal"),
                              ("Navicular","st_ak_ott_nav"),("5th Met Base","st_ak_ott_5mt")]),
            ("Peroneal",     [("Peroneal Prov","st_ak_per_prov")]),
        ]
        if any(f"{sid}_l" in spl for _, rows in _AK_ST_GROUPS_R for _, sid in rows):
            for grp_lbl, rows in _AK_ST_GROUPS_R:
                ak_st_rows_r = [[lbl, spl.get(f"{sid}_l") or "-", spl.get(f"{sid}_r") or "-"]
                                for lbl, sid in rows]
                _maybe_table(sl, [f"Ankle {grp_lbl}","Left","Right"], ak_st_rows_r)
            v = spl.get("st_ak_notes", "").strip()
            if v:
                sl.append(f"  Ankle test notes: {v}")
            elif not clean:
                sl.append("  Ankle test notes: (empty)")
        _flush_section("08 Special Tests", sl)

    # ── 09 CRPS ───────────────────────────────────────────────────────────────
    _rcrps_has_data = (
        any(crps.get(f) is not None for f in [
            "crps_disp_pain",
            "crps_sx_hyperesth","crps_sx_hyperalg","crps_sx_allodynia",
            "crps_sx_temp_asymm","crps_sx_skin_colour","crps_sx_colour_asymm",
            "crps_sx_oedema","crps_sx_sweat_chng","crps_sx_sweat_asymm",
            "crps_sx_rom_dec","crps_sx_weakness","crps_sx_tremor","crps_sx_dystonia","crps_sx_trophic",
            "crps_sg_hyperalg_pp","crps_sg_allod_lt","crps_sg_allod_press","crps_sg_allod_jt",
            "crps_sg_temp_asymm","crps_sg_skin_colour","crps_sg_colour_asymm",
            "crps_sg_oedema","crps_sg_sweat_chng","crps_sg_sweat_asymm",
            "crps_sg_rom_dec","crps_sg_weakness","crps_sg_tremor","crps_sg_dystonia","crps_sg_trophic",
            "crps_no_alt_dx",
        ]) or
        any(crps.get(t, "").strip() for t in [
            "crps_disp_pain_notes","crps_sx_notes","crps_sg_notes",
            "crps_no_alt_dx_notes","crps_subtype_notes","crps_notes",
            "crps_tpd_notes","crps_vis_notes","crps_lat_notes",
        ]) or
        any(crps.get(f"crps_lat_{r}_{c}", "") for r in ("quick","vanilla","context","abstract") for c in ("l_acc","l_speed","r_acc","r_speed")) or
        bool(crps.get("crps_subtype"))
    )
    if crps and (not clean or _rcrps_has_data):
        sl = []
        def _rcrps_flag(v) -> str:
            return "Yes" if v is True else "No" if v is False else "-"
        _rcrps_sx_domains = [
            ("Sensory",          [("crps_sx_hyperesth","Hyperesthesia"),("crps_sx_hyperalg","Hyperalgesia"),("crps_sx_allodynia","Allodynia")]),
            ("Vasomotor",        [("crps_sx_temp_asymm","Temp asymm"),("crps_sx_skin_colour","Skin colour"),("crps_sx_colour_asymm","Colour asymm")]),
            ("Sudomotor/Oedema", [("crps_sx_oedema","Oedema"),("crps_sx_sweat_chng","Sweat chng"),("crps_sx_sweat_asymm","Sweat asymm")]),
            ("Motor/Trophic",    [("crps_sx_rom_dec","Decr ROM"),("crps_sx_weakness","Weakness"),("crps_sx_tremor","Tremor"),("crps_sx_dystonia","Dystonia"),("crps_sx_trophic","Trophic")]),
        ]
        _rcrps_sg_domains = [
            ("Sensory",          [("crps_sg_hyperalg_pp","Hyperalg PP"),("crps_sg_allod_lt","Allod LT"),("crps_sg_allod_press","Allod Pres"),("crps_sg_allod_jt","Allod Joint")]),
            ("Vasomotor",        [("crps_sg_temp_asymm","Temp asymm"),("crps_sg_skin_colour","Skin colour"),("crps_sg_colour_asymm","Colour asymm")]),
            ("Sudomotor/Oedema", [("crps_sg_oedema","Oedema"),("crps_sg_sweat_chng","Sweat chng"),("crps_sg_sweat_asymm","Sweat asymm")]),
            ("Motor/Trophic",    [("crps_sg_rom_dec","Decr ROM"),("crps_sg_weakness","Weakness"),("crps_sg_tremor","Tremor"),("crps_sg_dystonia","Dystonia"),("crps_sg_trophic","Trophic")]),
        ]
        _rcrps_subtype_full = {
            "T-I":   "Type I — no discrete nerve injury",
            "T-II":  "Type II — confirmed discrete nerve injury; signs extend beyond nerve territory",
            "Remit": "CRPS with Remission of Some Features",
            "NOS":   "CRPS Not Otherwise Specified",
        }
        if not clean or crps.get("crps_disp_pain") is not None:
            sl.append(f"  Rule 1 — Disproportionate pain: {_rcrps_flag(crps.get('crps_disp_pain'))}")
        v = crps.get("crps_disp_pain_notes", "").strip()
        if v:
            sl.append(f"  Disp. pain notes: {v}")
        elif not clean:
            sl.append("  Disp. pain notes: (empty)")

        sx_t = crps.get("crps_sx_domains_triggered", 0)
        if not clean or sx_t > 0:
            sl.append(f"  Rule 2 — Symptoms: {sx_t}/4 domains triggered (need >= 3)")
            for dom_lbl, dom_items in _rcrps_sx_domains:
                triggered = any(crps.get(fid) is True for fid, _ in dom_items)
                if clean and not triggered:
                    continue
                present   = ", ".join(lbl for fid, lbl in dom_items if crps.get(fid) is True) or "-"
                sl.append(f"    {dom_lbl}: {'triggered' if triggered else '-'}  ({present})")
        v = crps.get("crps_sx_notes", "").strip()
        if v:
            sl.append(f"  Symptom notes: {v}")
        elif not clean:
            sl.append("  Symptom notes: (empty)")

        sg_t = crps.get("crps_sg_domains_triggered", 0)
        if not clean or sg_t > 0:
            sl.append(f"  Rule 3 — Signs: {sg_t}/4 domains triggered (need >= 2)")
            for dom_lbl, dom_items in _rcrps_sg_domains:
                triggered = any(crps.get(fid) is True for fid, _ in dom_items)
                if clean and not triggered:
                    continue
                present   = ", ".join(lbl for fid, lbl in dom_items if crps.get(fid) is True) or "-"
                sl.append(f"    {dom_lbl}: {'triggered' if triggered else '-'}  ({present})")
        v = crps.get("crps_sg_notes", "").strip()
        if v:
            sl.append(f"  Sign notes: {v}")
        elif not clean:
            sl.append("  Sign notes: (empty)")

        if not clean or crps.get("crps_no_alt_dx") is not None:
            sl.append(f"  Rule 4 — No other diagnosis: {_rcrps_flag(crps.get('crps_no_alt_dx'))}")
        v = crps.get("crps_no_alt_dx_notes", "").strip()
        if v:
            sl.append(f"  No-alt-dx notes: {v}")
        elif not clean:
            sl.append("  No-alt-dx notes: (empty)")

        _rcrps_flags_answered = any(crps.get(f) is not None for f in ("crps_disp_pain", "crps_no_alt_dx"))
        if not clean or _rcrps_flags_answered or crps.get("crps_criteria_met"):
            verdict = "CRITERIA MET" if crps.get("crps_criteria_met") else "CRITERIA NOT MET"
            sl.append(f"  Budapest/Valencia Criteria: {verdict}")

        subtype_val = crps.get("crps_subtype")
        if subtype_val:
            sl.append(f"  Subtype: {_rcrps_subtype_full.get(subtype_val, subtype_val)}")
        elif not clean:
            sl.append("  Subtype: (not selected)")
        for note_key, note_lbl in [("crps_subtype_notes","Subtype notes"),("crps_notes","General notes")]:
            v = crps.get(note_key, "").strip()
            if v:
                sl.append(f"  {note_lbl}: {v}")
            elif not clean:
                sl.append(f"  {note_lbl}: (empty)")

        v = crps.get("crps_tpd_notes", "").strip()
        if v:
            sl.append(f"  Two-Point Discrimination: {v}")
        elif not clean:
            sl.append("  Two-Point Discrimination: (empty)")

        v = crps.get("crps_vis_notes", "").strip()
        if v:
            sl.append(f"  Visualisation: {v}")
        elif not clean:
            sl.append("  Visualisation: (empty)")

        def _rcrps_lat_fmt(val: str, unit: str) -> str:
            val = (val or "").strip()
            if not val:
                return "-"
            if unit == "%" and not val.endswith("%"):
                return f"{val}%"
            if unit == "s" and not val.endswith("s"):
                return f"{val}s"
            return val
        _rcrps_row_labels = {"quick":"Quick","vanilla":"Vanilla","context":"Context","abstract":"Abstract"}
        lat_any = any(crps.get(f"crps_lat_{r}_{c}", "") for r in ("quick","vanilla","context","abstract") for c in ("l_acc","l_speed","r_acc","r_speed"))
        if lat_any or not clean:
            sl.append("  Laterality:")
            sl.append("    Task       L acc    L speed  R acc    R speed")
            for row_key in ("quick","vanilla","context","abstract"):
                la = _rcrps_lat_fmt(crps.get(f"crps_lat_{row_key}_l_acc",  ""), "%")
                ls = _rcrps_lat_fmt(crps.get(f"crps_lat_{row_key}_l_speed",""), "s")
                ra = _rcrps_lat_fmt(crps.get(f"crps_lat_{row_key}_r_acc",  ""), "%")
                rs = _rcrps_lat_fmt(crps.get(f"crps_lat_{row_key}_r_speed",""), "s")
                lbl = _rcrps_row_labels[row_key]
                sl.append(f"    {lbl:<10} {la:<8} {ls:<8} {ra:<8} {rs}")
        v = crps.get("crps_lat_notes", "").strip()
        if v:
            sl.append(f"  Laterality notes: {v}")
        elif not clean:
            sl.append("  Laterality notes: (empty)")
        _flush_section("09 CRPS (Budapest / Valencia Criteria)", sl)


# ---------------------------------------------------------------------------
# YAML subsection report registry
#
# Maps section JSON key → list of YAML subsection file paths.
# Any YAML subsection registered here is auto-rendered in both the full
# and clean reports, immediately after its parent section's hand-coded block.
#
# Usage: to add a new YAML form to (e.g.) the subjective section:
#
#   _YAML_SUBS["subjective"].append(
#       Path(__file__).parent / "sections/yaml/02_new_form.yaml"
#   )
#
# The sleep pilot is deliberately NOT registered here — it is already
# hand-coded in the subjective block of export_session_report.
# ---------------------------------------------------------------------------

from pathlib import Path as _Path
from collections import defaultdict as _defaultdict

_YAML_SUBS: dict[str, list[_Path]] = _defaultdict(list)


def _emit_yaml_subs_md(section_key: str, section_data: dict, clean: bool,
                        emit_fn, sub_fn) -> None:
    """Render all registered YAML subsections for a section into the MD report."""
    from .form_schema import load_subsection_yaml, render_subsection_md
    for path in _YAML_SUBS.get(section_key, []):
        try:
            defn = load_subsection_yaml(path)
            content = render_subsection_md(defn, section_data, clean)
            if content or not clean:
                sub_fn(defn.label)
                for line in content:
                    emit_fn(line)
        except Exception:
            pass


def _emit_yaml_subs_raw(section_key: str, section_data: dict, clean: bool,
                         emit_fn, sub_fn) -> None:
    """Render all registered YAML subsections for a section into the raw report."""
    from .form_schema import load_subsection_yaml, render_subsection_raw
    for path in _YAML_SUBS.get(section_key, []):
        try:
            defn = load_subsection_yaml(path)
            content = render_subsection_raw(defn, section_data, clean)
            if content or not clean:
                sub_fn(defn.label)
                for line in content:
                    emit_fn(line)
        except Exception:
            pass



# Denied-item phrasing for Section 4 evidence-against columns. "No X" reads correctly
# for bare noun/symptom labels ("No fatigue"); "Not X" (the default) fits adjective/
# descriptor labels ("Not localised", "Not widespread/multifocal"). A few labels need
# more than a prefix swap — double negatives ("Not constant" -> "Constant" when denied)
# or threshold flips ("Symptoms ≥ 3 months" -> "Symptoms < 3 months") — those are
# spelled out in full below.
_PAIN_CLASS_NEG_OVERRIDES = {
    "Constant pain":                              "No constant pain",
    "Morning stiffness":                          "No morning stiffness",
    "Night/sleep pain":                           "No night/sleep pain",
    "Activity improves":                          "No improvement with activity",
    "Trauma/incident":                            "No trauma/incident",
    "Responds to analgesia":                      "No response to analgesia",
    "Not constant":                                "Constant",
    "Local inflammation":                         "No local inflammation",
    "Recent onset":                                "No recent onset",
    "Mechanical reproduction":                    "No mechanical reproduction",
    "Palpation reproduction":                     "No palpation reproduction",
    "Local hyperalgesia":                         "No local hyperalgesia",
    "Antalgic posture":                           "No antalgic posture",
    "Known nerve injury":                         "No known nerve injury",
    "Neurological symptoms":                      "No neurological symptoms",
    "Responds to neuropathic meds":               "No response to neuropathic meds",
    "Dysaesthesia/allodynia":                     "No dysaesthesia/allodynia",
    "Positive neurodynamic test":                 "Negative neurodynamic test",
    "Neurology change":                           "No neurology change",
    "Hyperalgesia in distribution":               "No hyperalgesia in distribution",
    "Psychosocial contributors":                  "No psychosocial contributors",
    "Responds to centrally-acting meds":          "No response to centrally-acting meds",
    "Disturbed sleep/night pain":                 "No disturbed sleep/night pain",
    "Dysaesthesia":                                "No dysaesthesia",
    "Disproportionate exam findings":             "No disproportionate exam findings",
    "Widespread hyperalgesia/allodynia":          "No widespread hyperalgesia/allodynia",
    "Diffuse palpation tenderness":               "No diffuse palpation tenderness",
    "Psychosocial features on exam":              "No psychosocial features on exam",
    "Light sensitivity":                          "No light sensitivity",
    "Touch sensitivity":                          "No touch sensitivity",
    "Noise sensitivity":                          "No noise sensitivity",
    "Chemical/smell sensitivity":                 "No chemical/smell sensitivity",
    "Temperature sensitivity":                    "No temperature sensitivity",
    "Fatigue":                                     "No fatigue",
    "Sleep disturbance":                          "No sleep disturbance",
    "Concentration difficulty":                   "No concentration difficulty",
    "Perceived swelling":                         "No perceived swelling",
    "Tingling":                                    "No tingling",
    "Headaches":                                   "No headaches",
    "IBS":                                         "No IBS",
    "Depression":                                  "No depression",
    "Symptoms ≥ 3 months":                        "Symptoms < 3 months",
    "No alternative explanation":                 "Alternative explanation present",
    "LBP ≥ 3 months":                              "LBP < 3 months",
    "Static mechanical allodynia":                "No static mechanical allodynia",
    "Dynamic mechanical allodynia":               "No dynamic mechanical allodynia",
    "Heat or cold allodynia":                     "No heat or cold allodynia",
    "Painful after-sensations":                   "No painful after-sensations",
    "Hypersensitivity — touch":                   "No hypersensitivity — touch",
    "Hypersensitivity — movement":                "No hypersensitivity — movement",
    "Hypersensitivity — pressure":                "No hypersensitivity — pressure",
    "Hypersensitivity — heat":                    "No hypersensitivity — heat",
    "Hypersensitivity — cold":                    "No hypersensitivity — cold",
}


def _emit_pain_class_dev(pc: dict, clean: bool, emit_fn, sub_fn) -> None:
    """Section 4 — Pain Classification in tabulated dev format (Reports / Denies columns)."""

    def _neg(lbl: str) -> str:
        return _PAIN_CLASS_NEG_OVERRIDES.get(lbl, f"Not {lbl}")

    def _rd_pairs(fields: list[tuple]) -> list[tuple[str, str]]:
        """One (report, deny) pair per row so each item lands on its own table line —
        Textual's MarkdownViewer has no raw-HTML support, so "<br>" is not an option; a
        dot-joined single cell is what was too dense in exported .md/.docx/EMR views."""
        rep = [lbl for lbl, key in fields if pc.get(key) is True]
        den = [_neg(lbl) for lbl, key in fields if pc.get(key) is False]
        if not rep and not den:
            return [("—", "—")]
        return list(zip_longest(rep or ["—"], den or ["—"], fillvalue=""))

    def _rd_rows(label: str, fields: list[tuple]) -> list[list[str]]:
        return [[label if i == 0 else "", r, d]
                for i, (r, d) in enumerate(_rd_pairs(fields))]

    def _score_rows(label: str, fields: list[tuple]) -> list[list[str]]:
        """One row per scored field (not a Yes/No flag) — same one-item-per-line
        treatment as _rd_rows, for the FM WPI/SS component scores."""
        return [[label if i == 0 else "", f"{lbl}: {(pc.get(k) or '').strip() or '—'}", ""]
                for i, (lbl, k) in enumerate(fields)]

    def _any(fields: list[tuple]) -> bool:
        return any(pc.get(key) is not None for _, key in fields)

    # ── Inflammatory ──────────────────────────────────────────────────────────
    _INFL = [("Constant pain","infl_constant"),("Morning stiffness","infl_morning"),
             ("Night/sleep pain","infl_sleep"),("Activity improves","infl_activity")]
    lh = (pc.get("infl_likelihood") or "").strip()
    if not clean or _any(_INFL) or lh:
        sub_fn("Inflammatory Pain")
        rows = _rd_rows("Features", _INFL)
        if lh or not clean:
            rows.append(["Likelihood", lh or "—", ""])
        emit_fn(*_md_table(["", "Evidence for", "Evidence against"], rows))

    # ── Nociceptive ───────────────────────────────────────────────────────────
    _NOCI_SX = [
        ("Mechanical","noci_subj_mechanical"),("Trauma/incident","noci_subj_trauma"),
        ("Localised","noci_subj_localised"),("Resolving","noci_subj_resolving"),
        ("Responds to analgesia","noci_subj_analgesia"),("Not constant","noci_subj_no_constant"),
        ("Local inflammation","noci_subj_inflammation"),("Recent onset","noci_subj_recent"),
    ]
    _NOCI_EX = [
        ("Mechanical reproduction","noci_exam_mechanical"),
        ("Palpation reproduction","noci_exam_palpation"),
        ("Local hyperalgesia","noci_exam_hyperalgesia"),
        ("Antalgic posture","noci_exam_antalgic"),
    ]
    lh     = (pc.get("noci_likelihood")     or "").strip()
    interp = (pc.get("noci_interpretation") or "").strip()
    if not clean or _any(_NOCI_SX) or _any(_NOCI_EX) or lh:
        sub_fn("Nociceptive Pain")
        rows = _rd_rows("Subjective", _NOCI_SX) + _rd_rows("Examination", _NOCI_EX)
        if lh or not clean:
            rows.append(["Likelihood", lh or "—", ""])
        emit_fn(*_md_table(["", "Evidence for", "Evidence against"], rows))
        if interp:
            emit_fn(f"*{interp}*")

    # ── Neuropathic ───────────────────────────────────────────────────────────
    _NEURO_SX = [
        ("Burning/electric/shooting","neuro_subj_quality"),
        ("Known nerve injury","neuro_subj_nerve_injury"),
        ("Neurological symptoms","neuro_subj_neurological"),
        ("Dermatomal/nerve trunk","neuro_subj_dermatomal"),
        ("Responds to neuropathic meds","neuro_subj_medication"),
        ("Severe/night pain","neuro_subj_severity"),
        ("Provoked by neural loading","neuro_subj_neural_loading"),
        ("Dysaesthesia/allodynia","neuro_subj_dysaesthesia"),
        ("Spontaneous pain","neuro_subj_spontaneous"),
    ]
    _NEURO_EX = [
        ("Positive neurodynamic test","neuro_exam_neurodynamic"),
        ("Neural palpation sensitive","neuro_exam_neural_palpation"),
        ("Neurology change","neuro_exam_neurology"),
        ("Antalgic posture","neuro_exam_antalgic"),
        ("Hyperalgesia in distribution","neuro_exam_hyperalgesia"),
    ]
    lh     = (pc.get("neuro_likelihood")     or "").strip()
    interp = (pc.get("neuro_interpretation") or "").strip()
    if not clean or _any(_NEURO_SX) or _any(_NEURO_EX) or lh:
        sub_fn("Neuropathic Pain")
        rows = _rd_rows("Subjective", _NEURO_SX) + _rd_rows("Examination", _NEURO_EX)
        if lh or not clean:
            rows.append(["Likelihood", lh or "—", ""])
        emit_fn(*_md_table(["", "Evidence for", "Evidence against"], rows))
        if interp:
            emit_fn(f"*{interp}*")

    # ── Nociplastic ───────────────────────────────────────────────────────────
    _NOCIP_SX = [
        ("Disproportionate to pathology","nocip_subj_disproportionate"),
        ("Persistent beyond healing","nocip_subj_persistent"),
        ("Disproportionate to stimulus","nocip_subj_disproportionate2"),
        ("Widespread/multifocal","nocip_subj_widespread"),
        ("Failed previous treatment","nocip_subj_failed"),
        ("Psychosocial contributors","nocip_subj_psychosocial"),
        ("Responds to centrally-acting meds","nocip_subj_medication"),
        ("Spontaneous pain","nocip_subj_spontaneous"),
        ("High disability","nocip_subj_disability"),
        ("Constant/unpredictable","nocip_subj_constant"),
        ("Disturbed sleep/night pain","nocip_subj_night_pain"),
        ("Dysaesthesia","nocip_subj_dysaesthesia"),
        ("Severe/difficult to control","nocip_subj_severity"),
    ]
    _NOCIP_EX = [
        ("Disproportionate exam findings","nocip_exam_disproportionate"),
        ("Widespread hyperalgesia/allodynia","nocip_exam_hyperalgesia"),
        ("Diffuse palpation tenderness","nocip_exam_diffuse"),
        ("Psychosocial features on exam","nocip_exam_psychosocial"),
    ]
    lh     = (pc.get("nocip_likelihood")     or "").strip()
    interp = (pc.get("nocip_interpretation") or "").strip()
    if not clean or _any(_NOCIP_SX) or _any(_NOCIP_EX) or lh:
        sub_fn("Nociplastic Pain")
        rows = _rd_rows("Subjective", _NOCIP_SX) + _rd_rows("Examination", _NOCIP_EX)
        if lh or not clean:
            rows.append(["Likelihood", lh or "—", ""])
        emit_fn(*_md_table(["", "Evidence for", "Evidence against"], rows))
        if interp:
            emit_fn(f"*{interp}*")

    # ── Central Sensitisation ─────────────────────────────────────────────────
    _CS = [
        ("Light sensitivity","cs_light"),("Touch sensitivity","cs_touch"),
        ("Noise sensitivity","cs_noise"),("Chemical/smell sensitivity","cs_pesticides"),
        ("Temperature sensitivity","cs_temperature"),("Fatigue","cs_fatigue"),
        ("Sleep disturbance","cs_sleep"),("Concentration difficulty","cs_concentration"),
        ("Perceived swelling","cs_swelling"),("Tingling","cs_tingling"),
    ]
    csi = (pc.get("csi_score") or "").strip()
    if not clean or _any(_CS) or csi:
        sub_fn("Central Sensitisation")
        if csi or not clean:
            emit_fn(f"**CSI score:** {csi or '*(not entered)*'}")
        emit_fn(*_md_table(["Evidence for", "Evidence against"], [list(p) for p in _rd_pairs(_CS)]))

    # ── Fibromyalgia ──────────────────────────────────────────────────────────
    _FM_SC = [("WPI (0–19)","fm_wpi"),("Fatigue (0–3)","fm_fatigue"),
              ("Waking unrefreshed (0–3)","fm_waking"),("Cognitive (0–3)","fm_cognitive")]
    _FM_SY = [
        ("Headaches","fm_headaches"),("IBS","fm_ibs"),("Depression","fm_depression"),
        ("Symptoms ≥ 3 months","fm_duration"),("No alternative explanation","fm_exclusion"),
    ]
    scores_ok = any((pc.get(k) or "").strip() for _, k in _FM_SC)
    symp_ok   = _any(_FM_SY)
    if not clean or scores_ok or symp_ok:
        sub_fn("Fibromyalgia")
        rows = []
        if scores_ok or not clean:
            rows.extend(_score_rows("Scores", _FM_SC))
        if symp_ok or not clean:
            rows.extend(_rd_rows("Symptoms", _FM_SY))
        if rows:
            emit_fn(*_md_table(["Aspect", "Evidence for / Score", "Evidence against"], rows))
        # ── FM interpretation ─────────────────────────────────────────────
        def _fm_int(s: str | None) -> int | None:
            v = (s or "").strip()
            return int(v) if v.isdigit() else None
        wpi  = _fm_int(pc.get("fm_wpi"))
        fat  = _fm_int(pc.get("fm_fatigue"))
        wak  = _fm_int(pc.get("fm_waking"))
        cog  = _fm_int(pc.get("fm_cognitive"))
        if wpi is not None and all(v is not None for v in (fat, wak, cog)):
            add = sum(1 for k in ("fm_headaches","fm_ibs","fm_depression") if pc.get(k) is True)
            ss  = fat + wak + cog + add  # type: ignore[operator]
            crit_a = wpi > 7 and ss > 5
            crit_b = 3 <= wpi <= 6 and ss > 9
            dur = pc.get("fm_duration")  is True
            exc = pc.get("fm_exclusion") is True
            if crit_a or crit_b:
                crit_lbl = "A" if crit_a else "B"
                if dur and exc:
                    interp = f"⚠ Fibromyalgia criteria **{crit_lbl}** met — WPI {wpi} · SS {ss}/12"
                else:
                    missing = []
                    if not dur: missing.append("duration ≥ 3 months")
                    if not exc: missing.append("no alternative explanation")
                    interp = (f"Scoring criteria {crit_lbl} met (WPI {wpi} · SS {ss}/12)"
                              f" — unconfirmed: {'; '.join(missing)}")
            else:
                interp = f"FM criteria not met — WPI {wpi} · SS {ss}/12 (need A: WPI >7 & SS >5 or B: WPI 3–6 & SS >9)"
            emit_fn(f"*{interp}*  " if clean else f"*{interp}*")

    # ── BACPAP ────────────────────────────────────────────────────────────────
    _BP_CH = [("LBP ≥ 3 months","bacpap_chronic"),
              ("Regional/widespread distribution","bacpap_distribution")]
    _BP_ME = [("Nociceptive mainly responsible","bacpap_nociceptive"),
              ("Neuropathic mainly responsible","bacpap_neuropathic")]
    _BP_EV = [("Static mechanical allodynia","bacpap_static"),
              ("Dynamic mechanical allodynia","bacpap_dynamic"),
              ("Heat or cold allodynia","bacpap_thermal"),
              ("Painful after-sensations","bacpap_after")]
    _BP_NO = [("Hypersensitivity — touch","bacpap_hyper_touch"),
              ("Hypersensitivity — movement","bacpap_hyper_movement"),
              ("Hypersensitivity — pressure","bacpap_hyper_pressure"),
              ("Hypersensitivity — heat","bacpap_hyper_heat"),
              ("Hypersensitivity — cold","bacpap_hyper_cold"),
              ("Comorbid — light/sound/odour sensitivity","bacpap_como_sensory"),
              ("Comorbid — sleep disturbance","bacpap_como_sleep"),
              ("Comorbid — fatigue","bacpap_como_fatigue"),
              ("Comorbid — cognitive problems","bacpap_como_cognitive")]
    bp_notes = (pc.get("bacpap_notes") or "").strip()
    _bp_all  = _BP_CH + _BP_ME + _BP_EV + _BP_NO
    if not clean or _any(_bp_all):
        sub_fn("BACPAP LBP Phenotyping")
        rows = []
        for row_lbl, grp in [
            ("Chronicity & Distribution", _BP_CH),
            ("Dominant Mechanism",        _BP_ME),
            ("Evoked Hypersensitivity",   _BP_EV),
            ("Nociplastic Features",      _BP_NO),
        ]:
            if _any(grp) or not clean:
                rows.extend(_rd_rows(row_lbl, grp))
        if rows:
            emit_fn(*_md_table(["Aspect", "Evidence for", "Evidence against"], rows))
        if bp_notes:
            emit_fn(f"*Notes: {bp_notes}*")

    # ── Pain Type Summary ─────────────────────────────────────────────────────
    dom  = (pc.get("summary_dominant")     or "").strip()
    cont = (pc.get("summary_contributing") or "").strip()
    reas = (pc.get("summary_reasoning")    or "").strip()
    if dom or cont or reas or not clean:
        sub_fn("Pain Type Summary")
        if dom or not clean:
            emit_fn(f"**Dominant pain type:** {dom or '*(not entered)*'}")
        if cont:
            emit_fn("**Contributing:**  ")
            for row in cont.split("\n"):
                emit_fn((row + "  ") if row.strip() else row)
            emit_fn("")
        elif not clean:
            emit_fn("**Contributing:** *(empty)*")
        if reas:
            emit_fn(f"**Reasoning:** {reas}")
        elif not clean:
            emit_fn("**Reasoning:** *(empty)*")


def export_session_report(session_file: str, clean: bool = False, dev: bool = False) -> str:  # noqa: C901
    """
    Write a Markdown report to the session directory.

    clean=False (default): writes *_report.md with all fields shown.
    clean=True: writes *_clean.md with only fields that have data.
    dev=True: writes *_report_dev.md (full) or *_clean.md (clean) with tabulated sections.
    Returns the output path, or empty string on failure.
    """
    import time as _time

    try:
        data = json.loads(Path(session_file).read_text()) if Path(session_file).exists() else {}
    except Exception as e:
        logger.error(f"export_session_report: {e}")
        return ""

    # Overlay TUI assessment data from the separate _assessment.json
    assess_p = assessment_path(session_file)
    if assess_p.exists():
        try:
            assess_data = json.loads(assess_p.read_text())
            data["assessment"] = assess_data.get("assessment", data.get("assessment", {}))
            data.setdefault("sections_complete", assess_data.get("sections_complete", {}))
        except Exception:
            pass

    # Load objective sections from _objective.json
    obj_file_data = load_objective(session_file)
    obj_assessment = obj_file_data.get("assessment", {})

    session_dir  = Path(session_file).parent
    session_name = data.get("session_name", "session")
    if dev:
        out_name = f"{session_name}_clean.md" if clean else f"{session_name}_report_dev.md"
    else:
        out_name = f"{session_name}_clean.md" if clean else f"{session_name}_report.md"
    out_path     = session_dir / out_name

    a = data.get("assessment", {})
    lines: list[str] = []
    _pending: list[str] = []  # buffered section/sub headers waiting for content

    # ── helpers ────────────────────────────────────────────────────────────
    def _v(val) -> str:
        if val is True:  return "Yes"
        if val is False: return "No"
        if val is None:  return "*(not answered)*"
        s = str(val).strip()
        return s if s else "*(empty)*"

    def _emit(*ls: str) -> None:
        if _pending:
            lines.extend(_pending)
            _pending.clear()
        lines.extend(ls)

    def sec(title):
        if clean:
            if title == "Body Chart Summary":
                _pending[:] = []  # suppress entirely in clean mode
                return
            # Strip "Section N: " prefix
            clean_title = re.sub(r'^Section \d+:\s*', '', title)
            if clean_title != title:
                # Section 1 (Consent) — emit only a divider, no heading
                if title.startswith("Section 1:"):
                    _pending[:] = ["\n---\n"]
                else:
                    _pending[:] = [f"\n---\n\n## {clean_title}\n"]
            else:
                _pending[:] = [f"\n---\n\n## {title}\n"]
        else:
            lines.append(f"\n---\n\n## {title}\n")

    def sub(title):
        clean_title = title.replace(" (ICE+)", "") if clean else title
        if clean:
            while _pending and _pending[-1].lstrip().startswith("### "):
                _pending.pop()
            _pending.append(f"\n### {clean_title}\n")
        else:
            lines.append(f"\n### {title}\n")

    def _empty(val) -> bool:
        if val is None:
            return True
        if isinstance(val, str) and not val.strip():
            return True
        return False

    def f(fid, d):
        val = d.get(fid)
        if clean and _empty(val):
            return
        line = f"**{_label(fid)}:** {_v(val)}"
        _emit(line + "  " if clean else line)

    def txt(fid, d):
        val = (d.get(fid) or "").strip()
        if clean and not val:
            return
        label = _label(fid)
        if val and "\n" in val:
            _emit(f"**{label}:**  ")
            # Data-purity fix: hard-break markers used to be gated on
            # `clean`, so a multi-paragraph note kept its line breaks in the
            # clean report but collapsed into one run-on paragraph in the
            # FULL report — same underlying CommonMark soft-break issue as
            # _maybe_note above, just previously fixed in only one of the
            # two modes. Applies regardless of clean/full now.
            rows = val.split("\n")
            last = len(rows) - 1
            for i, row in enumerate(rows):
                _emit(row if (i == last or not row.strip()) else row + "  ")
            _emit("")
        elif val:
            line = f"**{label}:** {val}"
            _emit(line + "  " if clean else line)
        else:
            _emit(f"**{label}:** *(empty)*")

    # ── header ──────────────────────────────────────────────────────────────
    c_hdr = a.get("consent", {}) or {}
    preferred_name = c_hdr.get("preferred_name", "").strip() or "*(not set)*"
    created  = data.get("created", 0)
    date_str = _time.strftime("%d %b %Y %H:%M", _time.localtime(created)) if created else "*(unknown)*"
    regions  = ", ".join(data.get("regions", [])) or "*(not set)*"

    if clean:
        lines.extend([f"**Date:** {date_str}  ", ""])
    else:
        lines.extend(["# Physiotherapy Assessment — Full Record", "",
                      f"**Patient:** {preferred_name}  ",
                      f"**Date:** {date_str}  ",
                      f"**Region:** {regions}  ",
                      f"**Session ID:** {data.get('session_name', '')}  ",
                      ""])

    # Plain Language Summary — the F10 notes-panel freeform text. Moved to
    # the very top of the report 2026-09-17 (was "Scratchpad Notes" at the
    # very bottom, after Rx & Plan) per direct request: it should be the
    # first thing anyone reading the report sees, right after the date and
    # before Subjective. clean+empty emits nothing at all (heading included)
    # — matches every other clean-mode section's "omit if no data" rule.
    pls = a.get("scratchpad", {}) or {}
    pls_notes = (pls.get("notes") or "").strip()
    if pls_notes or not clean:
        lines.append("\n## Plain Language Summary\n")
        if pls_notes:
            for row in pls_notes.split("\n"):
                lines.append((row + "  ") if (clean and row.strip()) else row)
        else:
            lines.append("*(empty)*")

    lines.append("\n# S — Subjective\n")

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 1: CONSENT & SETUP
    # ════════════════════════════════════════════════════════════════════════
    c = a.get("consent", {}) or {}
    sec("Section 1: Consent & Setup")

    sub("Consent")
    f("consent_to_proceed",       c)
    f("consent_sensitive_topics", c)
    f("preferred_name",           c)

    sub("Session Framing")
    f("pain_multifactorial_explained",    c)
    f("education_as_treatment_explained", c)
    txt("patient_expectations",           c)

    sub("Patient Perspective (ICE+)")
    txt("reason_for_attending",      c)
    f("cause_understanding",         c)
    txt("cause_understanding_detail", c)
    txt("prognosis_expectations",    c)
    txt("treatment_preference",      c)
    _emit_yaml_subs_md("consent", c, clean, _emit, sub)

    sub("Beliefs")
    f("belief_hurt_harm",      c)
    f("belief_unsafe",         c)
    f("belief_passive",        c)
    f("belief_rehab",          c)
    f("belief_high_se",        c)
    f("belief_internal_locus", c)
    txt("belief_notes",        c)

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 2: SUBJECTIVE EXAMINATION
    # ════════════════════════════════════════════════════════════════════════
    s = a.get("subjective", {}) or {}
    sec("Section 2: Subjective Examination")

    sub("Symptoms")
    f("body_chart_completed", s)
    note_fields = s.get("note_fields") or {}
    for sid, nf in note_fields.items():
        if any(nf.get(k, "").strip() for k in ("loc", "nat", "agg", "ease")):
            _emit(f"**Note {int(sid) + 1}:**  ")
            if nf.get("loc", "").strip():
                _emit(f"  Location: {nf['loc'].strip()}  ")
            if nf.get("nat", "").strip():
                _emit(f"  Nature: {nf['nat'].strip()}  ")
            if nf.get("agg", "").strip():
                _emit(f"  Aggravating: {nf['agg'].strip()}  ")
            if nf.get("ease", "").strip():
                _emit(f"  Easing: {nf['ease'].strip()}  ")
            _emit("")
    if s.get("misc_loc", "").strip() or s.get("misc_nat", "").strip():
        _emit("**Misc symptoms (no note):**  ")
        if s.get("misc_loc", "").strip():
            _emit(f"  Location: {s['misc_loc'].strip()}  ")
        if s.get("misc_nat", "").strip():
            _emit(f"  Nature: {s['misc_nat'].strip()}  ")
        _emit("")

    sub("History")
    txt("onset",              s)
    txt("duration",           s)
    f("course_improving",     s)
    f("course_worsening",     s)
    f("course_stable",        s)
    f("course_fluctuating",   s)
    txt("context_at_onset",   s)
    txt("previous_episodes",  s)
    txt("previous_treatment", s)

    sub("Behaviour")
    f("behaviour_boom_bust",         s)
    txt("behaviour_boom_bust_text",  s)
    f("behaviour_avoidance",         s)
    txt("behaviour_avoidance_text",  s)
    f("behaviour_endurance",         s)
    txt("behaviour_endurance_text",  s)
    f("behaviour_flareups",          s)
    txt("behaviour_flareups_text",   s)

    sub("Self-Management & Control")
    f("pain_control_score",       s)
    txt("flareup_prevention",     s)
    txt("management_strategies",  s)
    f("confidence_score",         s)

    sub("Activity & Exercise")
    txt("pre_activity_level",     s)
    txt("current_activity_level", s)
    txt("exercise_type",          s)
    txt("exercise_dose",          s)
    txt("exercise_response",      s)

    sub("Work")
    txt("pre_injury_role",     s)
    f("pre_injury_hours",      s)
    txt("pre_injury_duties",   s)
    txt("current_work_status", s)
    f("current_hours",         s)
    txt("current_duties",      s)

    sub("Sleep")
    f("sleep_overall_rating",       s)
    f("sleep_feels_rested",         s)
    f("sleep_time_to_bed",          s)
    f("sleep_time_attempt",         s)
    f("sleep_onset_time",           s)
    f("sleep_waso_clock",           s)
    f("sleep_waso_duration",        s)
    f("sleep_awake_in_bed",         s)
    f("sleep_awake_out_bed",        s)
    f("sleep_final_wakeup",         s)
    f("sleep_time_out_of_bed",      s)
    f("sleep_efficiency",           s)
    txt("sleep_postural_factors",   s)
    txt("sleep_environment_quality",s)
    f("sleep_daytime_naps",         s)
    txt("sleep_overall_comments",   s)
    txt("energy_levels",            s)

    sub("Behaviour of Symptoms")
    txt("aggravating_factors",     s)
    txt("easing_factors",          s)
    txt("daily_pattern_comments",  s)
    txt("hr24_am",                 s)
    txt("hr24_day",                s)
    txt("hr24_pm",                 s)
    txt("hr24_nocte",              s)

    sub("Psychosocial")
    f("mood_influences",           s)
    txt("mood_text",               s)
    txt("social_situation",        s)
    txt("financial_status",        s)
    txt("cultural_considerations", s)
    txt("psychological_distress",  s)
    txt("screening_tool",          s)

    sub("Suicide / Self-Harm Risk")
    f("self_harm_risk",   s)
    txt("harm_plan",      s)
    txt("harm_means",     s)
    txt("harm_intent",    s)
    txt("harm_action",    s)

    sub("SMART Goals")
    f("goal_1", s)
    f("goal_2", s)
    f("goal_3", s)
    f("goal_4", s)
    _emit_yaml_subs_md("subjective", s, clean, _emit, sub)

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 3: MEDICAL SCREENING
    # ════════════════════════════════════════════════════════════════════════
    m = a.get("medical", {}) or {}
    sec("Section 3: Medical Screening")

    # ── clean-mode clustered helpers (md) — only used when clean=True ─────
    def _cluster_md(prefix: str, items: list, d: dict) -> None:
        rows = []
        for lbl, key in items:
            val = d.get(key)
            if val is None:
                continue
            rows.append([lbl if val is True else f"{lbl} — Absent"])
        if rows:
            _emit(*_md_table(["Factor"], rows))
            _emit("")

    def _rf_md(name: str, flags: list, d: dict, action_key: str = None) -> None:
        raised     = [l for l, k in flags if d.get(k) is True]
        not_raised = [l for l, k in flags if d.get(k) is False]
        action = (d.get(action_key) or "").strip() if action_key else ""
        if raised:
            _emit(f"\n### Red Flags — {name}\n")
            line = "**⚠️ RED FLAGS RAISED:** " + "; ".join(f"**{l}**" for l in raised)
            _emit(line + "  " if clean else line)
            if not_raised:
                line = "**Not reported:** " + "; ".join(not_raised)
                _emit(line + "  " if clean else line)
            if action:
                line = f"**Action:** {action}"
                _emit(line + "  " if clean else line)
        else:
            suffix = f" — {action}" if action else ""
            _emit(f"\n### Red Flags — {name} NIL REPORTED{suffix}\n")

    def _pain_md(prefix: str, items: list, d: dict) -> None:
        present = [l for l, k in items if d.get(k) is True]
        absent  = [l for l, k in items if d.get(k) is False]
        if present:
            _emit("**" + prefix + ":** " + ", ".join(f"**{l}:** Yes" for l in present))
        if absent:
            _emit("**" + prefix + ": DENIES:** " + ", ".join(absent))

    sub("Comorbidities / PMH")
    f("no_previous_injuries", m)
    txt("previous_injuries",   m)
    _COMORBID = [
        ("Cancer",                "comorbid_cancer"),
        ("Mental health",         "comorbid_mental_health"),
        ("Osteoporosis",          "comorbid_osteoporosis"),
        ("Inflammatory arthritis","comorbid_inflammatory"),
        ("Fibromyalgia",          "comorbid_fibromyalgia"),
        ("CFS",                   "comorbid_cfs"),
        ("IBS",                   "comorbid_ibs"),
        ("Whiplash",              "comorbid_whiplash"),
        ("Skin rash",             "comorbid_skin_rash"),
        ("Drug/alcohol",          "comorbid_drug_alcohol"),
        ("Fatigue/memory issues", "comorbid_fatigue_memory"),
    ]
    if dev:
        _c_rep = [lbl for lbl, key in _COMORBID if m.get(key) is True]
        _c_den = [lbl for lbl, key in _COMORBID if m.get(key) is False]
        if not clean or _c_rep or _c_den:
            _emit(*_md_table(
                ["Present", "Absent"],
                [[" · ".join(_c_rep) if _c_rep else "—",
                  " · ".join(_c_den) if _c_den else "—"]],
            ))
    elif clean:
        _cluster_md("Comorbidities", _COMORBID, m)
    else:
        f("comorbid_cancer",         m)
        f("comorbid_mental_health",  m)
        f("comorbid_osteoporosis",   m)
        f("comorbid_inflammatory",   m)
        f("comorbid_fibromyalgia",   m)
        f("comorbid_cfs",            m)
        f("comorbid_ibs",            m)
        f("comorbid_whiplash",       m)
        f("comorbid_skin_rash",      m)
        f("comorbid_drug_alcohol",   m)
        f("comorbid_fatigue_memory", m)
    txt("comorbid_other", m)

    sub("Cardiovascular Risk Factors")
    if clean:
        _cluster_md("CVD risk", [
            ("Hypercholesterolaemia",    "cvd_hypercholesterolaemia"),
            ("Cardiac disease",          "cvd_cardiac"),
            ("Vascular disease",         "cvd_vascular"),
            ("Stroke/TIA",               "cvd_stroke_tia"),
            ("Diabetes",                 "cvd_diabetes"),
            ("Long-term corticosteroids","cvd_corticosteroids"),
            ("Clotting disorder",        "cvd_clotting"),
            ("OCP use",                  "cvd_ocp"),
            ("Smoker",                   "cvd_smoker"),
            ("Postpartum",               "cvd_postpartum"),
            ("Familial history",         "cvd_familial_history"),
        ], m)
    else:
        f("cvd_hypercholesterolaemia", m)
        f("cvd_cardiac",               m)
        f("cvd_vascular",              m)
        f("cvd_stroke_tia",            m)
        f("cvd_diabetes",              m)
        f("cvd_corticosteroids",       m)
        f("cvd_clotting",              m)
        f("cvd_ocp",                   m)
        f("cvd_smoker",                m)
        f("cvd_postpartum",            m)
        f("cvd_familial_history",      m)

    if clean:
        _rf_md("Malignancy", [
            ("Unexplained weight loss","rf_weight_loss"),
            ("Cancer history",         "rf_cancer_history"),
            ("Age >50 with spinal",    "rf_age_50_spinal"),
            ("Failed conservative",    "rf_failed_conservative"),
        ], m)
        _rf_md("Fracture", [
            ("Recent trauma",               "rf_trauma"),
            ("Corticosteroid fracture risk","rf_corticosteroids_fracture"),
            ("Osteoporosis fracture risk",  "rf_osteoporosis_fracture"),
        ], m)
        _rf_md("Infection", [
            ("Fever",                  "rf_fever"),
            ("Immunosuppressed",       "rf_immunosuppressed"),
            ("Recent spinal procedure","rf_spinal_procedure"),
        ], m)
        _rf_md("Cauda Equina (URGENT)", [
            ("Saddle anaesthesia",  "rf_saddle_anaesthesia"),
            ("Bladder disturbance", "rf_bladder_disturbance"),
            ("Bowel disturbance",   "rf_bowel_disturbance"),
        ], m, action_key="cauda_equina_action")
        _rf_md("Spinal Cord (URGENT)", [
            ("Bilateral paraesthesia","rf_bilateral_paraesthesia"),
            ("Gait disturbance",     "rf_gait_disturbance"),
        ], m, action_key="spinal_cord_action")
    else:
        sub("Red Flags — Malignancy")
        f("rf_weight_loss",         m)
        f("rf_cancer_history",      m)
        f("rf_age_50_spinal",       m)
        f("rf_failed_conservative", m)

        sub("Red Flags — Fracture")
        f("rf_trauma",                   m)
        f("rf_corticosteroids_fracture", m)
        f("rf_osteoporosis_fracture",    m)

        sub("Red Flags — Infection")
        f("rf_fever",           m)
        f("rf_immunosuppressed", m)
        f("rf_spinal_procedure", m)

        sub("Red Flags — Cauda Equina (URGENT)")
        f("rf_saddle_anaesthesia",  m)
        f("rf_bladder_disturbance", m)
        f("rf_bowel_disturbance",   m)
        txt("cauda_equina_action",  m)

        sub("Red Flags — Spinal Cord (URGENT)")
        f("rf_bilateral_paraesthesia", m)
        f("rf_gait_disturbance",       m)
        txt("spinal_cord_action",      m)

    sub("Differential — Ankylosing Spondylitis")
    f("diff_as_insidious",          m)
    f("diff_as_lumbar_sij",         m)
    f("diff_as_inflammatory",       m)
    f("diff_as_breathing",          m)
    f("diff_as_fever_weight_loss",  m)
    f("diff_as_likelihood",         m)
    txt("diff_as_action",           m)

    sub("Differential — Abdominal Aortic Aneurysm")
    f("diff_aaa_pulsating",  m)
    f("diff_aaa_age_50",     m)
    f("diff_aaa_cvd_risk",   m)
    f("diff_aaa_ruptured",   m)
    f("diff_aaa_likelihood", m)
    txt("diff_aaa_action",   m)

    sub("Differential — Vascular Claudication")
    f("diff_vc_non_dermatomal", m)
    f("diff_vc_age_50",         m)
    f("diff_vc_cvd_risk",       m)
    f("diff_vc_walking_pain",   m)
    f("diff_vc_pvd_signs",      m)
    f("diff_vc_impotence",      m)
    f("diff_vc_night_pain",     m)
    f("diff_vc_likelihood",     m)
    txt("diff_vc_action",       m)

    sub("Medications")
    meds_list = m.get("medications", [])
    if meds_list:
        med_rows = []
        for i, med in enumerate(meds_list, 1):
            name     = (med.get("name", "") or "").strip()
            dose     = (med.get("dose", "") or "").strip()
            timing   = (med.get("timing", "") or "").strip()
            comments = (med.get("comments", "") or "").strip()
            med_rows.append([str(i), name or "—", dose or "—", timing or "—", comments or "—"])
        _emit(*_md_table(["#", "Name", "Dose", "Timing", "Comments"], med_rows))
    elif not clean:
        _emit("*(none recorded)*")

    sub("Imaging")
    _IMG = [
        ("Xray",  "img_xray",  "img_xray_detail"),
        ("U/S",   "img_us",    "img_us_detail"),
        ("CT",    "img_ct",    "img_ct_detail"),
        ("MRI",   "img_mri",   "img_mri_detail"),
        ("NCS",   "img_ncs",   "img_ncs_detail"),
        ("Other", "img_other", "img_other_detail"),
    ]
    if clean:
        for lbl, bid, did in _IMG:
            val = m.get(bid)
            det = (m.get(did) or "").strip()
            if val is True or det:
                line = f"**{lbl}**" + (f": {det}" if det else "")
                _emit(line + "  ")
            elif val is False:
                _emit(f"**{lbl}:** Not performed  ")
    else:
        for lbl, bid, did in _IMG:
            val = m.get(bid)
            det = (m.get(did) or "").strip()
            line = f"**{lbl}:** {_v(val)}" + (f" — {det}" if det else "")
            _emit(line)

    _emit_yaml_subs_md("medical", m, clean, _emit, sub)

    # ════════════════════════════════════════════════════════════════════════
    # SOAP: OBJECTIVE
    # ════════════════════════════════════════════════════════════════════════
    lines.append("\n# O — Objective\n")
    _obj_md_lines = _render_objective_md(obj_assessment, clean=clean)
    if _obj_md_lines:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.extend(_obj_md_lines)

    # ════════════════════════════════════════════════════════════════════════
    # SOAP: ASSESSMENT
    # ════════════════════════════════════════════════════════════════════════
    lines.append("\n# A — Assessment\n")

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 4: PAIN CLASSIFICATION
    # ════════════════════════════════════════════════════════════════════════
    pc = a.get("pain_classification", {}) or {}
    sec("Section 4: Pain Classification")

    if dev:
        _emit_pain_class_dev(pc, clean, _emit, sub)
    else:

        sub("Inflammatory Pain Features")
        if clean:
            _pain_md("Inflammatory", [
                ("Constant pain",     "infl_constant"),
                ("Morning stiffness", "infl_morning"),
                ("Night/sleep pain",  "infl_sleep"),
                ("Activity improves", "infl_activity"),
            ], pc)
        else:
            f("infl_constant",   pc)
            f("infl_morning",    pc)
            f("infl_sleep",      pc)
            f("infl_activity",   pc)
        f("infl_likelihood", pc)

        sub("Nociceptive Pain — Subjective Features")
        if clean:
            _pain_md("Nociceptive (Sx)", [
                ("Mechanical",              "noci_subj_mechanical"),
                ("Trauma/incident",         "noci_subj_trauma"),
                ("Localised",               "noci_subj_localised"),
                ("Resolving",               "noci_subj_resolving"),
                ("Responds to analgesia",   "noci_subj_analgesia"),
                ("Not constant",            "noci_subj_no_constant"),
                ("Local inflammation",      "noci_subj_inflammation"),
                ("Recent onset",            "noci_subj_recent"),
            ], pc)
        else:
            f("noci_subj_mechanical",   pc)
            f("noci_subj_trauma",       pc)
            f("noci_subj_localised",    pc)
            f("noci_subj_resolving",    pc)
            f("noci_subj_analgesia",    pc)
            f("noci_subj_no_constant",  pc)
            f("noci_subj_inflammation", pc)
            f("noci_subj_recent",       pc)

        sub("Nociceptive Pain — Examination Features")
        if clean:
            _pain_md("Nociceptive (Ex)", [
                ("Mechanical reproduction","noci_exam_mechanical"),
                ("Palpation reproduction", "noci_exam_palpation"),
                ("Local hyperalgesia",     "noci_exam_hyperalgesia"),
                ("Antalgic posture",       "noci_exam_antalgic"),
            ], pc)
        else:
            f("noci_exam_mechanical",   pc)
            f("noci_exam_palpation",    pc)
            f("noci_exam_hyperalgesia", pc)
            f("noci_exam_antalgic",     pc)
        f("noci_likelihood",        pc)
        txt("noci_interpretation",  pc)

        sub("Neuropathic Pain — Subjective Features")
        if clean:
            _pain_md("Neuropathic (Sx)", [
                ("Burning/electric/shooting quality","neuro_subj_quality"),
                ("Known nerve injury",               "neuro_subj_nerve_injury"),
                ("Neurological symptoms",            "neuro_subj_neurological"),
                ("Dermatomal/nerve trunk",           "neuro_subj_dermatomal"),
                ("Responds to neuropathic meds",     "neuro_subj_medication"),
                ("Severe/night pain",                "neuro_subj_severity"),
                ("Provoked by neural loading",       "neuro_subj_neural_loading"),
                ("Dysaesthesia/allodynia",           "neuro_subj_dysaesthesia"),
                ("Spontaneous pain",                 "neuro_subj_spontaneous"),
            ], pc)
        else:
            f("neuro_subj_quality",         pc)
            f("neuro_subj_nerve_injury",    pc)
            f("neuro_subj_neurological",    pc)
            f("neuro_subj_dermatomal",      pc)
            f("neuro_subj_medication",      pc)
            f("neuro_subj_severity",        pc)
            f("neuro_subj_neural_loading",  pc)
            f("neuro_subj_dysaesthesia",    pc)
            f("neuro_subj_spontaneous",     pc)

        sub("Neuropathic Pain — Examination Features")
        if clean:
            _pain_md("Neuropathic (Ex)", [
                ("Positive neurodynamic test",   "neuro_exam_neurodynamic"),
                ("Neural palpation sensitive",   "neuro_exam_neural_palpation"),
                ("Neurology change",             "neuro_exam_neurology"),
                ("Antalgic posture",             "neuro_exam_antalgic"),
                ("Hyperalgesia in distribution", "neuro_exam_hyperalgesia"),
            ], pc)
        else:
            f("neuro_exam_neurodynamic",     pc)
            f("neuro_exam_neural_palpation", pc)
            f("neuro_exam_neurology",        pc)
            f("neuro_exam_antalgic",         pc)
            f("neuro_exam_hyperalgesia",     pc)
        f("neuro_likelihood",            pc)
        txt("neuro_interpretation",      pc)

        sub("Nociplastic Pain — Subjective Features")
        if clean:
            _pain_md("Nociplastic (Sx)", [
                ("Disproportionate to pathology",    "nocip_subj_disproportionate"),
                ("Persistent beyond healing",        "nocip_subj_persistent"),
                ("Disproportionate to stimulus",     "nocip_subj_disproportionate2"),
                ("Widespread/multifocal",            "nocip_subj_widespread"),
                ("Failed previous treatment",        "nocip_subj_failed"),
                ("Psychosocial contributors",        "nocip_subj_psychosocial"),
                ("Responds to centrally-acting meds","nocip_subj_medication"),
                ("Spontaneous pain",                 "nocip_subj_spontaneous"),
                ("High disability",                  "nocip_subj_disability"),
                ("Constant/unpredictable",           "nocip_subj_constant"),
                ("Disturbed sleep/night pain",       "nocip_subj_night_pain"),
                ("Dysaesthesia",                     "nocip_subj_dysaesthesia"),
                ("Severe/difficult to control",      "nocip_subj_severity"),
            ], pc)
        else:
            f("nocip_subj_disproportionate",  pc)
            f("nocip_subj_persistent",        pc)
            f("nocip_subj_disproportionate2", pc)
            f("nocip_subj_widespread",        pc)
            f("nocip_subj_failed",            pc)
            f("nocip_subj_psychosocial",      pc)
            f("nocip_subj_medication",        pc)
            f("nocip_subj_spontaneous",       pc)
            f("nocip_subj_disability",        pc)
            f("nocip_subj_constant",          pc)
            f("nocip_subj_night_pain",        pc)
            f("nocip_subj_dysaesthesia",      pc)
            f("nocip_subj_severity",          pc)

        sub("Nociplastic Pain — Examination Features")
        if clean:
            _pain_md("Nociplastic (Ex)", [
                ("Disproportionate exam findings",    "nocip_exam_disproportionate"),
                ("Widespread hyperalgesia/allodynia", "nocip_exam_hyperalgesia"),
                ("Diffuse palpation tenderness",      "nocip_exam_diffuse"),
                ("Psychosocial features on exam",     "nocip_exam_psychosocial"),
            ], pc)
        else:
            f("nocip_exam_disproportionate", pc)
            f("nocip_exam_hyperalgesia",     pc)
            f("nocip_exam_diffuse",          pc)
            f("nocip_exam_psychosocial",     pc)
        f("nocip_likelihood",            pc)
        txt("nocip_interpretation",      pc)

        sub("Central Sensitisation")
        f("csi_score", pc)
        if clean:
            _pain_md("CS features", [
                ("Light sensitivity",        "cs_light"),
                ("Touch sensitivity",        "cs_touch"),
                ("Noise sensitivity",        "cs_noise"),
                ("Chemical/smell sensitivity","cs_pesticides"),
                ("Temperature sensitivity",  "cs_temperature"),
                ("Fatigue",                  "cs_fatigue"),
                ("Sleep disturbance",        "cs_sleep"),
                ("Concentration difficulty", "cs_concentration"),
                ("Perceived swelling",       "cs_swelling"),
                ("Tingling",                 "cs_tingling"),
            ], pc)
        else:
            f("cs_light",         pc)
            f("cs_touch",         pc)
            f("cs_noise",         pc)
            f("cs_pesticides",    pc)
            f("cs_temperature",   pc)
            f("cs_fatigue",       pc)
            f("cs_sleep",         pc)
            f("cs_concentration", pc)
            f("cs_swelling",      pc)
            f("cs_tingling",      pc)

        sub("Fibromyalgia")
        if clean:
            _pain_md("FM scores", [
                ("WPI (0–19)",              "fm_wpi"),
                ("Fatigue severity (0–3)",  "fm_fatigue"),
                ("Waking unrefreshed (0–3)","fm_waking"),
                ("Cognitive symptoms (0–3)","fm_cognitive"),
                ("Headaches",               "fm_headaches"),
                ("IBS",                     "fm_ibs"),
                ("Depression",              "fm_depression"),
                ("Symptoms ≥ 3 months",     "fm_duration"),
                ("No alternative explanation","fm_exclusion"),
            ], pc)
        else:
            f("fm_wpi",       pc)
            f("fm_fatigue",   pc)
            f("fm_waking",    pc)
            f("fm_cognitive", pc)
            f("fm_headaches", pc)
            f("fm_ibs",       pc)
            f("fm_depression",pc)
            f("fm_duration",  pc)
            f("fm_exclusion", pc)

        sub("BACPAP LBP Phenotyping")
        if clean:
            _pain_md("BACPAP", [
                ("LBP ≥ 3 months",                  "bacpap_chronic"),
                ("Regional/widespread distribution", "bacpap_distribution"),
                ("Nociceptive mainly responsible",   "bacpap_nociceptive"),
                ("Neuropathic mainly responsible",   "bacpap_neuropathic"),
                ("Static mechanical allodynia",      "bacpap_static"),
                ("Dynamic mechanical allodynia",     "bacpap_dynamic"),
                ("Heat or cold allodynia",           "bacpap_thermal"),
                ("Painful after-sensations",         "bacpap_after"),
                ("Hypersensitivity — touch",         "bacpap_hyper_touch"),
                ("Hypersensitivity — movement",      "bacpap_hyper_movement"),
                ("Hypersensitivity — pressure",      "bacpap_hyper_pressure"),
                ("Hypersensitivity — heat",          "bacpap_hyper_heat"),
                ("Hypersensitivity — cold",          "bacpap_hyper_cold"),
                ("Comorbid — light/sound/odour sensitivity", "bacpap_como_sensory"),
                ("Comorbid — sleep disturbance",     "bacpap_como_sleep"),
                ("Comorbid — fatigue",               "bacpap_como_fatigue"),
                ("Comorbid — cognitive problems",    "bacpap_como_cognitive"),
            ], pc)
        else:
            f("bacpap_chronic",      pc)
            f("bacpap_distribution", pc)
            f("bacpap_nociceptive",  pc)
            f("bacpap_neuropathic",  pc)
            f("bacpap_static",       pc)
            f("bacpap_dynamic",      pc)
            f("bacpap_thermal",      pc)
            f("bacpap_after",        pc)
            f("bacpap_hyper_touch",     pc)
            f("bacpap_hyper_movement",  pc)
            f("bacpap_hyper_pressure",  pc)
            f("bacpap_hyper_heat",      pc)
            f("bacpap_hyper_cold",      pc)
            f("bacpap_como_sensory",    pc)
            f("bacpap_como_sleep",      pc)
            f("bacpap_como_fatigue",    pc)
            f("bacpap_como_cognitive",  pc)
        txt("bacpap_notes",          pc)

        sub("Pain Type Summary")
        f("summary_dominant",        pc)
        txt("summary_contributing",  pc)
        txt("summary_reasoning",     pc)

    _emit_yaml_subs_md("pain_classification", pc, clean, _emit, sub)
    # ════════════════════════════════════════════════════════════════════════
    # SECTION 5: OUTCOME MEASURES
    # ════════════════════════════════════════════════════════════════════════
    om = a.get("outcome_measures", {}) or {}
    sec("Section 5: Outcome Measures")

    sub("Patient Specific Functional Scale (PSFS)")
    f("psfs_act_1", om)
    f("psfs_act_2",  om)
    f("psfs_act_3",  om)

    sub("Brief Pain Inventory (BPI) — interference /10")
    f("bpi_activity",  om)
    f("bpi_mood",      om)
    f("bpi_walking",   om)
    f("bpi_work",      om)
    f("bpi_relations", om)
    f("bpi_sleep",     om)
    f("bpi_enjoyment", om)

    sub("DASS-21")
    f("dass_dep_score",  om)
    f("dass_dep_interp", om)
    f("dass_anx_score",  om)
    f("dass_anx_interp", om)
    f("dass_str_score",  om)
    f("dass_str_interp", om)

    sub("PHQ-4")
    f("phq4_nervous",   om)
    f("phq4_worry",     om)
    f("phq4_noint",     om)
    f("phq4_depressed", om)

    sub("Pain Catastrophising Scale (PCS)")
    f("pcs_rum_score",   om)
    f("pcs_rum_risk",    om)
    f("pcs_mag_score",   om)
    f("pcs_mag_risk",    om)
    f("pcs_help_score",  om)
    f("pcs_help_risk",   om)
    f("pcs_total_score", om)
    f("pcs_total_risk",  om)

    sub("Pain Self-Efficacy Questionnaire (PSEQ / PSEQ-2)")
    f("pseq_score",   om)
    f("pseq_interp",  om)
    f("pseq2_score",  om)
    f("pseq2_interp", om)

    sub("PCL-5 (PTSD)")
    f("pcl5_score",    om)
    f("pcl5_interp",   om)
    txt("pcl5_action", om)

    sub("Sleep Measures")
    f("isi_score",   om)
    f("isi_interp",  om)
    f("pbas_score",  om)
    f("pbas_interp", om)

    sub("Additional Measures")
    f("add_audit",  om)
    f("add_dudit",  om)
    txt("add_epoc", om)
    txt("add_other", om)

    sub("Planned Outcome Measures")
    f("plan_psfs",       om)
    f("plan_bpi",        om)
    f("plan_dass",       om)
    f("plan_phq4",       om)
    f("plan_pcs",        om)
    f("plan_pseq",       om)
    f("plan_pcl5",       om)
    f("plan_sleep",      om)
    f("plan_additional", om)

    sub("Hypothesis Testing")
    hyp_rows = []
    for i in range(3):
        measure   = (om.get(f"hyp_{i}_measure",   "") or "").strip()
        baseline  = (om.get(f"hyp_{i}_baseline",  "") or "").strip()
        interval  = (om.get(f"hyp_{i}_interval",  "") or "").strip()
        rationale = (om.get(f"hyp_{i}_rationale", "") or "").strip()
        if clean and not any([measure, baseline, interval, rationale]):
            continue
        hyp_rows.append([str(i + 1), measure or "—", baseline or "—", interval or "—", rationale or "—"])
    if hyp_rows:
        _emit(*_md_table(["#", "Measure", "Baseline", "Interval", "Rationale"], hyp_rows))

    _emit_yaml_subs_md("outcome_measures", om, clean, _emit, sub)
    # ════════════════════════════════════════════════════════════════════════
    # SECTION 6: DIAGNOSIS
    # ════════════════════════════════════════════════════════════════════════
    dx = a.get("diagnosis", {}) or {}
    sec("Section 6: Diagnosis")

    workups = dx.get("workups") or []
    if workups:
        # CAL-CP (ICD-11 Chronic Pain Classification Algorithm) result —
        # compact by design (this report is the clinical-facing summary;
        # the full per-question decision path lives in the raw report
        # only). One line per workup/pain site; incomplete workups show
        # the last node reached rather than being silently omitted.
        sub("ICD-11 Diagnosis (CAL-CP)")
        for wd in workups:
            wu = _CalCpWorkup.from_dict(wd)
            line = f"**{wu.label}:** {wu.result_or_progress_text()}"
            _emit(line + "  " if clean else line)
    else:
        # Pre-CAL-CP sessions (or sessions never re-opened since the
        # rebuild) keep their old free-form fields under "legacy" —
        # rendered as-is rather than silently dropped.
        legacy = dx.get("legacy") or dx
        sub("ICD-11 Pathway Selection")
        f("duration_over_3_months", legacy)
        f("mechanism",              legacy)

        sub("Chronic Primary Pain")
        f("primary_distress",     legacy)
        f("primary_not_other_dx", legacy)
        f("primary_subtype",      legacy)
        f("primary_severity",     legacy)

        sub("Chronic Post-Surgical Pain")
        f("surgical_procedure", legacy)
        f("surgical_subtype",   legacy)
        f("surgical_source",    legacy)
        f("surgical_severity",  legacy)

        sub("Chronic Post-Traumatic Pain")
        f("traumatic_event",    legacy)
        f("traumatic_subtype",  legacy)
        f("traumatic_source",   legacy)
        f("traumatic_severity", legacy)

        sub("Chronic Secondary MSK Pain")
        f("msk_pathology", legacy)
        f("msk_subtype",   legacy)
        f("msk_source",    legacy)
        f("msk_severity",  legacy)

        sub("Chronic Neuropathic Pain")
        f("neuro_lesion",   legacy)
        f("neuro_subtype",  legacy)
        f("neuro_severity", legacy)

        sub("Mixed / Indeterminate")
        f("mixed_dominant",    legacy)
        txt("mixed_reasoning", legacy)

    _emit_yaml_subs_md("diagnosis", dx, clean, _emit, sub)

    # ════════════════════════════════════════════════════════════════════════
    # SOAP: PLAN
    # ════════════════════════════════════════════════════════════════════════
    lines.append("\n# P — Plan\n")

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 7: BARRIERS & TREATMENT PLAN
    # ════════════════════════════════════════════════════════════════════════
    br = a.get("barriers", {}) or {}
    sec("Section 7: Barriers & Treatment Plan")

    # ── clean-mode barrier helper (md) ───────────────────────────────────
    def _barrier_md(prefix: str, items: list, d: dict) -> None:
        """Render assessed barriers as a markdown table — selected implies present;
        only an explicit 'No' on the widget shows as Absent."""
        rows = []
        for label, key, sub_items in items:
            val = d.get(key)
            if val is None:
                continue
            if val is True:
                sub_parts = []
                for sub_label, sub_key in sub_items:
                    sv = d.get(sub_key)
                    if sv is True:
                        sub_parts.append(sub_label)
                    elif isinstance(sv, str) and sv.strip():
                        sub_parts.append(sv.strip())
                entry = label + (f" ({', '.join(sub_parts)})" if sub_parts else "")
            else:
                entry = f"{label} — Absent"
            rows.append([entry])
        if rows:
            _emit(*_md_table(["Barrier"], rows))
            _emit("")

    _NOCI_B = [
        ("Disease/pathology",      "b_noci_disease",        []),
        ("Pacing issues",          "b_noci_pacing",         []),
        ("Inflammatory",           "b_noci_inflammatory",   []),
        ("Deconditioning",         "b_noci_deconditioning", []),
        ("Reduced movement",       "b_noci_movement",       [("Region", "bi_movement_region")]),
        ("Gait",                   "b_noci_gait",           []),
        ("Strength deficits",      "b_noci_strength",       [
            ("Glute max",  "bx_strength_glute_max"),
            ("Glute med",  "bx_strength_glute_med"),
            ("Iliopsoas",  "bx_strength_iliopsoas"),
            ("Quads",      "bx_strength_quads"),
            ("Other",      "bi_strength_other"),
        ]),
        ("Deep muscle",            "b_noci_deep_muscle",    [
            ("Multifidus", "bx_deep_multifidus"),
            ("TA",         "bx_deep_ta"),
            ("Erector",    "bx_deep_erector"),
            ("Other",      "bi_deep_other"),
        ]),
        ("Overactivity",           "b_noci_overactivity",   [
            ("Erector",    "bx_over_erector"),
            ("QL",         "bx_over_ql"),
            ("RA",         "bx_over_ra"),
            ("Obliques",   "bx_over_obliques"),
            ("Piriformis", "bx_over_piriformis"),
            ("Iliopsoas",  "bx_over_iliopsoas"),
            ("Hamstrings", "bx_over_hamstrings"),
            ("Adductors",  "bx_over_adductors"),
            ("Other",      "bi_over_other"),
        ]),
        ("Nerve mechanosensitivity","b_noci_nerve_mech",    [("Region", "bi_nerve_region")]),
        ("Diet/weight",            "b_noci_diet",           []),
    ]
    _PSYCH_B = [
        ("Depression",            "b_psych_depression",       [
            ("Severity",           "bx_dep_severity"),
            ("Psychiatry ref",     "bx_dep_psychiatry"),
        ]),
        ("Anxiety",               "b_psych_anxiety",          [
            ("Severity",           "bx_anx_severity"),
            ("Psychiatry ref",     "bx_anx_psychiatry"),
        ]),
        ("Stress",                "b_psych_stress",           [
            ("Severity",           "bx_stress_severity"),
            ("Psychiatry ref",     "bx_stress_psychiatry"),
        ]),
        ("Catastrophising",       "b_psych_catastrophising",  []),
        ("Reduced self-efficacy", "b_psych_self_efficacy",    []),
        ("Unhelpful beliefs",     "b_psych_unhelpful_beliefs",[
            ("Unrealistic expectations","bx_belief_expectations"),
            ("Symptom focus",           "bx_belief_symptom_focus"),
            ("Cure focus",              "bx_belief_cure_focus"),
            ("Further treatment",       "bx_belief_further_tx"),
        ]),
        ("PTSD",                  "b_psych_ptsd",             [
            ("Mechanism",          "bx_ptsd_mechanism"),
            ("Psychiatry ref",     "bx_ptsd_psychiatry"),
        ]),
        ("Unclear readiness",     "b_psych_readiness",        []),
    ]
    _SOCIAL_B = [
        ("Disturbed sleep",   "b_sleep_disturbed",  []),
        ("Home/social",       "b_social_home",      [
            ("Family support",   "bx_soc_family_support"),
            ("Social support",   "bx_soc_social_support"),
            ("Relationship",     "bx_soc_relationship"),
            ("Personal rel",     "bx_soc_personal_rel"),
            ("Financial",        "bx_soc_financial"),
            ("Residential",      "bx_soc_residential"),
            ("Distance to care", "bx_soc_distance"),
        ]),
        ("Return to work",    "b_social_rtw",       []),
    ]
    _MED_B = [
        ("Red flag",             "b_med_red_flag",    [("Detail", "bi_red_flag_detail")]),
        ("Substance use",        "b_med_substance",   [("Detail", "bi_substance_detail")]),
        ("Possible AS",          "b_med_as",          []),
        ("Possible AAA",         "b_med_aaa",         []),
        ("Vascular claudication","b_med_vascular",    []),
        ("Cervical headache",    "b_med_cervical_ha", []),
        ("Medico-legal",         "b_med_medico_legal",[]),
    ]

    sub("Physical / Nociceptive Barriers")
    if clean:
        _barrier_md("Nociceptive barriers", _NOCI_B, br)
    else:
        f("b_noci_disease",        br)
        f("b_noci_pacing",         br)
        f("b_noci_inflammatory",   br)
        f("b_noci_deconditioning", br)
        f("b_noci_movement",       br)
        f("bi_movement_region",    br)
        f("b_noci_gait",           br)
        f("b_noci_strength",       br)
        f("bx_strength_glute_max", br)
        f("bx_strength_glute_med", br)
        f("bx_strength_iliopsoas", br)
        f("bx_strength_quads",     br)
        f("bi_strength_other",     br)
        f("b_noci_deep_muscle",    br)
        f("bx_deep_multifidus",    br)
        f("bx_deep_ta",            br)
        f("bx_deep_erector",       br)
        f("bi_deep_other",         br)
        f("b_noci_overactivity",   br)
        f("bx_over_erector",       br)
        f("bx_over_ql",            br)
        f("bx_over_ra",            br)
        f("bx_over_obliques",      br)
        f("bx_over_piriformis",    br)
        f("bx_over_iliopsoas",     br)
        f("bx_over_hamstrings",    br)
        f("bx_over_adductors",     br)
        f("bi_over_other",         br)
        f("b_noci_nerve_mech",     br)
        f("bi_nerve_region",       br)
        f("b_noci_diet",           br)

    sub("Neuropathic Barriers")
    if clean:
        _barrier_md("Neuropathic barriers", [
            ("Neuropathic (confirmed)",   "b_neuro_confirmed",   []),
            ("Neuropathic (unconfirmed)", "b_neuro_unconfirmed", []),
        ], br)
    else:
        f("b_neuro_confirmed",   br)
        f("b_neuro_unconfirmed", br)

    sub("Nociplastic / Central Sensitisation Barriers")
    if clean:
        _barrier_md("Nociplastic barriers", [
            ("Nociplastic/CS", "b_nocip_moderate", []),
            ("CRPS",           "b_nocip_crps",     []),
            ("FND",            "b_nocip_fnd",      []),
        ], br)
    else:
        f("b_nocip_moderate", br)
        f("b_nocip_crps",     br)
        f("b_nocip_fnd",      br)

    sub("Psychological Barriers")
    if clean:
        _barrier_md("Psychological barriers", _PSYCH_B, br)
    else:
        f("b_psych_depression",        br)
        f("bx_dep_severity",           br)
        f("bx_dep_psychiatry",         br)
        f("b_psych_anxiety",           br)
        f("bx_anx_severity",           br)
        f("bx_anx_psychiatry",         br)
        f("b_psych_stress",            br)
        f("bx_stress_severity",        br)
        f("bx_stress_psychiatry",      br)
        f("b_psych_catastrophising",   br)
        f("b_psych_self_efficacy",     br)
        f("b_psych_unhelpful_beliefs", br)
        f("bx_belief_expectations",    br)
        f("bx_belief_symptom_focus",   br)
        f("bx_belief_cure_focus",      br)
        f("bx_belief_further_tx",      br)
        f("b_psych_ptsd",              br)
        f("bx_ptsd_mechanism",         br)
        f("bx_ptsd_psychiatry",        br)
        f("b_psych_readiness",         br)

    sub("Sleep & Social / Contextual Barriers")
    if clean:
        _barrier_md("Sleep/social barriers", _SOCIAL_B, br)
    else:
        f("b_sleep_disturbed",     br)
        f("b_social_home",         br)
        f("bx_soc_family_support", br)
        f("bx_soc_social_support", br)
        f("bx_soc_relationship",   br)
        f("bx_soc_personal_rel",   br)
        f("bx_soc_financial",      br)
        f("bx_soc_residential",    br)
        f("bx_soc_distance",       br)
        f("b_social_rtw",          br)

    sub("Medical / Systemic Barriers")
    if clean:
        _barrier_md("Medical barriers", _MED_B, br)
    else:
        f("b_med_red_flag",      br)
        f("bi_red_flag_detail",  br)
        f("b_med_substance",     br)
        f("bi_substance_detail", br)
        f("b_med_as",            br)
        f("b_med_aaa",           br)
        f("b_med_vascular",      br)
        f("b_med_cervical_ha",   br)
        f("b_med_medico_legal",  br)

    sub("Custom Barriers")
    f("custom_1_barrier",  br)
    f("custom_1_strategy", br)
    f("custom_2_barrier",  br)
    f("custom_2_strategy", br)

    _emit_yaml_subs_md("barriers", br, clean, _emit, sub)

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 8: RX PLAN
    # ════════════════════════════════════════════════════════════════════════
    rp = a.get("rx_plan", {}) or {}
    sec("Section 8: Rx Plan")

    sub("Treatment Plan Summary")
    f("tx_pain_type",           rp)
    f("tx_debunk_radiology",    rp)
    f("tx_consent_explanation", rp)
    txt("tx_goal_orientation",  rp)
    txt("tx_formulation",       rp)
    txt("tx_program",           rp)
    txt("tx_home_program",      rp)
    txt("tx_psychosocial",      rp)
    txt("tx_medical",           rp)
    txt("tx_rtw",               rp)

    sub("Session 1 Treatment")
    txt("s1_education",     rp)
    txt("s1_experiential",  rp)
    f("s1_consent_content", rp)
    f("s1_confidence_nrs",  rp)
    f("hw_online_module",   rp)
    f("hw_mindfulness",     rp)
    f("hw_goal_sheet",      rp)
    f("hw_activity_diary",  rp)
    f("hw_sleep_diary",     rp)
    txt("s1_hw_other",      rp)
    f("tx_email_obtained",  rp)
    f("tx_display_book",    rp)

    sub("Day 1 Checklist")
    f("d1_explanation",       rp)
    f("d1_session2",          rp)
    f("d1_hypothesis",        rp)
    f("d1_diagnosis",         rp)
    f("d1_values",            rp)
    f("d1_evidence",          rp)
    f("d1_plan",              rp)
    f("d1_prognosis",         rp)
    f("d1_stakeholders",      rp)
    f("d1_confidence_tested", rp)
    f("d1_questionnaires",    rp)

    sub("Follow-Up Plan")
    txt("fu_next_focus",   rp)
    txt("fu_monitoring",   rp)
    f("fu_om_schedule",    rp)
    f("ps_questionnaires", rp)
    f("ps_eppoc",          rp)
    f("ps_ptsd_scored",    rp)
    f("ps_isi_pbas",       rp)
    f("ps_csi",            rp)
    f("ps_audit_dudit",    rp)

    # ════════════════════════════════════════════════════════════════════════
    # BODY CHART SUMMARY — omitted in clean mode
    # ════════════════════════════════════════════════════════════════════════
    if not clean:
        subj_chart = data.get("subjective", {}) or {}
        obj_chart  = data.get("objective",  {}) or {}
        sec("Body Chart Summary")
        n_strokes = len(subj_chart.get("strokes", []))
        n_notes   = len(subj_chart.get("notes", []))
        n_arrows  = len(subj_chart.get("arrows", []))
        n_zones   = len(obj_chart.get("zones", []))
        n_points  = len(obj_chart.get("points", []))
        _emit(f"**Symptom strokes drawn:** {n_strokes}",
              f"**Note annotations:** {n_notes}",
              f"**Arrows:** {n_arrows}",
              f"**Objective zones:** {n_zones}",
              f"**Measurement points (PPT):** {n_points}")

    # ── Write ──────────────────────────────────────────────────────────────
    if _MD_H_OFFSET:
        lines = [_shift_md_heading(ln, _MD_H_OFFSET) for ln in lines]
    try:
        out_path.write_text("\n".join(lines))
        logger.info(f"Report written to {out_path}")
        return str(out_path)
    except Exception as e:
        logger.error(f"export_session_report write failed: {e}")
        return ""


def save_all_sections(
    session_file: str,
    assessment: dict,
    sections_complete: dict[str, bool],
) -> bool:
    """
    Save all assessment sections in a single atomic write.

    Reads the current JSON to preserve body chart and other top-level data,
    replaces each named section under assessment.{key}, updates
    sections_complete and sections_last_modified, then writes atomically.

    assessment keys must match the JSON sub-keys:
      consent, subjective, medical, pain_classification,
      outcome_measures, diagnosis, barriers, scratchpad
    """
    # Write to TUI-owned _assessment.json — GTK never touches this file.
    path = assessment_path(session_file)
    try:
        data = json.loads(path.read_text()) if path.exists() else {}

        if "assessment" not in data:
            data["assessment"] = {}
        for key, val in assessment.items():
            data["assessment"][key] = val
        data["assessment"]["modified"] = int(time.time())

        if "sections_complete" not in data:
            data["sections_complete"] = {}
        if "sections_last_modified" not in data:
            data["sections_last_modified"] = {}
        now = int(time.time())
        for section_id, complete in sections_complete.items():
            data["sections_complete"][section_id] = complete
            data["sections_last_modified"][section_id] = now

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)

        logger.debug(f"Saved all sections to {path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save all sections to {path}: {e}")
        return False


# ---------------------------------------------------------------------------
# Raw report export
# ---------------------------------------------------------------------------

LABELS: dict[str, str] = {
    # ── 01 Consent ──────────────────────────────────────────────────────────
    "consent_to_proceed":               "Consent to proceed",
    "consent_sensitive_topics":         "Consent to discuss sensitive topics",
    "preferred_name":                   "Preferred name",
    "pain_multifactorial_explained":    "Pain as multifactorial explained",
    "education_as_treatment_explained": "Education as part of treatment explained",
    "patient_expectations":             "Patient expectations",
    "reason_for_attending":             "Reason for attending",
    "cause_understanding":              "Has understanding of cause",
    "cause_understanding_detail":       "Understanding of cause (detail)",
    "prognosis_expectations":           "Prognosis expectations",
    "treatment_preference":             "Treatment preference",
    "belief_hurt_harm":                 "Belief: Hurt=Harm",
    "belief_unsafe":                    "Belief: Unsafe to move",
    "belief_passive":                   "Belief: Passive coping",
    "belief_rehab":                     "Belief: Rehab-oriented",
    "belief_high_se":                   "Belief: High self-efficacy",
    "belief_internal_locus":            "Belief: Internal locus of control",
    "belief_notes":                     "Beliefs (notes)",
    # ── 02 Subjective ───────────────────────────────────────────────────────
    "body_chart_completed":             "Body chart completed",
    "course_improving":                 "Course: Improving",
    "course_worsening":                 "Course: Worsening",
    "course_stable":                    "Course: Stable",
    "course_fluctuating":               "Course: Fluctuating",
    "behaviour_boom_bust":               "Behaviour: Boom-Bust",
    "behaviour_avoidance":              "Behaviour: Avoidance",
    "behaviour_endurance":              "Behaviour: Endurance",
    "behaviour_flareups":               "Behaviour: Flare-ups",
    "sleep_overall_rating":             "Sleep overall rating",
    "sleep_feels_rested":               "Feels rested",
    "mood_influences":                  "Mood influences pain",
    "mood_text":                        "Mood / emotional context",
    "hr24_am":                          "24hr pattern — Morning",
    "hr24_day":                         "24hr pattern — Daytime",
    "hr24_pm":                          "24hr pattern — Evening",
    "hr24_nocte":                       "24hr pattern — Night",
    "self_harm_risk":                   "Self-harm risk assessed",
    "symptom_location":                 "Symptom location",
    "symptom_nature":                   "Nature of symptoms",
    "onset":                            "Onset",
    "duration":                         "Duration",
    "context_at_onset":                 "Context at onset",
    "previous_episodes":                "Previous episodes",
    "previous_treatment":               "Previous treatment",
    "behaviour_boom_bust_text":         "Boom-Bust (notes)",
    "behaviour_avoidance_text":         "Avoidance (notes)",
    "behaviour_endurance_text":         "Endurance (notes)",
    "behaviour_flareups_text":          "Flare-ups (notes)",
    "flareup_prevention":               "Flare-up prevention",
    "management_strategies":            "Management strategies",
    "pre_activity_level":               "Pre-injury activity level",
    "current_activity_level":           "Current activity level",
    "exercise_type":                    "Exercise type",
    "exercise_dose":                    "Exercise dose",
    "exercise_response":                "Exercise response",
    "pre_injury_role":                  "Pre-injury work role",
    "pre_injury_duties":                "Pre-injury duties",
    "current_work_status":              "Current work status",
    "current_duties":                   "Current duties",
    "sleep_postural_factors":           "Sleep postural factors",
    "sleep_environment_quality":        "Sleep environment quality",
    "sleep_overall_comments":           "Sleep overall comments",
    "energy_levels":                    "Energy levels",
    "aggravating_factors":              "Aggravating factors",
    "easing_factors":                   "Easing factors",
    "daily_pattern_comments":           "Daily pattern comments",
    "social_situation":                 "Social situation",
    "financial_status":                 "Financial status",
    "cultural_considerations":          "Cultural considerations",
    "psychological_distress":           "Psychological distress",
    "screening_tool":                   "Screening tool used",
    "harm_plan":                        "Harm plan",
    "harm_means":                       "Harm means",
    "harm_intent":                      "Harm intent",
    "harm_action":                      "Harm action",
    "pain_control_score":               "Pain control score",
    "confidence_score":                 "Confidence score (PSEQ-2)",
    "pre_injury_hours":                 "Pre-injury work hours/week",
    "current_hours":                    "Current work hours/week",
    "sleep_time_to_bed":                "Time to bed",
    "sleep_time_attempt":               "Time to attempt sleep",
    "sleep_onset_time":                 "Sleep onset time (clock)",
    "sleep_waso_clock":                 "WASO — time (clock)",
    "sleep_waso_duration":              "WASO — duration",
    "sleep_awake_in_bed":               "Time awake in bed",
    "sleep_awake_out_bed":              "Time awake out of bed",
    "sleep_final_wakeup":               "Final wake up",
    "sleep_time_out_of_bed":            "Time out of bed",
    "sleep_efficiency":                 "Sleep efficiency (%)",
    "sleep_daytime_naps":               "Daytime naps",
    # ── 03 Medical ──────────────────────────────────────────────────────────
    "no_previous_injuries":             "No previous injuries",
    "previous_injuries":                "Previous injuries (detail)",
    "comorbid_cancer":                  "Comorbidity: Cancer",
    "comorbid_mental_health":           "Comorbidity: Mental health",
    "comorbid_osteoporosis":            "Comorbidity: Osteoporosis",
    "comorbid_inflammatory":            "Comorbidity: Inflammatory arthritis",
    "comorbid_fibromyalgia":            "Comorbidity: Fibromyalgia",
    "comorbid_cfs":                     "Comorbidity: CFS",
    "comorbid_ibs":                     "Comorbidity: IBS",
    "comorbid_whiplash":                "Comorbidity: Whiplash",
    "comorbid_skin_rash":               "Comorbidity: Skin rash",
    "comorbid_drug_alcohol":            "Comorbidity: Drug/alcohol",
    "comorbid_fatigue_memory":          "Comorbidity: Fatigue/memory issues",
    "comorbid_other":                   "Other comorbidities",
    "cvd_hypercholesterolaemia":        "CVD risk: Hypercholesterolaemia",
    "cvd_cardiac":                      "CVD risk: Cardiac disease",
    "cvd_vascular":                     "CVD risk: Vascular disease",
    "cvd_stroke_tia":                   "CVD risk: Stroke/TIA",
    "cvd_diabetes":                     "CVD risk: Diabetes",
    "cvd_corticosteroids":              "CVD risk: Long-term corticosteroids",
    "cvd_clotting":                     "CVD risk: Clotting disorder",
    "cvd_ocp":                          "CVD risk: OCP use",
    "cvd_smoker":                       "CVD risk: Smoker",
    "cvd_postpartum":                   "CVD risk: Postpartum",
    "cvd_familial_history":             "CVD risk: Familial history",
    "rf_weight_loss":                   "Red flag: Unexplained weight loss",
    "rf_cancer_history":                "Red flag: Cancer history",
    "rf_age_50_spinal":                 "Red flag: Age >50 with spinal",
    "rf_failed_conservative":           "Red flag: Failed conservative care",
    "rf_trauma":                        "Red flag: Recent trauma",
    "rf_corticosteroids_fracture":      "Red flag: Corticosteroid fracture risk",
    "rf_osteoporosis_fracture":         "Red flag: Osteoporosis fracture risk",
    "rf_fever":                         "Red flag: Fever",
    "rf_immunosuppressed":              "Red flag: Immunosuppressed",
    "rf_spinal_procedure":              "Red flag: Recent spinal procedure",
    "rf_saddle_anaesthesia":            "Red flag: Saddle anaesthesia",
    "rf_bladder_disturbance":           "Red flag: Bladder disturbance",
    "rf_bowel_disturbance":             "Red flag: Bowel disturbance",
    "rf_bilateral_paraesthesia":        "Red flag: Bilateral paraesthesia",
    "rf_gait_disturbance":              "Red flag: Gait disturbance",
    "cauda_equina_action":              "Cauda equina action taken",
    "spinal_cord_action":               "Spinal cord compression action taken",
    "diff_as_insidious":                "Diff AS: Insidious onset",
    "diff_as_lumbar_sij":               "Diff AS: Lumbar/SIJ location",
    "diff_as_inflammatory":             "Diff AS: Inflammatory pattern",
    "diff_as_breathing":                "Diff AS: Thoracic/breathing",
    "diff_as_fever_weight_loss":        "Diff AS: Fever/weight loss",
    "diff_as_likelihood":               "Diff AS: Likelihood",
    "diff_as_action":                   "Diff AS: Action taken",
    "diff_aaa_pulsating":               "Diff AAA: Pulsating abdominal mass",
    "diff_aaa_age_50":                  "Diff AAA: Age >50",
    "diff_aaa_cvd_risk":                "Diff AAA: CVD risk factors",
    "diff_aaa_ruptured":                "Diff AAA: Ruptured symptoms",
    "diff_aaa_likelihood":              "Diff AAA: Likelihood",
    "diff_aaa_action":                  "Diff AAA: Action taken",
    "diff_vc_non_dermatomal":           "Diff VC: Non-dermatomal leg pain",
    "diff_vc_age_50":                   "Diff VC: Age >50",
    "diff_vc_cvd_risk":                 "Diff VC: CVD risk factors",
    "diff_vc_walking_pain":             "Diff VC: Walking-related pain",
    "diff_vc_pvd_signs":                "Diff VC: PVD signs",
    "diff_vc_impotence":                "Diff VC: Impotence",
    "diff_vc_night_pain":               "Diff VC: Night pain",
    "diff_vc_likelihood":               "Diff VC: Likelihood",
    "diff_vc_action":                   "Diff VC: Action taken",
    # ── 04 Pain Classification ───────────────────────────────────────────────
    "infl_constant":                    "Inflammatory: Constant pain",
    "infl_morning":                     "Inflammatory: Morning stiffness",
    "infl_sleep":                       "Inflammatory: Night/sleep pain",
    "infl_activity":                    "Inflammatory: Activity improves",
    "infl_likelihood":                  "Inflammatory likelihood",
    "noci_subj_mechanical":             "Nociceptive (Sx): Mechanical",
    "noci_subj_trauma":                 "Nociceptive (Sx): Trauma/incident",
    "noci_subj_localised":              "Nociceptive (Sx): Localised",
    "noci_subj_resolving":              "Nociceptive (Sx): Resolving",
    "noci_subj_analgesia":              "Nociceptive (Sx): Responds to analgesia",
    "noci_subj_no_constant":            "Nociceptive (Sx): Not constant",
    "noci_subj_inflammation":           "Nociceptive (Sx): Local inflammation",
    "noci_subj_recent":                 "Nociceptive (Sx): Recent onset",
    "noci_exam_mechanical":             "Nociceptive (Ex): Mechanical reproduction",
    "noci_exam_palpation":              "Nociceptive (Ex): Palpation reproduction",
    "noci_exam_hyperalgesia":           "Nociceptive (Ex): Local hyperalgesia",
    "noci_exam_antalgic":               "Nociceptive (Ex): Antalgic posture",
    "noci_likelihood":                  "Nociceptive likelihood",
    "noci_interpretation":              "Nociceptive interpretation",
    "neuro_subj_quality":               "Neuropathic (Sx): Burning/electric/shooting quality",
    "neuro_subj_nerve_injury":          "Neuropathic (Sx): Known nerve injury/pathology",
    "neuro_subj_neurological":          "Neuropathic (Sx): Neurological symptoms",
    "neuro_subj_dermatomal":            "Neuropathic (Sx): Dermatomal/nerve trunk",
    "neuro_subj_medication":            "Neuropathic (Sx): Responds to neuropathic meds",
    "neuro_subj_severity":              "Neuropathic (Sx): Severe/night pain",
    "neuro_subj_neural_loading":        "Neuropathic (Sx): Provoked by neural loading",
    "neuro_subj_dysaesthesia":          "Neuropathic (Sx): Dysaesthesia/allodynia",
    "neuro_subj_spontaneous":           "Neuropathic (Sx): Spontaneous pain",
    "neuro_exam_neurodynamic":          "Neuropathic (Ex): Positive neurodynamic test",
    "neuro_exam_neural_palpation":      "Neuropathic (Ex): Neural palpation sensitive",
    "neuro_exam_neurology":             "Neuropathic (Ex): Neurology change",
    "neuro_exam_antalgic":              "Neuropathic (Ex): Antalgic posture",
    "neuro_exam_hyperalgesia":          "Neuropathic (Ex): Hyperalgesia in distribution",
    "neuro_likelihood":                 "Neuropathic likelihood",
    "neuro_interpretation":             "Neuropathic interpretation",
    "nocip_subj_disproportionate":      "Nociplastic (Sx): Disproportionate to pathology",
    "nocip_subj_persistent":            "Nociplastic (Sx): Persistent beyond healing",
    "nocip_subj_disproportionate2":     "Nociplastic (Sx): Disproportionate to stimulus",
    "nocip_subj_widespread":            "Nociplastic (Sx): Widespread/multifocal",
    "nocip_subj_failed":                "Nociplastic (Sx): Failed previous treatment",
    "nocip_subj_psychosocial":          "Nociplastic (Sx): Psychosocial contributors",
    "nocip_subj_medication":            "Nociplastic (Sx): Responds to centrally-acting meds",
    "nocip_subj_spontaneous":           "Nociplastic (Sx): Spontaneous pain",
    "nocip_subj_disability":            "Nociplastic (Sx): High disability",
    "nocip_subj_constant":              "Nociplastic (Sx): Constant/unpredictable",
    "nocip_subj_night_pain":            "Nociplastic (Sx): Disturbed sleep/night pain",
    "nocip_subj_dysaesthesia":          "Nociplastic (Sx): Dysaesthesia",
    "nocip_subj_severity":              "Nociplastic (Sx): Severe/difficult to control",
    "nocip_exam_disproportionate":      "Nociplastic (Ex): Disproportionate exam findings",
    "nocip_exam_hyperalgesia":          "Nociplastic (Ex): Widespread hyperalgesia/allodynia",
    "nocip_exam_diffuse":               "Nociplastic (Ex): Diffuse palpation tenderness",
    "nocip_exam_psychosocial":          "Nociplastic (Ex): Psychosocial features on exam",
    "nocip_likelihood":                 "Nociplastic likelihood",
    "nocip_interpretation":             "Nociplastic interpretation",
    "cs_light":                         "CS feature: Light sensitivity",
    "cs_touch":                         "CS feature: Touch sensitivity",
    "cs_noise":                         "CS feature: Noise sensitivity",
    "cs_pesticides":                    "CS feature: Chemical/smell sensitivity",
    "cs_temperature":                   "CS feature: Temperature sensitivity",
    "cs_fatigue":                       "CS feature: Fatigue",
    "cs_sleep":                         "CS feature: Sleep disturbance",
    "cs_concentration":                 "CS feature: Concentration difficulty",
    "cs_swelling":                      "CS feature: Perceived swelling",
    "cs_tingling":                      "CS feature: Tingling",
    "csi_score":                        "CSI score",
    "fm_wpi":                           "FM: WPI score",
    "fm_fatigue":                       "FM: Fatigue severity (0–3)",
    "fm_waking":                        "FM: Waking unrefreshed (0–3)",
    "fm_cognitive":                     "FM: Cognitive symptoms (0–3)",
    "fm_headaches":                     "FM: Headaches",
    "fm_ibs":                           "FM: IBS",
    "fm_depression":                    "FM: Depression",
    "fm_duration":                      "FM: Symptoms ≥ 3 months",
    "fm_exclusion":                     "FM: No alternative explanation",
    "bacpap_chronic":                   "BACPAP: LBP ≥ 3 months",
    "bacpap_distribution":              "BACPAP: Regional/widespread distribution",
    "bacpap_nociceptive":               "BACPAP: Nociceptive mainly responsible",
    "bacpap_neuropathic":               "BACPAP: Neuropathic mainly responsible",
    "bacpap_static":                    "BACPAP: Static mechanical allodynia",
    "bacpap_dynamic":                   "BACPAP: Dynamic mechanical allodynia",
    "bacpap_thermal":                   "BACPAP: Heat or cold allodynia",
    "bacpap_after":                     "BACPAP: Painful after-sensations",
    "bacpap_hyper_touch":               "BACPAP: Hypersensitivity — touch",
    "bacpap_hyper_movement":            "BACPAP: Hypersensitivity — movement",
    "bacpap_hyper_pressure":            "BACPAP: Hypersensitivity — pressure",
    "bacpap_hyper_heat":                "BACPAP: Hypersensitivity — heat",
    "bacpap_hyper_cold":                "BACPAP: Hypersensitivity — cold",
    "bacpap_como_sensory":              "BACPAP: Comorbid — light/sound/odour sensitivity",
    "bacpap_como_sleep":                "BACPAP: Comorbid — sleep disturbance",
    "bacpap_como_fatigue":              "BACPAP: Comorbid — fatigue",
    "bacpap_como_cognitive":            "BACPAP: Comorbid — cognitive problems",
    "bacpap_notes":                     "BACPAP: Notes",
    "summary_dominant":                 "Dominant pain type",
    "summary_contributing":             "Contributing pain types",
    "summary_reasoning":                "Pain classification reasoning",
    # ── 05 Outcome Measures ───────────────────────────────────────────────────
    "psfs_act_1":                       "PSFS activity 1",
    "psfs_act_2":                       "PSFS activity 2",
    "psfs_act_3":                       "PSFS activity 3",
    "bpi_activity":                     "BPI: Activity interference",
    "bpi_mood":                         "BPI: Mood interference",
    "bpi_walking":                      "BPI: Walking interference",
    "bpi_work":                         "BPI: Normal work interference",
    "bpi_relations":                    "BPI: Relations with others",
    "bpi_sleep":                        "BPI: Sleep interference",
    "bpi_enjoyment":                    "BPI: Enjoyment of life interference",
    "dass_dep_score":                   "DASS-21: Depression score",
    "dass_anx_score":                   "DASS-21: Anxiety score",
    "dass_str_score":                   "DASS-21: Stress score",
    "dass_dep_interp":                  "DASS-21: Depression interpretation",
    "dass_anx_interp":                  "DASS-21: Anxiety interpretation",
    "dass_str_interp":                  "DASS-21: Stress interpretation",
    "pcs_rum_score":                    "PCS: Rumination score",
    "pcs_mag_score":                    "PCS: Magnification score",
    "pcs_help_score":                   "PCS: Helplessness score",
    "pcs_total_score":                  "PCS: Total score",
    "pcs_rum_risk":                     "PCS: Rumination risk",
    "pcs_mag_risk":                     "PCS: Magnification risk",
    "pcs_help_risk":                    "PCS: Helplessness risk",
    "pcs_total_risk":                   "PCS: Total risk",
    "pseq_score":                       "PSEQ score",
    "pseq_interp":                      "PSEQ interpretation",
    "pseq2_score":                      "PSEQ-2 score",
    "pseq2_interp":                     "PSEQ-2 interpretation",
    "phq4_nervous":                     "PHQ-4: Nervous",
    "phq4_worry":                       "PHQ-4: Worry",
    "phq4_noint":                       "PHQ-4: No interest",
    "phq4_depressed":                   "PHQ-4: Depressed",
    "plan_phq4":                        "Plan: PHQ-4",
    "pcl5_score":                       "PCL-5 score",
    "pcl5_interp":                      "PCL-5 interpretation",
    "pcl5_action":                      "PCL-5 action taken",
    "isi_score":                        "ISI score",
    "isi_interp":                       "ISI interpretation",
    "pbas_score":                       "PBAS score",
    "pbas_interp":                      "PBAS interpretation",
    "add_audit":                        "AUDIT administered",
    "add_dudit":                        "DUDIT administered",
    "add_epoc":                         "EPPOC notes",
    "add_other":                        "Additional measures notes",
    "plan_psfs":                        "Plan: PSFS",
    "plan_bpi":                         "Plan: BPI",
    "plan_dass":                        "Plan: DASS-21",
    "plan_pcs":                         "Plan: PCS",
    "plan_pseq":                        "Plan: PSEQ",
    "plan_pcl5":                        "Plan: PCL-5",
    "plan_sleep":                       "Plan: Sleep measures",
    "plan_additional":                  "Plan: Additional measures",
    # ── 06 Diagnosis ──────────────────────────────────────────────────────────
    "mechanism":                        "Mechanism",
    "primary_subtype":                  "Primary subtype",
    "primary_severity":                 "Primary severity",
    "primary_distress":                 "Primary: High psychological distress",
    "primary_not_other_dx":             "Primary: Not better explained by other dx",
    "surgical_subtype":                 "Surgical subtype",
    "surgical_severity":                "Surgical severity",
    "surgical_procedure":               "Surgical procedure",
    "surgical_source":                  "Surgical source",
    "traumatic_subtype":                "Traumatic subtype",
    "traumatic_severity":               "Traumatic severity",
    "traumatic_event":                  "Traumatic event",
    "traumatic_source":                 "Traumatic source",
    "msk_subtype":                      "MSK subtype",
    "msk_severity":                     "MSK severity",
    "msk_pathology":                    "MSK pathology",
    "msk_source":                       "MSK source",
    "neuro_subtype":                    "Neurological subtype",
    "neuro_severity":                   "Neurological severity",
    "neuro_lesion":                     "Neurological lesion",
    "mixed_dominant":                   "Mixed: Dominant type",
    "mixed_reasoning":                  "Mixed reasoning",
    "duration_over_3_months":           "Duration > 3 months",
    "goal_1":                           "SMART Goal 1",
    "goal_2":                           "SMART Goal 2",
    "goal_3":                           "SMART Goal 3",
    "goal_4":                           "SMART Goal 4",
    # ── 07 Barriers & Treatment ───────────────────────────────────────────────
    "b_noci_disease":                   "Barrier: Disease/pathology",
    "b_noci_pacing":                    "Barrier: Pacing issues",
    "b_noci_inflammatory":              "Barrier: Inflammatory features",
    "b_noci_deconditioning":            "Barrier: Deconditioning",
    "b_noci_movement":                  "Barrier: Reduced movement",
    "b_noci_gait":                      "Barrier: Asymmetrical gait",
    "b_noci_strength":                  "Barrier: Strength deficits",
    "b_noci_deep_muscle":               "Barrier: Deep muscle activation",
    "b_noci_overactivity":              "Barrier: Muscle overactivity",
    "b_noci_nerve_mech":                "Barrier: Nerve mechanosensitivity",
    "b_noci_diet":                      "Barrier: Diet/weight",
    "bx_strength_glute_max":            "  Strength deficit: Glute max",
    "bx_strength_glute_med":            "  Strength deficit: Glute med",
    "bx_strength_iliopsoas":            "  Strength deficit: Iliopsoas",
    "bx_strength_quads":                "  Strength deficit: Quads",
    "bx_deep_multifidus":               "  Deep muscle: Multifidus",
    "bx_deep_ta":                       "  Deep muscle: Transversus abdominis",
    "bx_deep_erector":                  "  Deep muscle: Erector spinae",
    "bx_over_erector":                  "  Overactivity: Erector spinae",
    "bx_over_ql":                       "  Overactivity: Quadratus lumborum",
    "bx_over_ra":                       "  Overactivity: Rectus abdominis",
    "bx_over_obliques":                 "  Overactivity: Obliques",
    "bx_over_piriformis":               "  Overactivity: Piriformis",
    "bx_over_iliopsoas":                "  Overactivity: Iliopsoas",
    "bx_over_hamstrings":               "  Overactivity: Hamstrings",
    "bx_over_adductors":                "  Overactivity: Adductors",
    "bi_movement_region":               "  Movement region",
    "bi_strength_other":                "  Strength other",
    "bi_deep_other":                    "  Deep muscle other",
    "bi_over_other":                    "  Overactivity other",
    "bi_nerve_region":                  "  Nerve region",
    "bi_red_flag_detail":               "  Red flag detail",
    "bi_substance_detail":              "  Substance detail",
    "b_neuro_confirmed":                "Barrier: Neuropathic (confirmed)",
    "b_neuro_unconfirmed":              "Barrier: Neuropathic (unconfirmed)",
    "b_nocip_moderate":                 "Barrier: Nociplastic/CS",
    "b_nocip_crps":                     "Barrier: CRPS",
    "b_nocip_fnd":                      "Barrier: FND",
    "b_psych_depression":               "Barrier: Depression",
    "b_psych_anxiety":                  "Barrier: Anxiety",
    "b_psych_stress":                   "Barrier: Stress",
    "b_psych_catastrophising":          "Barrier: Catastrophising",
    "b_psych_self_efficacy":            "Barrier: Reduced self-efficacy",
    "b_psych_unhelpful_beliefs":        "Barrier: Unhelpful beliefs",
    "b_psych_ptsd":                     "Barrier: PTSD symptoms",
    "b_psych_readiness":                "Barrier: Unclear readiness to change",
    "bx_dep_psychiatry":                "  Depression: Psychiatry referral",
    "bx_anx_psychiatry":                "  Anxiety: Psychiatry referral",
    "bx_stress_psychiatry":             "  Stress: Psychiatry referral",
    "bx_ptsd_psychiatry":               "  PTSD: Psychiatry referral",
    "bx_dep_severity":                  "  Depression severity",
    "bx_anx_severity":                  "  Anxiety severity",
    "bx_stress_severity":               "  Stress severity",
    "bx_ptsd_mechanism":                "  PTSD mechanism",
    "bx_belief_expectations":           "  Belief: Unrealistic expectations",
    "bx_belief_symptom_focus":          "  Belief: Symptom focus",
    "bx_belief_cure_focus":             "  Belief: Cure focus",
    "bx_belief_further_tx":             "  Belief: Further treatment needed",
    "b_sleep_disturbed":                "Barrier: Disturbed sleep",
    "b_social_home":                    "Barrier: Home/social barriers",
    "b_social_rtw":                     "Barrier: Return to work barriers",
    "bx_soc_family_support":            "  Social: Family support",
    "bx_soc_social_support":            "  Social: Social support",
    "bx_soc_relationship":              "  Social: Relationship issues",
    "bx_soc_personal_rel":              "  Social: Personal relationships",
    "bx_soc_financial":                 "  Social: Financial",
    "bx_soc_residential":               "  Social: Residential",
    "bx_soc_distance":                  "  Social: Distance to care",
    "b_med_red_flag":                   "Barrier: Red flag",
    "b_med_substance":                  "Barrier: Substance use",
    "b_med_as":                         "Barrier: Possible AS",
    "b_med_aaa":                        "Barrier: Possible AAA",
    "b_med_vascular":                   "Barrier: Vascular claudication",
    "b_med_cervical_ha":                "Barrier: Cervical headache",
    "b_med_medico_legal":               "Barrier: Medico-legal",
    "custom_1_barrier":                 "Custom barrier 1",
    "custom_1_strategy":                "Custom strategy 1",
    "custom_2_barrier":                 "Custom barrier 2",
    "custom_2_strategy":                "Custom strategy 2",
    "tx_consent_explanation":           "Consent/explanation given",
    "s1_consent_content":               "Consent content discussed",
    "tx_email_obtained":                "Email obtained",
    "tx_display_book":                  "Display book shown",
    "hw_online_module":                 "Online module",
    "hw_mindfulness":                   "Mindfulness",
    "hw_goal_sheet":                    "Goal sheet",
    "hw_activity_diary":                "Activity diary",
    "hw_sleep_diary":                   "Sleep diary",
    "d1_explanation":                   "Explanation provided",
    "d1_session2":                      "Session 2 booked",
    "d1_hypothesis":                    "Hypothesis shared",
    "d1_diagnosis":                     "Diagnosis discussed",
    "d1_values":                        "Values explored",
    "d1_evidence":                      "Evidence discussed",
    "d1_plan":                          "Plan shared",
    "d1_prognosis":                     "Prognosis discussed",
    "d1_stakeholders":                  "Stakeholders identified",
    "d1_confidence_tested":             "Confidence tested",
    "d1_questionnaires":                "Questionnaires completed",
    "ps_questionnaires":                "Post-session: Questionnaires saved",
    "ps_eppoc":                         "Post-session: EPPOC submitted",
    "ps_ptsd_scored":                   "Post-session: PTSD scored",
    "ps_isi_pbas":                      "Post-session: ISI/PBAS scored",
    "ps_csi":                           "Post-session: CSI scored",
    "ps_audit_dudit":                   "Post-session: AUDIT/DUDIT scored",
    "s1_confidence_nrs":                "Confidence NRS",
    "fu_om_schedule":                   "OM schedule",
    "tx_goal_orientation":              "Goal orientation",
    "tx_formulation":                   "Formulation",
    "tx_program":                       "Program",
    "tx_home_program":                  "Home program",
    "tx_psychosocial":                  "Psychosocial strategies",
    "tx_medical":                       "Medical/referral plan",
    "tx_rtw":                           "RTW plan",
    "tx_pain_type":                     "Pain type",
    "tx_debunk_radiology":              "Debunk radiology",
    "s1_education":                     "Education provided",
    "s1_experiential":                  "Experiential learning",
    "s1_hw_other":                      "Homework other",
    "fu_next_focus":                    "Next session focus",
    "fu_monitoring":                    "Monitoring plan",
}


def _label(fid: str) -> str:
    return LABELS.get(fid, fid)


def _val_raw(val) -> str:
    if val is True:
        return "✓ Yes"
    if val is False:
        return "✗ No"
    if val is None:
        return "(not answered)"
    if isinstance(val, str):
        s = val.strip()
        return s if s else "(empty)"
    if isinstance(val, list):
        return f"[{len(val)} items]"
    return str(val)


def export_raw_report(session_data: dict, clean: bool = False) -> str:  # noqa: C901
    """
    Generate a plain-text export of session fields.

    clean=False (default): every field shown; unanswered fields show "(not answered)".
    clean=True: only fields with real data; empty fields and their headers are omitted.
    """
    import time as _time

    SEP  = "═" * 60
    SEP2 = "─" * 60

    lines: list[str] = []
    _pending: list[str] = []  # buffered section/sub headers waiting for content
    a = session_data.get("assessment", {})
    obj_assessment = session_data.get("objective_assessment", {}) or {}

    # ── helpers ─────────────────────────────────────────────────────────────

    def _emit(*ls: str) -> None:
        if _pending:
            lines.extend(_pending)
            _pending.clear()
        lines.extend(ls)

    def sec(title: str) -> None:
        if clean:
            _pending[:] = ["", SEP, title, SEP]
        else:
            lines.extend(["", SEP, title, SEP])

    def sub(title: str) -> None:
        if clean:
            while _pending and _pending[-1].lstrip().startswith("— "):
                _pending.pop()
            _pending.append(f"  — {title} —")
        else:
            lines.append(f"  — {title} —")

    def _empty(val) -> bool:
        if val is None:
            return True
        if isinstance(val, str) and not val.strip():
            return True
        return False

    def f(fid: str, d: dict) -> None:
        val = d.get(fid)
        if clean and _empty(val):
            return
        label = _label(fid)
        if isinstance(val, str) and "\n" in val.strip():
            _emit(f"  {label}:")
            for row in val.strip().split("\n"):
                _emit(f"    {row}" if row.strip() else "")
        else:
            _emit(f"  {label}: {_val_raw(val)}")

    def txt(fid: str, d: dict) -> None:
        val = (d.get(fid) or "").strip()
        if clean and not val:
            return
        label = _label(fid)
        _emit(f"  {label}:")
        if val:
            for row in val.split("\n"):
                _emit(f"    {row}")
        else:
            _emit("    (empty)")

    # ── header ──────────────────────────────────────────────────────────────

    c_hdr = a.get("consent", {}) or {}
    preferred_name = c_hdr.get("preferred_name", "").strip() or "(not set)"
    session_name   = session_data.get("session_name", "")
    created        = session_data.get("created", 0)
    date_str       = _time.strftime("%d %b %Y %H:%M", _time.localtime(created)) if created else "(unknown)"
    regions        = ", ".join(session_data.get("regions", [])) or "(not set)"

    title = "PHYSIOTHERAPY ASSESSMENT — ENTERED DATA" if clean else "PHYSIOTHERAPY ASSESSMENT — FULL RAW DATA"
    lines.extend([SEP, title, f"Patient:    {preferred_name}", f"Date:       {date_str}",
                  f"Region:     {regions}", f"Session ID: {session_name}", SEP])

    # Plain Language Summary — see export_session_report's identical block
    # for why this moved to the top (2026-09-17, was "SCRATCHPAD NOTES" at
    # the very bottom).
    pls = a.get("scratchpad", {}) or {}
    pls_notes = (pls.get("notes") or "").strip()
    if pls_notes or not clean:
        lines.extend(["", SEP, "PLAIN LANGUAGE SUMMARY", SEP])
        if pls_notes:
            for row in pls_notes.split("\n"):
                lines.append(f"  {row}")
        else:
            lines.append("  (empty)")

    lines.extend(["", SEP, "S — SUBJECTIVE", SEP])

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 1: CONSENT & SETUP
    # ════════════════════════════════════════════════════════════════════════
    c = a.get("consent", {}) or {}
    sec("SECTION 1: CONSENT & SETUP")

    sub("Consent")
    f("consent_to_proceed",        c)
    f("consent_sensitive_topics",  c)
    f("preferred_name",            c)

    sub("Session Framing")
    f("pain_multifactorial_explained",    c)
    f("education_as_treatment_explained", c)
    txt("patient_expectations",           c)

    sub("Patient Perspective (ICE+)")
    txt("reason_for_attending",     c)
    f("cause_understanding",        c)
    txt("cause_understanding_detail", c)
    txt("prognosis_expectations",   c)
    txt("treatment_preference",     c)
    _emit_yaml_subs_raw("consent", c, clean, _emit, sub)

    sub("Beliefs")
    f("belief_hurt_harm",      c)
    f("belief_unsafe",         c)
    f("belief_passive",        c)
    f("belief_rehab",          c)
    f("belief_high_se",        c)
    f("belief_internal_locus", c)
    txt("belief_notes",        c)

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 2: SUBJECTIVE EXAMINATION
    # ════════════════════════════════════════════════════════════════════════
    s = a.get("subjective", {}) or {}
    sec("SECTION 2: SUBJECTIVE EXAMINATION")

    sub("Symptoms")
    f("body_chart_completed", s)
    note_fields_r = s.get("note_fields") or {}
    for sid, nf in note_fields_r.items():
        if any(nf.get(k, "").strip() for k in ("loc", "nat", "agg", "ease")):
            _emit(f"  Note {int(sid) + 1}:")
            for key, label in (("loc","Location"),("nat","Nature"),("agg","Aggravating"),("ease","Easing")):
                val = nf.get(key, "").strip()
                if val or not clean:
                    _emit(f"    {label}:")
                    for row in (val or "(empty)").split("\n"):
                        _emit(f"      {row}")
    if s.get("misc_loc","").strip() or s.get("misc_nat","").strip():
        _emit("  Misc symptoms (no note):")
        for key, label in (("misc_loc","Location"),("misc_nat","Nature")):
            val = s.get(key,"").strip()
            if val or not clean:
                _emit(f"    {label}:")
                for row in (val or "(empty)").split("\n"):
                    _emit(f"      {row}")

    sub("History")
    txt("onset",              s)
    txt("duration",           s)
    f("course_improving",     s)
    f("course_worsening",     s)
    f("course_stable",        s)
    f("course_fluctuating",   s)
    txt("context_at_onset",   s)
    txt("previous_episodes",  s)
    txt("previous_treatment", s)

    sub("Behaviour")
    f("behaviour_boom_bust",         s)
    txt("behaviour_boom_bust_text",  s)
    f("behaviour_avoidance",         s)
    txt("behaviour_avoidance_text",  s)
    f("behaviour_endurance",         s)
    txt("behaviour_endurance_text",  s)
    f("behaviour_flareups",          s)
    txt("behaviour_flareups_text",   s)

    sub("Self-Management & Control")
    f("pain_control_score",      s)
    txt("flareup_prevention",    s)
    txt("management_strategies", s)
    f("confidence_score",        s)

    sub("Activity & Exercise")
    txt("pre_activity_level",     s)
    txt("current_activity_level", s)
    txt("exercise_type",          s)
    txt("exercise_dose",          s)
    txt("exercise_response",      s)

    sub("Work")
    txt("pre_injury_role",    s)
    f("pre_injury_hours",     s)
    txt("pre_injury_duties",  s)
    txt("current_work_status", s)
    f("current_hours",        s)
    txt("current_duties",     s)

    sub("Sleep")
    f("sleep_overall_rating",        s)
    f("sleep_feels_rested",          s)
    f("sleep_time_to_bed",           s)
    f("sleep_time_attempt",          s)
    f("sleep_onset_time",            s)
    f("sleep_waso_clock",            s)
    f("sleep_waso_duration",         s)
    f("sleep_awake_in_bed",          s)
    f("sleep_awake_out_bed",         s)
    f("sleep_final_wakeup",          s)
    f("sleep_time_out_of_bed",       s)
    f("sleep_efficiency",            s)
    txt("sleep_postural_factors",    s)
    txt("sleep_environment_quality", s)
    f("sleep_daytime_naps",          s)
    txt("sleep_overall_comments",    s)
    txt("energy_levels",             s)

    sub("Behaviour of Symptoms")
    txt("aggravating_factors",    s)
    txt("easing_factors",         s)
    txt("daily_pattern_comments", s)
    txt("hr24_am",                s)
    txt("hr24_day",               s)
    txt("hr24_pm",                s)
    txt("hr24_nocte",             s)

    sub("Psychosocial")
    f("mood_influences",          s)
    txt("mood_text",              s)
    txt("social_situation",       s)
    txt("financial_status",       s)
    txt("cultural_considerations", s)
    txt("psychological_distress", s)
    txt("screening_tool",         s)

    sub("Suicide / Self-Harm Risk")
    f("self_harm_risk",   s)
    txt("harm_plan",      s)
    txt("harm_means",     s)
    txt("harm_intent",    s)
    txt("harm_action",    s)

    sub("SMART Goals")
    f("goal_1", s)
    f("goal_2", s)
    f("goal_3", s)
    f("goal_4", s)
    _emit_yaml_subs_raw("subjective", s, clean, _emit, sub)

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 3: MEDICAL SCREENING
    # ════════════════════════════════════════════════════════════════════════
    m = a.get("medical", {}) or {}
    sec("SECTION 3: MEDICAL SCREENING")

    # ── clean-mode clustered helpers (raw) — only used when clean=True ───
    def _cluster_raw(prefix: str, items: list, d: dict) -> None:
        present = [l for l, k in items if d.get(k) is True]
        absent  = [l for l, k in items if d.get(k) is False]
        if present:
            _emit("  " + prefix + " PRESENT: " + "; ".join(present))
        if absent:
            _emit("  " + prefix + " ABSENT: " + "; ".join(absent))

    def _rf_raw(name: str, flags: list, d: dict, action_key: str = None) -> None:
        raised     = [l for l, k in flags if d.get(k) is True]
        not_raised = [l for l, k in flags if d.get(k) is False]
        action = (d.get(action_key) or "").strip() if action_key else ""
        if raised:
            _emit(f"  Red Flags — {name}: ⚠️ RAISED: " + "; ".join(raised))
            if not_raised:
                _emit("    Not reported: " + "; ".join(not_raised))
            if action:
                _emit(f"    Action: {action}")
        else:
            suffix = f" — {action}" if action else ""
            _emit(f"  Red Flags — {name}: NIL REPORTED{suffix}")

    def _pain_raw(prefix: str, items: list, d: dict) -> None:
        present = [l for l, k in items if d.get(k) is True]
        absent  = [l for l, k in items if d.get(k) is False]
        if present:
            _emit("  " + prefix + " PRESENT: " + "; ".join(present))
        if absent:
            _emit("  " + prefix + " DENIES: " + "; ".join(absent))

    sub("Comorbidities / PMH")
    f("no_previous_injuries",     m)
    txt("previous_injuries",      m)
    if clean:
        _cluster_raw("Comorbidities", [
            ("Cancer",                "comorbid_cancer"),
            ("Mental health",         "comorbid_mental_health"),
            ("Osteoporosis",          "comorbid_osteoporosis"),
            ("Inflammatory arthritis","comorbid_inflammatory"),
            ("Fibromyalgia",          "comorbid_fibromyalgia"),
            ("CFS",                   "comorbid_cfs"),
            ("IBS",                   "comorbid_ibs"),
            ("Whiplash",              "comorbid_whiplash"),
            ("Skin rash",             "comorbid_skin_rash"),
            ("Drug/alcohol",          "comorbid_drug_alcohol"),
            ("Fatigue/memory issues", "comorbid_fatigue_memory"),
        ], m)
    else:
        f("comorbid_cancer",          m)
        f("comorbid_mental_health",   m)
        f("comorbid_osteoporosis",    m)
        f("comorbid_inflammatory",    m)
        f("comorbid_fibromyalgia",    m)
        f("comorbid_cfs",             m)
        f("comorbid_ibs",             m)
        f("comorbid_whiplash",        m)
        f("comorbid_skin_rash",       m)
        f("comorbid_drug_alcohol",    m)
        f("comorbid_fatigue_memory",  m)
    txt("comorbid_other",         m)

    sub("Cardiovascular Risk Factors")
    if clean:
        _cluster_raw("CVD risk", [
            ("Hypercholesterolaemia",    "cvd_hypercholesterolaemia"),
            ("Cardiac disease",          "cvd_cardiac"),
            ("Vascular disease",         "cvd_vascular"),
            ("Stroke/TIA",               "cvd_stroke_tia"),
            ("Diabetes",                 "cvd_diabetes"),
            ("Long-term corticosteroids","cvd_corticosteroids"),
            ("Clotting disorder",        "cvd_clotting"),
            ("OCP use",                  "cvd_ocp"),
            ("Smoker",                   "cvd_smoker"),
            ("Postpartum",               "cvd_postpartum"),
            ("Familial history",         "cvd_familial_history"),
        ], m)
    else:
        f("cvd_hypercholesterolaemia", m)
        f("cvd_cardiac",              m)
        f("cvd_vascular",             m)
        f("cvd_stroke_tia",           m)
        f("cvd_diabetes",             m)
        f("cvd_corticosteroids",      m)
        f("cvd_clotting",             m)
        f("cvd_ocp",                  m)
        f("cvd_smoker",               m)
        f("cvd_postpartum",           m)
        f("cvd_familial_history",     m)

    if clean:
        _rf_raw("Malignancy", [
            ("Unexplained weight loss","rf_weight_loss"),
            ("Cancer history",         "rf_cancer_history"),
            ("Age >50 with spinal",    "rf_age_50_spinal"),
            ("Failed conservative",    "rf_failed_conservative"),
        ], m)
        _rf_raw("Fracture", [
            ("Recent trauma",               "rf_trauma"),
            ("Corticosteroid fracture risk","rf_corticosteroids_fracture"),
            ("Osteoporosis fracture risk",  "rf_osteoporosis_fracture"),
        ], m)
        _rf_raw("Infection", [
            ("Fever",                  "rf_fever"),
            ("Immunosuppressed",       "rf_immunosuppressed"),
            ("Recent spinal procedure","rf_spinal_procedure"),
        ], m)
        _rf_raw("Cauda Equina (URGENT)", [
            ("Saddle anaesthesia",  "rf_saddle_anaesthesia"),
            ("Bladder disturbance", "rf_bladder_disturbance"),
            ("Bowel disturbance",   "rf_bowel_disturbance"),
        ], m, action_key="cauda_equina_action")
        _rf_raw("Spinal Cord (URGENT)", [
            ("Bilateral paraesthesia","rf_bilateral_paraesthesia"),
            ("Gait disturbance",     "rf_gait_disturbance"),
        ], m, action_key="spinal_cord_action")
    else:
        sub("Red Flags — Malignancy")
        f("rf_weight_loss",          m)
        f("rf_cancer_history",       m)
        f("rf_age_50_spinal",        m)
        f("rf_failed_conservative",  m)

        sub("Red Flags — Fracture")
        f("rf_trauma",                  m)
        f("rf_corticosteroids_fracture", m)
        f("rf_osteoporosis_fracture",   m)

        sub("Red Flags — Infection")
        f("rf_fever",           m)
        f("rf_immunosuppressed", m)
        f("rf_spinal_procedure", m)

        sub("Red Flags — Cauda Equina (URGENT)")
        f("rf_saddle_anaesthesia", m)
        f("rf_bladder_disturbance", m)
        f("rf_bowel_disturbance",  m)
        txt("cauda_equina_action", m)

        sub("Red Flags — Spinal Cord (URGENT)")
        f("rf_bilateral_paraesthesia", m)
        f("rf_gait_disturbance",      m)
        txt("spinal_cord_action",     m)

    sub("Differential — Ankylosing Spondylitis")
    f("diff_as_insidious",         m)
    f("diff_as_lumbar_sij",        m)
    f("diff_as_inflammatory",      m)
    f("diff_as_breathing",         m)
    f("diff_as_fever_weight_loss", m)
    f("diff_as_likelihood",        m)
    txt("diff_as_action",          m)

    sub("Differential — Abdominal Aortic Aneurysm")
    f("diff_aaa_pulsating",  m)
    f("diff_aaa_age_50",     m)
    f("diff_aaa_cvd_risk",   m)
    f("diff_aaa_ruptured",   m)
    f("diff_aaa_likelihood", m)
    txt("diff_aaa_action",   m)

    sub("Differential — Vascular Claudication")
    f("diff_vc_non_dermatomal", m)
    f("diff_vc_age_50",         m)
    f("diff_vc_cvd_risk",       m)
    f("diff_vc_walking_pain",   m)
    f("diff_vc_pvd_signs",      m)
    f("diff_vc_impotence",      m)
    f("diff_vc_night_pain",     m)
    f("diff_vc_likelihood",     m)
    txt("diff_vc_action",       m)

    sub("Medications")
    meds = m.get("medications", [])
    if meds:
        for i, med in enumerate(meds, 1):
            name     = med.get("name", "").strip()
            dose     = med.get("dose", "").strip()
            timing   = med.get("timing", "").strip()
            comments = med.get("comments", "").strip()
            parts    = [x for x in [name, dose, timing] if x]
            med_str  = "  ".join(parts) if parts else "(unnamed)"
            if comments:
                med_str += f"  [{comments}]"
            _emit(f"  {i}. {med_str}")
    elif not clean:
        _emit("  (none recorded)")

    sub("Imaging")
    _IMG = [
        ("Xray",  "img_xray",  "img_xray_detail"),
        ("U/S",   "img_us",    "img_us_detail"),
        ("CT",    "img_ct",    "img_ct_detail"),
        ("MRI",   "img_mri",   "img_mri_detail"),
        ("NCS",   "img_ncs",   "img_ncs_detail"),
        ("Other", "img_other", "img_other_detail"),
    ]
    if clean:
        for lbl, bid, did in _IMG:
            val = m.get(bid)
            det = (m.get(did) or "").strip()
            if val is True or det:
                _emit("  " + lbl + (f": {det}" if det else ""))
            elif val is False:
                _emit(f"  {lbl}: Not performed")
    else:
        for lbl, bid, did in _IMG:
            val = m.get(bid)
            det = (m.get(did) or "").strip()
            _emit(f"  {lbl}: {_val_raw(val)}" + (f" — {det}" if det else ""))

    _emit_yaml_subs_raw("medical", m, clean, _emit, sub)

    # ════════════════════════════════════════════════════════════════════════
    # SOAP: OBJECTIVE
    # ════════════════════════════════════════════════════════════════════════
    lines.extend(["", SEP, "O — OBJECTIVE", SEP])
    _render_objective_raw(obj_assessment, lines, SEP, SEP2, clean=clean)

    # ════════════════════════════════════════════════════════════════════════
    # SOAP: ASSESSMENT
    # ════════════════════════════════════════════════════════════════════════
    lines.extend(["", SEP, "A — ASSESSMENT", SEP])

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 4: PAIN CLASSIFICATION
    # ════════════════════════════════════════════════════════════════════════
    pc = a.get("pain_classification", {}) or {}
    sec("SECTION 4: PAIN CLASSIFICATION")

    sub("Inflammatory Pain Features")
    if clean:
        _pain_raw("Inflammatory", [
            ("Constant pain",     "infl_constant"),
            ("Morning stiffness", "infl_morning"),
            ("Night/sleep pain",  "infl_sleep"),
            ("Activity improves", "infl_activity"),
        ], pc)
    else:
        f("infl_constant",    pc)
        f("infl_morning",     pc)
        f("infl_sleep",       pc)
        f("infl_activity",    pc)
    f("infl_likelihood",  pc)

    sub("Nociceptive Pain — Subjective Features")
    if clean:
        _pain_raw("Nociceptive (Sx)", [
            ("Mechanical",            "noci_subj_mechanical"),
            ("Trauma/incident",       "noci_subj_trauma"),
            ("Localised",             "noci_subj_localised"),
            ("Resolving",             "noci_subj_resolving"),
            ("Responds to analgesia", "noci_subj_analgesia"),
            ("Not constant",          "noci_subj_no_constant"),
            ("Local inflammation",    "noci_subj_inflammation"),
            ("Recent onset",          "noci_subj_recent"),
        ], pc)
    else:
        f("noci_subj_mechanical",   pc)
        f("noci_subj_trauma",       pc)
        f("noci_subj_localised",    pc)
        f("noci_subj_resolving",    pc)
        f("noci_subj_analgesia",    pc)
        f("noci_subj_no_constant",  pc)
        f("noci_subj_inflammation", pc)
        f("noci_subj_recent",       pc)

    sub("Nociceptive Pain — Examination Features")
    if clean:
        _pain_raw("Nociceptive (Ex)", [
            ("Mechanical reproduction","noci_exam_mechanical"),
            ("Palpation reproduction", "noci_exam_palpation"),
            ("Local hyperalgesia",     "noci_exam_hyperalgesia"),
            ("Antalgic posture",       "noci_exam_antalgic"),
        ], pc)
    else:
        f("noci_exam_mechanical",  pc)
        f("noci_exam_palpation",   pc)
        f("noci_exam_hyperalgesia", pc)
        f("noci_exam_antalgic",    pc)
    f("noci_likelihood",       pc)
    txt("noci_interpretation", pc)

    sub("Neuropathic Pain — Subjective Features")
    if clean:
        _pain_raw("Neuropathic (Sx)", [
            ("Burning/electric/shooting quality","neuro_subj_quality"),
            ("Known nerve injury",               "neuro_subj_nerve_injury"),
            ("Neurological symptoms",            "neuro_subj_neurological"),
            ("Dermatomal/nerve trunk",           "neuro_subj_dermatomal"),
            ("Responds to neuropathic meds",     "neuro_subj_medication"),
            ("Severe/night pain",                "neuro_subj_severity"),
            ("Provoked by neural loading",       "neuro_subj_neural_loading"),
            ("Dysaesthesia/allodynia",           "neuro_subj_dysaesthesia"),
            ("Spontaneous pain",                 "neuro_subj_spontaneous"),
        ], pc)
    else:
        f("neuro_subj_quality",        pc)
        f("neuro_subj_nerve_injury",   pc)
        f("neuro_subj_neurological",   pc)
        f("neuro_subj_dermatomal",     pc)
        f("neuro_subj_medication",     pc)
        f("neuro_subj_severity",       pc)
        f("neuro_subj_neural_loading", pc)
        f("neuro_subj_dysaesthesia",   pc)
        f("neuro_subj_spontaneous",    pc)

    sub("Neuropathic Pain — Examination Features")
    if clean:
        _pain_raw("Neuropathic (Ex)", [
            ("Positive neurodynamic test",   "neuro_exam_neurodynamic"),
            ("Neural palpation sensitive",   "neuro_exam_neural_palpation"),
            ("Neurology change",             "neuro_exam_neurology"),
            ("Antalgic posture",             "neuro_exam_antalgic"),
            ("Hyperalgesia in distribution", "neuro_exam_hyperalgesia"),
        ], pc)
    else:
        f("neuro_exam_neurodynamic",    pc)
        f("neuro_exam_neural_palpation", pc)
        f("neuro_exam_neurology",       pc)
        f("neuro_exam_antalgic",        pc)
        f("neuro_exam_hyperalgesia",    pc)
    f("neuro_likelihood",           pc)
    txt("neuro_interpretation",     pc)

    sub("Nociplastic Pain — Subjective Features")
    if clean:
        _pain_raw("Nociplastic (Sx)", [
            ("Disproportionate to pathology",    "nocip_subj_disproportionate"),
            ("Persistent beyond healing",        "nocip_subj_persistent"),
            ("Disproportionate to stimulus",     "nocip_subj_disproportionate2"),
            ("Widespread/multifocal",            "nocip_subj_widespread"),
            ("Failed previous treatment",        "nocip_subj_failed"),
            ("Psychosocial contributors",        "nocip_subj_psychosocial"),
            ("Responds to centrally-acting meds","nocip_subj_medication"),
            ("Spontaneous pain",                 "nocip_subj_spontaneous"),
            ("High disability",                  "nocip_subj_disability"),
            ("Constant/unpredictable",           "nocip_subj_constant"),
            ("Disturbed sleep/night pain",       "nocip_subj_night_pain"),
            ("Dysaesthesia",                     "nocip_subj_dysaesthesia"),
            ("Severe/difficult to control",      "nocip_subj_severity"),
        ], pc)
    else:
        f("nocip_subj_disproportionate",  pc)
        f("nocip_subj_persistent",        pc)
        f("nocip_subj_disproportionate2", pc)
        f("nocip_subj_widespread",        pc)
        f("nocip_subj_failed",            pc)
        f("nocip_subj_psychosocial",      pc)
        f("nocip_subj_medication",        pc)
        f("nocip_subj_spontaneous",       pc)
        f("nocip_subj_disability",        pc)
        f("nocip_subj_constant",          pc)
        f("nocip_subj_night_pain",        pc)
        f("nocip_subj_dysaesthesia",      pc)
        f("nocip_subj_severity",          pc)

    sub("Nociplastic Pain — Examination Features")
    if clean:
        _pain_raw("Nociplastic (Ex)", [
            ("Disproportionate exam findings",    "nocip_exam_disproportionate"),
            ("Widespread hyperalgesia/allodynia", "nocip_exam_hyperalgesia"),
            ("Diffuse palpation tenderness",      "nocip_exam_diffuse"),
            ("Psychosocial features on exam",     "nocip_exam_psychosocial"),
        ], pc)
    else:
        f("nocip_exam_disproportionate", pc)
        f("nocip_exam_hyperalgesia",     pc)
        f("nocip_exam_diffuse",          pc)
        f("nocip_exam_psychosocial",     pc)
    f("nocip_likelihood",            pc)
    txt("nocip_interpretation",      pc)

    sub("Central Sensitisation")
    f("csi_score",        pc)
    if clean:
        _pain_raw("CS features", [
            ("Light sensitivity",        "cs_light"),
            ("Touch sensitivity",        "cs_touch"),
            ("Noise sensitivity",        "cs_noise"),
            ("Chemical/smell sensitivity","cs_pesticides"),
            ("Temperature sensitivity",  "cs_temperature"),
            ("Fatigue",                  "cs_fatigue"),
            ("Sleep disturbance",        "cs_sleep"),
            ("Concentration difficulty", "cs_concentration"),
            ("Perceived swelling",       "cs_swelling"),
            ("Tingling",                 "cs_tingling"),
        ], pc)
    else:
        f("cs_light",         pc)
        f("cs_touch",         pc)
        f("cs_noise",         pc)
        f("cs_pesticides",    pc)
        f("cs_temperature",   pc)
        f("cs_fatigue",       pc)
        f("cs_sleep",         pc)
        f("cs_concentration", pc)
        f("cs_swelling",      pc)
        f("cs_tingling",      pc)

    sub("Fibromyalgia")
    if clean:
        _pain_raw("FM scores", [
            ("WPI (0–19)",              "fm_wpi"),
            ("Fatigue severity (0–3)",  "fm_fatigue"),
            ("Waking unrefreshed (0–3)","fm_waking"),
            ("Cognitive symptoms (0–3)","fm_cognitive"),
            ("Headaches",               "fm_headaches"),
            ("IBS",                     "fm_ibs"),
            ("Depression",              "fm_depression"),
            ("Symptoms ≥ 3 months",     "fm_duration"),
            ("No alternative explanation","fm_exclusion"),
        ], pc)
    else:
        f("fm_wpi",       pc)
        f("fm_fatigue",   pc)
        f("fm_waking",    pc)
        f("fm_cognitive", pc)
        f("fm_headaches", pc)
        f("fm_ibs",       pc)
        f("fm_depression",pc)
        f("fm_duration",  pc)
        f("fm_exclusion", pc)

    sub("BACPAP LBP Phenotyping")
    if clean:
        _pain_raw("BACPAP", [
            ("LBP ≥ 3 months",                  "bacpap_chronic"),
            ("Regional/widespread distribution", "bacpap_distribution"),
            ("Nociceptive mainly responsible",   "bacpap_nociceptive"),
            ("Neuropathic mainly responsible",   "bacpap_neuropathic"),
            ("Static mechanical allodynia",      "bacpap_static"),
            ("Dynamic mechanical allodynia",     "bacpap_dynamic"),
            ("Heat or cold allodynia",           "bacpap_thermal"),
            ("Painful after-sensations",         "bacpap_after"),
            ("Hypersensitivity — touch",         "bacpap_hyper_touch"),
            ("Hypersensitivity — movement",      "bacpap_hyper_movement"),
            ("Hypersensitivity — pressure",      "bacpap_hyper_pressure"),
            ("Hypersensitivity — heat",          "bacpap_hyper_heat"),
            ("Hypersensitivity — cold",          "bacpap_hyper_cold"),
            ("Comorbid — light/sound/odour sensitivity", "bacpap_como_sensory"),
            ("Comorbid — sleep disturbance",     "bacpap_como_sleep"),
            ("Comorbid — fatigue",               "bacpap_como_fatigue"),
            ("Comorbid — cognitive problems",    "bacpap_como_cognitive"),
        ], pc)
    else:
        f("bacpap_chronic",      pc)
        f("bacpap_distribution", pc)
        f("bacpap_nociceptive",  pc)
        f("bacpap_neuropathic",  pc)
        f("bacpap_static",       pc)
        f("bacpap_dynamic",      pc)
        f("bacpap_thermal",      pc)
        f("bacpap_after",        pc)
        f("bacpap_hyper_touch",     pc)
        f("bacpap_hyper_movement",  pc)
        f("bacpap_hyper_pressure",  pc)
        f("bacpap_hyper_heat",      pc)
        f("bacpap_hyper_cold",      pc)
        f("bacpap_como_sensory",    pc)
        f("bacpap_como_sleep",      pc)
        f("bacpap_como_fatigue",    pc)
        f("bacpap_como_cognitive",  pc)
    txt("bacpap_notes",         pc)

    sub("Pain Type Summary")
    f("summary_dominant",       pc)
    txt("summary_contributing", pc)
    txt("summary_reasoning",    pc)

    _emit_yaml_subs_raw("pain_classification", pc, clean, _emit, sub)
    # ════════════════════════════════════════════════════════════════════════
    # SECTION 5: OUTCOME MEASURES
    # ════════════════════════════════════════════════════════════════════════
    om = a.get("outcome_measures", {}) or {}
    sec("SECTION 5: OUTCOME MEASURES")

    sub("Patient Specific Functional Scale (PSFS)")
    f("psfs_act_1",  om)
    f("psfs_act_2",  om)
    f("psfs_act_3",  om)

    sub("Brief Pain Inventory (BPI) — interference /10")
    f("bpi_activity",  om)
    f("bpi_mood",      om)
    f("bpi_walking",   om)
    f("bpi_work",      om)
    f("bpi_relations", om)
    f("bpi_sleep",     om)
    f("bpi_enjoyment", om)

    sub("DASS-21")
    f("dass_dep_score",  om)
    f("dass_dep_interp", om)
    f("dass_anx_score",  om)
    f("dass_anx_interp", om)
    f("dass_str_score",  om)
    f("dass_str_interp", om)

    sub("PHQ-4")
    f("phq4_nervous",   om)
    f("phq4_worry",     om)
    f("phq4_noint",     om)
    f("phq4_depressed", om)

    sub("Pain Catastrophising Scale (PCS)")
    f("pcs_rum_score",   om)
    f("pcs_rum_risk",    om)
    f("pcs_mag_score",   om)
    f("pcs_mag_risk",    om)
    f("pcs_help_score",  om)
    f("pcs_help_risk",   om)
    f("pcs_total_score", om)
    f("pcs_total_risk",  om)

    sub("Pain Self-Efficacy Questionnaire (PSEQ / PSEQ-2)")
    f("pseq_score",   om)
    f("pseq_interp",  om)
    f("pseq2_score",  om)
    f("pseq2_interp", om)

    sub("PCL-5 (PTSD)")
    f("pcl5_score",      om)
    f("pcl5_interp",     om)
    txt("pcl5_action",   om)

    sub("Sleep Measures")
    f("isi_score",   om)
    f("isi_interp",  om)
    f("pbas_score",  om)
    f("pbas_interp", om)

    sub("Additional Measures")
    f("add_audit",    om)
    f("add_dudit",    om)
    txt("add_epoc",   om)
    txt("add_other",  om)

    sub("Planned Outcome Measures")
    f("plan_psfs",       om)
    f("plan_bpi",        om)
    f("plan_dass",       om)
    f("plan_phq4",       om)
    f("plan_pcs",        om)
    f("plan_pseq",       om)
    f("plan_pcl5",       om)
    f("plan_sleep",      om)
    f("plan_additional", om)

    sub("Hypothesis Testing")
    for i in range(3):
        measure   = (om.get(f"hyp_{i}_measure",   "") or "").strip()
        baseline  = (om.get(f"hyp_{i}_baseline",  "") or "").strip()
        interval  = (om.get(f"hyp_{i}_interval",  "") or "").strip()
        rationale = (om.get(f"hyp_{i}_rationale", "") or "").strip()
        if clean and not any([measure, baseline, interval, rationale]):
            continue
        _emit(
            f"  Row {i+1}: {measure or '—'}"
            f"  |  baseline: {baseline or '—'}"
            f"  |  interval: {interval or '—'}"
            f"  |  rationale: {rationale or '—'}"
        )

    _emit_yaml_subs_raw("outcome_measures", om, clean, _emit, sub)
    # ════════════════════════════════════════════════════════════════════════
    # SECTION 6: DIAGNOSIS
    # ════════════════════════════════════════════════════════════════════════
    dx = a.get("diagnosis", {}) or {}
    sec("SECTION 6: DIAGNOSIS")

    workups = dx.get("workups") or []
    if workups:
        sub("ICD-11 Diagnosis (CAL-CP)")
        for wd in workups:
            wu = _CalCpWorkup.from_dict(wd)
            _emit(f"  {wu.label}:")
            if clean:
                # *_clean.txt — compact, same one-line-per-workup summary
                # as the Markdown report; the full question-by-question
                # path is raw.txt's job only (see the else branch).
                _emit(f"    {wu.result_or_progress_text()}")
            else:
                # *_raw.txt — the full decision tree: every question
                # answered on this workup's path, in order, then the
                # final result or (if the walk is incomplete) the last
                # node reached.
                breadcrumb = wu.breadcrumb(markup=False)
                if breadcrumb:
                    for step_line in breadcrumb.split("  →  "):
                        _emit(f"    {step_line}")
                else:
                    _emit("    (no questions answered yet)")
                _emit(f"    Result: {wu.result_or_progress_text()}")
    else:
        # Pre-CAL-CP sessions (or sessions never re-opened since the
        # rebuild) keep their old free-form fields under "legacy" —
        # rendered as-is rather than silently dropped.
        legacy = dx.get("legacy") or dx
        sub("ICD-11 Pathway Selection")
        f("duration_over_3_months", legacy)
        f("mechanism",              legacy)

        sub("Chronic Primary Pain")
        f("primary_distress",     legacy)
        f("primary_not_other_dx", legacy)
        f("primary_subtype",      legacy)
        f("primary_severity",     legacy)

        sub("Chronic Post-Surgical Pain")
        f("surgical_procedure", legacy)
        f("surgical_subtype",   legacy)
        f("surgical_source",    legacy)
        f("surgical_severity",  legacy)

        sub("Chronic Post-Traumatic Pain")
        f("traumatic_event",    legacy)
        f("traumatic_subtype",  legacy)
        f("traumatic_source",   legacy)
        f("traumatic_severity", legacy)

        sub("Chronic Secondary MSK Pain")
        f("msk_pathology", legacy)
        f("msk_subtype",   legacy)
        f("msk_source",    legacy)
        f("msk_severity",  legacy)

        sub("Chronic Neuropathic Pain")
        f("neuro_lesion",   legacy)
        f("neuro_subtype",  legacy)
        f("neuro_severity", legacy)

        sub("Mixed / Indeterminate")
        f("mixed_dominant",     legacy)
        txt("mixed_reasoning",  legacy)

    _emit_yaml_subs_raw("diagnosis", dx, clean, _emit, sub)

    # ════════════════════════════════════════════════════════════════════════
    # SOAP: PLAN
    # ════════════════════════════════════════════════════════════════════════
    lines.extend(["", SEP, "P — PLAN", SEP])

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 7: BARRIERS & TREATMENT PLAN
    # ════════════════════════════════════════════════════════════════════════
    br = a.get("barriers", {}) or {}
    sec("SECTION 7: BARRIERS & TREATMENT PLAN")

    # ── clean-mode barrier helper (raw) ──────────────────────────────────
    def _barrier_raw(prefix: str, items: list, d: dict) -> None:
        present_parts = []
        absent_parts  = []
        for label, key, sub_items in items:
            val = d.get(key)
            if val is True:
                sub_parts = []
                for sub_label, sub_key in sub_items:
                    sv = d.get(sub_key)
                    if sv is True:
                        sub_parts.append(sub_label)
                    elif isinstance(sv, str) and sv.strip():
                        sub_parts.append(sv.strip())
                present_parts.append(
                    f"{label} ({', '.join(sub_parts)})" if sub_parts else label)
            elif val is False:
                absent_parts.append(label)
        if present_parts:
            _emit("  " + prefix + " PRESENT: " + "; ".join(present_parts))
        if absent_parts:
            _emit("  " + prefix + " ABSENT: " + "; ".join(absent_parts))

    _NOCI_B = [
        ("Disease/pathology",      "b_noci_disease",        []),
        ("Pacing issues",          "b_noci_pacing",         []),
        ("Inflammatory",           "b_noci_inflammatory",   []),
        ("Deconditioning",         "b_noci_deconditioning", []),
        ("Reduced movement",       "b_noci_movement",       [("Region", "bi_movement_region")]),
        ("Gait",                   "b_noci_gait",           []),
        ("Strength deficits",      "b_noci_strength",       [
            ("Glute max",  "bx_strength_glute_max"),
            ("Glute med",  "bx_strength_glute_med"),
            ("Iliopsoas",  "bx_strength_iliopsoas"),
            ("Quads",      "bx_strength_quads"),
            ("Other",      "bi_strength_other"),
        ]),
        ("Deep muscle",            "b_noci_deep_muscle",    [
            ("Multifidus", "bx_deep_multifidus"),
            ("TA",         "bx_deep_ta"),
            ("Erector",    "bx_deep_erector"),
            ("Other",      "bi_deep_other"),
        ]),
        ("Overactivity",           "b_noci_overactivity",   [
            ("Erector",    "bx_over_erector"),
            ("QL",         "bx_over_ql"),
            ("RA",         "bx_over_ra"),
            ("Obliques",   "bx_over_obliques"),
            ("Piriformis", "bx_over_piriformis"),
            ("Iliopsoas",  "bx_over_iliopsoas"),
            ("Hamstrings", "bx_over_hamstrings"),
            ("Adductors",  "bx_over_adductors"),
            ("Other",      "bi_over_other"),
        ]),
        ("Nerve mechanosensitivity","b_noci_nerve_mech",    [("Region", "bi_nerve_region")]),
        ("Diet/weight",            "b_noci_diet",           []),
    ]
    _PSYCH_B = [
        ("Depression",            "b_psych_depression",       [
            ("Severity",           "bx_dep_severity"),
            ("Psychiatry ref",     "bx_dep_psychiatry"),
        ]),
        ("Anxiety",               "b_psych_anxiety",          [
            ("Severity",           "bx_anx_severity"),
            ("Psychiatry ref",     "bx_anx_psychiatry"),
        ]),
        ("Stress",                "b_psych_stress",           [
            ("Severity",           "bx_stress_severity"),
            ("Psychiatry ref",     "bx_stress_psychiatry"),
        ]),
        ("Catastrophising",       "b_psych_catastrophising",  []),
        ("Reduced self-efficacy", "b_psych_self_efficacy",    []),
        ("Unhelpful beliefs",     "b_psych_unhelpful_beliefs",[
            ("Unrealistic expectations","bx_belief_expectations"),
            ("Symptom focus",           "bx_belief_symptom_focus"),
            ("Cure focus",              "bx_belief_cure_focus"),
            ("Further treatment",       "bx_belief_further_tx"),
        ]),
        ("PTSD",                  "b_psych_ptsd",             [
            ("Mechanism",          "bx_ptsd_mechanism"),
            ("Psychiatry ref",     "bx_ptsd_psychiatry"),
        ]),
        ("Unclear readiness",     "b_psych_readiness",        []),
    ]
    _SOCIAL_B = [
        ("Disturbed sleep",   "b_sleep_disturbed",  []),
        ("Home/social",       "b_social_home",      [
            ("Family support",   "bx_soc_family_support"),
            ("Social support",   "bx_soc_social_support"),
            ("Relationship",     "bx_soc_relationship"),
            ("Personal rel",     "bx_soc_personal_rel"),
            ("Financial",        "bx_soc_financial"),
            ("Residential",      "bx_soc_residential"),
            ("Distance to care", "bx_soc_distance"),
        ]),
        ("Return to work",    "b_social_rtw",       []),
    ]
    _MED_B = [
        ("Red flag",             "b_med_red_flag",    [("Detail", "bi_red_flag_detail")]),
        ("Substance use",        "b_med_substance",   [("Detail", "bi_substance_detail")]),
        ("Possible AS",          "b_med_as",          []),
        ("Possible AAA",         "b_med_aaa",         []),
        ("Vascular claudication","b_med_vascular",    []),
        ("Cervical headache",    "b_med_cervical_ha", []),
        ("Medico-legal",         "b_med_medico_legal",[]),
    ]

    sub("Physical / Nociceptive Barriers")
    if clean:
        _barrier_raw("Nociceptive barriers", _NOCI_B, br)
    else:
        f("b_noci_disease",        br)
        f("b_noci_pacing",         br)
        f("b_noci_inflammatory",   br)
        f("b_noci_deconditioning", br)
        f("b_noci_movement",       br)
        f("bi_movement_region",    br)
        f("b_noci_gait",           br)
        f("b_noci_strength",       br)
        f("bx_strength_glute_max", br)
        f("bx_strength_glute_med", br)
        f("bx_strength_iliopsoas", br)
        f("bx_strength_quads",     br)
        f("bi_strength_other",     br)
        f("b_noci_deep_muscle",    br)
        f("bx_deep_multifidus",    br)
        f("bx_deep_ta",            br)
        f("bx_deep_erector",       br)
        f("bi_deep_other",         br)
        f("b_noci_overactivity",   br)
        f("bx_over_erector",       br)
        f("bx_over_ql",            br)
        f("bx_over_ra",            br)
        f("bx_over_obliques",      br)
        f("bx_over_piriformis",    br)
        f("bx_over_iliopsoas",     br)
        f("bx_over_hamstrings",    br)
        f("bx_over_adductors",     br)
        f("bi_over_other",         br)
        f("b_noci_nerve_mech",     br)
        f("bi_nerve_region",       br)
        f("b_noci_diet",           br)

    sub("Neuropathic Barriers")
    if clean:
        _barrier_raw("Neuropathic barriers", [
            ("Neuropathic (confirmed)",   "b_neuro_confirmed",   []),
            ("Neuropathic (unconfirmed)", "b_neuro_unconfirmed", []),
        ], br)
    else:
        f("b_neuro_confirmed",   br)
        f("b_neuro_unconfirmed", br)

    sub("Nociplastic / Central Sensitisation Barriers")
    if clean:
        _barrier_raw("Nociplastic barriers", [
            ("Nociplastic/CS", "b_nocip_moderate", []),
            ("CRPS",           "b_nocip_crps",     []),
            ("FND",            "b_nocip_fnd",      []),
        ], br)
    else:
        f("b_nocip_moderate", br)
        f("b_nocip_crps",     br)
        f("b_nocip_fnd",      br)

    sub("Psychological Barriers")
    if clean:
        _barrier_raw("Psychological barriers", _PSYCH_B, br)
    else:
        f("b_psych_depression",       br)
        f("bx_dep_severity",          br)
        f("bx_dep_psychiatry",        br)
        f("b_psych_anxiety",          br)
        f("bx_anx_severity",          br)
        f("bx_anx_psychiatry",        br)
        f("b_psych_stress",           br)
        f("bx_stress_severity",       br)
        f("bx_stress_psychiatry",     br)
        f("b_psych_catastrophising",  br)
        f("b_psych_self_efficacy",    br)
        f("b_psych_unhelpful_beliefs", br)
        f("bx_belief_expectations",   br)
        f("bx_belief_symptom_focus",  br)
        f("bx_belief_cure_focus",     br)
        f("bx_belief_further_tx",     br)
        f("b_psych_ptsd",             br)
        f("bx_ptsd_mechanism",        br)
        f("bx_ptsd_psychiatry",       br)
        f("b_psych_readiness",        br)

    sub("Sleep & Social / Contextual Barriers")
    if clean:
        _barrier_raw("Sleep/social barriers", _SOCIAL_B, br)
    else:
        f("b_sleep_disturbed",       br)
        f("b_social_home",           br)
        f("bx_soc_family_support",   br)
        f("bx_soc_social_support",   br)
        f("bx_soc_relationship",     br)
        f("bx_soc_personal_rel",     br)
        f("bx_soc_financial",        br)
        f("bx_soc_residential",      br)
        f("bx_soc_distance",         br)
        f("b_social_rtw",            br)

    sub("Medical / Systemic Barriers")
    if clean:
        _barrier_raw("Medical barriers", _MED_B, br)
    else:
        f("b_med_red_flag",     br)
        f("bi_red_flag_detail", br)
        f("b_med_substance",    br)
        f("bi_substance_detail", br)
        f("b_med_as",           br)
        f("b_med_aaa",          br)
        f("b_med_vascular",     br)
        f("b_med_cervical_ha",  br)
        f("b_med_medico_legal", br)

    sub("Custom Barriers")
    f("custom_1_barrier",  br)
    f("custom_1_strategy", br)
    f("custom_2_barrier",  br)
    f("custom_2_strategy", br)

    _emit_yaml_subs_raw("barriers", br, clean, _emit, sub)

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 8: RX PLAN
    # ════════════════════════════════════════════════════════════════════════
    rp = a.get("rx_plan", {}) or {}
    sec("SECTION 8: RX PLAN")

    sub("Treatment Plan Summary")
    f("tx_pain_type",           rp)
    f("tx_debunk_radiology",    rp)
    f("tx_consent_explanation", rp)
    txt("tx_goal_orientation",  rp)
    txt("tx_formulation",       rp)
    txt("tx_program",           rp)
    txt("tx_home_program",      rp)
    txt("tx_psychosocial",      rp)
    txt("tx_medical",           rp)
    txt("tx_rtw",               rp)

    sub("Session 1 Treatment")
    txt("s1_education",     rp)
    txt("s1_experiential",  rp)
    f("s1_consent_content", rp)
    f("s1_confidence_nrs",  rp)
    f("hw_online_module",   rp)
    f("hw_mindfulness",     rp)
    f("hw_goal_sheet",      rp)
    f("hw_activity_diary",  rp)
    f("hw_sleep_diary",     rp)
    txt("s1_hw_other",      rp)
    f("tx_email_obtained",  rp)
    f("tx_display_book",    rp)

    sub("Day 1 Checklist")
    f("d1_explanation",       rp)
    f("d1_session2",          rp)
    f("d1_hypothesis",        rp)
    f("d1_diagnosis",         rp)
    f("d1_values",            rp)
    f("d1_evidence",          rp)
    f("d1_plan",              rp)
    f("d1_prognosis",         rp)
    f("d1_stakeholders",      rp)
    f("d1_confidence_tested", rp)
    f("d1_questionnaires",    rp)

    sub("Follow-Up Plan")
    txt("fu_next_focus",   rp)
    txt("fu_monitoring",   rp)
    f("fu_om_schedule",    rp)
    f("ps_questionnaires", rp)
    f("ps_eppoc",          rp)
    f("ps_ptsd_scored",    rp)
    f("ps_isi_pbas",       rp)
    f("ps_csi",            rp)
    f("ps_audit_dudit",    rp)

    # ════════════════════════════════════════════════════════════════════════
    # BODY CHART SUMMARY
    # ════════════════════════════════════════════════════════════════════════
    subj_chart = session_data.get("subjective", {}) or {}
    obj_chart  = session_data.get("objective",  {}) or {}
    sec("BODY CHART SUMMARY")
    n_strokes = len(subj_chart.get("strokes", []))
    n_notes   = len(subj_chart.get("notes",   []))
    n_arrows  = len(subj_chart.get("arrows",  []))
    n_zones   = len(obj_chart.get("zones",    []))
    n_points  = len(obj_chart.get("points",   []))
    if not clean or any([n_strokes, n_notes, n_arrows, n_zones, n_points]):
        _emit(f"  Symptom strokes drawn:    {n_strokes}",
              f"  Note annotations:         {n_notes}",
              f"  Arrows:                   {n_arrows}",
              f"  Objective zones:          {n_zones}",
              f"  Measurement points (PPT): {n_points}")

    # symptom types from the chart watcher summary (if present)
    body_chart = session_data.get("body_chart") or session_data.get("assessment", {}).get("body_chart")
    if isinstance(body_chart, dict):
        sym_types = body_chart.get("symptom_types_used", [])
        if sym_types:
            _emit(f"  Symptom types used: {', '.join(str(t) for t in sym_types)}")
        views = body_chart.get("views_drawn", [])
        if views:
            _emit(f"  Views drawn: {', '.join(str(v) for v in views)}")

    # ── footer ──────────────────────────────────────────────────────────────
    footer_title = "END OF ASSESSMENT DATA" if clean else "END OF RAW ASSESSMENT DATA"
    lines.extend(["", SEP, footer_title,
                  f"Generated: {_time.strftime('%d %b %Y %H:%M:%S')}",
                  "For clinical use only — verify all entries before use", SEP])

    return "\n".join(lines)


def save_raw_report(session_file: str) -> str:
    """
    Generate and save a raw plain-text report into the session directory.

    Output: <session_dir>/<session_name>_raw.txt  (same folder as all other
    session files — overwrites on each call so the file stays current).
    Returns the output path, or empty string on failure.
    """
    try:
        data = json.loads(Path(session_file).read_text()) if Path(session_file).exists() else {}
    except Exception as e:
        logger.error(f"save_raw_report: failed to read session: {e}")
        return ""

    # Overlay TUI assessment data from the separate _assessment.json
    assess_p = assessment_path(session_file)
    if assess_p.exists():
        try:
            assess_data = json.loads(assess_p.read_text())
            data["assessment"] = assess_data.get("assessment", data.get("assessment", {}))
            data.setdefault("sections_complete", assess_data.get("sections_complete", {}))
        except Exception:
            pass

    # Load objective sections from _objective.json
    obj_file_data = load_objective(session_file)
    data["objective_assessment"] = obj_file_data.get("assessment", {})

    content = export_raw_report(data)
    session_name = data.get("session_name", "session")
    out_path = Path(session_file).parent / f"{session_name}_raw.txt"

    try:
        out_path.write_text(content, encoding="utf-8")
        logger.debug(f"Raw report written to {out_path}")
        return str(out_path)
    except Exception as e:
        logger.error(f"save_raw_report: write failed: {e}")
        return ""


def save_clean_reports(session_file: str) -> None:
    """
    Generate and save *_clean.txt and *_clean.md containing only fields with data.

    Called from _do_save() alongside save_raw_report() and export_session_report().
    Errors are logged but never raised — clean reports are non-critical.
    """
    try:
        data = json.loads(Path(session_file).read_text()) if Path(session_file).exists() else {}
    except Exception as e:
        logger.error(f"save_clean_reports: failed to read session: {e}")
        return

    assess_p = assessment_path(session_file)
    if assess_p.exists():
        try:
            assess_data = json.loads(assess_p.read_text())
            data["assessment"] = assess_data.get("assessment", data.get("assessment", {}))
            data.setdefault("sections_complete", assess_data.get("sections_complete", {}))
        except Exception:
            pass

    obj_file_data = load_objective(session_file)
    data["objective_assessment"] = obj_file_data.get("assessment", {})

    session_name = data.get("session_name", "session")
    session_dir  = Path(session_file).parent

    try:
        content = export_raw_report(data, clean=True)
        clean_txt = session_dir / f"{session_name}_clean.txt"
        clean_txt.write_text(content, encoding="utf-8")
        logger.debug(f"Clean txt written to {clean_txt}")
    except Exception as e:
        logger.error(f"save_clean_reports: txt write failed: {e}")

    export_session_report(session_file, clean=True, dev=True)


def save_docx_report(session_file: str) -> str:
    """
    Convert *_clean.md to *_clean.docx using pandoc.

    Requires pandoc on PATH. Silent no-op if pandoc is absent.
    Returns the output path on success, empty string on failure.
    """
    p = Path(session_file)
    session_name = p.stem.replace("_session", "")
    md_path   = p.parent / f"{session_name}_clean.md"
    docx_path = p.parent / f"{session_name}_clean.docx"

    if not md_path.exists():
        logger.warning(f"save_docx_report: {md_path} not found — run save_clean_reports first")
        return ""

    try:
        result = subprocess.run(
            ["pandoc", str(md_path), "-o", str(docx_path)],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0:
            logger.debug(f"Docx written to {docx_path}")
            return str(docx_path)
        logger.error(f"pandoc failed: {result.stderr.decode().strip()}")
        return ""
    except FileNotFoundError:
        logger.warning("pandoc not found — skipping docx generation")
        return ""
    except Exception as e:
        logger.error(f"save_docx_report: {e}")
        return ""


def create_new_session(patient_id: str, regions: list[str]) -> dict:
    """
    Create a new assessment session (JSON scaffold).

    Returns session dict with initialized fields ready to save.
    """
    from datetime import datetime
    now = int(time.time())
    iso_date = datetime.fromtimestamp(now).isoformat() + "Z"

    return {
        "version": 3,
        "patient_id": patient_id,
        "session_label": f"Assessment - {regions[0] if regions else 'General'}" if regions else "Assessment",
        "session_name": f"{patient_id}_{datetime.now().strftime('%d_%m_%Y_%H%M')}",
        "created": now,
        "modified": now,
        "regions": regions,
        "launched_by": "tui",
        "workflow_stage": "01_consent",
        "body_chart_requested": False,
        "body_chart_complete": False,
        "ui": {
            "layout_mode": 0,
            "right_slot_views": [0, 1],
        },
        "subjective": {
            "strokes": [],
            "stroke_clusters": [],
            "misc_cluster_ids": [],
            "notes": [],
            "arrows": [],
            "link_matrix": [],
            "link_relations": [],
            "link_summary_active": False,
            "link_summary_view": 0,
            "link_summary_bx": 12.0,
            "link_summary_by": 378.0,
        },
        "objective": {
            "zones": [],
            "points": [],
        },
        "neuro": {},
        "assessment": {
            "consent": {
                "consent_to_proceed": None,
                "consent_sensitive_topics": None,
                "preferred_name": "",
                "pain_multifactorial_explained": None,
                "education_as_treatment_explained": None,
                "patient_expectations": "",
                "reason_for_attending": "",
                "cause_understanding": None,
                "cause_understanding_detail": "",
                "prognosis_expectations": "",
                "treatment_preference": "",
            },
            "history": "",
            "agg_factors": "",
            "ease_factors": "",
            "behaviour_24hr": "",
            "diagnosis": "",
            "plan": "",
            "clinical_notes": "",
            "modified": now,
        },
        "report": {
            "assessment": "",
            "plan": "",
            "clinical_notes": "",
            "note_subj": [],
        },
    }
