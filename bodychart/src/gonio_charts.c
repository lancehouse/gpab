#include "gonio_charts.h"
#include "canvas.h"

#include <glib/gstdio.h>
#include <string.h>
#include <math.h>

/* Close (hide) badge and resize grip size in device px — fixed, not scaled
 * with the chart so they stay tappable at any chart size. */
#define GC_CLOSE_PX  22.0
#define GC_HANDLE_PX 22.0

/* Default tiled layout (fractions of the objective canvas). Charts land in a
 * non-overlapping grid, filling left-to-right then wrapping to the next row
 * — never cascaded/stacked. A chart at scale 1.0 is GONIO_CHART_BASE_FRAC
 * (~0.28) wide, so three fit across; GC_TILE_DX/DY leave a small gutter.
 * The user drags/scales from here; this is only the starting arrangement. */
#define GC_TILE_COLS 3
#define GC_TILE_MX   0.015    /* left margin  */
#define GC_TILE_MY   0.030    /* top margin   */
#define GC_TILE_DX   0.325    /* column pitch */
#define GC_TILE_DY   0.240    /* row pitch    */

static void gonio_tile_pos(int i, double *fx, double *fy)
{
    int col = i % GC_TILE_COLS;
    int row = i / GC_TILE_COLS;
    *fx = GC_TILE_MX + col * GC_TILE_DX;
    *fy = GC_TILE_MY + row * GC_TILE_DY;
}

/* ── directory sync ─────────────────────────────────────────────────────── */

static int find_chart(AppState *app, const char *base)
{
    for (int i = 0; i < app->gonio_chart_count; i++)
        if (strcmp(app->gonio_charts[i].file, base) == 0)
            return i;
    return -1;
}

static void charts_dir(AppState *app, char *buf, size_t len)
{
    g_snprintf(buf, len, "%s/gonio_charts", app->session_dir);
}

void gonio_charts_rescan(AppState *app)
{
    if (!app->session_dir[0]) return;

    /* The sweep below compacts app->gonio_charts[], so any raw index into it
     * is stale afterwards. A rescan only runs on load / on entering
     * Objective mode — never mid-drag — so just drop them. */
    app->gonio_chart_active_idx = -1;
    app->gonio_chart_drag_idx   = -1;
    app->gonio_chart_resizing   = FALSE;

    char dir[600];
    charts_dir(app, dir, sizeof(dir));

    GError *err = NULL;
    GDir *d = g_dir_open(dir, 0, &err);
    if (!d) {                       /* no import yet — drop any stale entries */
        if (err) g_error_free(err);
        for (int i = 0; i < app->gonio_chart_count; i++)
            if (app->gonio_charts[i].surf)
                cairo_surface_destroy(app->gonio_charts[i].surf);
        app->gonio_chart_count = 0;
        return;
    }

    /* Collect the .png names, sorted — the NN_ prefix gives capture order. */
    GPtrArray *names = g_ptr_array_new_with_free_func(g_free);
    const char *name;
    while ((name = g_dir_read_name(d))) {
        if (g_str_has_suffix(name, ".png"))
            g_ptr_array_add(names, g_strdup(name));
    }
    g_dir_close(d);
    g_ptr_array_sort_values(names, (GCompareFunc)g_strcmp0);

    /* Mark-and-sweep: which existing entries still have a file. */
    gboolean seen[MAX_GONIO_CHARTS] = { FALSE };
    for (guint k = 0; k < names->len; k++) {
        const char *base = g_ptr_array_index(names, k);
        int idx = find_chart(app, base);
        if (idx >= 0) {
            seen[idx] = TRUE;
            continue;
        }
        if (app->gonio_chart_count >= MAX_GONIO_CHARTS) continue;
        int slot = app->gonio_chart_count;   /* next free grid cell */
        GonioChart *gc = &app->gonio_charts[slot];
        memset(gc, 0, sizeof(*gc));
        g_strlcpy(gc->file, base, sizeof(gc->file));
        gonio_tile_pos(slot, &gc->fx, &gc->fy);   /* tiled, wraps to a new row */
        gc->scale   = 1.0;
        gc->visible = TRUE;
        seen[slot] = TRUE;
        app->gonio_chart_count++;
    }
    g_ptr_array_free(names, TRUE);

    /* Sweep entries whose file vanished. */
    int w = 0;
    for (int i = 0; i < app->gonio_chart_count; i++) {
        if (seen[i]) {
            if (w != i) app->gonio_charts[w] = app->gonio_charts[i];
            w++;
        } else if (app->gonio_charts[i].surf) {
            cairo_surface_destroy(app->gonio_charts[i].surf);
        }
    }
    app->gonio_chart_count = w;
    if (app->gonio_chart_active_idx >= app->gonio_chart_count)
        app->gonio_chart_active_idx = -1;
}

