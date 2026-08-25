#include "window.h"
#include "canvas.h"
#include "input.h"
#include "overlays.h"
#include "stroke.h"
#include "session.h"
#include "persistence.h"
#include "report.h"
#include "integration.h"
#include <string.h>
#include <stdio.h>
#include <time.h>

/* ── Forward decls ──────────────────────────────────────────────────────── */
static void update_toolbar_state(AppState *app);

/* ── Key controller ─────────────────────────────────────────────────────── */
static gboolean on_key_pressed(GtkEventControllerKey *ctrl,
                                guint keyval, guint keycode,
                                GdkModifierType mods, gpointer data)
{
    (void)ctrl; (void)keycode;
    AppState *app = (AppState *)data;

    if ((mods & GDK_CONTROL_MASK) && (keyval == GDK_KEY_q || keyval == GDK_KEY_Q ||
                                       keyval == GDK_KEY_c || keyval == GDK_KEY_C)) {
        /* gtk_window_close() (not gtk_window_destroy()) — routes through the
         * "close-request" signal on_main_window_close is connected to, so
         * the autosave/PDF-export chain still runs. See that handler's
         * docstring for why this distinction matters. */
        gtk_window_close(GTK_WINDOW(app->window));
        return TRUE;
    }

    /* Ctrl+A — raise gpab's window (stale binding from the VTE-embedded-TUI
     * era, "focus the assessment TUI terminal"; integration_focus_tui now
     * does the real 2026-08-25 equivalent — see that function). Left bound
     * as a second way in, alongside the new dedicated key below. */
    if ((mods & GDK_CONTROL_MASK) && (keyval == GDK_KEY_a || keyval == GDK_KEY_A)) {
        integration_focus_tui(app);
        return TRUE;
    }

    /* Ctrl+B — the dedicated "switch to gpab" key (2026-08-25). Two earlier
     * attempts both got silently intercepted before reaching this handler
     * at all — first Ctrl+` (backtick, the user's original preference from
     * the old embedded-TUI toggle), then Ctrl+Tab — each reproducibly
     * triggering the user's system app/window-switcher instead (checked
     * gsettings/mutter/shell schemas thoroughly for both; no explicit
     * binding for either found anywhere, so whatever's catching them is
     * lower-level than anything inspectable there). Ctrl+B is a plain
     * letter with no switcher-like semantics, confirmed free in both apps'
     * own bindings. See integration_focus_tui and gpab's own
     * app.py::_switch_to_bodychart for the matching other-direction key. */
    if ((mods & GDK_CONTROL_MASK) && (keyval == GDK_KEY_b || keyval == GDK_KEY_B)) {
        integration_focus_tui(app);
        return TRUE;
    }

    /* F11 — toggle fullscreen */
    if (keyval == GDK_KEY_F11) {
        if (gtk_window_is_fullscreen(GTK_WINDOW(app->window)))
            gtk_window_unfullscreen(GTK_WINDOW(app->window));
        else
            gtk_window_fullscreen(GTK_WINDOW(app->window));
        return TRUE;
    }

    return input_key_pressed(app, keyval, mods);
}

/* ── Symptom buttons ────────────────────────────────────────────────────── */
static void on_symptom_clicked(GtkButton *btn, gpointer data)
{
    AppState *app = ((gpointer*)data)[0];
    SymptomType st = (SymptomType)(gintptr)((gpointer*)data)[1];
    (void)btn;
    app->symptom = st;
    app->tool    = TOOL_DRAW;
    update_toolbar_state(app);
    persistence_write_session_current(app);
}

/* ── Layout / view switching ────────────────────────────────────────────── */
static void on_layout_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    gpointer *pair  = data;
    AppState  *app  = pair[0];
    LayoutMode mode = (LayoutMode)(gintptr)pair[1];
    canvas_set_layout(app, mode);
    update_toolbar_state(app);
    persistence_write_session_current(app);
}

/* ── Overlay controls ───────────────────────────────────────────────────── */
static void on_overlay_cat_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    gpointer *pair = data;
    AppState *app  = pair[0];
    OverlayCategory cat = (OverlayCategory)(gintptr)pair[1];
    if (app->overlay_category == cat && app->overlay_visible) {
        app->overlay_visible = FALSE;
    } else {
        app->overlay_category = cat;
        app->overlay_index    = 0;
        app->overlay_visible  = TRUE;
    }
    canvas_invalidate(app);
    update_toolbar_state(app);
    persistence_write_session_current(app);
}

static void on_overlay_prev(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    int n = overlay_count(app->overlay_category);
    if (n > 0) {
        app->overlay_index = (app->overlay_index - 1 + n) % n;
        app->overlay_visible = TRUE;
        canvas_invalidate(app);
        update_toolbar_state(app);
        persistence_write_session_current(app);
    }
}

static void on_overlay_next(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    int n = overlay_count(app->overlay_category);
    if (n > 0) {
        app->overlay_index = (app->overlay_index + 1) % n;
        app->overlay_visible = TRUE;
        canvas_invalidate(app);
        update_toolbar_state(app);
        persistence_write_session_current(app);
    }
}

static void on_overlay_alpha(GtkRange *range, gpointer data)
{
    AppState *app = data;
    app->overlay_alpha = (float)gtk_range_get_value(range);
    canvas_invalidate(app);
}

/* ── Note tool button ───────────────────────────────────────────────────── */
static void on_note_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    app->tool = (app->tool == TOOL_NOTE) ? TOOL_DRAW : TOOL_NOTE;
    update_toolbar_state(app);
    persistence_write_session_current(app);
}

/* ── Arrow tool button ──────────────────────────────────────────────────── */
static void on_arrow_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    app->tool = (app->tool == TOOL_ARROW) ? TOOL_DRAW : TOOL_ARROW;
    update_toolbar_state(app);
    persistence_write_session_current(app);
}

/* ── Tool buttons ───────────────────────────────────────────────────────── */
static void on_erase_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    app->tool = (app->tool == TOOL_ERASE) ? TOOL_DRAW : TOOL_ERASE;
    update_toolbar_state(app);
    persistence_write_session_current(app);
}
/* ── Link matrix popup ───────────────────────────────────────────────────── */

static GtkWidget *make_btn(const char *label, int min_w, int min_h);  /* fwd */

typedef struct _LinkPopupData LinkPopupData;
typedef struct {
    LinkPopupData *pd;
    int            from, to;
} LinkCellData;

struct _LinkPopupData {
    AppState     *app;
    GtkWidget    *window;
    GtkWidget    *cell_btns[MAX_NOTES][MAX_NOTES];
    LinkCellData  cd[MAX_NOTES][MAX_NOTES];
};

static const char *link_state_label(int state)
{
    switch (state) {
        case LINK_YES: return "-->";
        case LINK_NO:  return "-/->";
        default:       return "  ";
    }
}

static void on_link_cell(GtkButton *btn, gpointer data)
{
    (void)btn;
    LinkCellData  *c  = data;
    LinkPopupData *pd = c->pd;
    int i = c->from, j = c->to;
    pd->app->link_matrix[i][j] = (pd->app->link_matrix[i][j] + 1) % 3;
    gtk_button_set_label(GTK_BUTTON(pd->cell_btns[i][j]),
                         link_state_label(pd->app->link_matrix[i][j]));
}

static void on_link_generate(GtkButton *btn, gpointer data)
{
    (void)btn;
    LinkPopupData *pd = data;
    AppState *app = pd->app;

    app->link_rel_count = 0;
    for (int i = 0; i < app->note_count; i++) {
        for (int j = 0; j < app->note_count; j++) {
            if (i == j) continue;
            int st = app->link_matrix[i][j];
            if (st == LINK_NEITHER) continue;
            if (app->link_rel_count < MAX_NOTES * MAX_NOTES) {
                app->link_relations[app->link_rel_count].from  = i;
                app->link_relations[app->link_rel_count].to    = j;
                app->link_relations[app->link_rel_count].state = st;
                app->link_rel_count++;
            }
        }
    }

    if (app->link_rel_count > 0) {
        app->link_summary_active = TRUE;
        app->link_summary_view   = (int)VIEW_ANTERIOR;
        app->link_summary_bx     = 12.0;
        app->link_summary_by     = 378.0;
    }
    canvas_invalidate(app);
    gtk_window_destroy(GTK_WINDOW(pd->window));
}

static void on_link_cancel(GtkButton *btn, gpointer data)
{
    (void)btn;
    LinkPopupData *pd = data;
    gtk_window_destroy(GTK_WINDOW(pd->window));
}

static void on_link_popup_destroy(GtkWidget *w, gpointer d)
{
    (void)w;
    LinkPopupData *pd = d;
    pd->app->tool = TOOL_DRAW;
    if (pd->app->toolbar_update_cb) pd->app->toolbar_update_cb(pd->app);
    g_free(d);
}

static void show_link_popup(AppState *app)
{
    if (app->note_count < 1) return;

    LinkPopupData *pd = g_malloc0(sizeof(LinkPopupData));
    pd->app = app;

    pd->window = gtk_window_new();
    gtk_window_set_title(GTK_WINDOW(pd->window), "Link notes");
    gtk_window_set_transient_for(GTK_WINDOW(pd->window),
                                 GTK_WINDOW(app->window));
    gtk_window_set_modal(GTK_WINDOW(pd->window), TRUE);
    gtk_window_set_resizable(GTK_WINDOW(pd->window), FALSE);
    g_signal_connect(pd->window, "destroy",
                     G_CALLBACK(on_link_popup_destroy), pd);

    int n = app->note_count;

    /* Outer layout */
    GtkWidget *outer = gtk_box_new(GTK_ORIENTATION_VERTICAL, 10);
    gtk_widget_set_margin_top(outer, 14);
    gtk_widget_set_margin_bottom(outer, 14);
    gtk_widget_set_margin_start(outer, 14);
    gtk_widget_set_margin_end(outer, 14);

    GtkWidget *title = gtk_label_new("Tap cells to cycle:  blank → --> → -/-> → blank");
    gtk_widget_set_name(title, "wiz-title");
    gtk_box_append(GTK_BOX(outer), title);

    /* Matrix grid */
    GtkWidget *grid = gtk_grid_new();
    gtk_grid_set_row_spacing(GTK_GRID(grid), 3);
    gtk_grid_set_column_spacing(GTK_GRID(grid), 3);

    /* Column headers */
    for (int j = 0; j < n; j++) {
        char lbl[16]; snprintf(lbl, sizeof(lbl), "→ %d", j+1);
        GtkWidget *h = gtk_label_new(lbl);
        gtk_widget_set_size_request(h, 52, 28);
        gtk_label_set_xalign(GTK_LABEL(h), 0.5);
        gtk_grid_attach(GTK_GRID(grid), h, j+1, 0, 1, 1);
    }

    /* Rows */
    for (int i = 0; i < n; i++) {
        char row_lbl[16]; snprintf(row_lbl, sizeof(row_lbl), "%d", i+1);
        GtkWidget *rl = gtk_label_new(row_lbl);
        gtk_widget_set_size_request(rl, 28, 44);
        gtk_label_set_xalign(GTK_LABEL(rl), 0.5);
        gtk_grid_attach(GTK_GRID(grid), rl, 0, i+1, 1, 1);

        for (int j = 0; j < n; j++) {
            if (i == j) {
                GtkWidget *dash = gtk_label_new("—");
                gtk_widget_set_size_request(dash, 52, 44);
                gtk_label_set_xalign(GTK_LABEL(dash), 0.5);
                gtk_grid_attach(GTK_GRID(grid), dash, j+1, i+1, 1, 1);
            } else {
                pd->cd[i][j].pd   = pd;
                pd->cd[i][j].from = i;
                pd->cd[i][j].to   = j;
                GtkWidget *btn = gtk_button_new_with_label(
                    link_state_label(app->link_matrix[i][j]));
                gtk_widget_set_name(btn, "wiz-num");
                gtk_widget_set_size_request(btn, 52, 44);
                g_signal_connect(btn, "clicked",
                                 G_CALLBACK(on_link_cell), &pd->cd[i][j]);
                pd->cell_btns[i][j] = btn;
                gtk_grid_attach(GTK_GRID(grid), btn, j+1, i+1, 1, 1);
            }
        }
    }
    gtk_box_append(GTK_BOX(outer), grid);

    /* Action row */
    GtkWidget *actions = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    gtk_widget_set_halign(actions, GTK_ALIGN_END);
    GtkWidget *cancel_btn = make_btn("Cancel", 100, 44);
    g_signal_connect(cancel_btn, "clicked", G_CALLBACK(on_link_cancel), pd);
    GtkWidget *gen_btn = make_btn("Generate Summary", 180, 44);
    gtk_widget_set_name(gen_btn, "wiz-btn");
    g_signal_connect(gen_btn, "clicked", G_CALLBACK(on_link_generate), pd);
    gtk_box_append(GTK_BOX(actions), cancel_btn);
    gtk_box_append(GTK_BOX(actions), gen_btn);
    gtk_box_append(GTK_BOX(outer), actions);

    gtk_window_set_child(GTK_WINDOW(pd->window), outer);
    gtk_window_present(GTK_WINDOW(pd->window));
}

static void on_cycle_right_slot(GtkButton *btn, gpointer data)
{
    (void)btn;
    gpointer *pair = data;
    AppState  *app  = pair[0];
    int        slot = (int)(gintptr)pair[1];
    canvas_cycle_right_slot(app, slot);
    update_toolbar_state(app);
}

