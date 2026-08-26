#include <gtk/gtk.h>
#include <string.h>
#include "canvas.h"
#include "window.h"
#include "stroke.h"
#include "overlays.h"
#include "svg_views.h"
#include "overlay_svg.h"
#include "svg_regions.h"
#include "settings.h"
#include "input.h"
#include "persistence.h"
#include "py_embed.h"
#include "integration.h"

/* Global session path if provided via --session argument */
static char g_session_path[512] = "";

/* "quit" GAction (2026-08-25) — activated remotely via
 * `gapplication action com.gpab.bodychart quit`, the half of "close both
 * windows together" that lets gpab's own close handler ask bodychart to
 * close too (see integration.c and gpab's app.py::_on_close_request for
 * the other half, and window.c's on_key_pressed for the matching Ctrl+B
 * that raises gpab's window instead of closing anything). Closes the same
 * way the titlebar's own close button does, so it still goes through
 * on_main_window_close's autosave/PDF-export chain — no shortcuts. A
 * no-op if there's no window yet (e.g. bodychart is still sitting on its
 * launch dialog). */
static void on_quit_action(GSimpleAction *action, GVariant *parameter, gpointer user_data)
{
    (void)action; (void)parameter;
    AppState *state = user_data;
    if (state->window)
        gtk_window_close(GTK_WINDOW(state->window));
}

static void on_activate(GtkApplication *app, gpointer user_data)
{
    AppState *state = user_data;

    /* Re-activation of an already-running instance (2026-08-25) — e.g.
     * clicking the desktop icon again, or `gapplication launch
     * com.gpab.bodychart` run by hand, while bodychart's already open.
     * (gpab's own Ctrl+B no longer goes through this path as of the
     * merged-app embedding spike — it calls straight into
     * gtk_window_present() via py_embed's bodychart_bridge, bypassing
     * GApplication activation entirely — but this guard is still needed
     * for the other, still-live ways to re-trigger "activate".) Without
     * this guard, "activate" fired a second time re-ran persistence_load +
     * window_create unconditionally, creating a SECOND window inside the
     * same process that clobbered window.c's static g_save_indicator (and
     * app->window itself) out from under the first, real window — found
     * live via a since-retired D-Bus version of gpab's Ctrl+B: a
     * GTK-CRITICAL assertion (gtk_label_set_text on a dangling GtkLabel)
     * on the next close, same root cause as the earlier window_autosave
     * coredump fix, just a different way to reach two live windows sharing
     * one static pointer. The equivalent bug (and fix) is in gpab's own
     * app.py::build_app's on_activate. */
    if (state->window) {
        gtk_window_present(GTK_WINDOW(state->window));
        return;
    }

    /* If --session was provided, load that session directly */
    if (g_session_path[0] != '\0') {
        if (persistence_load(state, g_session_path)) {
            persistence_monitor_start(state);
            window_create(state, app);
            /* merged-app spike only: the real desktop flow always goes
             * through the launch dialog (launch_commit_new/_open), which
             * already calls this — --session bypasses that dialog
             * entirely, so nothing opened gpab. Added here purely to make
             * --session a usable end-to-end test path for this spike
             * without needing to drive the dialog's buttons. */
            integration_create_tui_window(state, app);
        } else {
            /* Failed to load; show launch dialog as fallback */
            window_show_launch(state, app);
        }
    } else {
        /* No session provided; show launch dialog */
        window_show_launch(state, app);
    }
}

int main(int argc, char *argv[])
{
    svg_views_init();
    overlay_svg_init();

    /* Parse --session before GTK sees argv */
    for (int i = 1; i < argc; ) {
        if (strcmp(argv[i], "--session") == 0 && i + 1 < argc) {
            strncpy(g_session_path, argv[i + 1], sizeof(g_session_path) - 1);
            for (int j = i; j < argc - 2; j++) argv[j] = argv[j + 2];
            argc -= 2;
        } else {
            i++;
        }
    }

    /* Initialise app state */
    AppState state;
    memset(&state, 0, sizeof(state));
    state.strokes          = stroke_list_new();
    state.current_view     = VIEW_ANTERIOR;
    state.layout_mode      = LAYOUT_QUAD;
    state.tool             = TOOL_DRAW;
    state.symptom          = SYMPTOM_PAIN_CONSTANT;
    state.overlay_visible  = FALSE;
    state.overlay_category = OVERLAY_DERMATOME;
    state.overlay_index    = 0;
    state.overlay_alpha    = 0.5f;
    state.canvas_w         = 900;
    state.canvas_h         = 700;

    state.pen_gamma           = 2.0f;
    state.pen_wide_mode       = FALSE;
    state.pen_palm_reject     = TRUE;
    state.pen_btn_action      = BTN_CYCLE_SYMPTOM;
    state.pen_dot_radius      = 1.0f;
    state.pen_dot_spacing     = 4.5f;
    state.pen_dash_len        = 2.0f;
    state.pen_dash_spacing    = 5.0f;
    state.pen_dash_width      = 0.5f;
    state.pen_x_arm           = 2.0f;
    state.pen_x_spacing       = 6.0f;
    state.pen_x_width         = 0.5f;
    state.pen_tilt_weight     = 0.0f;
    state.right_slot_views[0] = VIEW_LATERAL_L;
    state.right_slot_views[1] = VIEW_LATERAL_R;

    input_hotkeys_init(&state);   /* set defaults; settings_load may override */
    settings_load(&state);
    settings_apply_args(&state, &argc, argv);
    svg_regions_load(&state.svg_regions);

    /* Distinct app ID from production's "com.pab.bodychart" (this clone
     * only, 2026-08-23) — GtkApplication is single-instance per ID, so
     * sharing production's ID would mean launching this gpab-integrated
     * build while pabd/pabs's own bodychart is already running silently
     * hands off to that OLD process instead of starting this one, the same
     * class of bug fixed for gpab itself in integration.c. See CLAUDE.md's
     * isolation guarantee — this file is deliberately modified here only,
     * ~/Projects/pab's own main.c is untouched. */
    GtkApplication *gtk_app = gtk_application_new(
        "com.gpab.bodychart",
        G_APPLICATION_DEFAULT_FLAGS);

    /* Embeds gpab's Python assessment app in this process (merged-app spike,
     * 2026-08-25) — see py_embed.h/integration.c for why. Must run before
     * anything calls into Python (the first real call is
     * integration_create_tui_window, from the launch dialog), but doesn't
     * need to happen before gtk_application_new above — Python and GTK's
     * own init are independent of each other's ordering. */
    py_embed_init(&state);

    g_signal_connect(gtk_app, "activate", G_CALLBACK(on_activate), &state);

    GSimpleAction *quit_action = g_simple_action_new("quit", NULL);
    g_signal_connect(quit_action, "activate", G_CALLBACK(on_quit_action), &state);
    g_action_map_add_action(G_ACTION_MAP(gtk_app), G_ACTION(quit_action));
    g_object_unref(quit_action);

    int status = g_application_run(G_APPLICATION(gtk_app), argc, argv);

    py_embed_shutdown();
    stroke_list_free(state.strokes);
    g_object_unref(gtk_app);
    return status;
}
