#include "integration.h"
#include "persistence.h"
#include "py_embed.h"
#include <gtk/gtk.h>

/* GPAB INTEGRATION — MERGED-APP EMBEDDING SPIKE (2026-08-25) ────────────────
 *
 * Supersedes the separate-process design this file had from 2026-08-23
 * through 2026-08-25 (spawn `gpab-assessment` as an independent process,
 * coordinate open/close/raise via D-Bus `gapplication` calls — see git log
 * for that version if it's ever needed again). Root cause that forced this
 * rewrite: Ctrl+B's "raise gpab's window" never actually worked. Wayland
 * blocks one process from forcing focus onto a DIFFERENT process's window
 * (a deliberate anti-focus-steal security measure) — `gapplication launch`
 * on an unfocused app just produces a "ready" notification, not a real
 * raise, no matter how correctly the D-Bus plumbing is done. Confirmed live
 * repeatedly. The quit-coupling half worked fine over D-Bus; only the raise
 * half was ever actually broken — but "feels like one program" needs both.
 *
 * The fix: gpab's Python runs INSIDE this process now, via an embedded
 * CPython interpreter (see py_embed.c/.h) — imported, not spawned. A window
 * raising a SIBLING window in its own process is not cross-process, so the
 * Wayland restriction never applies; gpab's window is exactly as raisable
 * as any of bodychart's own dialogs. The two are still genuinely separate
 * windows (this isn't a widget-embedding trick, GTK4 has no mechanism for
 * that — see py_embed.h) — just one process now instead of two.
 *
 * This is a THIRD-TIER experiment (see ../../CLAUDE.md's "Branch and
 * deployment rules" — the merged-app branch/worktree), deliberately kept
 * out of dev/gpabd and main/gpabs until proven and explicitly promoted.
 *
 * This file only exists modified in ~/Projects/gpab's own clone of
 * bodychart/ — see ../../CLAUDE.md's isolation guarantee. ~/Projects/pab is
 * never touched by this change; pabd/pabs keep building and running the
 * original integration.c unmodified. */

void integration_create_tui_window(AppState *app, GtkApplication *gapp)
{
    (void)gapp;
    if (!app->session_file[0]) return;
    py_embed_open_session(app->session_file);
}

void integration_focus_tui(AppState *app)
{
    /* Ctrl+A (stale binding from the VTE-embedded-TUI era) and Ctrl+B
     * (window.c's dedicated key) both land here — raise gpab's window, now
     * a same-process gtk_window_present() call via py_embed, not a
     * cross-process D-Bus request that Wayland would just ignore. */
    (void)app;
    py_embed_present_gpab();
}

void integration_destroy_tui(AppState *app)
{
    /* "Close once": bodychart closing also closes gpab — direct in-process
     * call via py_embed, routed through gpab's own TrialWindow.close()
     * (so its flush/report-regeneration close path still runs in full, no
     * shortcuts) rather than killing a process. Guarded against the
     * obvious mutual-recursion risk this creates now that both directions
     * are synchronous, same-process calls: gpab's own _on_close_request
     * has a self._closing re-entrancy flag (Python side), and see
     * window.c's on_main_window_close for the equivalent guard here. */
    (void)app;
    py_embed_close_gpab();
}