static void on_link_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    app->tool = TOOL_LINK;
    update_toolbar_state(app);
    show_link_popup(app);
}
static void on_linemode_clicked(GtkButton *b, gpointer data)
{
    (void)b;
    AppState *app = data;
    app->pen_wide_mode = !app->pen_wide_mode;
    update_toolbar_state(app);
}
static void on_undo_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    canvas_undo(app);
}
static void on_clear_confirm_response(GObject *source, GAsyncResult *result,
                                       gpointer data)
{
    AppState *app = data;
    GtkAlertDialog *dlg = GTK_ALERT_DIALOG(source);
    int btn = gtk_alert_dialog_choose_finish(dlg, result, NULL);
    g_object_unref(dlg);
    if (btn != 0) return;   /* 0 = "Clear all", 1 = "Cancel" */
    persistence_monitor_stop(app);
    canvas_clear(app);
    persistence_monitor_start(app);
}

static void request_clear(AppState *app)
{
    static const char *buttons[] = { "Clear all", "Cancel", NULL };
    GtkAlertDialog *dlg = gtk_alert_dialog_new("Clear the chart?");
    gtk_alert_dialog_set_detail(dlg, "All strokes and annotations will be removed. This cannot be undone.");
    gtk_alert_dialog_set_buttons(dlg, buttons);
    gtk_alert_dialog_set_default_button(dlg, 1);
    gtk_alert_dialog_set_cancel_button(dlg, 1);
    gtk_alert_dialog_choose(dlg, GTK_WINDOW(app->window), NULL,
                             on_clear_confirm_response, app);
}

static void on_clear_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    request_clear(data);
}

/* ── Toolbar state references ───────────────────────────────────────────── */
static GtkWidget *g_symptom_btns[SYMPTOM_COUNT];
static GtkWidget *g_note_btn;
static GtkWidget *g_arrow_btn;
static GtkWidget *g_erase_btn;
static GtkWidget *g_link_btn;
static GtkWidget *g_linemode_btn;
static GtkWidget *g_overlay_label;
static GtkWidget *g_overlay_cat_btns[3];
static GtkWidget *g_overlay_nav_box;
static GtkWidget *g_layout_btns[LAYOUT_COUNT];
static GtkWidget *g_right_slot_btns[2];
static GtkWidget *g_mode_btns[APP_MODE_COUNT];
static GtkWidget *g_save_indicator;      /* ✓/✗ label next to save button in drag handle */
static AppState  *g_app_ref;

/* ── Obj mode sidebar widget refs ────────────────────────────────────────── */
static GtkWidget *g_obj_zone_btns[OBJ_ZONE_COUNT];
static GtkWidget *g_obj_ppt_btn;
static GtkWidget *g_obj_mono_btn;
static GtkWidget *g_obj_ts_btn;
static GtkWidget *g_obj_tpd_btn;
static GtkWidget *g_obj_erase_btn;
static GtkWidget *g_sidebar_content_stack;

static void update_toolbar_state(AppState *app)
{
    if (!g_app_ref) return;

    for (int i = 0; i < SYMPTOM_COUNT; i++) {
        if (!g_symptom_btns[i]) continue;
        gboolean active = (app->symptom == (SymptomType)i &&
                           app->tool    == TOOL_DRAW);
        gtk_widget_set_name(g_symptom_btns[i],
                            active ? "symptom-btn-active" : "symptom-btn");
    }

    if (g_note_btn)
        gtk_widget_set_name(g_note_btn,
            app->tool == TOOL_NOTE ? "tool-btn-active" : "tool-btn");
    if (g_arrow_btn)
        gtk_widget_set_name(g_arrow_btn,
            app->tool == TOOL_ARROW ? "tool-btn-active" : "tool-btn");
    if (g_erase_btn)
        gtk_widget_set_name(g_erase_btn,
            app->tool == TOOL_ERASE ? "tool-btn-active" : "tool-btn");
    if (g_link_btn)
        gtk_widget_set_name(g_link_btn,
            app->tool == TOOL_LINK ? "tool-btn-active" : "tool-btn");
    if (g_linemode_btn) {
        gtk_widget_set_name(g_linemode_btn,
            app->pen_wide_mode ? "tool-btn-active" : "tool-btn");
        gtk_button_set_label(GTK_BUTTON(g_linemode_btn),
            app->pen_wide_mode ? "Bold" : "Fine");
    }

    for (int i = 0; i < 3; i++) {
        if (!g_overlay_cat_btns[i]) continue;
        OverlayCategory cat = (OverlayCategory)(i + 1);
        gboolean active = (app->overlay_category == cat && app->overlay_visible);
        gtk_widget_set_name(g_overlay_cat_btns[i],
                            active ? "overlay-btn-active" : "overlay-btn");
    }

    for (int i = 0; i < LAYOUT_COUNT; i++) {
        if (!g_layout_btns[i]) continue;
        gboolean active = (app->layout_mode == (LayoutMode)i);
        gtk_widget_set_name(g_layout_btns[i],
                            active ? "tool-btn-active" : "tool-btn");
    }

    for (int i = 0; i < APP_MODE_COUNT; i++) {
        if (!g_mode_btns[i]) continue;
        gboolean active = (app->current_mode == (AppMode)i);
        gtk_widget_set_name(g_mode_btns[i],
                            active ? "mode-btn-active" : "mode-btn");
    }

    for (int i = 0; i < 2; i++) {
        if (!g_right_slot_btns[i]) continue;
        char buf[20];
        snprintf(buf, sizeof(buf), "%s \xe2\x86\xbb",
                 canvas_view_short_name(app->right_slot_views[i]));
        gtk_button_set_label(GTK_BUTTON(g_right_slot_btns[i]), buf);
    }

    if (g_overlay_nav_box) {
        /* Nav only makes sense for somatic (multiple patterns); hide for derm */
        gboolean show_nav = app->overlay_visible &&
                            app->overlay_category == OVERLAY_SOMATIC;
        gtk_widget_set_visible(g_overlay_nav_box, show_nav);
    }

    if (g_overlay_label) {
        if (app->overlay_visible && app->overlay_category != OVERLAY_NONE) {
            if (app->overlay_category == OVERLAY_DERMATOME)
                gtk_label_set_text(GTK_LABEL(g_overlay_label), "Dermatomes");
            else if (app->overlay_category == OVERLAY_PERIPHERAL)
                gtk_label_set_text(GTK_LABEL(g_overlay_label), "Peripheral");
            else {
                const OverlayDef *ov = overlay_get(app->overlay_category,
                                                   app->overlay_index);
                if (ov) {
                    char buf[64];
                    int n = overlay_count(app->overlay_category);
                    snprintf(buf, sizeof(buf), "%s  %d/%d",
                             ov->short_label, app->overlay_index + 1, n);
                    gtk_label_set_text(GTK_LABEL(g_overlay_label), buf);
                }
            }
        } else {
            gtk_label_set_text(GTK_LABEL(g_overlay_label), "Off");
        }
    }


    /* ── Objective sidebar button states ── */
    for (int i = 0; i < OBJ_ZONE_COUNT; i++) {
        if (!g_obj_zone_btns[i]) continue;
        gboolean active = (app->current_mode == APP_MODE_OBJECTIVE &&
                           !app->obj_point_mode &&
                           app->tool != TOOL_ERASE &&
                           app->obj_zone_type == (ObjZoneType)i);
        gtk_widget_set_name(g_obj_zone_btns[i],
                            active ? "tool-btn-active" : "tool-btn");
    }
    if (g_obj_ppt_btn)
        gtk_widget_set_name(g_obj_ppt_btn,
            (app->current_mode == APP_MODE_OBJECTIVE &&
             app->obj_point_mode &&
             app->obj_point_type == OBJ_POINT_PPT)
            ? "tool-btn-active" : "tool-btn");
    if (g_obj_ts_btn)
        gtk_widget_set_name(g_obj_ts_btn,
            (app->current_mode == APP_MODE_OBJECTIVE &&
             app->obj_point_mode &&
             app->obj_point_type == OBJ_POINT_TEMPORAL_SUM)
            ? "tool-btn-active" : "tool-btn");
    if (g_obj_mono_btn)
        gtk_widget_set_name(g_obj_mono_btn,
            (app->current_mode == APP_MODE_OBJECTIVE &&
             app->obj_point_mode &&
             app->obj_point_type == OBJ_POINT_MONOFILAMENT)
            ? "tool-btn-active" : "tool-btn");
    if (g_obj_tpd_btn)
        gtk_widget_set_name(g_obj_tpd_btn,
            (app->current_mode == APP_MODE_OBJECTIVE &&
             app->obj_point_mode &&
             app->obj_point_type == OBJ_POINT_TWO_PD)
            ? "tool-btn-active" : "tool-btn");
    if (g_obj_erase_btn)
        gtk_widget_set_name(g_obj_erase_btn,
            (app->current_mode == APP_MODE_OBJECTIVE &&
             app->tool == TOOL_ERASE)
            ? "tool-btn-active" : "tool-btn");

    /* ── Sidebar content stack: switch per mode ── */
    if (g_sidebar_content_stack) {
        const char *page;
        switch (app->current_mode) {
            case APP_MODE_OBJECTIVE: page = "obj"; break;
            default:                 page = "sx";  break;
        }
        gtk_stack_set_visible_child_name(
            GTK_STACK(g_sidebar_content_stack), page);
    }
}

/* ── Auto-save ───────────────────────────────────────────────────────────── */
static gboolean reset_save_indicator(gpointer data)
{
    (void)data;
    if (g_save_indicator)
        gtk_label_set_text(GTK_LABEL(g_save_indicator), "");
    return G_SOURCE_REMOVE;
}

void window_autosave(AppState *app)
{
    if (!app->session_file[0]) return;
    gboolean ok = persistence_save(app);
    if (ok) ok = session_export_subj_png(app);
    if (ok) ok = session_export_obj_png(app);
    if (ok) ok = session_export_combined_png(app);
    if (ok) ok = session_export_subj_focus_png(app);
    if (ok) ok = session_export_obj_focus_png(app);
    if (ok) ok = session_export_combined_focus_png(app);
    persistence_write_session_current(app);
    if (g_save_indicator) {
        gtk_label_set_text(GTK_LABEL(g_save_indicator), ok ? "✓" : "✗");
        g_timeout_add_seconds(3, reset_save_indicator, NULL);
    }
}

/* ── Mode strip callback ─────────────────────────────────────────────────── */
static void on_mode_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    gpointer *pair  = data;
    AppState  *app  = pair[0];
    AppMode    mode = (AppMode)(gintptr)pair[1];
    if (app->current_mode == mode) return;

    window_autosave(app);
    app->current_mode = mode;
    persistence_write_session_current(app);

    update_toolbar_state(app);
    canvas_invalidate(app);
}

/* ── Symptom indicator strip draw function ───────────────────────────────── */
static void draw_symptom_indicator(GtkDrawingArea *da, cairo_t *cr,
                                    int w, int h, gpointer data)
{
    (void)da;
    SymptomType stype = (SymptomType)(gintptr)data;
    const SymptomDef *sd = &SYMPTOM_DEFS[stype];
    double cy = h / 2.0;

    cairo_set_source_rgba(cr, sd->r, sd->g, sd->b, 0.95);

    switch (sd->pattern) {
    case FILL_SOLID:
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_width(cr, 3.5);
        cairo_move_to(cr, 4, cy); cairo_line_to(cr, w - 4, cy);
        cairo_stroke(cr);
        break;
    case FILL_DASHED: {
        double dashes[] = { 5.0, 3.5 };
        cairo_set_dash(cr, dashes, 2, 0);
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_width(cr, 2.5);
        cairo_move_to(cr, 4, cy); cairo_line_to(cr, w - 4, cy);
        cairo_stroke(cr);
        cairo_set_dash(cr, NULL, 0, 0);
        break;
    }
    case FILL_DOTS_SPACED:
        for (int x = 6; x < w - 3; x += 9) {
            cairo_new_sub_path(cr);
            cairo_arc(cr, x, cy, 2.5, 0, 2 * G_PI);
        }
        cairo_fill(cr);
        break;
    case FILL_H_STROKES:
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_width(cr, 1.5);
        for (int x = 6; x < w - 3; x += 9) {
            cairo_move_to(cr, x - 3, cy);
            cairo_line_to(cr, x + 3, cy);
        }
        cairo_stroke(cr);
        break;
    case FILL_XMARKS:
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_width(cr, 1.5);
        for (int x = 7; x < w - 3; x += 11) {
            cairo_move_to(cr, x - 3, cy - 3); cairo_line_to(cr, x + 3, cy + 3);
            cairo_move_to(cr, x + 3, cy - 3); cairo_line_to(cr, x - 3, cy + 3);
        }
        cairo_stroke(cr);
        break;
    case FILL_TICK:
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND);
        cairo_set_line_width(cr, 1.5);
        cairo_move_to(cr, w / 2 - 5, cy);
        cairo_line_to(cr, w / 2 - 1, cy + 3);
        cairo_line_to(cr, w / 2 + 6, cy - 3);
        cairo_stroke(cr);
        break;
    case FILL_PENCIL:
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_width(cr, 1.5);
        cairo_move_to(cr, 4, cy); cairo_line_to(cr, w - 4, cy);
        cairo_stroke(cr);
        break;
    }
}

