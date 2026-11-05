"""ROM Ring movement graphs → the open session's Objective bodychart (Ctrl+M).

The ROM Ring phone app (~/Projects/ROM, GraphExport.kt) sends one PNG per rep over
KDE Connect, named ``romring_YYYYMMDD_HHMMSS.png`` from the rep's start time. It
carries no patient code, so a graph has no patient until it is imported: Ctrl+M
attaches every graph waiting in ~/GSConnectInbox or ~/Downloads to whichever session is open.
No numeric import and no wizard (deliberately; see the goniometer Ctrl+G flow for
that). The graph image itself carries date/time, voice note and figures.

Only TODAY's graphs (by the timestamp in the filename) are attached, so one left
over from an earlier day can't land on the wrong patient; older ones are left in
the inbox and counted in the status line.

Destination is ``<session dir>/gonio_charts/`` — the same folder the goniometer
import uses — because bodychart's gonio_charts_rescan() shows any .png there on
the Objective canvas (draggable, scalable, hideable). Writes are temp+rename.
Consumed inbox files are moved (not deleted) to ~/PAB/_inbox/rom/_imported/, so
a graph attached to the wrong patient can be recovered.

The gsconnect-goniometer-router only moves *.gonio.json / *.gonio.zip, so it
never touches these files.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

# GSConnect's global receive folder is ~/GSConnectInbox, but a device's own
# Share setting can override it (the clinic phone saves to ~/Downloads, checked
# 2026-11-05), so look in both.
INBOXES = (Path.home() / "GSConnectInbox", Path.home() / "Downloads")
ARCHIVE = Path.home() / "PAB" / "_inbox" / "rom" / "_imported"

# KDE Connect adds its counter AFTER the extension when the same graph is sent
# twice: "romring_20261105_142233.png (1)" (seen 2026-11-05). Allow that and a
# counter before it too.
_NAME = re.compile(r"^romring_(\d{8})_(\d{6})[^/]*\.png(?: \(\d+\))?$")


@dataclass
class AttachResult:
    attached: list[str] = field(default_factory=list)   # basenames now in gonio_charts/
    older_left: int = 0                                  # earlier-day graphs left in the inbox


def _graph_day(name: str) -> str | None:
    m = _NAME.match(name)
    return m.group(1) if m else None


def rep_time(name: str) -> str:
    """'romring_20261105_142233.png' -> '14:22' (the rep's start time on the phone)."""
    m = _NAME.match(name)
    return f"{m.group(2)[:2]}:{m.group(2)[2:4]}" if m else "?"


def chart_name(name: str) -> str:
    """The name the graph gets in gonio_charts/: always 'romring_<date>_<time>.png',
    so a re-sent graph replaces the earlier copy instead of showing twice, and
    bodychart (which only reads *.png) sees it."""
    m = _NAME.match(name)
    return f"romring_{m.group(1)}_{m.group(2)}.png" if m else name


def waiting(inboxes: tuple[Path, ...] = INBOXES) -> list[Path]:
    """Every ROM Ring graph in the inbox folders, oldest first."""
    found = [p for d in inboxes if d.is_dir() for p in d.iterdir()
             if p.is_file() and _NAME.match(p.name)]
    return sorted(found, key=lambda p: p.name)


def _free_name(d: Path, name: str) -> Path:
    target = d / name
    n = 1
    while target.exists():
        target = d / f"{Path(name).stem}_{n}.png"
        n += 1
    return target


def attach(session_file: str, inboxes: tuple[Path, ...] = INBOXES, archive: Path = ARCHIVE,
           today: date | None = None) -> AttachResult:
    """Copy today's waiting graphs into the session's gonio_charts/ and archive
    the inbox copies. A re-sent graph with the same name overwrites in place."""
    day = (today or date.today()).strftime("%Y%m%d")
    result = AttachResult()
    graphs = waiting(inboxes)
    if not graphs:
        return result

    dest_dir = Path(session_file).parent / "gonio_charts"
    for src in graphs:
        if _graph_day(src.name) != day:
            result.older_left += 1
            continue
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            name = chart_name(src.name)
            tmp = dest_dir / (name + ".tmp")
            shutil.copyfile(src, tmp)
            tmp.replace(dest_dir / name)
            archive.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(_free_name(archive, name)))
            if name not in result.attached:
                result.attached.append(name)
            logger.info("rom graph %s -> %s", src.name, dest_dir)
        except OSError as e:
            logger.warning("rom graph %s not attached: %s", src.name, e)
    return result
