#include "session.h"
#include <cairo/cairo.h>
#include <cairo/cairo-svg.h>
#include <cairo/cairo-pdf.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <sys/stat.h>
#include <errno.h>

/* ── Export layout constants ─────────────────────────────────────────────── *
 * Quad: ant(EU×EU*2) | post(EU×EU*2) | right-top(EU/2×EU) + right-bot      *
 *       Total: 2.5EU × 2EU = 1000×800 px  — larger with more padding.      *
 * Single: one view at SINGLE_W × SINGLE_H (1:2 ratio).                      *
 * EXPORT_ZOOM < 1.0 adds margin so edge strokes are never clipped.           */
#define EU           400.0
#define EXPORT_W     (EU * 2.5)
#define EXPORT_H     (EU * 2.0)
#define SINGLE_W     533.0
#define SINGLE_H     1066.0
#define EXPORT_ZOOM  0.96

typedef struct {
    BodyView view;
    double   x, y, w, h;
    int      col_idx;
} ExportSlot;

static const BodyView SINGLE_VIEWS[4] = {
    VIEW_ANTERIOR, VIEW_POSTERIOR, VIEW_LATERAL_L, VIEW_LATERAL_R
};

static void export_dims(AppState *app, double *out_w, double *out_h)
{
    if (app->layout_mode == LAYOUT_QUAD) { *out_w = EXPORT_W; *out_h = EXPORT_H; }
    else                                 { *out_w = SINGLE_W; *out_h = SINGLE_H; }
}

/* ── Renderers ───────────────────────────────────────────────────────────── */

/* Export render: fixed zoom=EXPORT_ZOOM, pan=0 → body centred with margin. */
static void render_all_views_export(AppState *app, cairo_t *cr)
{
    cairo_set_source_rgb(cr, 1.0, 1.0, 1.0);
    cairo_paint(cr);

    if (app->layout_mode == LAYOUT_QUAD) {
        ExportSlot slots[4] = {
            { VIEW_ANTERIOR,              0,    0,    EU,   EU*2, 0 },
            { VIEW_POSTERIOR,             EU,   0,    EU,   EU*2, 1 },
            { app->right_slot_views[0],   EU*2, 0,    EU/2, EU,   2 },
            { app->right_slot_views[1],   EU*2, EU,   EU/2, EU,   3 },
        };
        for (int i = 0; i < 4; i++) {
            cairo_save(cr);
            cairo_translate(cr, slots[i].x, slots[i].y);
            cairo_rectangle(cr, 0, 0, slots[i].w, slots[i].h);
            cairo_clip(cr);
            canvas_render_view(app, cr, slots[i].view,
                               slots[i].w, slots[i].h,
                               EXPORT_ZOOM, 0.0, 0.0);
            cairo_restore(cr);
        }
    } else {
        int slot = (int)app->layout_mode - 1;
        canvas_render_view(app, cr, SINGLE_VIEWS[slot],
                           SINGLE_W, SINGLE_H, EXPORT_ZOOM, 0.0, 0.0);
    }

    /* Floating ROM charts sit above every panel — bake them in for the
     * objective export at the same fractional positions as on screen. */
    if (app->current_mode == APP_MODE_OBJECTIVE) {
        double gw, gh;
        export_dims(app, &gw, &gh);
        gonio_charts_render(app, cr, gw, gh, FALSE);
    }
}

/* Focus dims: quad uses fixed export size; single uses actual widget pixels.
 * Falls back to SINGLE_W/H if the widget is gone or sized to 0 (e.g. on destroy). */
static void focus_dims(AppState *app, double *out_w, double *out_h)
{
    if (app->layout_mode == LAYOUT_QUAD) {
        *out_w = EXPORT_W; *out_h = EXPORT_H;
    } else {
        int slot = (int)app->layout_mode - 1;
        GtkWidget *da = app->single_da[slot];
        double dw = da ? (double)gtk_widget_get_width(da)  : 0.0;
        double dh = da ? (double)gtk_widget_get_height(da) : 0.0;
        *out_w = dw > 0.0 ? dw : SINGLE_W;
        *out_h = dh > 0.0 ? dh : SINGLE_H;
    }
}