/* ── Symptom button factory (label + pattern/colour strip) ───────────────── */
static GtkWidget *make_symptom_btn(const char *label, SymptomType stype)
{
    GtkWidget *btn  = gtk_button_new();
    gtk_widget_set_size_request(btn, -1, 44);

    GtkWidget *vbox = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_set_margin_top(vbox, 3);
    gtk_widget_set_margin_bottom(vbox, 3);

    GtkWidget *lbl = gtk_label_new(label);
    gtk_widget_set_vexpand(lbl, TRUE);
    gtk_box_append(GTK_BOX(vbox), lbl);

    GtkWidget *strip = gtk_drawing_area_new();
    gtk_widget_set_size_request(strip, -1, 9);
    gtk_widget_set_can_target(strip, FALSE);   /* don't absorb button clicks */
    gtk_drawing_area_set_draw_func(GTK_DRAWING_AREA(strip),
                                    draw_symptom_indicator,
                                    (gpointer)(gintptr)stype, NULL);
    gtk_box_append(GTK_BOX(vbox), strip);

    gtk_button_set_child(GTK_BUTTON(btn), vbox);
    return btn;
}

/* ── Shared button factory ───────────────────────────────────────────────── */
static GtkWidget *make_btn(const char *label, int min_w, int min_h)
{
    GtkWidget *btn = gtk_button_new_with_label(label);
    gtk_widget_set_size_request(btn, min_w, min_h);
    gtk_widget_set_name(btn, "tool-btn");
    return btn;
}

/* ── 2-column homogeneous grid helper ────────────────────────────────────── */
static GtkWidget *make_grid2col(void)
{
    GtkWidget *g = gtk_grid_new();
    gtk_grid_set_row_spacing(GTK_GRID(g), 3);
    gtk_grid_set_column_spacing(GTK_GRID(g), 3);
    gtk_grid_set_column_homogeneous(GTK_GRID(g), TRUE);
    return g;
}

/* ── CSS ─────────────────────────────────────────────────────────────────── */
static void apply_css(void)
{
    GtkCssProvider *css = gtk_css_provider_new();
    gtk_css_provider_load_from_string(css,
        "window { background: #2b2b2b; }"
        "#toolbar { background: #1e1e1e; padding: 2px; }"
        "button { "
        "  min-height: 34px; min-width: 28px; "
        "  border-radius: 6px; padding: 1px 3px; "
        "  font-size: 11px; "
        "}"
        "#symptom-btn { background: #3a3a3a; color: #ccc; border: 1px solid #555; }"
        "#symptom-btn-active { background: #555; color: #fff; border: 2px solid #aaa; }"
        "#tool-btn { background: #333; color: #bbb; border: 1px solid #555; }"
        "#tool-btn-active { background: #666; color: #fff; border: 2px solid #aaa; }"
        "#overlay-btn { background: #2a3040; color: #8ab; border: 1px solid #446; }"
        "#overlay-btn-active { background: #3a5080; color: #cef; border: 2px solid #68c; }"
        "#section-label { color: #888; font-size: 9px; margin-top: 4px; margin-bottom: 1px; }"
        "#overlay-name { color: #8ab; font-size: 10px; }"
        "separator { background: #444; min-width: 1px; margin: 1px 2px; }"
        "#col-header { background: #f0f0f0; border-bottom: 1px solid #ccc; min-height: 28px; }"
        "#col-header label { font-size: 11px; font-weight: bold; color: #333; }"
        "#zoom-btn { min-height: 22px; min-width: 40px; padding: 0 6px; font-size: 10px;"
        "  background: #e0e0e0; color: #444; border: 1px solid #bbb; border-radius: 4px; }"
        "#zoom-btn:hover { background: #d0d0d0; }"

        /* ── Sidebar + drag handle ── */
        "#sidebar { background: #1e1e1e; min-width: 150px; max-width: 150px; }"
        ".drag-handle { background: #444; border-radius: 3px; margin: 2px; }"
        "#drag-handle-btn { background: #333; color: #999; border: 1px solid #555;"
        "  font-size: 14px; padding: 0; border-radius: 2px; }"
        "#drag-handle-btn:hover { background: #444; color: #ccc; }"
        "#save-btn { background: #1a2a1a; color: #6a9; border: 1px solid #2a4a2a;"
        "  border-radius: 2px; padding: 0 4px; min-height: 20px; }"
        "#save-btn:hover { background: #243a24; color: #8bc; }"
        "#save-indicator { color: #6f9; font-size: 11px; font-weight: bold;"
        "  padding: 0 2px; min-width: 10px; }"

        /* ── Mode strip ── */
        "#mode-strip { background: #111118; padding: 3px; }"
        "#mode-btn { background: #222230; color: #667; font-size: 12px; font-weight: bold;"
        "  border-radius: 4px; min-height: 34px; min-width: 0; border: 1px solid #333348; }"
        "#mode-btn:hover { background: #2a2a40; color: #99a; }"
        "#mode-btn-active { background: #1a3a5a; color: #8cf; font-size: 12px; font-weight: bold;"
        "  border-radius: 4px; min-height: 34px; min-width: 0; border: 2px solid #3a7aaa; }"

        /* ── Launch dialog ── */
        "#launch-win { background: #1a1a2a; }"
        "#launch-title { font-size: 18px; font-weight: bold; color: #cdf;"
        "  margin-bottom: 6px; }"
        "#launch-label { font-size: 11px; color: #888; margin-top: 6px; }"
        "#launch-entry { font-size: 14px; min-height: 40px; background: #252535;"
        "  color: #dde; border: 1px solid #445; border-radius: 4px; padding: 0 8px; }"
        "#launch-row { background: #252535; border-radius: 4px; padding: 6px 10px; "
        "  margin: 1px 0; }"
        "#launch-row:selected, #launch-row:hover { background: #2a3a5a; }"
        "#launch-row-id { font-size: 13px; font-weight: bold; color: #8cf; }"
        "#launch-row-label { font-size: 12px; color: #bbc; }"
        "#launch-row-date { font-size: 11px; color: #667; }"
        "#launch-btn { font-size: 14px; min-height: 48px;"
        "  background: #1a3a5a; color: #cdf; border: 1px solid #3a6a9a;"
        "  border-radius: 6px; }"
        "#launch-btn:hover { background: #2a4a6a; color: #fff; }"
        "#launch-btn-dim { font-size: 14px; min-height: 48px;"
        "  background: #252535; color: #556; border: 1px solid #334;"
        "  border-radius: 6px; }"

        /* ── Note wizard ── */
        "#wiz-title { font-size: 15px; font-weight: bold; color: #ddd;"
        "  margin-bottom: 6px; }"
        "#wiz-btn { font-size: 14px; min-height: 56px; min-width: 180px;"
        "  background: #2a4a70; color: #dde; border: 1px solid #4a6a90; }"
        "#wiz-btn:hover { background: #3a5a80; color: #fff; }"
        "#wiz-num { font-size: 14px; font-weight: bold; min-height: 52px;"
        "  min-width: 40px; background: #1e3050; color: #ccd;"
        "  border: 1px solid #3a5070; }"
        "#wiz-num:hover { background: #2a4060; color: #fff; }"
        "#wiz-qual-btn { font-size: 12px; min-height: 44px; min-width: 76px;"
        "  background: #2a4a70; color: #dde; border: 1px solid #4a6a90; }"
        "#wiz-qual-btn:hover { background: #3a5a80; color: #fff; }"
        "#wiz-qual-btn-active { font-size: 12px; min-height: 44px; min-width: 76px;"
        "  background: #1a7a40; color: #fff; border: 2px solid #3aaa60; }"
        "#wiz-qual-next { font-size: 13px; min-height: 44px; margin-top: 8px;"
        "  background: #2a5a30; color: #beb; border: 1px solid #4a8a50; }"
        "#wiz-qual-next:hover { background: #3a7a40; color: #fff; }"
        "#wiz-num-active { font-size: 14px; font-weight: bold; min-height: 52px;"
        "  min-width: 40px; background: #1a7a40; color: #fff;"
        "  border: 2px solid #3aaa60; }"
        "#wiz-window { background: #1a1a2e; }"

        /* ── Report view ── */
        "#report-root { background: #0a0a14; }"
        "#report-toolbar { background: #0a0a14; border-bottom: 1px solid #1a1a30; }"
        "#rpt-btn { background: #151528; color: #7878a8; border: 1px solid #252545;"
        "  font-size: 11px; min-height: 28px; border-radius: 4px; padding: 0 8px; }"
        "#rpt-btn:hover { background: #1e1e38; color: #aac; }"
        "#report-status { color: #445; font-size: 10px; }"
        "#report-tv { font-size: 14px; caret-color: #ffcc44; }"
        "#report-tv text { background: #0d0d1a; color: #c0c0d8; }"
        "#report-tv selection { background: #1a3a5a; }"

        /* ── Subjective wizard ── */
        "#subj-btn-row { background: transparent; }"
        "#subj-btn { font-size: 13px; min-height: 40px; min-width: 84px;"
        "  background: #1a2444; color: #88aadd; border: 1px solid #2e4070;"
        "  border-radius: 5px; padding: 0 10px; margin: 2px; }"
        "#subj-btn:hover { background: #243060; color: #aaccff; }"
        "#subj-opt-btn { font-size: 13px; min-height: 36px; min-width: 80px;"
        "  background: #162040; color: #7aabcc; border: 1px solid #264060;"
        "  border-radius: 4px; padding: 0 8px; margin: 3px; }"
        "#subj-opt-btn:hover { background: #1e3050; color: #b0d8f0; }"
        "#subj-opt-sub { font-size: 12px; min-height: 32px; min-width: 70px;"
        "  background: #0e1830; color: #5a88aa; border: 1px solid #1c2e48;"
        "  border-radius: 4px; padding: 0 6px; margin: 3px; }"
        "#subj-opt-sub:hover { background: #162440; color: #90bbdd; }"
        "#subj-hint { font-size: 12px; color: #6a7898; font-style: italic; }"
        "#subj-tv text { background: #0d0d20; color: #d0d0e8; }"
        "#subj-tv { font-size: 14px; caret-color: #aaccff; }"
    );
    gtk_style_context_add_provider_for_display(
        gdk_display_get_default(),
        GTK_STYLE_PROVIDER(css),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
}

/* ── Timed autosave (JSON only — no PNG exports) ─────────────────────────── */
static gboolean on_autosave_timer(gpointer data)
{
    (void)data;
    if (g_app_ref && g_app_ref->session_file[0])
        persistence_save(g_app_ref);
    return G_SOURCE_CONTINUE;
}

/* ── Save / export callbacks ─────────────────────────────────────────────── */
static void do_export(const char *ext)
{
    if (!g_app_ref) return;
    char path[1024];
    session_auto_path(path, sizeof(path), ext);

    if      (strcmp(ext, "svg") == 0) session_save(g_app_ref, path);
    else if (strcmp(ext, "png") == 0) session_export_png(g_app_ref, path);
    else if (strcmp(ext, "pdf") == 0) session_export_pdf(g_app_ref, path);
}

static void on_save_session(GtkButton *b, gpointer d)
{
    (void)b; (void)d;
    if (g_app_ref) window_autosave(g_app_ref);
}

/* Public wrapper used by keyboard shortcuts in input.c */
void window_do_export(const char *ext) { do_export(ext); }

/* ── Note wizard ─────────────────────────────────────────────────────────── */

typedef struct _WizardData WizardData;

typedef struct { WizardData *wd; int value; int step; } WBtnPair;
typedef struct { WizardData *wd; int value; } WizQualBtn;
typedef struct { WizardData *wd; int value; } WizIntBtn;

struct _WizardData {
    AppState   *app;
    int         view;
    double      bx, by;
    GtkWidget  *window;
    GtkWidget  *stack;
    int         temporal;
    int         depth;
    /* quality page */
    int         qualities[3];
    int         quality_count;
    GtkWidget  *qual_btns[NOTE_QUALITY_COUNT];
    GtkWidget  *qual_next_btn;
    /* intensity page: low_int=-1 means nothing selected yet */
    int         low_int;
    int         high_int;
    GtkWidget  *int_btns[11];
    /* button callback data */
    WBtnPair    c_q1[2];
    WBtnPair    c_q2[2];
    WizQualBtn  q3_btns[NOTE_QUALITY_COUNT];
    WizIntBtn   n_q4[11];
    /* voice descriptor */
    gboolean    whis_available;
    gboolean    voice_busy;
    guint       voice_poll_id;
    char        voice_text[256];
    GtkWidget  *mic_btn;
    GtkWidget  *voice_label;
    GtkWidget  *voice_reset_btn;
};

static gboolean g_wizard_open = FALSE;
static gboolean g_ppt_dialog_open = FALSE;

static void wizard_commit(WizardData *wd);   /* forward decl */

static void on_wiz_answer(GtkButton *b, gpointer data)
{
    (void)b;
    WBtnPair   *p  = data;
    WizardData *wd = p->wd;
    switch (p->step) {
        case 0: wd->temporal = p->value;
                gtk_stack_set_visible_child_name(GTK_STACK(wd->stack), "q2"); break;
        case 1: wd->depth    = p->value;
                gtk_stack_set_visible_child_name(GTK_STACK(wd->stack), "q3"); break;
    }
}

static void on_wiz_qual_toggle(GtkButton *b, gpointer data)
{
    (void)b;
    WizQualBtn *qb = data;
    WizardData *wd = qb->wd;
    int v = qb->value;

    /* Check if already selected — deselect it */
    for (int i = 0; i < wd->quality_count; i++) {
        if (wd->qualities[i] == v) {
            /* Remove by shifting */
            for (int j = i; j < wd->quality_count - 1; j++)
                wd->qualities[j] = wd->qualities[j + 1];
            wd->quality_count--;
            gtk_widget_set_name(wd->qual_btns[v], "wiz-qual-btn");
            return;
        }
    }
    /* Not selected — add if room */
    if (wd->quality_count < 3) {
        wd->qualities[wd->quality_count++] = v;
        gtk_widget_set_name(wd->qual_btns[v], "wiz-qual-btn-active");
        /* Auto-advance when 3 selected */
        if (wd->quality_count == 3)
            gtk_stack_set_visible_child_name(GTK_STACK(wd->stack), "q4");
    }
}

static void on_wiz_qual_next(GtkButton *b, gpointer data)
{
    (void)b;
    WizardData *wd = data;
    if (wd->quality_count >= 1 || wd->voice_text[0])
        gtk_stack_set_visible_child_name(GTK_STACK(wd->stack), "q4");
}

static void on_wiz_int_click(GtkButton *b, gpointer data)
{
    (void)b;
    WizIntBtn  *ib = data;
    WizardData *wd = ib->wd;
    int v = ib->value;

    if (wd->low_int < 0) {
        /* First click — record low, highlight it */
        wd->low_int = v;
        gtk_widget_set_name(wd->int_btns[v], "wiz-num-active");
    } else {
        /* Second click — record high, ensure order, commit */
        wd->high_int = v;
        if (wd->high_int < wd->low_int) {
            int tmp     = wd->low_int;
            wd->low_int = wd->high_int;
            wd->high_int = tmp;
        }
        wizard_commit(wd);
    }
}

static void on_wizard_destroy(GtkWidget *w, gpointer d)
{
    (void)w;
    WizardData *wd = d;
    if (wd->voice_poll_id != 0) {
        g_source_remove(wd->voice_poll_id);
        wd->voice_poll_id = 0;
    }
    g_wizard_open = FALSE;
    g_free(d);
}

static const char *QUALITY_SHORT[NOTE_QUALITY_COUNT] = {
    "Throb", "Press", "Ache",  "Stab",
    "Tight", "Burn",  "Freez", "Elec",
    "Shot",  "P+N",   "Numb",  "Itch"
};

static void wizard_commit(WizardData *wd)
{
    AppState *app = wd->app;
    if (app->note_count < MAX_NOTES) {
        NoteAnnotation *na = &app->notes[app->note_count];
        na->view          = wd->view;
        na->bx            = wd->bx;
        na->by            = wd->by;
        na->stable_id     = app->next_note_id++;
        na->number        = app->note_count + 1;
        na->temporal      = wd->temporal;
        na->depth         = wd->depth;
        na->quality_count = wd->quality_count;
        for (int i = 0; i < wd->quality_count; i++)
            na->qualities[i] = wd->qualities[i];
        na->low_intensity  = wd->low_int  >= 0 ? wd->low_int  : 0;
        na->high_intensity = wd->high_int >= 0 ? wd->high_int : 0;
        na->label.placed   = 0;   /* default offset; user can drag later */

        /* Copy voice transcript (empty string if voice was not used) */
        g_strlcpy(na->voice_note, wd->voice_text, sizeof(na->voice_note));

        /* Build display text line 2 — prefer voice transcript over short codes */
        char line2[128] = {0};
        if (na->voice_note[0]) {
            snprintf(line2, sizeof(line2), "%.44s%s",
                     na->voice_note,
                     strlen(na->voice_note) > 44 ? "…" : "");
        } else {
            char qual_buf[64] = {0};
            for (int i = 0; i < na->quality_count; i++) {
                if (i > 0) strncat(qual_buf, "+",
                                   sizeof(qual_buf) - strlen(qual_buf) - 1);
                strncat(qual_buf, QUALITY_SHORT[na->qualities[i]],
                        sizeof(qual_buf) - strlen(qual_buf) - 1);
            }
            if (na->quality_count == 0)
                strncat(qual_buf, "?", sizeof(qual_buf) - strlen(qual_buf) - 1);
            g_strlcpy(line2, qual_buf, sizeof(line2));
        }
        /* Line 1: number + temporal + depth + intensity; line 2: descriptor */
        snprintf(na->text, sizeof(na->text), "(%d)%s %s %d-%d/10\n%s",
                 na->number,
                 na->temporal == 0 ? "Con" : "Int",
                 na->depth    == 0 ? "Sup" : "Dep",
                 na->low_intensity, na->high_intensity,
                 line2);
        app->note_count++;
    }
    canvas_invalidate(app);
    gtk_window_destroy(GTK_WINDOW(wd->window));  /* triggers on_wizard_destroy → g_free */
}

static GtkWidget *wiz_choice_row(WBtnPair pairs[2],
                                  const char *l0, const char *l1)
{
    GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 16);
    gtk_widget_set_halign(row, GTK_ALIGN_CENTER);
    const char *lbls[2] = { l0, l1 };
    for (int i = 0; i < 2; i++) {
        GtkWidget *btn = gtk_button_new_with_label(lbls[i]);
        gtk_widget_set_name(btn, "wiz-btn");
        g_signal_connect(btn, "clicked", G_CALLBACK(on_wiz_answer), &pairs[i]);
        gtk_box_append(GTK_BOX(row), btn);
    }
    return row;
}