/* ── surface cache ─────────────────────────────────────────────────────── */

cairo_surface_t *gonio_chart_get_surface(AppState *app, GonioChart *gc)
{
    char path[720];
    g_snprintf(path, sizeof(path), "%s/gonio_charts/%s", app->session_dir, gc->file);

    GStatBuf st;
    gint64 mtime = (g_stat(path, &st) == 0) ? (gint64)st.st_mtime : 0;

    if (gc->surf && gc->surf_mtime == mtime &&
        cairo_surface_status(gc->surf) == CAIRO_STATUS_SUCCESS)
        return gc->surf;

    if (gc->surf) {
        cairo_surface_destroy(gc->surf);
        gc->surf = NULL;
    }
    cairo_surface_t *s = cairo_image_surface_create_from_png(path);
    if (cairo_surface_status(s) != CAIRO_STATUS_SUCCESS) {
        cairo_surface_destroy(s);
        gc->surf = NULL;
        gc->surf_mtime = mtime;   /* don't hammer the disk every frame */
        return NULL;
    }
    gc->surf = s;
    gc->surf_mtime = mtime;
    return gc->surf;
}

int gonio_charts_reset_layout(AppState *app)
{
    for (int i = 0; i < app->gonio_chart_count; i++) {
        GonioChart *gc = &app->gonio_charts[i];
        gc->visible = TRUE;
        gc->scale   = 1.0;
        gonio_tile_pos(i, &gc->fx, &gc->fy);
    }
    return app->gonio_chart_count;
}

void gonio_chart_bump_active_scale(AppState *app, double factor)
{
    int i = app->gonio_chart_active_idx;
    if (i < 0 || i >= app->gonio_chart_count) return;
    double s = app->gonio_charts[i].scale;
    if (s <= 0) s = 1.0;
    s *= factor;
    if (s < 0.15) s = 0.15;
    if (s > 6.0)  s = 6.0;
    app->gonio_charts[i].scale = s;
}

void gonio_charts_free_surfaces(AppState *app)
{
    for (int i = 0; i < app->gonio_chart_count; i++) {
        if (app->gonio_charts[i].surf) {
            cairo_surface_destroy(app->gonio_charts[i].surf);
            app->gonio_charts[i].surf = NULL;
        }
        app->gonio_charts[i].surf_mtime = 0;
    }
}

/* ── geometry ──────────────────────────────────────────────────────────── */

/* Resolve a chart's drawn rectangle in a w x h area. Returns FALSE if the
 * PNG can't be loaded (nothing to draw / hit). */
static gboolean chart_rect(AppState *app, GonioChart *gc, double w, double h,
                           double *x, double *y, double *cw, double *ch)
{
    cairo_surface_t *s = gonio_chart_get_surface(app, gc);
    if (!s) return FALSE;
    double sw = cairo_image_surface_get_width(s);
    double sh = cairo_image_surface_get_height(s);
    if (sw <= 0 || sh <= 0) return FALSE;

    *cw = GONIO_CHART_BASE_FRAC * w * (gc->scale > 0 ? gc->scale : 1.0);
    *ch = *cw * (sh / sw);
    *x  = gc->fx * w;
    *y  = gc->fy * h;
    return TRUE;
}

/* ── render ────────────────────────────────────────────────────────────── */