/* Focus render: live zoom/pan with actual widget size in single-view mode. */
static void render_all_views_focus(AppState *app, cairo_t *cr)
{
    cairo_set_source_rgb(cr, 1.0, 1.0, 1.0);
    cairo_paint(cr);

    if (app->layout_mode == LAYOUT_QUAD) {
        ExportSlot slots[4] = {
            { VIEW_ANTERIOR,              0,    0,    EU,   EU*2, 0 },
            { VIEW_POSTERIOR,             EU,   0,    EU,   EU*2, 1 },
            { app->right_slot_views[0],   EU*2, 0,    EU/2, EU,   2 },
            { app->right_slot_views[1],   EU*2, EU,   EU/2, EU,   3 },
        };
        for (int i = 0; i < 4; i++) {
            cairo_save(cr);
            cairo_translate(cr, slots[i].x, slots[i].y);
            cairo_rectangle(cr, 0, 0, slots[i].w, slots[i].h);
            cairo_clip(cr);
            canvas_render_view(app, cr, slots[i].view,
                               slots[i].w, slots[i].h,
                               app->col_zoom[slots[i].col_idx],
                               app->col_pan_x[slots[i].col_idx],
                               app->col_pan_y[slots[i].col_idx]);
            cairo_restore(cr);
        }
    } else {
        int slot = (int)app->layout_mode - 1;
        GtkWidget *da = app->single_da[slot];
        double dw = da ? (double)gtk_widget_get_width(da)  : 0.0;
        double dh = da ? (double)gtk_widget_get_height(da) : 0.0;
        double w = dw > 0.0 ? dw : SINGLE_W;
        double h = dh > 0.0 ? dh : SINGLE_H;
        canvas_render_view(app, cr, SINGLE_VIEWS[slot],
                           w, h,
                           app->single_zoom[slot],
                           app->single_pan_x[slot],
                           app->single_pan_y[slot]);
    }

    if (app->current_mode == APP_MODE_OBJECTIVE) {
        double gw, gh;
        focus_dims(app, &gw, &gh);
        gonio_charts_render(app, cr, gw, gh, FALSE);
    }
}

/* Live render (uses current zoom/pan — kept for SVG export). */
static void render_all_views_live(AppState *app, cairo_t *cr)
{
    cairo_set_source_rgb(cr, 1.0, 1.0, 1.0);
    cairo_paint(cr);

    if (app->layout_mode == LAYOUT_QUAD) {
        ExportSlot slots[4] = {
            { VIEW_ANTERIOR,              0,    0,    EU,   EU*2, 0 },
            { VIEW_POSTERIOR,             EU,   0,    EU,   EU*2, 1 },
            { app->right_slot_views[0],   EU*2, 0,    EU/2, EU,   2 },
            { app->right_slot_views[1],   EU*2, EU,   EU/2, EU,   3 },
        };
        for (int i = 0; i < 4; i++) {
            cairo_save(cr);
            cairo_translate(cr, slots[i].x, slots[i].y);
            cairo_rectangle(cr, 0, 0, slots[i].w, slots[i].h);
            cairo_clip(cr);
            canvas_render_view(app, cr, slots[i].view,
                               slots[i].w, slots[i].h,
                               app->col_zoom[slots[i].col_idx],
                               app->col_pan_x[slots[i].col_idx],
                               app->col_pan_y[slots[i].col_idx]);
            cairo_restore(cr);
        }
    } else {
        int slot = (int)app->layout_mode - 1;
        canvas_render_view(app, cr, SINGLE_VIEWS[slot],
                           SINGLE_W, SINGLE_H,
                           app->single_zoom[slot],
                           app->single_pan_x[slot],
                           app->single_pan_y[slot]);
    }

    if (app->current_mode == APP_MODE_OBJECTIVE) {
        double gw, gh;
        export_dims(app, &gw, &gh);
        gonio_charts_render(app, cr, gw, gh, FALSE);
    }
}

/* ── Path helpers ────────────────────────────────────────────────────────── */

void session_build_path(AppState *app, const char *suffix, char *buf, size_t len)
{
    snprintf(buf, len, "%s/%s_%s", app->session_dir, app->session_name, suffix);
}

static void ensure_save_dir(char *buf, size_t len)
{
    const char *home = g_get_home_dir();
    snprintf(buf, len, "%s/PAB", home);
    if (mkdir(buf, 0755) != 0 && errno != EEXIST)
        snprintf(buf, len, "%s", home);
}

void session_auto_path(char *buf, size_t len, const char *ext)
{
    char dir[512];
    ensure_save_dir(dir, sizeof(dir));
    time_t now = time(NULL);
    struct tm *t = localtime(&now);
    char ts[20];
    strftime(ts, sizeof(ts), "%Y%m%d%H%M", t);
    snprintf(buf, len, "%s/BodyChart%s.%s", dir, ts, ext);
}