/* Returns a vertical box containing the quality grid + Next button.
   Stores button widget pointers in wd->qual_btns[]. */
/* ── Voice helpers ─────────────────────────────────────────────────────────── */

static void whis_run_wiz(const char *subcmd)
{
    GError *err  = NULL;
    gchar  *argv[] = { "whis", (gchar *)subcmd, NULL };
    g_spawn_async(NULL, argv, NULL,
                  G_SPAWN_SEARCH_PATH | G_SPAWN_STDOUT_TO_DEV_NULL
                  | G_SPAWN_STDERR_TO_DEV_NULL,
                  NULL, NULL, NULL, &err);
    if (err) g_error_free(err);
}

/* Synchronous status probe — a local IPC round-trip, single-digit ms, safe
 * to call on the UI thread right before starting a recording. Detects a
 * daemon left in "recording" state by a prior session that never toggled
 * it off (e.g. app closed mid-recording), which would otherwise make the
 * next toggle stop that stale recording instead of starting a fresh one. */
static gboolean whis_stuck_recording(void)
{
    gchar *out = NULL;
    gchar *argv[] = { "whis", "status", NULL };
    g_spawn_sync(NULL, argv, NULL,
                 G_SPAWN_SEARCH_PATH | G_SPAWN_STDERR_TO_DEV_NULL,
                 NULL, NULL, &out, NULL, NULL, NULL);
    gboolean stuck = out && (strstr(out, "Recording") || strstr(out, "recording"));
    g_free(out);
    return stuck;
}

/* Force a clean daemon state: stop (idempotent even if already stopped),
 * then start fresh. Used for both automatic stale-state recovery and the
 * manual reset button. */
static void whis_reset_daemon(void)
{
    gchar *stop_argv[] = { "whis", "stop", NULL };
    g_spawn_sync(NULL, stop_argv, NULL,
                 G_SPAWN_SEARCH_PATH | G_SPAWN_STDERR_TO_DEV_NULL,
                 NULL, NULL, NULL, NULL, NULL, NULL);
    whis_run_wiz("start");
}

typedef struct { WizardData *wd; int attempts; } VoiceCtx;

static gboolean voice_poll_cb(gpointer data)
{
    VoiceCtx   *ctx = data;
    WizardData *wd  = ctx->wd;

    gchar *out = NULL;
    gchar *sargv[] = { "whis", "status", NULL };
    g_spawn_sync(NULL, sargv, NULL,
                 G_SPAWN_SEARCH_PATH | G_SPAWN_STDERR_TO_DEV_NULL,
                 NULL, NULL, &out, NULL, NULL, NULL);

    gboolean busy = out && (strstr(out, "Recording")   || strstr(out, "Transcribing") ||
                            strstr(out, "recording")   || strstr(out, "transcribing"));
    g_free(out);
    ctx->attempts++;

    if (busy && ctx->attempts < 30)
        return G_SOURCE_CONTINUE;

    gchar *clip = NULL;
    gchar *wlargv[] = { "wl-paste", "--no-newline", NULL };
    g_spawn_sync(NULL, wlargv, NULL,
                 G_SPAWN_SEARCH_PATH | G_SPAWN_STDERR_TO_DEV_NULL,
                 NULL, NULL, &clip, NULL, NULL, NULL);

    if (clip && clip[0]) {
        g_strlcpy(wd->voice_text, clip, sizeof(wd->voice_text));
        char preview[56];
        snprintf(preview, sizeof(preview), "%.52s%s",
                 clip, strlen(clip) > 52 ? "…" : "");
        gtk_label_set_text(GTK_LABEL(wd->voice_label), preview);
        /* Jump straight to NRS intensity page */
        gtk_stack_set_visible_child_name(GTK_STACK(wd->stack), "q4");
    } else {
        gtk_label_set_text(GTK_LABEL(wd->voice_label),
                           "No result — tap descriptors below");
    }
    g_free(clip);

    gtk_button_set_label(GTK_BUTTON(wd->mic_btn), "🎤  Speak");
    wd->voice_busy    = FALSE;
    wd->voice_poll_id = 0;
    g_free(ctx);
    return G_SOURCE_REMOVE;
}

/* Manual fallback for the automatic recovery above — lets you force a clean
 * daemon state directly if a recording still won't start. */
static void on_voice_reset_clicked(GtkButton *b, gpointer data)
{
    (void)b;
    WizardData *wd = data;
    if (wd->voice_busy || wd->voice_poll_id != 0) return;  /* mid-flow, don't touch */
    gtk_label_set_text(GTK_LABEL(wd->voice_label), "Resetting voice service…");
    whis_reset_daemon();
    gtk_label_set_text(GTK_LABEL(wd->voice_label), "— or tap descriptors below —");
}

static void on_voice_btn_clicked(GtkButton *b, gpointer data)
{
    (void)b;
    WizardData *wd = data;

    if (!wd->voice_busy) {
        if (wd->voice_poll_id != 0) return;  /* poll still running */
        if (whis_stuck_recording()) {
            whis_reset_daemon();
        } else {
            whis_run_wiz("start");
        }
        whis_run_wiz("toggle");
        wd->voice_busy = TRUE;
        gtk_button_set_label(GTK_BUTTON(wd->mic_btn), "⏹  Stop");
        gtk_label_set_text(GTK_LABEL(wd->voice_label),
                           "Recording… tap Stop when done");
    } else {
        whis_run_wiz("toggle");
        gtk_label_set_text(GTK_LABEL(wd->voice_label), "Transcribing…");
        wd->voice_busy = FALSE;

        VoiceCtx *ctx   = g_new0(VoiceCtx, 1);
        ctx->wd         = wd;
        ctx->attempts   = 0;
        wd->voice_poll_id = g_timeout_add(500, voice_poll_cb, ctx);
    }
}

/* ── Quality grid ─────────────────────────────────────────────────────────── */

static GtkWidget *wiz_quality_grid(WizardData *wd)
{
    /* Row 0 — Nociceptive:  Throbbing | Pressure | Aching    | Stabbing  */
    /* Row 1 — Noci+Neuro:   Tight     | Burning  | Freezing  | Electrical */
    /* Row 2 — Neuro+Dysae:  Shooting  | P+N      | Numbness  | Itching   */
    static const char *labels[NOTE_QUALITY_COUNT] = {
        "Throbbing",  "Pressure",  "Aching",     "Stabbing",
        "Tight",      "Burning",   "Freezing",   "Electrical",
        "Shooting",   "P+N",       "Numbness",   "Itching"
    };

    GtkWidget *vbox = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
    gtk_widget_set_halign(vbox, GTK_ALIGN_CENTER);

    /* Voice row — only if whis is available */
    if (wd->whis_available) {
        GtkWidget *voice_row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
        gtk_widget_set_halign(voice_row, GTK_ALIGN_CENTER);
        wd->mic_btn = gtk_button_new_with_label("🎤  Speak");
        gtk_widget_set_name(wd->mic_btn, "wiz-btn");
        gtk_widget_set_size_request(wd->mic_btn, -1, 44);
        g_signal_connect(wd->mic_btn, "clicked",
                         G_CALLBACK(on_voice_btn_clicked), wd);
        gtk_box_append(GTK_BOX(voice_row), wd->mic_btn);

        wd->voice_reset_btn = gtk_button_new_with_label("↺");
        gtk_widget_set_name(wd->voice_reset_btn, "wiz-btn");
        gtk_widget_set_size_request(wd->voice_reset_btn, 44, 44);
        gtk_widget_set_tooltip_text(wd->voice_reset_btn,
                                    "Reset voice service (use if mic stops responding)");
        g_signal_connect(wd->voice_reset_btn, "clicked",
                         G_CALLBACK(on_voice_reset_clicked), wd);
        gtk_box_append(GTK_BOX(voice_row), wd->voice_reset_btn);

        gtk_box_append(GTK_BOX(vbox), voice_row);

        wd->voice_label = gtk_label_new("— or tap descriptors below —");
        gtk_widget_set_name(wd->voice_label, "wiz-title");
        gtk_box_append(GTK_BOX(vbox), wd->voice_label);

        gtk_box_append(GTK_BOX(vbox),
                       gtk_separator_new(GTK_ORIENTATION_HORIZONTAL));
    }

    GtkWidget *grid = gtk_grid_new();
    gtk_grid_set_row_spacing(GTK_GRID(grid), 4);
    gtk_grid_set_column_spacing(GTK_GRID(grid), 4);
    gtk_widget_set_halign(grid, GTK_ALIGN_CENTER);

    for (int i = 0; i < NOTE_QUALITY_COUNT; i++) {
        GtkWidget *btn = gtk_button_new_with_label(labels[i]);
        gtk_widget_set_name(btn, "wiz-qual-btn");
        wd->qual_btns[i] = btn;
        g_signal_connect(btn, "clicked", G_CALLBACK(on_wiz_qual_toggle),
                         &wd->q3_btns[i]);
        gtk_grid_attach(GTK_GRID(grid), btn, i % 4, i / 4, 1, 1);
    }
    gtk_box_append(GTK_BOX(vbox), grid);

    GtkWidget *next = gtk_button_new_with_label("Next →");
    gtk_widget_set_name(next, "wiz-qual-next");
    gtk_widget_set_halign(next, GTK_ALIGN_CENTER);
    wd->qual_next_btn = next;
    g_signal_connect(next, "clicked", G_CALLBACK(on_wiz_qual_next), wd);
    gtk_box_append(GTK_BOX(vbox), next);

    return vbox;
}

