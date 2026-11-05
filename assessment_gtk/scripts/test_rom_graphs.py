#!/usr/bin/env python3
"""Checks rom_graphs.attach() (Ctrl+M) against temporary folders only — never
touches ~/GSConnectInbox, ~/PAB or a real session.

Run from assessment_gtk/: .venv/bin/python scripts/test_rom_graphs.py
"""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gpab_assessment import rom_graphs  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32

with tempfile.TemporaryDirectory() as t:
    root = Path(t)
    inbox, archive, sess = root / "inbox", root / "archive", root / "PAT_session"
    inbox.mkdir(); sess.mkdir()
    (root / "downloads").mkdir()
    (root / "downloads" / "romring_20261105_150000.png").write_bytes(PNG)  # device saves to ~/Downloads
    session_file = str(sess / "PAT_session_session.json")
    for n in ("romring_20261105_142233.png",          # today
              "romring_20261105_142233.png (1)",      # KDE Connect duplicate rename (seen on device)
              "romring_20261104_090000.png",          # yesterday: must stay
              "IMG_0001.png",                         # unrelated photo: must stay
              "TEST_05_11_2026_1112.gonio.zip"):      # goniometer bundle: must stay
        (inbox / n).write_bytes(PNG)

    r = rom_graphs.attach(session_file, (inbox, root / "downloads"), archive, today=date(2026, 11, 5))
    got = sorted(p.name for p in (sess / "gonio_charts").iterdir())
    left = sorted(p.name for p in inbox.iterdir())
    archived = sorted(p.name for p in archive.iterdir())

    assert sorted(r.attached) == ["romring_20261105_142233.png", "romring_20261105_150000.png"], r
    assert got == sorted(r.attached), got   # duplicate collapsed onto one chart
    assert r.older_left == 1, r
    assert left == ["IMG_0001.png", "TEST_05_11_2026_1112.gonio.zip", "romring_20261104_090000.png"], left
    assert archived == ["romring_20261105_142233.png", "romring_20261105_142233_1.png",
                        "romring_20261105_150000.png"], archived
    assert (sess / "gonio_charts" / "romring_20261105_142233.png").read_bytes() == PNG

    # Re-send of the same graph: overwrites in gonio_charts/, archive keeps both copies.
    (inbox / "romring_20261105_142233.png").write_bytes(PNG + b"x")
    r2 = rom_graphs.attach(session_file, (inbox, root / "downloads"), archive, today=date(2026, 11, 5))
    assert r2.attached == ["romring_20261105_142233.png"], r2
    assert (sess / "gonio_charts" / "romring_20261105_142233.png").read_bytes() == PNG + b"x"
    assert len(list(archive.iterdir())) == 4

    # Nothing waiting.
    assert rom_graphs.attach(session_file, (inbox, root / "downloads"), archive, today=date(2026, 11, 5)).attached == []
    assert rom_graphs.attach(session_file, (root / "missing",), archive).attached == []

assert rom_graphs.rep_time("romring_20261105_142233.png (1)") == "14:22"
print("rom_graphs: all checks passed")