/* ── Public API ──────────────────────────────────────────────────────────── */

gboolean session_export_subj_png(AppState *app)
{
    if (!app->session_dir[0] || !app->session_name[0]) return FALSE;
    char path[1024];
    session_build_path(app, "subj.png", path, sizeof(path));

    AppMode saved_mode = app->current_mode;
    app->current_mode = APP_MODE_SUBJECTIVE;

    double w, h;
    export_dims(app, &w, &h);
    cairo_surface_t *surf = cairo_image_surface_create(
        CAIRO_FORMAT_RGB24, (int)w, (int)h);
    cairo_t *cr = cairo_create(surf);
    render_all_views_export(app, cr);
    cairo_destroy(cr);
    cairo_status_t st = cairo_surface_write_to_png(surf, path);
    cairo_surface_destroy(surf);

    app->current_mode = saved_mode;

    if (st != CAIRO_STATUS_SUCCESS) {
        fprintf(stderr, "session_export_subj_png: failed: %s\n",
                cairo_status_to_string(st));
        return FALSE;
    }
    fprintf(stderr, "session_export_subj_png: %s\n", path);
    return TRUE;
}

gboolean session_export_obj_png(AppState *app)
{
    if (!app->session_dir[0] || !app->session_name[0]) return FALSE;
    char path[1024];
    session_build_path(app, "obj.png", path, sizeof(path));

    AppMode saved_mode = app->current_mode;
    app->current_mode = APP_MODE_OBJECTIVE;

    double w, h;
    export_dims(app, &w, &h);
    cairo_surface_t *surf = cairo_image_surface_create(
        CAIRO_FORMAT_RGB24, (int)w, (int)h);
    cairo_t *cr = cairo_create(surf);
    render_all_views_export(app, cr);
    cairo_destroy(cr);
    cairo_status_t st = cairo_surface_write_to_png(surf, path);
    cairo_surface_destroy(surf);

    app->current_mode = saved_mode;

    if (st != CAIRO_STATUS_SUCCESS) {
        fprintf(stderr, "session_export_obj_png: failed: %s\n",
                cairo_status_to_string(st));
        return FALSE;
    }
    fprintf(stderr, "session_export_obj_png: %s\n", path);
    return TRUE;
}

gboolean session_export_combined_png(AppState *app)
{
    if (!app->session_dir[0] || !app->session_name[0]) return FALSE;
    char path[1024];
    session_build_path(app, "combined.png", path, sizeof(path));

    AppMode saved_mode = app->current_mode;
    double w, h;
    export_dims(app, &w, &h);

    /* Create temporary surfaces for subjective and objective */
    cairo_surface_t *surf_sx = cairo_image_surface_create(
        CAIRO_FORMAT_RGB24, (int)w, (int)h);
    cairo_t *cr_sx = cairo_create(surf_sx);
    app->current_mode = APP_MODE_SUBJECTIVE;
    render_all_views_export(app, cr_sx);
    cairo_destroy(cr_sx);

    cairo_surface_t *surf_obj = cairo_image_surface_create(
        CAIRO_FORMAT_RGB24, (int)w, (int)h);
    cairo_t *cr_obj = cairo_create(surf_obj);
    app->current_mode = APP_MODE_OBJECTIVE;
    render_all_views_export(app, cr_obj);
    cairo_destroy(cr_obj);

    /* Create final combined surface (double height) */
    cairo_surface_t *surf = cairo_image_surface_create(
        CAIRO_FORMAT_RGB24, (int)w, (int)(h * 2));
    cairo_t *cr = cairo_create(surf);

    /* Copy subjective to top */
    cairo_set_source_surface(cr, surf_sx, 0, 0);
    cairo_paint(cr);

    /* Copy objective to bottom */
    cairo_set_source_surface(cr, surf_obj, 0, h);
    cairo_paint(cr);

    /* Draw labels */
    cairo_set_font_size(cr, 16.0);
    cairo_set_source_rgb(cr, 0.1, 0.1, 0.1);
    cairo_move_to(cr, 10.0, 20.0);
    cairo_show_text(cr, "Subjective");

    cairo_move_to(cr, 10.0, h + 20.0);
    cairo_show_text(cr, "Objective");

    cairo_destroy(cr);

    /* Save final image */
    cairo_status_t st = cairo_surface_write_to_png(surf, path);
    cairo_surface_destroy(surf);
    cairo_surface_destroy(surf_sx);
    cairo_surface_destroy(surf_obj);

    app->current_mode = saved_mode;

    if (st != CAIRO_STATUS_SUCCESS) {
        fprintf(stderr, "session_export_combined_png: failed: %s\n",
                cairo_status_to_string(st));
        return FALSE;
    }
    fprintf(stderr, "session_export_combined_png: %s\n", path);
    return TRUE;
}