/* Returns a row of 0-10 buttons for intensity.
   First click highlights; second click commits. Stores widgets in wd->int_btns[]. */
static GtkWidget *wiz_intensity_row(WizardData *wd)
{
    GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 4);
    gtk_widget_set_halign(row, GTK_ALIGN_CENTER);
    for (int n = 0; n <= 10; n++) {
        char buf[3];
        snprintf(buf, sizeof(buf), "%d", n);
        GtkWidget *btn = gtk_button_new_with_label(buf);
        gtk_widget_set_name(btn, "wiz-num");
        wd->int_btns[n] = btn;
        g_signal_connect(btn, "clicked", G_CALLBACK(on_wiz_int_click), &wd->n_q4[n]);
        gtk_box_append(GTK_BOX(row), btn);
    }
    return row;
}

static GtkWidget *wiz_page(const char *title, GtkWidget *buttons)
{
    GtkWidget *page = gtk_box_new(GTK_ORIENTATION_VERTICAL, 10);
    gtk_widget_set_margin_top(page, 16);
    gtk_widget_set_margin_bottom(page, 16);
    gtk_widget_set_margin_start(page, 16);
    gtk_widget_set_margin_end(page, 16);
    GtkWidget *lbl = gtk_label_new(title);
    gtk_widget_set_name(lbl, "wiz-title");
    gtk_label_set_xalign(GTK_LABEL(lbl), 0.5);
    gtk_box_append(GTK_BOX(page), lbl);
    gtk_box_append(GTK_BOX(page), buttons);
    return page;
}

static void show_note_wizard(AppState *app, int view, double bx, double by)
{
    if (g_wizard_open) return;
    g_wizard_open = TRUE;

    WizardData *wd = g_malloc0(sizeof(WizardData));
    wd->app            = app;
    wd->view           = view;
    wd->bx             = bx;
    wd->by             = by;
    wd->low_int        = -1;  /* nothing selected yet */
    wd->whis_available = (g_find_program_in_path("whis") != NULL);

    for (int i = 0; i < 2; i++) {
        wd->c_q1[i] = (WBtnPair){ wd, i, 0 };
        wd->c_q2[i] = (WBtnPair){ wd, i, 1 };
    }
    for (int i = 0; i < NOTE_QUALITY_COUNT; i++)
        wd->q3_btns[i] = (WizQualBtn){ wd, i };
    for (int i = 0; i <= 10; i++)
        wd->n_q4[i] = (WizIntBtn){ wd, i };

    wd->window = gtk_window_new();
    gtk_widget_set_name(wd->window, "wiz-window");
    gtk_window_set_title(GTK_WINDOW(wd->window), "Note");
    gtk_window_set_transient_for(GTK_WINDOW(wd->window),
                                 GTK_WINDOW(app->window));
    gtk_window_set_modal(GTK_WINDOW(wd->window), TRUE);
    gtk_window_set_resizable(GTK_WINDOW(wd->window), FALSE);
    g_signal_connect(wd->window, "destroy",
                     G_CALLBACK(on_wizard_destroy), wd);

    wd->stack = gtk_stack_new();
    gtk_stack_set_transition_type(GTK_STACK(wd->stack),
                                  GTK_STACK_TRANSITION_TYPE_NONE);

    gtk_stack_add_named(GTK_STACK(wd->stack),
        wiz_page("Temporal pattern?",
                 wiz_choice_row(wd->c_q1, "Constant (C)", "Intermittent (Im)")),
        "q1");

    gtk_stack_add_named(GTK_STACK(wd->stack),
        wiz_page("Depth?",
                 wiz_choice_row(wd->c_q2, "Superficial (S)", "Deep (D)")),
        "q2");

    gtk_stack_add_named(GTK_STACK(wd->stack),
        wiz_page("Quality?  (tap up to 3, then Next)",
                 wiz_quality_grid(wd)),
        "q3");

    gtk_stack_add_named(GTK_STACK(wd->stack),
        wiz_page("Intensity /10  (tap low, then high)",
                 wiz_intensity_row(wd)),
        "q4");

    gtk_stack_set_visible_child_name(GTK_STACK(wd->stack), "q1");
    gtk_window_set_child(GTK_WINDOW(wd->window), wd->stack);
    gtk_window_present(GTK_WINDOW(wd->window));
}

/* ── Build "Draw" tab content ────────────────────────────────────────────── */
static GtkWidget *build_draw_tab(AppState *app)
{
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 3);
    gtk_widget_set_name(box, "toolbar");
    gtk_widget_set_margin_start(box, 2);
    gtk_widget_set_margin_end(box, 2);
    gtk_widget_set_margin_top(box, 2);

    /* ── View section: 4-View full-width, then 2×2 grid ── */
    GtkWidget *lbl0 = gtk_label_new("View");
    gtk_widget_set_name(lbl0, "section-label");
    gtk_box_append(GTK_BOX(box), lbl0);

    static const char *layout_labels[] = { "4-View", "Ant", "Post", "Lat L", "Lat R" };
    static gpointer    layout_pairs[LAYOUT_COUNT][2];
    static gpointer    cycle_pairs[2][2];

    GtkWidget *view_grid = make_grid2col();

    /* 4-View full-width */
    {
        GtkWidget *btn = make_btn(layout_labels[0], -1, 34);
        gtk_widget_set_hexpand(btn, TRUE);
        gtk_widget_set_name(btn, "tool-btn-active");
        layout_pairs[0][0] = app;
        layout_pairs[0][1] = (gpointer)(gintptr)0;
        g_signal_connect(btn, "clicked", G_CALLBACK(on_layout_clicked), layout_pairs[0]);
        g_layout_btns[0] = btn;
        gtk_grid_attach(GTK_GRID(view_grid), btn, 0, 0, 2, 1);
    }
    /* Ant / Post single-view buttons */
    for (int i = 1; i <= 2; i++) {
        GtkWidget *btn = make_btn(layout_labels[i], -1, 34);
        gtk_widget_set_hexpand(btn, TRUE);
        gtk_widget_set_name(btn, "tool-btn");
        layout_pairs[i][0] = app;
        layout_pairs[i][1] = (gpointer)(gintptr)i;
        g_signal_connect(btn, "clicked", G_CALLBACK(on_layout_clicked), layout_pairs[i]);
        g_layout_btns[i] = btn;
        gtk_grid_attach(GTK_GRID(view_grid), btn, i - 1, 1, 1, 1);
    }
    /* Right column cycle buttons */
    for (int s = 0; s < 2; s++) {
        char lbl[20];
        snprintf(lbl, sizeof(lbl), "%s \xe2\x86\xbb",
                 canvas_view_short_name(app->right_slot_views[s]));
        GtkWidget *btn = make_btn(lbl, -1, 34);
        gtk_widget_set_hexpand(btn, TRUE);
        gtk_widget_set_name(btn, "tool-btn");
        cycle_pairs[s][0] = app;
        cycle_pairs[s][1] = (gpointer)(gintptr)s;
        g_signal_connect(btn, "clicked", G_CALLBACK(on_cycle_right_slot), cycle_pairs[s]);
        g_right_slot_btns[s] = btn;
        gtk_grid_attach(GTK_GRID(view_grid), btn, s, 2, 1, 1);
    }
    gtk_box_append(GTK_BOX(box), view_grid);

    gtk_box_append(GTK_BOX(box), gtk_separator_new(GTK_ORIENTATION_HORIZONTAL));

    /* ── Symptom section: 2-column grid ── */
    GtkWidget *lbl1 = gtk_label_new("Symptom");
    gtk_widget_set_name(lbl1, "section-label");
    gtk_box_append(GTK_BOX(box), lbl1);

    /* Labels — single line; pattern/colour shown via indicator strip below */
    static const char *sym_labels[] = {
        "Pain", "Intermt", "P&N", "Numb", "Para", "Tick", "Pencil"
    };
    static gpointer   sym_pairs[SYMPTOM_COUNT][2];

    GtkWidget *sym_grid = make_grid2col();
    for (int i = 0; i < SYMPTOM_COUNT; i++) {
        GtkWidget *btn = make_symptom_btn(sym_labels[i], (SymptomType)i);
        gtk_widget_set_hexpand(btn, TRUE);
        gtk_widget_set_name(btn, "symptom-btn");
        sym_pairs[i][0] = app;
        sym_pairs[i][1] = (gpointer)(gintptr)i;
        g_signal_connect(btn, "clicked", G_CALLBACK(on_symptom_clicked), sym_pairs[i]);
        g_symptom_btns[i] = btn;
        gtk_grid_attach(GTK_GRID(sym_grid), btn, i % 2, i / 2, 1, 1);
    }

    /* Arrow tool button — half width, shares row with Pencil symptom button */
    g_arrow_btn = make_btn("Arrow →", -1, 44);
    gtk_widget_set_hexpand(g_arrow_btn, TRUE);
    gtk_widget_set_name(g_arrow_btn, "tool-btn");
    g_signal_connect(g_arrow_btn, "clicked", G_CALLBACK(on_arrow_clicked), app);
    gtk_grid_attach(GTK_GRID(sym_grid), g_arrow_btn, 1, SYMPTOM_COUNT / 2, 1, 1);

    /* Note tool button — full width, below Arrow */
    g_note_btn = make_btn("Note ✎", -1, 34);
    gtk_widget_set_hexpand(g_note_btn, TRUE);
    gtk_widget_set_name(g_note_btn, "tool-btn");
    g_signal_connect(g_note_btn, "clicked", G_CALLBACK(on_note_clicked), app);
    gtk_grid_attach(GTK_GRID(sym_grid), g_note_btn, 0, SYMPTOM_COUNT / 2 + 1, 2, 1);

    gtk_box_append(GTK_BOX(box), sym_grid);

    gtk_box_append(GTK_BOX(box), gtk_separator_new(GTK_ORIENTATION_HORIZONTAL));

    /* ── Tools section: 2-column grid ── */
    GtkWidget *lbl2 = gtk_label_new("Tools");
    gtk_widget_set_name(lbl2, "section-label");
    gtk_box_append(GTK_BOX(box), lbl2);

    GtkWidget *tool_grid = make_grid2col();

    g_linemode_btn = make_btn(app->pen_wide_mode ? "Bold" : "Fine", -1, 34);
    gtk_widget_set_hexpand(g_linemode_btn, TRUE);
    gtk_widget_set_name(g_linemode_btn, app->pen_wide_mode ? "tool-btn-active" : "tool-btn");
    g_signal_connect(g_linemode_btn, "clicked", G_CALLBACK(on_linemode_clicked), app);
    gtk_grid_attach(GTK_GRID(tool_grid), g_linemode_btn, 0, 0, 1, 1);

    g_erase_btn = make_btn("Erase", -1, 34);
    gtk_widget_set_hexpand(g_erase_btn, TRUE);
    g_signal_connect(g_erase_btn, "clicked", G_CALLBACK(on_erase_clicked), app);
    gtk_grid_attach(GTK_GRID(tool_grid), g_erase_btn, 1, 0, 1, 1);

    GtkWidget *undo_btn = make_btn("Undo", -1, 34);
    gtk_widget_set_hexpand(undo_btn, TRUE);
    g_signal_connect(undo_btn, "clicked", G_CALLBACK(on_undo_clicked), app);
    gtk_grid_attach(GTK_GRID(tool_grid), undo_btn, 0, 1, 1, 1);

    GtkWidget *clear_btn = make_btn("Clear", -1, 34);
    gtk_widget_set_hexpand(clear_btn, TRUE);
    g_signal_connect(clear_btn, "clicked", G_CALLBACK(on_clear_clicked), app);
    gtk_grid_attach(GTK_GRID(tool_grid), clear_btn, 1, 1, 1, 1);

    g_link_btn = make_btn("Link", -1, 34);
    gtk_widget_set_hexpand(g_link_btn, TRUE);
    g_signal_connect(g_link_btn, "clicked", G_CALLBACK(on_link_clicked), app);
    gtk_grid_attach(GTK_GRID(tool_grid), g_link_btn, 0, 2, 2, 1);

    gtk_box_append(GTK_BOX(box), tool_grid);

    gtk_box_append(GTK_BOX(box), gtk_separator_new(GTK_ORIENTATION_HORIZONTAL));

    /* ── Overlay section: 2-column grid + compact nav ── */
    GtkWidget *lbl4 = gtk_label_new("Overlay");
    gtk_widget_set_name(lbl4, "section-label");
    gtk_box_append(GTK_BOX(box), lbl4);

    static const char *cat_labels[] = { "Derm", "Periph", "Somat" };
    static gpointer    cat_pairs[3][2];

    GtkWidget *ov_grid = make_grid2col();
    for (int i = 0; i < 2; i++) {
        GtkWidget *btn = make_btn(cat_labels[i], -1, 34);
        gtk_widget_set_hexpand(btn, TRUE);
        gtk_widget_set_name(btn, "overlay-btn");
        cat_pairs[i][0] = app;
        cat_pairs[i][1] = (gpointer)(gintptr)(i + 1);
        g_signal_connect(btn, "clicked", G_CALLBACK(on_overlay_cat_clicked), cat_pairs[i]);
        g_overlay_cat_btns[i] = btn;
        gtk_grid_attach(GTK_GRID(ov_grid), btn, i, 0, 1, 1);
    }
    g_overlay_cat_btns[2] = NULL;  /* Somatic button removed */
    gtk_box_append(GTK_BOX(box), ov_grid);

    g_overlay_label = gtk_label_new("Off");
    gtk_widget_set_name(g_overlay_label, "overlay-name");
    gtk_widget_set_hexpand(g_overlay_label, TRUE);
    gtk_label_set_wrap(GTK_LABEL(g_overlay_label), TRUE);
    gtk_label_set_justify(GTK_LABEL(g_overlay_label), GTK_JUSTIFY_CENTER);
    gtk_box_append(GTK_BOX(box), g_overlay_label);

    g_overlay_nav_box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 2);
    GtkWidget *prev_btn = gtk_button_new_with_label("◀");
    GtkWidget *next_btn = gtk_button_new_with_label("▶");
    gtk_widget_set_size_request(prev_btn, 28, 30);
    gtk_widget_set_size_request(next_btn, 28, 30);
    g_signal_connect(prev_btn, "clicked", G_CALLBACK(on_overlay_prev), app);
    g_signal_connect(next_btn, "clicked", G_CALLBACK(on_overlay_next), app);
    gtk_box_append(GTK_BOX(g_overlay_nav_box), prev_btn);
    gtk_box_append(GTK_BOX(g_overlay_nav_box), next_btn);
    gtk_widget_set_visible(g_overlay_nav_box, FALSE);
    gtk_box_append(GTK_BOX(box), g_overlay_nav_box);

    GtkWidget *alpha_lbl = gtk_label_new("Opacity");
    gtk_widget_set_name(alpha_lbl, "section-label");
    gtk_box_append(GTK_BOX(box), alpha_lbl);

    GtkWidget *slider = gtk_scale_new_with_range(GTK_ORIENTATION_HORIZONTAL, 0.0, 1.0, 0.05);
    gtk_range_set_value(GTK_RANGE(slider), 0.5);
    gtk_scale_set_draw_value(GTK_SCALE(slider), FALSE);
    gtk_widget_set_hexpand(slider, TRUE);
    g_signal_connect(slider, "value-changed", G_CALLBACK(on_overlay_alpha), app);
    gtk_box_append(GTK_BOX(box), slider);

    GtkWidget *spacer = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_set_vexpand(spacer, TRUE);
    gtk_box_append(GTK_BOX(box), spacer);

    return box;
}

