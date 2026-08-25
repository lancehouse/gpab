#include "integration.h"
#include "persistence.h"
#include <gtk/gtk.h>

/* GPAB INTEGRATION (this clone only, changed 2026-08-23) ───────────────────
 *
 * The original PAB integration embedded the Textual assessment TUI in a VTE
 * terminal inside a window owned by this app (see git history for the prior
 * version of this file). gpab replaces that TUI with a standalone GTK4 app
 * that manages its own window entirely, so there is nothing left to embed —
 * this just launches it as an independent process against the same session
 * file and otherwise gets out of the way. Deliberately NOT supervised in the
 * sense that gpab exiting doesn't close bodychart and vice versa (see
 * on_main_window_close / this file's own no-op focus/destroy below) — the
 * two are meant to run side by side as separate programs now, not one
 * owning the other's lifecycle the way the embedded TUI window used to.
 * The one thing that IS tracked here is gpab's PID (app->gpab_pid), purely
 * for bookkeeping/reaping — see on_gpab_exited below. Making way for a
 * newly-opened session is instead done by killing any running gpab process
 * BY NAME (kill_existing_gpab), not just one this bodychart process itself
 * spawned. That distinction matters: bodychart only shows its launch dialog
 * once, at startup, so in practice a bodychart process only ever calls
 * integration_create_tui_window once — a this-process-only PID check would
 * never fire for the actual real-world case, which is: bodychart is quit
 * and relaunched for a different patient while gpab (independent lifetime,
 * by design) is still open from before. Confirmed live 2026-08-23: gpab is
 * a single-instance GtkApplication, so launching a second copy for a
 * DIFFERENT session doesn't open a new window — it silently hands off to
 * the existing instance and exits, leaving the wrong patient's data on
 * screen with no error at all. Killing by name mirrors the same pkill this
 * repo's own `./gpab <session>` launcher script already uses for the
 * identical staleness problem.
 *
 * This file only exists modified in ~/Projects/gpab's own clone of
 * bodychart/ — see ../../CLAUDE.md's isolation guarantee. ~/Projects/pab is
 * never touched by this change; pabd/pabs keep building and running the
 * original integration.c unmodified.
 *
 * DEV/STABLE SPLIT (2026-08-25) — mirrors pab's own "assessment" (pabd, dev
 * branch) vs "assessments" (pabs, main branch) launcher split exactly, see
 * ../../CLAUDE.md's "Branch and deployment rules". GPAB_LAUNCHER names a
 * small wrapper script on $PATH (~/.local/bin/) rather than hardcoding an
 * absolute venv path — this is the ONE line that's meant to differ between
 * the `dev` and `main` copies of this file (a `gpab-stable/` git worktree
 * checked out at `main` carries "gpab-assessment-stable" here instead), so
 * a `dev`→`main` merge always surfaces it as a conflict to resolve, not a
 * silent overwrite of which checkout stable actually launches. */

#define GPAB_LAUNCHER "gpab-assessment"

/* Reap the gpab child when it exits (window closed by the user, crash, or
 * killed below to make way for a new session) so app->gpab_pid never goes
 * stale. Guards against clobbering a newer PID: if a session was reopened
 * while this watch was still pending on the old process, app->gpab_pid
 * already points at the new one by the time this fires. */
static void on_gpab_exited(GPid pid, gint status, gpointer user_data)
{
    (void)status;
    AppState *app = user_data;
    if (app->gpab_pid == pid)
        app->gpab_pid = 0;
    g_spawn_close_pid(pid);
}

/* Kill any running gpab process by name — see file header for why this has
 * to be name-based rather than app->gpab_pid-based. */
static void kill_existing_gpab(void)
{
    char *argv[] = { "pkill", "-f", GPAB_LAUNCHER, NULL };
    g_spawn_sync(NULL, argv, NULL,
                 G_SPAWN_SEARCH_PATH | G_SPAWN_STDOUT_TO_DEV_NULL | G_SPAWN_STDERR_TO_DEV_NULL,
                 NULL, NULL, NULL, NULL, NULL, NULL);
    /* Give the old process a moment to release its D-Bus name/GtkApplication
     * registration before spawning a new one — otherwise a spawn that races
     * the old process's teardown can still hand off to it instead of
     * starting fresh, the same race `./gpab`'s own `sleep 0.3` exists to
     * avoid. */
    g_usleep(300000);
}

/* A launch failure is otherwise silent — just a line to a terminal nobody's
 * watching on a machine used touchscreen-only. */
static void show_launch_error(AppState *app, const char *message)
{
    GtkAlertDialog *dlg = gtk_alert_dialog_new("Could not launch the assessment app");
    gtk_alert_dialog_set_detail(dlg, message);
    gtk_alert_dialog_show(dlg, app->window ? GTK_WINDOW(app->window) : NULL);
    g_object_unref(dlg);
}

void integration_create_tui_window(AppState *app, GtkApplication *gapp)
{
    (void)gapp;
    if (!app->session_file[0]) return;

    kill_existing_gpab();
    app->gpab_pid = 0;

    /* GPAB_LAUNCHER is a bare command name, resolved via $PATH
     * (G_SPAWN_SEARCH_PATH) to a small wrapper script in ~/.local/bin/ that
     * cds into the right checkout and execs its own venv's python — see
     * this file's header comment. cwd NULL: inherit, the wrapper does its
     * own cd rather than this process needing to know the checkout path. */
    char *argv[] = {
        (char *)GPAB_LAUNCHER,
        "--session", app->session_file,
        NULL
    };

    GError *error = NULL;
    GPid pid = 0;
    gboolean ok = g_spawn_async(
        NULL,
        argv,
        NULL,
        G_SPAWN_SEARCH_PATH | G_SPAWN_DO_NOT_REAP_CHILD,
        NULL, NULL,
        &pid,
        &error);

    if (!ok) {
        g_warning("Failed to launch gpab: %s", error ? error->message : "unknown error");
        show_launch_error(app, error ? error->message : "unknown error");
        g_clear_error(&error);
        return;
    }

    app->gpab_pid = pid;
    g_child_watch_add(pid, on_gpab_exited, app);
}

void integration_focus_tui(AppState *app)
{
    (void)app;
    /* No embedded window to focus — gpab manages its own window/taskbar
     * presence as an independent process. */
}

void integration_destroy_tui(AppState *app)
{
    (void)app;
    /* gpab's lifetime is independent of bodychart's now — see file header.
     * Deliberately does NOT kill app->gpab_pid: bodychart's own window
     * closing shouldn't reach out and close gpab's, matching the "neither
     * owns the other's lifecycle" design stated above. */
}