gboolean session_export_subj_focus_png(AppState *app)
{
    if (!app->session_dir[0] || !app->session_name[0]) return FALSE;
    char path[1024];
    session_build_path(app, "subj_focus.png", path, sizeof(path));

    AppMode saved_mode = app->current_mode;
    app->current_mode = APP_MODE_SUBJECTIVE;

    double w, h;
    focus_dims(app, &w, &h);
    cairo_surface_t *surf = cairo_image_surface_create(
        CAIRO_FORMAT_RGB24, (int)w, (int)h);
    cairo_t *cr = cairo_create(surf);
    render_all_views_focus(app, cr);
    cairo_destroy(cr);
    cairo_status_t st = cairo_surface_write_to_png(surf, path);
    cairo_surface_destroy(surf);

    app->current_mode = saved_mode;

    if (st != CAIRO_STATUS_SUCCESS) {
        fprintf(stderr, "session_export_subj_focus_png: failed: %s\n",
                cairo_status_to_string(st));
        return FALSE;
    }
    fprintf(stderr, "session_export_subj_focus_png: %s\n", path);
    return TRUE;
}

gboolean session_export_obj_focus_png(AppState *app)
{
    if (!app->session_dir[0] || !app->session_name[0]) return FALSE;
    char path[1024];
    session_build_path(app, "obj_focus.png", path, sizeof(path));

    AppMode saved_mode = app->current_mode;
    app->current_mode = APP_MODE_OBJECTIVE;

    double w, h;
    focus_dims(app, &w, &h);
    cairo_surface_t *surf = cairo_image_surface_create(
        CAIRO_FORMAT_RGB24, (int)w, (int)h);
    cairo_t *cr = cairo_create(surf);
    render_all_views_focus(app, cr);
    cairo_destroy(cr);
    cairo_status_t st = cairo_surface_write_to_png(surf, path);
    cairo_surface_destroy(surf);

    app->current_mode = saved_mode;

    if (st != CAIRO_STATUS_SUCCESS) {
        fprintf(stderr, "session_export_obj_focus_png: failed: %s\n",
                cairo_status_to_string(st));
        return FALSE;
    }
    fprintf(stderr, "session_export_obj_focus_png: %s\n", path);
    return TRUE;
}

gboolean session_export_combined_focus_png(AppState *app)
{
    if (!app->session_dir[0] || !app->session_name[0]) return FALSE;
    char path[1024];
    session_build_path(app, "combined_focus.png", path, sizeof(path));

    AppMode saved_mode = app->current_mode;
    double w, h;
    focus_dims(app, &w, &h);

    cairo_surface_t *surf_sx = cairo_image_surface_create(
        CAIRO_FORMAT_RGB24, (int)w, (int)h);
    cairo_t *cr_sx = cairo_create(surf_sx);
    app->current_mode = APP_MODE_SUBJECTIVE;
    render_all_views_focus(app, cr_sx);
    cairo_destroy(cr_sx);

    cairo_surface_t *surf_obj = cairo_image_surface_create(
        CAIRO_FORMAT_RGB24, (int)w, (int)h);
    cairo_t *cr_obj = cairo_create(surf_obj);
    app->current_mode = APP_MODE_OBJECTIVE;
    render_all_views_focus(app, cr_obj);
    cairo_destroy(cr_obj);

    cairo_surface_t *surf = cairo_image_surface_create(
        CAIRO_FORMAT_RGB24, (int)w, (int)(h * 2));
    cairo_t *cr = cairo_create(surf);

    cairo_set_source_surface(cr, surf_sx, 0, 0);
    cairo_paint(cr);
    cairo_set_source_surface(cr, surf_obj, 0, h);
    cairo_paint(cr);

    cairo_set_font_size(cr, 16.0);
    cairo_set_source_rgb(cr, 0.1, 0.1, 0.1);
    cairo_move_to(cr, 10.0, 20.0);
    cairo_show_text(cr, "Subjective");
    cairo_move_to(cr, 10.0, h + 20.0);
    cairo_show_text(cr, "Objective");

    cairo_destroy(cr);

    cairo_status_t st = cairo_surface_write_to_png(surf, path);
    cairo_surface_destroy(surf);
    cairo_surface_destroy(surf_sx);
    cairo_surface_destroy(surf_obj);

    app->current_mode = saved_mode;

    if (st != CAIRO_STATUS_SUCCESS) {
        fprintf(stderr, "session_export_combined_focus_png: failed: %s\n",
                cairo_status_to_string(st));
        return FALSE;
    }
    fprintf(stderr, "session_export_combined_focus_png: %s\n", path);
    return TRUE;
}