/* ── PPT / TS value entry dialog ─────────────────────────────────────────── */
typedef struct {
    AppState    *app;
    int          view;
    double       bx, by;
    ObjPointType type;
    GtkWidget   *window;
    GtkWidget   *entry;
} PPTEntryData;

/* Called when the PPT window is destroyed (by OK, Cancel, or WM close).
 * Frees the PPTEntryData allocation exactly once. */
static void on_ppt_destroy(GtkWidget *w, gpointer data)
{
    (void)w;
    g_ppt_dialog_open = FALSE;
    g_free(data);
}

static void on_ppt_keypad_digit(GtkButton *btn, gpointer data)
{
    PPTEntryData *pd = (PPTEntryData *)data;
    const char *key = gtk_button_get_label(btn);
    if (!key || !key[0]) return;

    const char *current = gtk_editable_get_text(GTK_EDITABLE(pd->entry));
    gsize len = strlen(current);
    if (len >= 8) return;

    /* Only one decimal point allowed */
    if (key[0] == '.' && strchr(current, '.')) return;

    gchar buf[12];
    snprintf(buf, sizeof(buf), "%s%c", current, key[0]);
    gtk_editable_set_text(GTK_EDITABLE(pd->entry), buf);
}

static void on_ppt_keypad_delete(GtkButton *btn, gpointer data)
{
    (void)btn;
    PPTEntryData *pd = (PPTEntryData *)data;
    const char *current = gtk_editable_get_text(GTK_EDITABLE(pd->entry));
    gsize len = strlen(current);
    if (len == 0) return;

    gchar buf[12];
    snprintf(buf, sizeof(buf), "%.*s", (int)(len - 1), current);
    gtk_editable_set_text(GTK_EDITABLE(pd->entry), buf);
}

static void on_ppt_confirm(GtkButton *btn, gpointer data)
{
    (void)btn;
    PPTEntryData *pd = data;
    const char *txt = gtk_editable_get_text(GTK_EDITABLE(pd->entry));
    double val = g_strtod(txt, NULL);
    AppState *app = pd->app;
    if (app->obj_point_count < MAX_OBJ_POINTS) {
        ObjPoint *p = &app->obj_points[app->obj_point_count];
        p->bx    = pd->bx;
        p->by    = pd->by;
        p->view  = pd->view;
        p->type  = pd->type;
        p->value = val;
        if (pd->type == OBJ_POINT_PPT)
            snprintf(p->label, sizeof(p->label), "%.1f", val);
        else if (pd->type == OBJ_POINT_MONOFILAMENT)
            snprintf(p->label, sizeof(p->label), "%.2f", val);
        else if (pd->type == OBJ_POINT_TWO_PD)
            snprintf(p->label, sizeof(p->label), "%.0f", val);
        else  /* OBJ_POINT_TEMPORAL_SUM */
            snprintf(p->label, sizeof(p->label), "%d", (int)CLAMP(val, 0.0, 10.0));
        app->obj_point_count++;
        if (app->obj_undo_type_top < 64)
            app->obj_undo_type_stack[app->obj_undo_type_top++] = 1;
        canvas_invalidate(app);
    }
    /* g_free(pd) happens via on_ppt_destroy connected to "destroy" signal */
    gtk_window_destroy(GTK_WINDOW(pd->window));
}

static void on_ppt_cancel(GtkButton *btn, gpointer data)
{
    (void)btn;
    PPTEntryData *pd = data;
    /* g_free(pd) happens via on_ppt_destroy connected to "destroy" signal */
    gtk_window_destroy(GTK_WINDOW(pd->window));
}

static void show_ppt_entry(AppState *app, int view, double bx, double by)
{
    if (g_ppt_dialog_open) return;
    g_ppt_dialog_open = TRUE;

    PPTEntryData *pd = g_malloc0(sizeof(PPTEntryData));
    pd->app  = app;
    pd->view = view;
    pd->bx   = bx;
    pd->by   = by;
    pd->type = app->obj_point_type;

    pd->window = gtk_window_new();
    gtk_widget_set_name(pd->window, "wiz-window");
    const char *title = pd->type == OBJ_POINT_PPT         ? "PPT (kg/cm²)"        :
                        pd->type == OBJ_POINT_MONOFILAMENT ? "Monofilament (g)"    :
                        pd->type == OBJ_POINT_TWO_PD       ? "2-PD (mm)"           :
                                                             "Temporal Sum (0–10)";
    gtk_window_set_title(GTK_WINDOW(pd->window), title);
    gtk_window_set_transient_for(GTK_WINDOW(pd->window),
                                 GTK_WINDOW(app->window));
    gtk_window_set_modal(GTK_WINDOW(pd->window), TRUE);
    gtk_window_set_resizable(GTK_WINDOW(pd->window), FALSE);
    gtk_window_set_default_size(GTK_WINDOW(pd->window), 260, -1);
    /* Free pd exactly once on any close path (OK, Cancel, or WM close). */
    g_signal_connect(pd->window, "destroy", G_CALLBACK(on_ppt_destroy), pd);

    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
    gtk_widget_set_margin_start(box, 12);
    gtk_widget_set_margin_end(box, 12);
    gtk_widget_set_margin_top(box, 8);
    gtk_widget_set_margin_bottom(box, 8);

    GtkWidget *lbl = gtk_label_new(title);
    gtk_widget_set_name(lbl, "section-label");
    gtk_box_append(GTK_BOX(box), lbl);

    pd->entry = gtk_entry_new();
    gtk_entry_set_placeholder_text(GTK_ENTRY(pd->entry),
        pd->type == OBJ_POINT_PPT         ? "e.g. 4.2"  :
        pd->type == OBJ_POINT_MONOFILAMENT ? "e.g. 0.07" :
        pd->type == OBJ_POINT_TWO_PD       ? "e.g. 6"    : "0–10");
    gtk_widget_set_size_request(pd->entry, -1, 48);
    gtk_box_append(GTK_BOX(box), pd->entry);

    GtkWidget *keypad = gtk_grid_new();
    gtk_grid_set_column_spacing(GTK_GRID(keypad), 2);
    gtk_grid_set_row_spacing(GTK_GRID(keypad), 2);
    gtk_widget_set_hexpand(keypad, TRUE);

    const char *keypad_layout[] = { "7", "8", "9",
                                     "4", "5", "6",
                                     "1", "2", "3",
                                     ".", "0", "⌫" };
    for (int i = 0; i < 12; i++) {
        int row = i / 3, col = i % 3;
        const char *label = keypad_layout[i];
        if (!label || !label[0]) continue;

        GtkWidget *btn = gtk_button_new_with_label(label);
        gtk_widget_set_hexpand(btn, TRUE);
        gtk_widget_set_vexpand(btn, TRUE);
        gtk_widget_set_size_request(btn, 40, 40);

        if (strcmp(label, "⌫") == 0) {
            g_signal_connect(btn, "clicked", G_CALLBACK(on_ppt_keypad_delete), pd);
        } else {
            g_signal_connect(btn, "clicked", G_CALLBACK(on_ppt_keypad_digit), pd);
        }
        gtk_grid_attach(GTK_GRID(keypad), btn, col, row, 1, 1);
    }
    gtk_box_append(GTK_BOX(box), keypad);

    GtkWidget *btn_row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
    GtkWidget *cancel_btn = gtk_button_new_with_label("Cancel");
    GtkWidget *ok_btn     = gtk_button_new_with_label("OK");
    gtk_widget_set_hexpand(cancel_btn, TRUE);
    gtk_widget_set_hexpand(ok_btn,     TRUE);
    gtk_widget_set_size_request(cancel_btn, -1, 44);
    gtk_widget_set_size_request(ok_btn,     -1, 44);
    gtk_box_append(GTK_BOX(btn_row), cancel_btn);
    gtk_box_append(GTK_BOX(btn_row), ok_btn);
    gtk_box_append(GTK_BOX(box), btn_row);

    g_signal_connect(ok_btn,     "clicked",  G_CALLBACK(on_ppt_confirm), pd);
    g_signal_connect(cancel_btn, "clicked",  G_CALLBACK(on_ppt_cancel),  pd);
    g_signal_connect(pd->entry,  "activate", G_CALLBACK(on_ppt_confirm), pd);
    gtk_window_set_default_widget(GTK_WINDOW(pd->window), ok_btn);

    gtk_window_set_child(GTK_WINDOW(pd->window), box);
    gtk_widget_grab_focus(pd->entry);
    gtk_window_present(GTK_WINDOW(pd->window));
}

/* ── Obj tab button callbacks ────────────────────────────────────────────── */
static void on_obj_zone_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    gpointer *pair  = data;
    AppState *app   = pair[0];
    ObjZoneType zt  = (ObjZoneType)(gintptr)pair[1];
    app->obj_zone_type  = zt;
    app->obj_point_mode = FALSE;
    app->tool = TOOL_DRAW;
    if (app->toolbar_update_cb) app->toolbar_update_cb(app);
}

static void on_obj_ppt_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    app->obj_point_mode = TRUE;
    app->obj_point_type = OBJ_POINT_PPT;
    app->tool = TOOL_DRAW;
    if (app->toolbar_update_cb) app->toolbar_update_cb(app);
}

static void on_obj_ts_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    app->obj_point_mode = TRUE;
    app->obj_point_type = OBJ_POINT_TEMPORAL_SUM;
    app->tool = TOOL_DRAW;
    if (app->toolbar_update_cb) app->toolbar_update_cb(app);
}

static void on_obj_mono_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    app->obj_point_mode = TRUE;
    app->obj_point_type = OBJ_POINT_MONOFILAMENT;
    app->tool = TOOL_DRAW;
    if (app->toolbar_update_cb) app->toolbar_update_cb(app);
}

static void on_obj_tpd_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    app->obj_point_mode = TRUE;
    app->obj_point_type = OBJ_POINT_TWO_PD;
    app->tool = TOOL_DRAW;
    if (app->toolbar_update_cb) app->toolbar_update_cb(app);
}