void gonio_charts_render(AppState *app, cairo_t *cr, double w, double h,
                         gboolean interactive)
{
    for (int i = 0; i < app->gonio_chart_count; i++) {
        GonioChart *gc = &app->gonio_charts[i];
        if (!gc->visible) continue;

        double x, y, cw, ch;
        if (!chart_rect(app, gc, w, h, &x, &y, &cw, &ch)) continue;
        cairo_surface_t *s = gc->surf;
        double sw = cairo_image_surface_get_width(s);

        cairo_save(cr);
        /* Soft drop shadow so a chart over the body reads as "on top". */
        cairo_set_source_rgba(cr, 0, 0, 0, 0.18);
        cairo_rectangle(cr, x + 3, y + 3, cw, ch);
        cairo_fill(cr);

        /* The PNG itself, on an opaque white bed (the export PNGs have a
         * white ground already; the bed also covers any alpha). */
        cairo_rectangle(cr, x, y, cw, ch);
        cairo_set_source_rgb(cr, 1, 1, 1);
        cairo_fill(cr);

        cairo_save(cr);
        cairo_translate(cr, x, y);
        cairo_scale(cr, cw / sw, cw / sw);
        cairo_set_source_surface(cr, s, 0, 0);
        cairo_paint(cr);
        cairo_restore(cr);

        if (interactive) {
            gboolean active = (i == app->gonio_chart_active_idx);
            cairo_set_line_width(cr, active ? 2.0 : 1.0);
            cairo_set_source_rgba(cr, active ? 0.15 : 0.55,
                                       active ? 0.45 : 0.55,
                                       active ? 0.85 : 0.55,
                                       active ? 0.95 : 0.55);
            cairo_rectangle(cr, x + 0.5, y + 0.5, cw - 1, ch - 1);
            cairo_stroke(cr);

            /* Hide (x) badge, top-right, fixed device size. */
            double bx = x + cw - GC_CLOSE_PX, by = y;
            cairo_set_source_rgba(cr, 0.10, 0.10, 0.14, 0.75);
            cairo_rectangle(cr, bx, by, GC_CLOSE_PX, GC_CLOSE_PX);
            cairo_fill(cr);
            cairo_set_source_rgba(cr, 1, 1, 1, 0.9);
            cairo_set_line_width(cr, 1.6);
            cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
            double p = 6.0;
            cairo_move_to(cr, bx + p,               by + p);
            cairo_line_to(cr, bx + GC_CLOSE_PX - p,  by + GC_CLOSE_PX - p);
            cairo_move_to(cr, bx + GC_CLOSE_PX - p,  by + p);
            cairo_line_to(cr, bx + p,               by + GC_CLOSE_PX - p);
            cairo_stroke(cr);

            /* Resize grip, bottom-right — a few diagonal ticks. */
            double hx = x + cw - GC_HANDLE_PX, hy = y + ch - GC_HANDLE_PX;
            cairo_set_source_rgba(cr, 0.10, 0.10, 0.14, 0.75);
            cairo_rectangle(cr, hx, hy, GC_HANDLE_PX, GC_HANDLE_PX);
            cairo_fill(cr);
            cairo_set_source_rgba(cr, 1, 1, 1, 0.9);
            cairo_set_line_width(cr, 1.4);
            for (double o = 5.0; o <= 15.0; o += 5.0) {
                cairo_move_to(cr, hx + GC_HANDLE_PX - o, hy + GC_HANDLE_PX - 3);
                cairo_line_to(cr, hx + GC_HANDLE_PX - 3, hy + GC_HANDLE_PX - o);
                cairo_stroke(cr);
            }
        }
        cairo_restore(cr);
    }
}

int gonio_chart_hit(AppState *app, double w, double h,
                    double px, double py,
                    gboolean *on_close, gboolean *on_resize)
{
    if (on_close)  *on_close  = FALSE;
    if (on_resize) *on_resize = FALSE;
    for (int i = app->gonio_chart_count - 1; i >= 0; i--) {   /* topmost first */
        GonioChart *gc = &app->gonio_charts[i];
        if (!gc->visible) continue;
        double x, y, cw, ch;
        if (!chart_rect(app, gc, w, h, &x, &y, &cw, &ch)) continue;
        if (px < x || px > x + cw || py < y || py > y + ch) continue;
        if (on_close && px >= x + cw - GC_CLOSE_PX && py <= y + GC_CLOSE_PX)
            *on_close = TRUE;
        else if (on_resize && px >= x + cw - GC_HANDLE_PX &&
                              py >= y + ch - GC_HANDLE_PX)
            *on_resize = TRUE;
        return i;
    }
    return -1;
}