gboolean session_export_combined_pdf(AppState *app)
{
    if (!app->session_dir[0] || !app->session_name[0]) return FALSE;
    char png_path[1024];
    session_build_path(app, "combined.png", png_path, sizeof(png_path));

    const char *home = g_get_home_dir();
    char cmd[2048];
    snprintf(cmd, sizeof(cmd), "\"%s/.local/bin/placepdf\" \"%s\"", home, png_path);
    int ret = system(cmd);
    if (ret != 0) {
        fprintf(stderr, "session_export_combined_pdf: placepdf failed (exit %d)\n", ret);
        return FALSE;
    }
    fprintf(stderr, "session_export_combined_pdf: PDF written for %s\n", png_path);
    return TRUE;
}

gboolean session_export_combined_focus_pdf(AppState *app)
{
    if (!app->session_dir[0] || !app->session_name[0]) return FALSE;
    char png_path[1024];
    session_build_path(app, "combined_focus.png", png_path, sizeof(png_path));

    const char *home = g_get_home_dir();
    char cmd[2048];
    snprintf(cmd, sizeof(cmd), "\"%s/.local/bin/placepdf\" \"%s\"", home, png_path);
    int ret = system(cmd);
    if (ret != 0) {
        fprintf(stderr, "session_export_combined_focus_pdf: placepdf failed (exit %d)\n", ret);
        return FALSE;
    }
    fprintf(stderr, "session_export_combined_focus_pdf: PDF written for %s\n", png_path);
    return TRUE;
}

gboolean session_export_png(AppState *app, const char *path)
{
    double w, h;
    export_dims(app, &w, &h);
    cairo_surface_t *surf = cairo_image_surface_create(
        CAIRO_FORMAT_RGB24, (int)w, (int)h);
    cairo_t *cr = cairo_create(surf);
    render_all_views_export(app, cr);
    cairo_destroy(cr);
    cairo_status_t st = cairo_surface_write_to_png(surf, path);
    cairo_surface_destroy(surf);
    if (st != CAIRO_STATUS_SUCCESS) {
        fprintf(stderr, "session_export_png: failed: %s\n",
                cairo_status_to_string(st));
        return FALSE;
    }
    fprintf(stderr, "session_export_png: %s\n", path);
    return TRUE;
}

gboolean session_export_pdf(AppState *app, const char *path)
{
    double w, h;
    export_dims(app, &w, &h);
    cairo_surface_t *surf = cairo_pdf_surface_create(path, w, h);
    if (cairo_surface_status(surf) != CAIRO_STATUS_SUCCESS) {
        cairo_surface_destroy(surf);
        return FALSE;
    }
    cairo_t *cr = cairo_create(surf);
    render_all_views_export(app, cr);
    cairo_show_page(cr);
    cairo_destroy(cr);
    cairo_surface_destroy(surf);
    fprintf(stderr, "session_export_pdf: %s\n", path);
    return TRUE;
}

gboolean session_save(AppState *app, const char *path)
{
    double w, h;
    export_dims(app, &w, &h);
    cairo_surface_t *surf = cairo_svg_surface_create(path, w, h);
    if (cairo_surface_status(surf) != CAIRO_STATUS_SUCCESS) {
        cairo_surface_destroy(surf);
        return FALSE;
    }
    cairo_t *cr = cairo_create(surf);
    render_all_views_live(app, cr);
    cairo_destroy(cr);
    cairo_surface_destroy(surf);
    fprintf(stderr, "session_save: %s\n", path);
    return TRUE;
}

gboolean session_load(AppState *app, const char *path)
{
    (void)app; (void)path;
    fprintf(stderr, "session_load: use persistence_load instead\n");
    return FALSE;
}