static void on_obj_erase_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    app->tool = TOOL_ERASE;
    if (app->toolbar_update_cb) app->toolbar_update_cb(app);
}

static void on_obj_undo_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    canvas_undo((AppState *)data);
}

/* ── Build "Obj" tab content ─────────────────────────────────────────────── */
static GtkWidget *build_obj_tab(AppState *app)
{
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 3);
    gtk_widget_set_name(box, "toolbar");
    gtk_widget_set_margin_start(box, 2);
    gtk_widget_set_margin_end(box, 2);
    gtk_widget_set_margin_top(box, 2);

    /* ── Zone section — single column, full names ── */
    GtkWidget *lbl_z = gtk_label_new("Zone");
    gtk_widget_set_name(lbl_z, "section-label");
    gtk_box_append(GTK_BOX(box), lbl_z);

    static gpointer zone_pairs[OBJ_ZONE_COUNT][2];
    GtkWidget *zone_box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 3);
    for (int i = 0; i < OBJ_ZONE_COUNT; i++) {
        GtkWidget *btn = make_btn(OBJ_ZONE_DEFS[i].name, -1, 36);
        gtk_widget_set_hexpand(btn, TRUE);
        zone_pairs[i][0] = app;
        zone_pairs[i][1] = (gpointer)(gintptr)i;
        g_signal_connect(btn, "clicked", G_CALLBACK(on_obj_zone_clicked), zone_pairs[i]);
        g_obj_zone_btns[i] = btn;
        gtk_box_append(GTK_BOX(zone_box), btn);
    }
    gtk_box_append(GTK_BOX(box), zone_box);

    gtk_box_append(GTK_BOX(box), gtk_separator_new(GTK_ORIENTATION_HORIZONTAL));

    /* ── Point section — single column ── */
    GtkWidget *lbl_p = gtk_label_new("Point");
    gtk_widget_set_name(lbl_p, "section-label");
    gtk_box_append(GTK_BOX(box), lbl_p);

    g_obj_ppt_btn = make_btn("PPT kg/cm²", -1, 36);
    gtk_widget_set_hexpand(g_obj_ppt_btn, TRUE);
    g_signal_connect(g_obj_ppt_btn, "clicked", G_CALLBACK(on_obj_ppt_clicked), app);
    gtk_box_append(GTK_BOX(box), g_obj_ppt_btn);

    g_obj_ts_btn = make_btn("Temporal Sum", -1, 36);
    gtk_widget_set_hexpand(g_obj_ts_btn, TRUE);
    g_signal_connect(g_obj_ts_btn, "clicked", G_CALLBACK(on_obj_ts_clicked), app);
    gtk_box_append(GTK_BOX(box), g_obj_ts_btn);

    g_obj_mono_btn = make_btn("Monofilament", -1, 36);
    gtk_widget_set_hexpand(g_obj_mono_btn, TRUE);
    g_signal_connect(g_obj_mono_btn, "clicked", G_CALLBACK(on_obj_mono_clicked), app);
    gtk_box_append(GTK_BOX(box), g_obj_mono_btn);

    g_obj_tpd_btn = make_btn("2-PD mm", -1, 36);
    gtk_widget_set_hexpand(g_obj_tpd_btn, TRUE);
    g_signal_connect(g_obj_tpd_btn, "clicked", G_CALLBACK(on_obj_tpd_clicked), app);
    gtk_box_append(GTK_BOX(box), g_obj_tpd_btn);

    gtk_box_append(GTK_BOX(box), gtk_separator_new(GTK_ORIENTATION_HORIZONTAL));

    /* ── Tools section — single column ── */
    GtkWidget *lbl_t = gtk_label_new("Tools");
    gtk_widget_set_name(lbl_t, "section-label");
    gtk_box_append(GTK_BOX(box), lbl_t);

    g_obj_erase_btn = make_btn("Erase", -1, 36);
    gtk_widget_set_hexpand(g_obj_erase_btn, TRUE);
    g_signal_connect(g_obj_erase_btn, "clicked", G_CALLBACK(on_obj_erase_clicked), app);
    gtk_box_append(GTK_BOX(box), g_obj_erase_btn);

    GtkWidget *undo_btn = make_btn("Undo", -1, 36);
    gtk_widget_set_hexpand(undo_btn, TRUE);
    g_signal_connect(undo_btn, "clicked", G_CALLBACK(on_obj_undo_clicked), app);
    gtk_box_append(GTK_BOX(box), undo_btn);

    GtkWidget *spacer = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_set_vexpand(spacer, TRUE);
    gtk_box_append(GTK_BOX(box), spacer);

    return box;
}

/* ── Mode strip ──────────────────────────────────────────────────────────── */
static GtkWidget *build_mode_strip(AppState *app)
{
    GtkWidget *strip = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 2);
    gtk_widget_set_name(strip, "mode-strip");
    gtk_widget_set_margin_start(strip, 3);
    gtk_widget_set_margin_end(strip, 3);
    gtk_widget_set_margin_top(strip, 4);
    gtk_widget_set_margin_bottom(strip, 2);

    static const char *labels[APP_MODE_COUNT] = { "Sx", "Obj" };
    static gpointer    pairs[APP_MODE_COUNT][2];

    for (int i = 0; i < APP_MODE_COUNT; i++) {
        GtkWidget *btn = gtk_button_new_with_label(labels[i]);
        gtk_widget_set_name(btn,
            (AppMode)i == app->current_mode ? "mode-btn-active" : "mode-btn");
        gtk_widget_set_hexpand(btn, TRUE);
        gtk_widget_set_size_request(btn, -1, 34);
        pairs[i][0] = app;
        pairs[i][1] = (gpointer)(gintptr)i;
        g_signal_connect(btn, "clicked", G_CALLBACK(on_mode_clicked), pairs[i]);
        gtk_box_append(GTK_BOX(strip), btn);
        g_mode_btns[i] = btn;
    }
    return strip;
}

/* ── Drag handle callbacks ────────────────────────────────────────────────── */
static void on_minimize_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    gtk_window_minimize(GTK_WINDOW(app->window));
}

static void on_maximize_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    if (gtk_window_is_maximized(GTK_WINDOW(app->window)))
        gtk_window_unmaximize(GTK_WINDOW(app->window));
    else
        gtk_window_maximize(GTK_WINDOW(app->window));
}

static void on_close_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    AppState *app = data;
    /* gtk_window_close(), not gtk_window_destroy() — see on_main_window_close's
     * docstring; this is the custom titlebar's own close button, the most
     * common way this window actually gets closed day to day. */
    gtk_window_close(GTK_WINDOW(app->window));
}

/* ── Build drag handle with window controls ────────────────────────────── */
static GtkWidget *build_drag_handle(AppState *app)
{
    GtkWidget *handle = gtk_window_handle_new();
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 2);
    gtk_window_handle_set_child(GTK_WINDOW_HANDLE(handle), box);

    /* Left group: − □ [save icon + indicator] */
    GtkWidget *min_btn = gtk_button_new_with_label("−");
    gtk_widget_set_name(min_btn, "drag-handle-btn");
    gtk_widget_set_size_request(min_btn, 20, 20);
    g_signal_connect(min_btn, "clicked", G_CALLBACK(on_minimize_clicked), app);
    gtk_box_append(GTK_BOX(box), min_btn);

    GtkWidget *max_btn = gtk_button_new_with_label("□");
    gtk_widget_set_name(max_btn, "drag-handle-btn");
    gtk_widget_set_size_request(max_btn, 20, 20);
    g_signal_connect(max_btn, "clicked", G_CALLBACK(on_maximize_clicked), app);
    gtk_box_append(GTK_BOX(box), max_btn);

    /* Save button: icon + ✓/✗ indicator */
    GtkWidget *save_btn = gtk_button_new();
    gtk_widget_set_name(save_btn, "save-btn");
    gtk_widget_set_size_request(save_btn, -1, 20);
    GtkWidget *save_inner = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 2);
    GtkWidget *save_icon = gtk_image_new_from_icon_name("document-save-symbolic");
    gtk_image_set_pixel_size(GTK_IMAGE(save_icon), 12);
    g_save_indicator = gtk_label_new("");
    gtk_widget_set_name(g_save_indicator, "save-indicator");
    gtk_box_append(GTK_BOX(save_inner), save_icon);
    gtk_box_append(GTK_BOX(save_inner), g_save_indicator);
    gtk_button_set_child(GTK_BUTTON(save_btn), save_inner);
    g_signal_connect(save_btn, "clicked", G_CALLBACK(on_save_session), NULL);
    gtk_box_append(GTK_BOX(box), save_btn);

    /* Spacer pushes close button to the right */
    GtkWidget *spacer = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_widget_set_hexpand(spacer, TRUE);
    gtk_box_append(GTK_BOX(box), spacer);

    /* Right: × close */
    GtkWidget *close_btn = gtk_button_new_with_label("×");
    gtk_widget_set_name(close_btn, "drag-handle-btn");
    gtk_widget_set_size_request(close_btn, 20, 20);
    g_signal_connect(close_btn, "clicked", G_CALLBACK(on_close_clicked), app);
    gtk_box_append(GTK_BOX(box), close_btn);

    gtk_widget_set_hexpand(handle, TRUE);
    gtk_widget_set_valign(handle, GTK_ALIGN_START);
    return handle;
}

/* ── Build sidebar ───────────────────────────────────────────────────────── */
static GtkWidget *build_sidebar(AppState *app)
{
    GtkWidget *outer = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_set_name(outer, "sidebar");
    gtk_widget_set_size_request(outer, 150, -1);
    gtk_widget_set_hexpand(outer, FALSE);

    gtk_box_append(GTK_BOX(outer), build_drag_handle(app));

    /* Mode strip */
    gtk_box_append(GTK_BOX(outer), build_mode_strip(app));
    gtk_box_append(GTK_BOX(outer), gtk_separator_new(GTK_ORIENTATION_HORIZONTAL));

    /* Content stack: switches between Sx draw content and Obj content */
    g_sidebar_content_stack = gtk_stack_new();
    gtk_stack_set_transition_type(GTK_STACK(g_sidebar_content_stack),
                                  GTK_STACK_TRANSITION_TYPE_NONE);
    gtk_widget_set_vexpand(g_sidebar_content_stack, TRUE);

    /* ── Sx content: draw tools directly in scrolled window ── */
    GtkWidget *sx_sc = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(sx_sc),
                                   GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_scrolled_window_set_has_frame(GTK_SCROLLED_WINDOW(sx_sc), FALSE);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(sx_sc), build_draw_tab(app));
    gtk_stack_add_named(GTK_STACK(g_sidebar_content_stack), sx_sc, "sx");

    /* ── Obj content ── */
    GtkWidget *obj_sc = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(obj_sc),
                                   GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_scrolled_window_set_has_frame(GTK_SCROLLED_WINDOW(obj_sc), FALSE);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(obj_sc), build_obj_tab(app));
    gtk_stack_add_named(GTK_STACK(g_sidebar_content_stack), obj_sc, "obj");

    gtk_box_append(GTK_BOX(outer), g_sidebar_content_stack);
    return outer;
}

/* ── Launch dialog ───────────────────────────────────────────────────────── */

typedef struct {
    AppState       *app;
    GtkApplication *gapp;
    GtkWidget      *window;
    GtkWidget      *id_entry;
    GtkWidget      *label_entry;
    GtkWidget      *open_btn;
    char            selected_path[512];
} LaunchData;

static void launch_commit_new(GtkButton *btn, gpointer data)
{
    (void)btn;
    LaunchData *ld = data;
    const char *id  = gtk_editable_get_text(GTK_EDITABLE(ld->id_entry));
    const char *lbl = gtk_editable_get_text(GTK_EDITABLE(ld->label_entry));
    if (!id || id[0] == '\0') id = "XX";
    persistence_build_paths(ld->app, id, lbl);
    persistence_monitor_start(ld->app);
    GtkWidget *launch_win = ld->window;
    window_create(ld->app, ld->gapp);
    gtk_window_destroy(GTK_WINDOW(launch_win));
    persistence_write_session_current(ld->app);
    integration_create_tui_window(ld->app, ld->gapp);
    g_free(ld);
}

static void launch_commit_open(GtkButton *btn, gpointer data)
{
    (void)btn;
    LaunchData *ld = data;
    if (!ld->selected_path[0]) return;
    if (!persistence_load(ld->app, ld->selected_path)) return;
    persistence_monitor_start(ld->app);
    GtkWidget *launch_win = ld->window;
    window_create(ld->app, ld->gapp);
    gtk_window_destroy(GTK_WINDOW(launch_win));
    persistence_write_session_current(ld->app);
    integration_create_tui_window(ld->app, ld->gapp);
    g_free(ld);
}

static void on_recent_row_selected(GtkListBox *box, GtkListBoxRow *row, gpointer data)
{
    (void)box;
    LaunchData *ld = data;
    if (!row) {
        ld->selected_path[0] = '\0';
        gtk_widget_set_name(ld->open_btn, "launch-btn-dim");
        return;
    }
    /* Retrieve stored path from row widget data */
    const char *path = g_object_get_data(G_OBJECT(row), "session-path");
    if (path) {
        strncpy(ld->selected_path, path, sizeof(ld->selected_path) - 1);
        gtk_widget_set_name(ld->open_btn, "launch-btn");

        /* Pre-fill entries from row data */
        const char *pid = g_object_get_data(G_OBJECT(row), "patient-id");
        const char *lbl = g_object_get_data(G_OBJECT(row), "session-label");
        if (pid) gtk_editable_set_text(GTK_EDITABLE(ld->id_entry),    pid);
        if (lbl) gtk_editable_set_text(GTK_EDITABLE(ld->label_entry), lbl);
    }
}

static void on_recent_row_activated(GtkListBox *box, GtkListBoxRow *row, gpointer data)
{
    (void)box;
    /* Double-tap/click → select + open immediately */
    on_recent_row_selected(box, row, data);
    LaunchData *ld = data;
    if (ld->selected_path[0])
        launch_commit_open(NULL, ld);
}

static void on_id_entry_activate(GtkEntry *e, gpointer data)
{
    (void)e;
    LaunchData *ld = data;
    gtk_widget_grab_focus(ld->label_entry);
}

void window_show_launch(AppState *app, GtkApplication *gapp)
{
    apply_css();

    LaunchData *ld = g_new0(LaunchData, 1);
    ld->app  = app;
    ld->gapp = gapp;

    ld->window = gtk_application_window_new(gapp);
    gtk_widget_set_name(ld->window, "launch-win");
    gtk_window_set_title(GTK_WINDOW(ld->window), "PhysioChart");
    gtk_window_set_default_size(GTK_WINDOW(ld->window), 460, 560);
    gtk_window_set_resizable(GTK_WINDOW(ld->window), FALSE);

    GtkWidget *outer = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12);
    gtk_widget_set_margin_top(outer, 20);
    gtk_widget_set_margin_bottom(outer, 20);
    gtk_widget_set_margin_start(outer, 24);
    gtk_widget_set_margin_end(outer, 24);

    /* Title */
    GtkWidget *title = gtk_label_new("PhysioChart");
    gtk_widget_set_name(title, "launch-title");
    gtk_label_set_xalign(GTK_LABEL(title), 0.0);
    gtk_box_append(GTK_BOX(outer), title);

    /* Patient ID */
    GtkWidget *id_lbl = gtk_label_new("Patient ID (initials or code)");
    gtk_widget_set_name(id_lbl, "launch-label");
    gtk_label_set_xalign(GTK_LABEL(id_lbl), 0.0);
    gtk_box_append(GTK_BOX(outer), id_lbl);
    ld->id_entry = gtk_entry_new();
    gtk_widget_set_name(ld->id_entry, "launch-entry");
    gtk_entry_set_max_length(GTK_ENTRY(ld->id_entry), 16);
    gtk_entry_set_placeholder_text(GTK_ENTRY(ld->id_entry), "e.g. JB");
    gtk_widget_set_hexpand(ld->id_entry, TRUE);
    gtk_box_append(GTK_BOX(outer), ld->id_entry);

    /* Session label */
    GtkWidget *lbl_lbl = gtk_label_new("Session label (optional)");
    gtk_widget_set_name(lbl_lbl, "launch-label");
    gtk_label_set_xalign(GTK_LABEL(lbl_lbl), 0.0);
    gtk_box_append(GTK_BOX(outer), lbl_lbl);
    ld->label_entry = gtk_entry_new();
    gtk_widget_set_name(ld->label_entry, "launch-entry");
    gtk_entry_set_max_length(GTK_ENTRY(ld->label_entry), 60);
    gtk_entry_set_placeholder_text(GTK_ENTRY(ld->label_entry),
                                   "e.g. Initial assessment");
    gtk_widget_set_hexpand(ld->label_entry, TRUE);
    gtk_box_append(GTK_BOX(outer), ld->label_entry);

    /* Enter in ID field → focus label field; Enter in label field → start session */
    g_signal_connect(ld->id_entry,    "activate", G_CALLBACK(on_id_entry_activate), ld);
    g_signal_connect(ld->label_entry, "activate", G_CALLBACK(launch_commit_new),    ld);

    /* New session button */
    GtkWidget *new_btn = gtk_button_new_with_label("New Session");
    gtk_widget_set_name(new_btn, "launch-btn");
    gtk_widget_set_size_request(new_btn, -1, 48);
    g_signal_connect(new_btn, "clicked", G_CALLBACK(launch_commit_new), ld);
    gtk_box_append(GTK_BOX(outer), new_btn);
    gtk_window_set_default_widget(GTK_WINDOW(ld->window), new_btn);

    gtk_box_append(GTK_BOX(outer), gtk_separator_new(GTK_ORIENTATION_HORIZONTAL));

    /* Recent sessions */
    GtkWidget *rec_lbl = gtk_label_new("Recent sessions");
    gtk_widget_set_name(rec_lbl, "launch-label");
    gtk_label_set_xalign(GTK_LABEL(rec_lbl), 0.0);
    gtk_box_append(GTK_BOX(outer), rec_lbl);

    GtkWidget *scroll = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll),
                                   GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_widget_set_size_request(scroll, -1, 200);
    gtk_widget_set_vexpand(scroll, TRUE);

    GtkWidget *list = gtk_list_box_new();
    gtk_list_box_set_selection_mode(GTK_LIST_BOX(list), GTK_SELECTION_SINGLE);
    g_signal_connect(list, "row-selected",  G_CALLBACK(on_recent_row_selected),  ld);
    g_signal_connect(list, "row-activated", G_CALLBACK(on_recent_row_activated), ld);

    /* Populate recent sessions */
    PersistRecent recents[PERSIST_RECENT_MAX];
    int n_recent = persistence_scan_recent(recents, PERSIST_RECENT_MAX);
    for (int i = 0; i < n_recent; i++) {
        PersistRecent *r = &recents[i];

        /* Format date */
        char date_str[32] = "";
        if (r->modified > 0) {
            struct tm *t = localtime(&r->modified);
            strftime(date_str, sizeof(date_str), "%d %b %Y %H:%M", t);
        }

        /* Row box */
        GtkWidget *row_box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 2);
        gtk_widget_set_name(row_box, "launch-row");
        gtk_widget_set_margin_top(row_box, 2);
        gtk_widget_set_margin_bottom(row_box, 2);

        /* Top line: ID + date */
        GtkWidget *top = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
        GtkWidget *id_w = gtk_label_new(r->patient_id);
        gtk_widget_set_name(id_w, "launch-row-id");
        gtk_label_set_xalign(GTK_LABEL(id_w), 0.0);
        GtkWidget *date_w = gtk_label_new(date_str);
        gtk_widget_set_name(date_w, "launch-row-date");
        gtk_label_set_xalign(GTK_LABEL(date_w), 1.0);
        gtk_widget_set_hexpand(date_w, TRUE);
        gtk_box_append(GTK_BOX(top), id_w);
        gtk_box_append(GTK_BOX(top), date_w);
        gtk_box_append(GTK_BOX(row_box), top);

        /* Label line (if present) */
        if (r->session_label[0]) {
            GtkWidget *lbl_w = gtk_label_new(r->session_label);
            gtk_widget_set_name(lbl_w, "launch-row-label");
            gtk_label_set_xalign(GTK_LABEL(lbl_w), 0.0);
            gtk_label_set_ellipsize(GTK_LABEL(lbl_w), PANGO_ELLIPSIZE_END);
            gtk_box_append(GTK_BOX(row_box), lbl_w);
        }

        GtkWidget *list_row = gtk_list_box_row_new();
        gtk_list_box_row_set_child(GTK_LIST_BOX_ROW(list_row), row_box);

        /* Store path + metadata on the row for retrieval on selection */
        char *path_copy = g_strdup(r->path);
        char *id_copy   = g_strdup(r->patient_id);
        char *lbl_copy  = g_strdup(r->session_label);
        g_object_set_data_full(G_OBJECT(list_row), "session-path", path_copy, g_free);
        g_object_set_data_full(G_OBJECT(list_row), "patient-id",   id_copy,   g_free);
        g_object_set_data_full(G_OBJECT(list_row), "session-label",lbl_copy,  g_free);

        gtk_list_box_append(GTK_LIST_BOX(list), list_row);
    }

    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scroll), list);
    gtk_box_append(GTK_BOX(outer), scroll);

    /* Open selected button */
    ld->open_btn = gtk_button_new_with_label("Open Selected");
    gtk_widget_set_name(ld->open_btn, "launch-btn-dim");
    gtk_widget_set_size_request(ld->open_btn, -1, 48);
    g_signal_connect(ld->open_btn, "clicked", G_CALLBACK(launch_commit_open), ld);
    gtk_box_append(GTK_BOX(outer), ld->open_btn);

    gtk_window_set_child(GTK_WINDOW(ld->window), outer);
    gtk_window_present(GTK_WINDOW(ld->window));
}

/* ── Public: create main window ─────────────────────────────────────────── */
/* Connected to "close-request", not "destroy" (see window_create below) —
 * this must run BEFORE any teardown starts. window_autosave() touches
 * g_save_indicator (a sibling widget in the drag-handle titlebar), and
 * "destroy" fires DURING widget-tree teardown, which had already begun
 * disposing children by the time this ran from that signal: confirmed via
 * a real coredump (2026-08-25, systemd-coredump on a live clinical session)
 * with window_autosave crashing directly inside on_main_window_close — the
 * gtk_label_set_text() call on g_save_indicator hit an already-disposed
 * widget. That silently killed the process before it ever reached the
 * session_export_combined_pdf/session_export_combined_focus_pdf calls
 * below, which is why combined.pdf was going missing for real sessions
 * despite combined.png exporting fine every time. Returning FALSE lets the
 * window's default close-request handling (destroy) proceed normally
 * afterward.
 *
 * Re-entrancy guard (merged-app embedding spike, 2026-08-25): closing now
 * calls integration_destroy_tui(), which (in embedded mode) directly and
 * SYNCHRONOUSLY calls into gpab's Python to close ITS window — which,
 * coupled the same way on the Python side, calls straight back into
 * bodychart's own gtk_window_close(), re-entering this handler before the
 * first call has returned. g_closing makes the second entry a no-op,
 * mirroring app.py::TrialWindow._closing on the Python side of the same
 * coupling. Static rather than an AppState field since there's only ever
 * one bodychart main window in this process. */
static gboolean g_closing = FALSE;

static gboolean on_main_window_close(GtkWidget *w, gpointer data)
{
    (void)w;
    if (g_closing) return FALSE;
    g_closing = TRUE;

    AppState *app = data;
    integration_destroy_tui(app);
    persistence_monitor_stop(app);
    window_autosave(app);
    /* Re-render combined_focus.png unconditionally — window_autosave's if(ok)
     * chain can skip it if an earlier focus export fails, leaving a stale or
     * missing file that causes session_export_combined_focus_pdf to silently
     * do nothing. */
    session_export_combined_focus_png(app);
    session_export_combined_pdf(app);
    session_export_combined_focus_pdf(app);
    return FALSE;
}

/* Deferred fullscreen — waits 200 ms after the window appears before requesting
 * fullscreen.  One frame-clock tick (~16 ms) is not reliably enough for Mutter
 * to complete the windowed xdg_toplevel configure round-trip and register the
 * surface with zwp_tablet_v2; a short timeout gives the compositor enough time
 * regardless of display resolution or compositor load. */
static gboolean deferred_fullscreen(gpointer w)
{
    gtk_window_fullscreen(GTK_WINDOW(w));
    return G_SOURCE_REMOVE;
}

void window_create(AppState *app, GtkApplication *gtk_app)
{
    g_app_ref = app;
    app->toolbar_update_cb    = update_toolbar_state;
    app->show_note_wizard_cb  = show_note_wizard;
    app->show_ppt_entry_cb    = show_ppt_entry;
    app->request_clear_cb     = request_clear;
    apply_css();

    app->window = gtk_application_window_new(gtk_app);
    gtk_window_set_title(GTK_WINDOW(app->window), "PhysioChart");
    gtk_window_set_default_size(GTK_WINDOW(app->window), 900, 700);
    gtk_window_set_decorated(GTK_WINDOW(app->window), FALSE);

    g_signal_connect(app->window, "close-request",
                     G_CALLBACK(on_main_window_close), app);

    GtkWidget *hbox = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_window_set_child(GTK_WINDOW(app->window), hbox);

    gtk_box_append(GTK_BOX(hbox), build_sidebar(app));

    GtkWidget *canvas = canvas_new(app);
    gtk_widget_set_hexpand(canvas, TRUE);
    gtk_widget_set_vexpand(canvas, TRUE);
    gtk_box_append(GTK_BOX(hbox), canvas);

    GtkEventController *key_ctrl = gtk_event_controller_key_new();
    gtk_widget_add_controller(app->window, key_ctrl);
    g_signal_connect(key_ctrl, "key-pressed",
                     G_CALLBACK(on_key_pressed), app);

    /* Show session info in window title */
    if (app->patient_id[0]) {
        char title[128];
        if (app->session_label[0])
            snprintf(title, sizeof(title), "PhysioChart — %s · %s",
                     app->patient_id, app->session_label);
        else
            snprintf(title, sizeof(title), "PhysioChart — %s", app->patient_id);
        gtk_window_set_title(GTK_WINDOW(app->window), title);
    }

    update_toolbar_state(app);
    gtk_window_present(GTK_WINDOW(app->window));
    g_timeout_add(200, deferred_fullscreen, app->window);

    /* 30-second JSON autosave — JSON only, no PNG export overhead */
    g_timeout_add_seconds(30, on_autosave_timer, NULL);
}
