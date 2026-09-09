#include "canvas.h"
#include "stroke.h"
#include "body_outlines.h"
#include "overlays.h"
#include "overlay_svg.h"
#include "obj_chart.h"
#include <math.h>
#include <string.h>
#include <stdio.h>

/* ── Per-drawing-area context ────────────────────────────────────────────── *
 * g_col[0..3]  — quad view slots (anterior, posterior, lateral_l, lateral_r) *
 * g_col[4..7]  — matching single-view slots (same order)                    */
/* BLUR FIX: cache is now built at actual widget dimensions with the full
 * col transform applied, so it maps 1:1 to screen pixels.
 * ROLLBACK: uncomment the two #defines below and revert the three marked
 * sections in rebuild_stroke_cache and on_col_draw. */
/* #define STROKE_CACHE_W 400 */
/* #define STROKE_CACHE_H 800 */

typedef struct {
    AppState  *app;
    BodyView   view;
    double    *p_zoom;
    double    *p_pan_x;
    double    *p_pan_y;
    double     last_zoom_scale;
    double     last_cx, last_cy;
    double     mid_pan_x0, mid_pan_y0;  /* pan at start of middle-button drag */
    double     mouse_x, mouse_y;        /* last known cursor position (screen px) */
    gboolean   touch_drawing;           /* finger/mouse draw in progress */
    GtkWidget *da;
    GtkWidget *zoom_btn;
    GtkWidget *header_label;

    /* Committed-stroke offscreen cache.
     * Built at actual widget pixel dimensions with apply_col_transform applied,
     * so it maps 1:1 to screen pixels — no upsampling blur.
     * Rebuilt whenever stroke_version, widget size, zoom, or pan changes. */
    cairo_surface_t *stroke_cache;
    int              cache_stroke_version;
    int              cache_w, cache_h;               /* widget dims at last rebuild */
    double           cache_zoom, cache_pan_x, cache_pan_y; /* viewport at last rebuild */
} ColData;

static ColData g_col[8];

/* Fixed single-view slot order */
static const BodyView SINGLE_SLOT_VIEWS[4] = {
    VIEW_ANTERIOR, VIEW_POSTERIOR, VIEW_LATERAL_L, VIEW_LATERAL_R
};

/* ── Stroke rendering ────────────────────────────────────────────────────── *
 * All widths/sizes are body-space units (body = 200×400 bu). They scale      *
 * naturally with zoom because Cairo is already in body-space after the       *
 * col transform. Symbol patterns batch all geometry into one stroke/fill.    */
/* ts: scale factor for body-space widths on touch strokes.
 * Baked at draw time (1/draw_zoom), so body-space width is fixed after drawing.
 * Strokes naturally scale on screen with zoom — same as all other body features. */
static void draw_stroke(cairo_t *cr, const Stroke *s, const SymptomDef *sd,
                        const AppState *app, double zoom)
{
    if (s->n_pts < 1) return;
    const double ts = (s->draw_zoom > 0.0) ? (1.0 / s->draw_zoom) : 1.0;
    (void)zoom;

    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
    cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND);
    cairo_set_dash(cr, NULL, 0, 0);

    switch (sd->pattern) {

    case FILL_SOLID: {
        /* Pressure tracks within two bands selected by s->wide_mode:
         *   fine: 0.375–12.0 bu   wide: 1.5–16.0 bu */
        if (s->n_pts < 2) break;
        size_t n = s->n_pts;
        double p_cur = s->pts[0].pressure;
        double w_cur = ts * (s->wide_mode ? (1.5 + p_cur * 14.5) : (0.375 + p_cur * 11.625));
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_width(cr, w_cur);
        cairo_set_source_rgba(cr, sd->r, sd->g, sd->b, 0.8);
        cairo_move_to(cr, s->pts[0].x, s->pts[0].y);
        for (size_t i = 1; i < n; i++) {
            double p = (s->pts[i-1].pressure + s->pts[i].pressure) * 0.5;
            double w = ts * (s->wide_mode ? (1.5 + p * 14.5) : (0.375 + p * 11.625));
            if (fabs(w - w_cur) > 0.3) {
                cairo_stroke(cr);
                w_cur = w;
                cairo_set_line_width(cr, w_cur);
                cairo_set_source_rgba(cr, sd->r, sd->g, sd->b, 0.8);
                cairo_move_to(cr, s->pts[i-1].x, s->pts[i-1].y);
            }
            /* Catmull-Rom control points for segment pts[i-1] → pts[i] */
            double x0 = (i >= 2) ? (double)s->pts[i-2].x : 2.0*s->pts[i-1].x - s->pts[i].x;
            double y0 = (i >= 2) ? (double)s->pts[i-2].y : 2.0*s->pts[i-1].y - s->pts[i].y;
            double x3 = (i+1 < n) ? (double)s->pts[i+1].x : 2.0*s->pts[i].x - s->pts[i-1].x;
            double y3 = (i+1 < n) ? (double)s->pts[i+1].y : 2.0*s->pts[i].y - s->pts[i-1].y;
            double cp1x = s->pts[i-1].x + (s->pts[i].x - x0) / 6.0;
            double cp1y = s->pts[i-1].y + (s->pts[i].y - y0) / 6.0;
            double cp2x = s->pts[i].x   - (x3 - s->pts[i-1].x) / 6.0;
            double cp2y = s->pts[i].y   - (y3 - s->pts[i-1].y) / 6.0;
            cairo_curve_to(cr, cp1x, cp1y, cp2x, cp2y, s->pts[i].x, s->pts[i].y);
        }
        cairo_stroke(cr);
        break;
    }

    case FILL_DASHED: {
        /* Finer pink dashes; pressure sets width. thin: 0.3–6.0 bu  wide: 0.8–10.0 bu */
        if (s->n_pts < 2) break;
        size_t n = s->n_pts;
        double avg_p = 0.0;
        for (size_t i = 0; i < n; i++) avg_p += s->pts[i].pressure;
        avg_p /= (double)n;
        cairo_set_line_width(cr, ts * (s->wide_mode ? (0.8 + avg_p * 9.2) : (0.3 + avg_p * 5.7)));
        cairo_set_source_rgba(cr, sd->r, sd->g, sd->b, 0.8);
        double dashes[2] = { ts * 6.0, ts * 4.0 };
        cairo_set_dash(cr, dashes, 2, 0);
        cairo_move_to(cr, s->pts[0].x, s->pts[0].y);
        for (size_t i = 1; i < n; i++) {
            double x0 = (i >= 2) ? (double)s->pts[i-2].x : 2.0*s->pts[i-1].x - s->pts[i].x;
            double y0 = (i >= 2) ? (double)s->pts[i-2].y : 2.0*s->pts[i-1].y - s->pts[i].y;
            double x3 = (i+1 < n) ? (double)s->pts[i+1].x : 2.0*s->pts[i].x - s->pts[i-1].x;
            double y3 = (i+1 < n) ? (double)s->pts[i+1].y : 2.0*s->pts[i].y - s->pts[i-1].y;
            double cp1x = s->pts[i-1].x + (s->pts[i].x - x0) / 6.0;
            double cp1y = s->pts[i-1].y + (s->pts[i].y - y0) / 6.0;
            double cp2x = s->pts[i].x   - (x3 - s->pts[i-1].x) / 6.0;
            double cp2y = s->pts[i].y   - (y3 - s->pts[i-1].y) / 6.0;
            cairo_curve_to(cr, cp1x, cp1y, cp2x, cp2y, s->pts[i].x, s->pts[i].y);
        }
        cairo_stroke(cr);
        cairo_set_dash(cr, NULL, 0, 0);
        break;
    }

    case FILL_DOTS_SPACED: {
        /* Pressure controls COUNT of dots placed side-by-side perpendicular to stroke:
         *   p<0.40 → 1 dot   0.40–0.65 → 2 dots   0.65–0.82 → 3 dots   ≥0.82 → 4 dots
         * Dots are all the same radius (fixed, no size scaling with pressure). */
        double dot_r   = ts * (double)app->pen_dot_radius;
        double spacing = ts * (double)app->pen_dot_spacing;
        double dot_gap = dot_r * 2.5;  /* centre-to-centre perpendicular gap */
        cairo_set_source_rgba(cr, sd->r, sd->g, sd->b, 0.8);

        /* Stamp helper macro — places cnt dots perpendicular to (nx, ny) */
        #define STAMP_DOTS(px_, py_, nx_, ny_, cnt_) do { \
            double _o0 = -((cnt_) - 1) * 0.5 * dot_gap; \
            for (int _k = 0; _k < (cnt_); _k++) { \
                double _off = _o0 + _k * dot_gap; \
                cairo_new_sub_path(cr); \
                cairo_arc(cr, (px_) + (nx_)*_off, (py_) + (ny_)*_off, \
                          dot_r, 0, 2*M_PI); \
            } \
        } while (0)

        /* First point — no segment tangent yet; perp defaults to (0,1) */
        {
            double p = s->pts[0].pressure;
            int cnt = (p < 0.40) ? 1 : (p < 0.65) ? 2 : (p < 0.82) ? 3 : 4;
            STAMP_DOTS(s->pts[0].x, s->pts[0].y, 0.0, 1.0, cnt);
        }

        double accum = 0.0;
        for (size_t i = 1; i < s->n_pts; i++) {
            double dx  = s->pts[i].x - s->pts[i-1].x;
            double dy  = s->pts[i].y - s->pts[i-1].y;
            double len = sqrt(dx*dx + dy*dy);
            if (len < 1e-9) continue;
            double inv = 1.0 / len;
            double nx  = -dy * inv;   /* perpendicular to tangent */
            double ny  =  dx * inv;
            double need = spacing - accum;
            while (need <= len) {
                double t   = need / len;
                double px  = s->pts[i-1].x + t * dx;
                double py  = s->pts[i-1].y + t * dy;
                double p   = s->pts[i-1].pressure * (1.0 - t) + s->pts[i].pressure * t;
                int cnt = (p < 0.40) ? 1 : (p < 0.65) ? 2 : (p < 0.82) ? 3 : 4;
                STAMP_DOTS(px, py, nx, ny, cnt);
                need += spacing;
            }
            accum = len - (need - spacing);
        }
        #undef STAMP_DOTS
        cairo_fill(cr);
        break;
    }

    case FILL_H_STROKES: {
        /* Pressure controls dash LENGTH and COUNT (stacked vertically):
         *   p<0.45        → 1 short dash  (0.7× pen_dash_len)
         *   0.45–0.65     → 1 long dash   (1.4×)
         *   0.65–0.85     → 2 short dashes stacked
         *   ≥0.85         → 2 long dashes stacked
         * Dashes are always horizontal; stroke width set by pen_dash_width. */
        double dash_len = ts * (double)app->pen_dash_len;
        double spacing  = ts * (double)app->pen_dash_spacing;
        double lw       = ts * (double)app->pen_dash_width;
        double dash_gap = dash_len * 0.9 + lw;  /* vertical gap between stacked dashes */
        cairo_set_source_rgba(cr, sd->r, sd->g, sd->b, 0.8);
        cairo_set_line_width(cr, lw);

        #define STAMP_DASHES(px_, py_, p_) do { \
            int   _cnt  = ((p_) >= 0.65) ? 2 : 1; \
            int   _long = (((p_) >= 0.45) && ((p_) < 0.65)) || ((p_) >= 0.85); \
            double _hw  = _long ? dash_len * 1.4 : dash_len * 0.7; \
            double _o0  = -(_cnt - 1) * 0.5 * dash_gap; \
            for (int _k = 0; _k < _cnt; _k++) { \
                double _yo = _o0 + _k * dash_gap; \
                cairo_move_to(cr, (px_) - _hw, (py_) + _yo); \
                cairo_line_to(cr, (px_) + _hw, (py_) + _yo); \
            } \
        } while (0)

        double accum = spacing * 0.5;
        for (size_t i = 1; i < s->n_pts; i++) {
            double dx  = s->pts[i].x - s->pts[i-1].x;
            double dy  = s->pts[i].y - s->pts[i-1].y;
            double len = sqrt(dx*dx + dy*dy);
            if (len < 1e-9) continue;
            double need = spacing - accum;
            while (need <= len) {
                double t   = need / len;
                double px  = s->pts[i-1].x + t * dx;
                double py  = s->pts[i-1].y + t * dy;
                double p   = s->pts[i-1].pressure * (1.0 - t) + s->pts[i].pressure * t;
                STAMP_DASHES(px, py, p);
                need += spacing;
            }
            accum = len - (need - spacing);
        }
        #undef STAMP_DASHES
        cairo_stroke(cr);
        break;
    }

    case FILL_XMARKS: {
        /* Pressure controls COUNT of X marks placed side-by-side perpendicular to stroke:
         *   p<0.40 → 1 X   0.40–0.65 → 2 X   0.65–0.82 → 3 X   ≥0.82 → 4 X
         * Stroke width set by pen_x_width. */
        double arm     = ts * (double)app->pen_x_arm;
        double spacing = ts * (double)app->pen_x_spacing;
        double lw      = ts * (double)app->pen_x_width;
        double x_gap   = arm * 2.6;  /* centre-to-centre perpendicular gap */
        cairo_set_source_rgba(cr, sd->r, sd->g, sd->b, 0.8);
        cairo_set_line_width(cr, lw);

        #define STAMP_XS(px_, py_, nx_, ny_, cnt_) do { \
            double _o0 = -((cnt_) - 1) * 0.5 * x_gap; \
            for (int _k = 0; _k < (cnt_); _k++) { \
                double _off = _o0 + _k * x_gap; \
                double _cx = (px_) + (nx_)*_off; \
                double _cy = (py_) + (ny_)*_off; \
                cairo_move_to(cr, _cx - arm, _cy - arm); \
                cairo_line_to(cr, _cx + arm, _cy + arm); \
                cairo_move_to(cr, _cx + arm, _cy - arm); \
                cairo_line_to(cr, _cx - arm, _cy + arm); \
            } \
        } while (0)

        double accum = spacing * 0.5;
        for (size_t i = 1; i < s->n_pts; i++) {
            double dx  = s->pts[i].x - s->pts[i-1].x;
            double dy  = s->pts[i].y - s->pts[i-1].y;
            double len = sqrt(dx*dx + dy*dy);
            if (len < 1e-9) continue;
            double inv = 1.0 / len;
            double nx  = -dy * inv;
            double ny  =  dx * inv;
            double need = spacing - accum;
            while (need <= len) {
                double t   = need / len;
                double px  = s->pts[i-1].x + t * dx;
                double py  = s->pts[i-1].y + t * dy;
                double p   = s->pts[i-1].pressure * (1.0 - t) + s->pts[i].pressure * t;
                int cnt = (p < 0.40) ? 1 : (p < 0.65) ? 2 : (p < 0.82) ? 3 : 4;
                STAMP_XS(px, py, nx, ny, cnt);
                need += spacing;
            }
            accum = len - (need - spacing);
        }
        #undef STAMP_XS
        cairo_stroke(cr);
        break;
    }

    case FILL_TICK: {
        /* Checkmarks: pressure scales stroke width. */
        double avg_p = 0.0;
        for (size_t i = 0; i < s->n_pts; i++) avg_p += s->pts[i].pressure;
        if (s->n_pts > 0) avg_p /= (double)s->n_pts;
        cairo_set_source_rgba(cr, sd->r, sd->g, sd->b, 0.8);
        cairo_set_line_width(cr, 1.0 + avg_p * 1.4);
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND);

        #define TICK_AT(px, py) \
            cairo_move_to(cr, (px) - 4.5, (py) - 0.5); \
            cairo_line_to(cr, (px) - 1.0, (py) + 3.5); \
            cairo_line_to(cr, (px) + 5.5, (py) - 4.0);

        TICK_AT(s->pts[0].x, s->pts[0].y)

        double spacing = 14.0;
        double accum   = 0.0;
        for (size_t i = 1; i < s->n_pts; i++) {
            double dx  = s->pts[i].x - s->pts[i-1].x;
            double dy  = s->pts[i].y - s->pts[i-1].y;
            double len = sqrt(dx*dx + dy*dy);
            if (len < 1e-9) continue;
            double need = spacing - accum;
            while (need <= len) {
                double t = need / len;
                TICK_AT(s->pts[i-1].x + t * dx, s->pts[i-1].y + t * dy)
                need += spacing;
            }
            accum = len - (need - spacing);
        }
        #undef TICK_AT
        cairo_stroke(cr);
        break;
    }

    case FILL_PENCIL: {
        /* Narrow black writing line; ignores wide_mode.
         * Width: 0.6–2.0 bu (slightly wider onset than Pain/Fine 0.375). */
        if (s->n_pts < 2) break;
        size_t n = s->n_pts;
        double p_cur = s->pts[0].pressure;
        double w_cur = ts * (0.6 + p_cur * 1.4);
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_width(cr, w_cur);
        cairo_set_source_rgba(cr, sd->r, sd->g, sd->b, 1.0);
        cairo_move_to(cr, s->pts[0].x, s->pts[0].y);
        for (size_t i = 1; i < n; i++) {
            double p = (s->pts[i-1].pressure + s->pts[i].pressure) * 0.5;
            double w = ts * (0.6 + p * 1.4);
            if (fabs(w - w_cur) > 0.15) {
                cairo_stroke(cr);
                w_cur = w;
                cairo_set_line_width(cr, w_cur);
                cairo_set_source_rgba(cr, sd->r, sd->g, sd->b, 1.0);
                cairo_move_to(cr, s->pts[i-1].x, s->pts[i-1].y);
            }
            double x0 = (i >= 2) ? (double)s->pts[i-2].x : 2.0*s->pts[i-1].x - s->pts[i].x;
            double y0 = (i >= 2) ? (double)s->pts[i-2].y : 2.0*s->pts[i-1].y - s->pts[i].y;
            double x3 = (i+1 < n) ? (double)s->pts[i+1].x : 2.0*s->pts[i].x - s->pts[i-1].x;
            double y3 = (i+1 < n) ? (double)s->pts[i+1].y : 2.0*s->pts[i].y - s->pts[i-1].y;
            double cp1x = s->pts[i-1].x + (s->pts[i].x - x0) / 6.0;
            double cp1y = s->pts[i-1].y + (s->pts[i].y - y0) / 6.0;
            double cp2x = s->pts[i].x   - (x3 - s->pts[i-1].x) / 6.0;
            double cp2y = s->pts[i].y   - (y3 - s->pts[i-1].y) / 6.0;
            cairo_curve_to(cr, cp1x, cp1y, cp2x, cp2y, s->pts[i].x, s->pts[i].y);
        }
        cairo_stroke(cr);
        break;
    }

    } /* switch */
}

/* ── Coordinate transform ────────────────────────────────────────────────── */
static double col_base_scale(double w, double h)
{
    return fmin(w / 200.0, h / 400.0);
}

static void apply_col_transform(cairo_t *cr, ColData *cd, double w, double h)
{
    double s = col_base_scale(w, h) * (*cd->p_zoom);
    if (s <= 0.0) return;
    double cx = w / 2.0 + (*cd->p_pan_x);
    double cy = h / 2.0 + (*cd->p_pan_y);
    cairo_translate(cr, cx, cy);
    cairo_scale(cr, s, s);
    cairo_translate(cr, -100.0, -200.0);
}

static void screen_to_body(ColData *cd, double sx, double sy,
                            double *bx, double *by)
{
    double w  = (double)gtk_widget_get_width(cd->da);
    double h  = (double)gtk_widget_get_height(cd->da);
    double s  = col_base_scale(w, h) * (*cd->p_zoom);
    double cx = w / 2.0 + (*cd->p_pan_x);
    double cy = h / 2.0 + (*cd->p_pan_y);
    *bx = (sx - cx) / s + 100.0;
    *by = (sy - cy) / s + 200.0;
}

/* ── Screen-space hit testing for draggable annotations ─────────────────── */
static void label_anchor_resolve(const NoteAnnotation *na,
                                  double *out_lbx, double *out_lby);  /* fwd */
static void draw_pencil_strokes_body(AppState *app, cairo_t *cr, int view, double zoom);  /* fwd */

/* Returns index of the note whose label box contains (sx, sy), or -1 */
static int note_hit_screen(AppState *app, ColData *cd, double sx, double sy)
{
    double w  = (double)gtk_widget_get_width(cd->da);
    double h  = (double)gtk_widget_get_height(cd->da);
    double s  = col_base_scale(w, h) * (*cd->p_zoom);
    double cx = w / 2.0 + (*cd->p_pan_x);
    double cy = h / 2.0 + (*cd->p_pan_y);
    for (int i = 0; i < app->note_count; i++) {
        const NoteAnnotation *na = &app->notes[i];
        if (na->view != (int)cd->view) continue;
        double lbx, lby;
        label_anchor_resolve(na, &lbx, &lby);
        double lsx = (lbx - 100.0) * s + cx;
        double lsy = (lby - 200.0) * s + cy;
        /* Approximate label box: bw~180, bh~40, box_ly = lsy - bh */
        if (sx >= lsx        && sx <= lsx + 180 &&
            sy >= lsy - 40   && sy <= lsy)
            return i;
    }
    return -1;
}

static gboolean link_summary_hit_screen(AppState *app, ColData *cd,
                                         double sx, double sy)
{
    if (!app->link_summary_active) return FALSE;
    /* No view restriction — box is draggable from any panel */
    double w  = (double)gtk_widget_get_width(cd->da);
    double h  = (double)gtk_widget_get_height(cd->da);
    double s  = col_base_scale(w, h) * (*cd->p_zoom);
    double cx = w / 2.0 + (*cd->p_pan_x);
    double cy = h / 2.0 + (*cd->p_pan_y);
    double lsx = (app->link_summary_bx - 100.0) * s + cx;
    double lsy = (app->link_summary_by - 200.0) * s + cy;
    return (sx >= lsx - 5   && sx <= lsx + 80 &&
            sy >= lsy - 225  && sy <= lsy + 5);
}

static int arrow_head_hit_screen(AppState *app, ColData *cd,
                                  double sx, double sy)
{
    double w  = (double)gtk_widget_get_width(cd->da);
    double h  = (double)gtk_widget_get_height(cd->da);
    double s  = col_base_scale(w, h) * (*cd->p_zoom);
    double acx = w / 2.0 + (*cd->p_pan_x);
    double acy = h / 2.0 + (*cd->p_pan_y);
    for (int i = 0; i < app->arrow_count; i++) {
        if (app->arrows[i].view != (int)cd->view) continue;
        double ax = (app->arrows[i].x2 - 100.0) * s + acx;
        double ay = (app->arrows[i].y2 - 200.0) * s + acy;
        double dx = sx - ax, dy = sy - ay;
        if (sqrt(dx*dx + dy*dy) < 20.0) return i;
    }
    return -1;
}

static int obj_point_hit_screen(AppState *app, ColData *cd, double sx, double sy)
{
    double w  = (double)gtk_widget_get_width(cd->da);
    double h  = (double)gtk_widget_get_height(cd->da);
    double s  = col_base_scale(w, h) * (*cd->p_zoom);
    double cx = w / 2.0 + (*cd->p_pan_x);
    double cy = h / 2.0 + (*cd->p_pan_y);
    for (int i = app->obj_point_count - 1; i >= 0; i--) {
        const ObjPoint *p = &app->obj_points[i];
        if (p->view != (int)cd->view) continue;
        double lbx, lby;
        obj_label_resolve(p, &lbx, &lby);
        double lsx = (lbx - 100.0) * s + cx;
        double lsy = (lby - 200.0) * s + cy;
        /* Approximate label box: ~210px wide, ~26px tall, box_ly = lsy - bh */
        if (sx >= lsx        && sx <= lsx + 210 &&
            sy >= lsy - 26   && sy <= lsy)
            return i;
    }
    return -1;
}

/* ── Link summary rendering (graphical Cairo arrows, screen-space) ────────── */
static void draw_link_summary_screen(cairo_t *cr, AppState *app,
                                      double sx, double sy)
{
    if (!app->link_summary_active || app->link_rel_count == 0) return;

    const double pad   = 6.0;
    const double row_h = 20.0;
    const double fsz   = 11.0;
    const double bw    = 72.0;

    int    n  = app->link_rel_count;
    double bh = n * row_h + 2.0 * pad;

    cairo_save(cr);

    /* Background box — bottom-left anchored at (sx, sy) */
    cairo_set_source_rgba(cr, 0.95, 0.95, 0.82, 0.94);
    cairo_rectangle(cr, sx, sy - bh, bw, bh);
    cairo_fill(cr);
    cairo_set_source_rgba(cr, 0.25, 0.25, 0.25, 0.85);
    cairo_set_line_width(cr, 0.8);
    cairo_rectangle(cr, sx, sy - bh, bw, bh);
    cairo_stroke(cr);

    cairo_select_font_face(cr, "Sans",
                           CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD);
    cairo_set_font_size(cr, fsz);

    for (int i = 0; i < n; i++) {
        const LinkRel *rel = &app->link_relations[i];
        double ry = sy - bh + pad + (i + 0.5) * row_h;  /* row vertical centre */
        double rx = sx + pad;

        /* From-number */
        char nbuf[16];
        snprintf(nbuf, sizeof(nbuf), "%d", rel->from + 1);
        cairo_set_source_rgba(cr, 0.1, 0.1, 0.1, 1.0);
        cairo_move_to(cr, rx, ry + 4.0);
        cairo_show_text(cr, nbuf);

        /* Arrow body */
        double ax        = rx + 17.0;   /* stem start */
        double tip_x     = ax + 26.0;   /* arrowhead tip */
        double head_base = tip_x - 8.0; /* arrowhead base */

        if (rel->state == LINK_YES)
            cairo_set_source_rgba(cr, 0.1, 0.45, 0.1, 1.0);
        else
            cairo_set_source_rgba(cr, 0.50, 0.50, 0.50, 0.90);

        /* Stem */
        cairo_set_line_width(cr, 1.5);
        cairo_move_to(cr, ax, ry);
        cairo_line_to(cr, head_base, ry);
        cairo_stroke(cr);

        /* Filled arrowhead */
        cairo_move_to(cr, tip_x, ry);
        cairo_line_to(cr, head_base, ry - 5.0);
        cairo_line_to(cr, head_base, ry + 5.0);
        cairo_close_path(cr);
        cairo_fill(cr);

        /* Red diagonal slash for LINK_NO */
        if (rel->state == LINK_NO) {
            cairo_set_source_rgba(cr, 0.85, 0.10, 0.10, 1.0);
            cairo_set_line_width(cr, 2.0);
            double cx = ax + 10.0;
            cairo_move_to(cr, cx - 5.0, ry + 7.0);
            cairo_line_to(cr, cx + 5.0, ry - 7.0);
            cairo_stroke(cr);
        }

        /* To-number */
        snprintf(nbuf, sizeof(nbuf), "%d", rel->to + 1);
        cairo_set_source_rgba(cr, 0.1, 0.1, 0.1, 1.0);
        cairo_move_to(cr, tip_x + 3.0, ry + 4.0);
        cairo_show_text(cr, nbuf);
    }

    cairo_restore(cr);
}

/* ── Stroke legend (screen-space, posterior views only) ─────────────────── */
static int legend_count_used(const AppState *app, gboolean used[SYMPTOM_COUNT])
{
    for (int t = 0; t < SYMPTOM_COUNT; t++) used[t] = FALSE;
    for (int i = 0; i < app->strokes->n; i++)
        used[app->strokes->strokes[i]->type] = TRUE;
    int n = 0;
    for (int t = 0; t < SYMPTOM_COUNT; t++) if (used[t]) n++;
    return n;
}

static gboolean legend_hit_screen(AppState *app, ColData *cd,
                                   double sx, double sy)
{
    gboolean used[SYMPTOM_COUNT];
    int n = legend_count_used(app, used);
    if (n == 0) return FALSE;
    const double pad = 5.0, row_h = 18.0, bw = 122.0;
    double bh = n * row_h + 2.0 * pad;
    double w  = (double)gtk_widget_get_width(cd->da);
    double h  = (double)gtk_widget_get_height(cd->da);
    double s  = col_base_scale(w, h) * (*cd->p_zoom);
    double cx = w / 2.0 + (*cd->p_pan_x);
    double cy = h / 2.0 + (*cd->p_pan_y);
    double lsx = (app->legend_bx - 100.0) * s + cx;
    double lsy = (app->legend_by - 200.0) * s + cy;
    return (sx >= lsx && sx <= lsx + bw &&
            sy >= lsy - bh && sy <= lsy);
}

static void draw_stroke_legend(cairo_t *cr, AppState *app,
                                double sx, double sy)
{
    gboolean used[SYMPTOM_COUNT];
    int n = legend_count_used(app, used);
    if (n == 0) return;

    const double pad   = 5.0;
    const double row_h = 18.0;
    const double sw_w  = 28.0;
    const double gap   = 5.0;
    const double fsz   = 10.5;
    const double bw    = 122.0;
    double bh = n * row_h + 2.0 * pad;

    cairo_save(cr);

    /* Background box — bottom-left anchored at (sx, sy) */
    cairo_set_source_rgba(cr, 0.95, 0.95, 0.82, 0.94);
    cairo_rectangle(cr, sx, sy - bh, bw, bh);
    cairo_fill(cr);
    cairo_set_source_rgba(cr, 0.25, 0.25, 0.25, 0.85);
    cairo_set_line_width(cr, 0.8);
    cairo_rectangle(cr, sx, sy - bh, bw, bh);
    cairo_stroke(cr);

    cairo_select_font_face(cr, "Sans",
                           CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL);
    cairo_set_font_size(cr, fsz);

    int row = 0;
    for (int t = 0; t < SYMPTOM_COUNT; t++) {
        if (!used[t]) continue;
        const SymptomDef *sd = &SYMPTOM_DEFS[t];
        double ry_top = sy - bh + pad + row * row_h;
        double ry_mid = ry_top + row_h * 0.5;
        double rx     = sx + pad;
        double sw_y   = ry_top + (row_h - 10.0) * 0.5;
        double sw_cy  = sw_y + 5.0;
        double sw_cx  = rx + sw_w * 0.5;

        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND);
        cairo_set_dash(cr, NULL, 0, 0);
        cairo_set_source_rgba(cr, sd->r, sd->g, sd->b, 0.9);

        switch (sd->pattern) {
        case FILL_SOLID:
            cairo_set_line_width(cr, 3.5);
            cairo_move_to(cr, rx,          sw_cy);
            cairo_line_to(cr, rx + sw_w,   sw_cy);
            cairo_stroke(cr);
            break;
        case FILL_DASHED: {
            double dashes[2] = { 5.0, 3.0 };
            cairo_set_dash(cr, dashes, 2, 0);
            cairo_set_line_width(cr, 2.0);
            cairo_move_to(cr, rx,          sw_cy);
            cairo_line_to(cr, rx + sw_w,   sw_cy);
            cairo_stroke(cr);
            cairo_set_dash(cr, NULL, 0, 0);
            break;
        }
        case FILL_DOTS_SPACED:
            for (int d = 0; d < 4; d++) {
                cairo_new_sub_path(cr);
                cairo_arc(cr, rx + 3.5 + d * 7.0, sw_cy, 2.5, 0, 2*M_PI);
            }
            cairo_fill(cr);
            break;
        case FILL_H_STROKES:
            cairo_set_line_width(cr, 1.5);
            for (int d = 0; d < 4; d++) {
                double dx = rx + 4.0 + d * 6.0;
                cairo_move_to(cr, dx - 2.5, sw_cy - 2.0);
                cairo_line_to(cr, dx + 2.5, sw_cy - 2.0);
                cairo_move_to(cr, dx - 2.5, sw_cy + 2.0);
                cairo_line_to(cr, dx + 2.5, sw_cy + 2.0);
            }
            cairo_stroke(cr);
            break;
        case FILL_XMARKS:
            cairo_set_line_width(cr, 1.5);
            for (int d = 0; d < 3; d++) {
                double dx = rx + 5.0 + d * 9.0;
                cairo_move_to(cr, dx - 3.0, sw_cy - 3.0);
                cairo_line_to(cr, dx + 3.0, sw_cy + 3.0);
                cairo_move_to(cr, dx + 3.0, sw_cy - 3.0);
                cairo_line_to(cr, dx - 3.0, sw_cy + 3.0);
            }
            cairo_stroke(cr);
            break;
        case FILL_TICK:
            cairo_set_line_width(cr, 1.5);
            cairo_move_to(cr, sw_cx - 4.0, sw_cy);
            cairo_line_to(cr, sw_cx - 1.0, sw_cy + 3.0);
            cairo_line_to(cr, sw_cx + 5.0, sw_cy - 3.5);
            cairo_stroke(cr);
            break;
        case FILL_PENCIL:
            cairo_set_line_width(cr, 1.5);
            cairo_move_to(cr, rx,        sw_cy);
            cairo_line_to(cr, rx + sw_w, sw_cy);
            cairo_stroke(cr);
            break;
        }

        /* Label */
        cairo_set_source_rgba(cr, 0.1, 0.1, 0.1, 1.0);
        cairo_move_to(cr, rx + sw_w + gap, ry_mid + 4.0);
        cairo_show_text(cr, sd->label);

        row++;
    }

    cairo_restore(cr);
}

/* ── Objective legend (screen-space, posterior + obj mode only) ──────────── */
static int obj_legend_count_used(const AppState *app,
                                  gboolean zone_used[OBJ_ZONE_COUNT],
                                  gboolean point_used[OBJ_POINT_COUNT],
                                  gboolean tick_used[OBJ_TICK_TYPE_COUNT])
{
    for (int t = 0; t < OBJ_ZONE_COUNT;  t++) zone_used[t]  = FALSE;
    for (int t = 0; t < OBJ_POINT_COUNT; t++) point_used[t] = FALSE;
    for (int t = 0; t < OBJ_TICK_TYPE_COUNT; t++) tick_used[t] = FALSE;
    for (int i = 0; i < app->obj_zone_count;  i++) {
        const ObjZone *z = app->obj_zones[i];
        if (z) zone_used[z->type] = TRUE;
    }
    for (int i = 0; i < app->obj_point_count; i++)
        point_used[app->obj_points[i].type] = TRUE;
    for (int i = 0; i < app->obj_tick_count; i++)
        tick_used[app->obj_ticks[i].type] = TRUE;
    int n = 0;
    for (int t = 0; t < OBJ_ZONE_COUNT;  t++) if (zone_used[t])  n++;
    for (int t = 0; t < OBJ_POINT_COUNT; t++) if (point_used[t]) n++;
    for (int t = 0; t < OBJ_TICK_TYPE_COUNT; t++) if (tick_used[t]) n++;
    return n;
}

static gboolean obj_legend_hit_screen(AppState *app, ColData *cd,
                                       double sx, double sy)
{
    gboolean zu[OBJ_ZONE_COUNT], pu[OBJ_POINT_COUNT], tu[OBJ_TICK_TYPE_COUNT];
    int n = obj_legend_count_used(app, zu, pu, tu);
    if (n == 0) return FALSE;
    const double pad = 5.0, row_h = 18.0, bw = 122.0;
    double bh = n * row_h + 2.0 * pad;
    double w  = (double)gtk_widget_get_width(cd->da);
    double h  = (double)gtk_widget_get_height(cd->da);
    double s  = col_base_scale(w, h) * (*cd->p_zoom);
    double cx = w / 2.0 + (*cd->p_pan_x);
    double cy = h / 2.0 + (*cd->p_pan_y);
    double lsx = (app->legend_bx - 100.0) * s + cx;
    double lsy = (app->legend_by - 200.0) * s + cy;
    return (sx >= lsx && sx <= lsx + bw &&
            sy >= lsy - bh && sy <= lsy);
}

static void draw_obj_legend(cairo_t *cr, AppState *app,
                             double sx, double sy)
{
    gboolean zone_used[OBJ_ZONE_COUNT], point_used[OBJ_POINT_COUNT], tick_used[OBJ_TICK_TYPE_COUNT];
    int n = obj_legend_count_used(app, zone_used, point_used, tick_used);
    if (n == 0) return;

    const double pad   = 5.0;
    const double row_h = 18.0;
    const double sw_w  = 20.0;   /* swatch width */
    const double gap   = 5.0;
    const double fsz   = 10.5;
    const double bw    = 122.0;
    double bh = n * row_h + 2.0 * pad;

    cairo_save(cr);

    /* Background box — bottom-left anchored at (sx, sy) */
    cairo_set_source_rgba(cr, 0.08, 0.08, 0.15, 0.92);
    cairo_rectangle(cr, sx, sy - bh, bw, bh);
    cairo_fill(cr);
    cairo_set_source_rgba(cr, 0.50, 0.50, 0.65, 0.85);
    cairo_set_line_width(cr, 0.8);
    cairo_rectangle(cr, sx, sy - bh, bw, bh);
    cairo_stroke(cr);

    cairo_select_font_face(cr, "Sans",
                           CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL);
    cairo_set_font_size(cr, fsz);

    int row = 0;

    /* Zones */
    for (int t = 0; t < OBJ_ZONE_COUNT; t++) {
        if (!zone_used[t]) continue;
        const ObjZoneDef *d = &OBJ_ZONE_DEFS[t];
        double ry_top = sy - bh + pad + row * row_h;
        double ry_mid = ry_top + row_h * 0.5;
        double rx     = sx + pad;
        double sw_y   = ry_top + (row_h - 10.0) * 0.5;

        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND);

        /* Filled rect swatch — matches zone render style */
        cairo_set_source_rgba(cr, d->r, d->g, d->b, 0.35);
        cairo_rectangle(cr, rx, sw_y, sw_w, 10.0);
        cairo_fill(cr);
        cairo_set_source_rgba(cr, d->r, d->g, d->b, 0.80);
        cairo_set_line_width(cr, 1.0);
        cairo_rectangle(cr, rx, sw_y, sw_w, 10.0);
        cairo_stroke(cr);

        /* Label */
        cairo_set_source_rgba(cr, 0.88, 0.88, 0.95, 1.0);
        cairo_move_to(cr, rx + sw_w + gap, ry_mid + 4.0);
        cairo_show_text(cr, d->name);
        row++;
    }

    /* Points */
    for (int t = 0; t < OBJ_POINT_COUNT; t++) {
        if (!point_used[t]) continue;
        const ObjPointDef *d = &OBJ_POINT_DEFS[t];
        double ry_top = sy - bh + pad + row * row_h;
        double ry_mid = ry_top + row_h * 0.5;
        double rx     = sx + pad;

        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);

        /* Dot swatch — circle matching point dot style */
        cairo_new_sub_path(cr);
        cairo_arc(cr, rx + sw_w * 0.5, ry_mid, 4.5, 0, 2*M_PI);
        cairo_set_source_rgba(cr, d->r, d->g, d->b, 0.90);
        cairo_fill(cr);
        cairo_new_sub_path(cr);
        cairo_arc(cr, rx + sw_w * 0.5, ry_mid, 4.5, 0, 2*M_PI);
        cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 0.55);
        cairo_set_line_width(cr, 1.2);
        cairo_stroke(cr);

        /* Label */
        cairo_set_source_rgba(cr, 0.88, 0.88, 0.95, 1.0);
        cairo_move_to(cr, rx + sw_w + gap, ry_mid + 4.0);
        cairo_show_text(cr, d->name);
        row++;
    }

    /* Ticks/crosses — one row per TYPE (colour identifies the type; both
     * the tick and cross glyph share that colour, see obj_chart.c's
     * OBJ_TICK_DEFS), swatch shows the same small vector check mark used
     * on the chart itself so the legend key matches what's actually drawn. */
    for (int t = 0; t < OBJ_TICK_TYPE_COUNT; t++) {
        if (!tick_used[t]) continue;
        const ObjTickDef *d = &OBJ_TICK_DEFS[t];
        double ry_top = sy - bh + pad + row * row_h;
        double ry_mid = ry_top + row_h * 0.5;
        double rx     = sx + pad;
        double cx_sw  = rx + sw_w * 0.5;

        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND);

        cairo_new_sub_path(cr);
        cairo_arc(cr, cx_sw, ry_mid, 4.5, 0, 2*M_PI);
        cairo_set_source_rgba(cr, d->r, d->g, d->b, 0.90);
        cairo_fill(cr);
        cairo_new_sub_path(cr);
        cairo_arc(cr, cx_sw, ry_mid, 4.5, 0, 2*M_PI);
        cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 0.55);
        cairo_set_line_width(cr, 1.2);
        cairo_stroke(cr);

        cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 1.0);
        cairo_set_line_width(cr, 1.1);
        cairo_move_to(cr, cx_sw - 2.0, ry_mid + 0.2);
        cairo_line_to(cr, cx_sw - 0.5, ry_mid + 1.8);
        cairo_line_to(cr, cx_sw + 2.2, ry_mid - 2.0);
        cairo_stroke(cr);

        /* Label */
        cairo_set_source_rgba(cr, 0.88, 0.88, 0.95, 1.0);
        cairo_move_to(cr, rx + sw_w + gap, ry_mid + 4.0);
        cairo_show_text(cr, d->name);
        row++;
    }

    cairo_restore(cr);
}

/* ── Note annotation rendering (screen-space, fixed pixel size) ─────────── */
/* Resolve label position: default offset from spot when not user-placed */
static void label_anchor_resolve(const NoteAnnotation *na,
                                  double *out_lbx, double *out_lby)
{
    if (na->label.placed) {
        *out_lbx = na->label.lx;
        *out_lby = na->label.ly;
    } else {
        *out_lbx = na->bx + 12.0;
        *out_lby = na->by - 8.0;
    }
}

/* Draw the connector line + arrowhead from label-box edge to spot.
 * All coords are screen-space. */
static void draw_note_connector(cairo_t *cr,
                                 double spot_sx, double spot_sy,
                                 double box_lx,  double box_ly,
                                 double bw,       double bh)
{
    double box_cx = box_lx + bw / 2.0;
    double box_cy = box_ly + bh / 2.0;
    double dx = spot_sx - box_cx, dy = spot_sy - box_cy;
    double dist = sqrt(dx * dx + dy * dy);
    if (dist < 8.0) return;

    /* Unit vector from box centre toward spot */
    double ux = dx / dist, uy = dy / dist;

    /* Exact intersection of the ray with the rectangle boundary */
    double tx = (ux != 0.0) ? (bw / 2.0) / fabs(ux) : 1e9;
    double ty = (uy != 0.0) ? (bh / 2.0) / fabs(uy) : 1e9;
    double t  = fmin(tx, ty);
    double start_x = box_cx + ux * t;
    double start_y = box_cy + uy * t;

    /* Arrowhead tip lands at the spot dot edge */
    double spot_r = 5.5;
    double end_x  = spot_sx - ux * spot_r;
    double end_y  = spot_sy - uy * spot_r;

    double head = 12.0;
    double hw   = 5.0;
    double px   = -uy, py = ux;
    double hbx  = end_x - ux * head;
    double hby  = end_y - uy * head;

    /* Shaft */
    cairo_set_source_rgba(cr, 0.15, 0.15, 0.15, 0.85);
    cairo_set_line_width(cr, 2.0);
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
    cairo_move_to(cr, start_x, start_y);
    cairo_line_to(cr, hbx, hby);   /* stop at head base so it doesn't show behind head */
    cairo_stroke(cr);

    /* Filled arrowhead */
    cairo_move_to(cr, end_x, end_y);
    cairo_line_to(cr, hbx + px * hw, hby + py * hw);
    cairo_line_to(cr, hbx - px * hw, hby - py * hw);
    cairo_close_path(cr);
    cairo_fill(cr);
}

/* Render one note annotation: spot dot, connector, 2-line label box.
 * spot_sx/sy and label_sx/sy are screen-space. */
static void draw_note_screen(cairo_t *cr, const NoteAnnotation *na,
                              double spot_sx, double spot_sy,
                              double label_sx, double label_sy)
{
    double pad = 4.0;
    double fsz = 14.0;

    cairo_save(cr);
    cairo_select_font_face(cr, "Sans",
                           CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD);
    cairo_set_font_size(cr, fsz);

    /* Split text on '\n' into up to 2 lines */
    char line1[128] = {0}, line2[128] = {0};
    const char *nl = strchr(na->text, '\n');
    if (nl) {
        int len1 = (int)(nl - na->text);
        if (len1 >= (int)sizeof(line1)) len1 = (int)sizeof(line1) - 1;
        memcpy(line1, na->text, (size_t)len1);
        snprintf(line2, sizeof(line2), "%s", nl + 1);
    } else {
        snprintf(line1, sizeof(line1), "%s", na->text);
    }

    cairo_text_extents_t e1, e2;
    cairo_text_extents(cr, line1, &e1);
    cairo_text_extents(cr, line2[0] ? line2 : " ", &e2);

    double line_h = -e1.y_bearing;            /* ascent */
    double gap    = 2.0;
    double bw = fmax(e1.width - e1.x_bearing, e2.width - e2.x_bearing) + 2.0 * pad;
    double bh = (line2[0] ? (line_h * 2.0 + gap) : line_h) + 2.0 * pad;

    /* Label box is drawn with its reference point as its left-baseline */
    double box_lx = label_sx;
    double box_ly = label_sy - bh;   /* box above reference */

    /* Connector first (drawn behind label box) */
    draw_note_connector(cr, spot_sx, spot_sy, box_lx, box_ly, bw, bh);

    /* Filled label box */
    cairo_set_source_rgba(cr, 1.0, 1.0, 0.82, 0.93);
    cairo_rectangle(cr, box_lx, box_ly, bw, bh);
    cairo_fill(cr);

    /* Border */
    cairo_set_source_rgba(cr, 0.25, 0.25, 0.25, 0.85);
    cairo_set_line_width(cr, 0.8);
    cairo_rectangle(cr, box_lx, box_ly, bw, bh);
    cairo_stroke(cr);

    /* Spot dot — filled circle with white ring so it reads on any background */
    cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 0.90);
    cairo_arc(cr, spot_sx, spot_sy, 7.0, 0, 2 * M_PI);
    cairo_fill(cr);
    cairo_set_source_rgba(cr, 0.12, 0.12, 0.12, 0.92);
    cairo_arc(cr, spot_sx, spot_sy, 5.5, 0, 2 * M_PI);
    cairo_fill(cr);

    /* Text lines */
    cairo_set_source_rgba(cr, 0.05, 0.05, 0.05, 1.0);
    cairo_move_to(cr, box_lx + pad - e1.x_bearing,
                      box_ly + pad + line_h);
    cairo_show_text(cr, line1);
    if (line2[0]) {
        cairo_move_to(cr, box_lx + pad - e2.x_bearing,
                          box_ly + pad + line_h * 2.0 + gap);
        cairo_show_text(cr, line2);
    }

    cairo_restore(cr);
}

/* ── Arrow path tracking (bezier curve fit) ─────────────────────────────── */
static void arrow_track_add(AppState *app, double bx, double by)
{
    if (app->arrow_track_n == 32) {
        for (int i = 0; i < 16; i++) {
            app->arrow_track_x[i] = app->arrow_track_x[i * 2];
            app->arrow_track_y[i] = app->arrow_track_y[i * 2];
        }
        app->arrow_track_n = 16;
    }
    app->arrow_track_x[app->arrow_track_n] = bx;
    app->arrow_track_y[app->arrow_track_n] = by;
    app->arrow_track_n++;
}

/* Returns the quadratic bezier control point that makes the curve pass
 * through the sampled midpoint at t≈0.5. */
static void arrow_get_cp(const AppState *app, double *cpx, double *cpy)
{
    if (app->arrow_track_n >= 2) {
        double mx = app->arrow_track_x[app->arrow_track_n / 2];
        double my = app->arrow_track_y[app->arrow_track_n / 2];
        *cpx = 2.0 * mx - 0.5 * (app->arrow_x1 + app->arrow_x2);
        *cpy = 2.0 * my - 0.5 * (app->arrow_y1 + app->arrow_y2);
    } else {
        *cpx = (app->arrow_x1 + app->arrow_x2) * 0.5;
        *cpy = (app->arrow_y1 + app->arrow_y2) * 0.5;
    }
}

/* ── Arrow rendering (body-space coordinates, quadratic bezier) ─────────── */
static void draw_arrow_body_space(cairo_t *cr,
                                   double x1, double y1,
                                   double cx, double cy,
                                   double x2, double y2)
{
    double dx = x2 - x1, dy = y2 - y1;
    double len = sqrt(dx*dx + dy*dy);
    if (len < 1.0) return;

    /* Tangent at tip = Q'(1) = 2*(P2 - control); use for head orientation */
    double tx = x2 - cx, ty = y2 - cy;
    double tlen = sqrt(tx*tx + ty*ty);
    if (tlen < 1e-9) { tx = dx; ty = dy; tlen = len; }
    tx /= tlen; ty /= tlen;

    double head_len = fmin(6.0, len * 0.22);
    double half_w   = head_len * 0.38;
    double px = -ty, py = tx;
    double hbx = x2 - tx * head_len;
    double hby = y2 - ty * head_len;

    cairo_set_source_rgba(cr, 0.0, 0.0, 0.0, 0.88);
    cairo_set_line_width(cr, 0.8);
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);

    /* Full quadratic bezier (P0=x1,y1  P1=cx,cy  P2=x2,y2), converted to
     * cubic via standard exact degree elevation, drawn all the way to the
     * TRUE tip — not truncated at the head base. The previous version
     * truncated the shaft at hbx,hby but reused the same control point
     * cx,cy (computed for the full-length curve) as if it were valid for
     * that much shorter segment — it isn't a real subdivision of the
     * curve, just a different, wrong curve, and it showed up as a very
     * tight, exaggerated bend right at the tip (direct user report). The
     * opaque, filled arrowhead below simply sits on top of the last
     * head_len of shaft, same as any arrowhead covering the tail of its
     * own line — no truncation needed. */
    double c1x = x1 + (2.0/3.0) * (cx - x1);
    double c1y = y1 + (2.0/3.0) * (cy - y1);
    double c2x = x2 + (2.0/3.0) * (cx - x2);
    double c2y = y2 + (2.0/3.0) * (cy - y2);
    cairo_move_to(cr, x1, y1);
    cairo_curve_to(cr, c1x, c1y, c2x, c2y, x2, y2);
    cairo_stroke(cr);

    /* Filled triangular arrowhead */
    cairo_move_to(cr, x2, y2);
    cairo_line_to(cr, hbx + px * half_w, hby + py * half_w);
    cairo_line_to(cr, hbx - px * half_w, hby - py * half_w);
    cairo_close_path(cr);
    cairo_fill(cr);
}

/* ── Offscreen render (used by session export) ───────────────────────────── */
void canvas_render_view(AppState *app, cairo_t *cr, BodyView view,
                        double w, double h,
                        double zoom, double pan_x, double pan_y)
{
    double s  = col_base_scale(w, h) * zoom;
    double cx = w / 2.0 + pan_x;
    double cy = h / 2.0 + pan_y;

    cairo_save(cr);
    cairo_translate(cr, cx, cy);
    cairo_scale(cr, s, s);
    cairo_translate(cr, -100.0, -200.0);

    cairo_set_source_rgb(cr, 0.18, 0.18, 0.18);
    cairo_set_line_width(cr, 1.8);
    body_outline_draw(cr, view);

    if (app->current_mode == APP_MODE_OBJECTIVE) {
        obj_chart_render_body(app, cr, (int)view);
        obj_chart_render_ticks_body(app, cr, (int)view);
        draw_pencil_strokes_body(app, cr, (int)view, zoom);
    } else {
        for (int i = 0; i < app->strokes->n; i++) {
            Stroke *sk = app->strokes->strokes[i];
            if (sk->view != (int)view) continue;
            draw_stroke(cr, sk, &SYMPTOM_DEFS[sk->type], app, zoom);
        }

        for (int i = 0; i < app->arrow_count; i++) {
            if (app->arrows[i].view != (int)view) continue;
            draw_arrow_body_space(cr, app->arrows[i].x1, app->arrows[i].y1,
                                  app->arrows[i].cx,  app->arrows[i].cy,
                                  app->arrows[i].x2,  app->arrows[i].y2);
        }
    }

    cairo_restore(cr);

    if (app->current_mode == APP_MODE_OBJECTIVE) {
        obj_chart_render_screen(app, cr, (int)view, s, cx, cy);
    } else {
        /* Note annotations in screen space */
        for (int i = 0; i < app->note_count; i++) {
            const NoteAnnotation *na = &app->notes[i];
            if (na->view != (int)view) continue;
            double spot_sx = (na->bx - 100.0) * s + cx;
            double spot_sy = (na->by - 200.0) * s + cy;
            double lbx, lby;
            label_anchor_resolve(na, &lbx, &lby);
            draw_note_screen(cr, na, spot_sx, spot_sy,
                             (lbx - 100.0) * s + cx,
                             (lby - 200.0) * s + cy);
        }

        /* Link summary shown on anterior view only */
        if (app->link_summary_active && view == VIEW_ANTERIOR)
            draw_link_summary_screen(cr, app,
                                      (app->link_summary_bx - 100.0) * s + cx,
                                      (app->link_summary_by - 200.0) * s + cy);
    }

    /* Mode-specific legend on posterior view */
    if (view == VIEW_POSTERIOR) {
        double lsx = (app->legend_bx - 100.0) * s + cx;
        double lsy = (app->legend_by - 200.0) * s + cy;
        if (app->current_mode == APP_MODE_SUBJECTIVE)
            draw_stroke_legend(cr, app, lsx, lsy);
        else
            draw_obj_legend(cr, app, lsx, lsy);
    }
}

/* ── Committed-stroke cache management ────────────────────────────────────── *
 * rebuild_stroke_cache() renders all committed strokes and arrows for          *
 * cd->view into cd->stroke_cache (STROKE_CACHE_W × STROKE_CACHE_H pixels,     *
 * 2 px per body-unit).  The cache is then stamped onto the screen surface in   *
 * on_col_draw instead of re-iterating the full stroke list every frame.        *
 *                                                                               *
 * Cache space: body (0,0) maps to pixel (0,0); body (200,400) → pixel          *
 * (400,800).  The transform is simply scale(2,2) from body space.              */
static void rebuild_stroke_cache(ColData *cd)
{
    AppState *app = cd->app;

    /* BLUR FIX [1/3]: build cache at actual widget resolution with the full
     * col transform, so cache pixels map 1:1 to screen pixels.
     * ROLLBACK: delete from here to the matching ROLLBACK comment below,
     * and uncomment the old block. */
    int w = gtk_widget_get_width(cd->da);
    int h = gtk_widget_get_height(cd->da);
    if (w <= 0 || h <= 0) return;

    if (cd->stroke_cache)
        cairo_surface_destroy(cd->stroke_cache);
    cd->stroke_cache = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, w, h);

    cairo_t *cr = cairo_create(cd->stroke_cache);
    cairo_set_operator(cr, CAIRO_OPERATOR_CLEAR);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);

    /* Apply the same transform the screen uses — body space at screen scale */
    apply_col_transform(cr, cd, (double)w, (double)h);
    /* END BLUR FIX [1/3] */

    /* ROLLBACK [1/3]: replace the block above with:
    if (cd->stroke_cache)
        cairo_surface_destroy(cd->stroke_cache);
    cd->stroke_cache = cairo_image_surface_create(
        CAIRO_FORMAT_ARGB32, STROKE_CACHE_W, STROKE_CACHE_H);
    cairo_t *cr = cairo_create(cd->stroke_cache);
    cairo_set_operator(cr, CAIRO_OPERATOR_CLEAR);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);
    cairo_scale(cr, 2.0, 2.0);
    */

    /* Committed strokes */
    for (int i = 0; i < app->strokes->n; i++) {
        Stroke *s = app->strokes->strokes[i];
        if (s->view != (int)cd->view) continue;
        draw_stroke(cr, s, &SYMPTOM_DEFS[s->type], app, *cd->p_zoom);
    }

    /* Committed arrows */
    for (int i = 0; i < app->arrow_count; i++) {
        if (app->arrows[i].view != (int)cd->view) continue;
        draw_arrow_body_space(cr, app->arrows[i].x1, app->arrows[i].y1,
                              app->arrows[i].cx,  app->arrows[i].cy,
                              app->arrows[i].x2,  app->arrows[i].y2);
    }

    cairo_destroy(cr);
    cd->cache_stroke_version = app->stroke_version;

    /* BLUR FIX [2/3]: record viewport state so we know when to rebuild.
     * ROLLBACK: delete these five lines. */
    cd->cache_w     = w;
    cd->cache_h     = h;
    cd->cache_zoom  = *cd->p_zoom;
    cd->cache_pan_x = *cd->p_pan_x;
    cd->cache_pan_y = *cd->p_pan_y;
    /* END BLUR FIX [2/3] */
}

/* ── Draw callback ───────────────────────────────────────────────────────── */
static void on_col_draw(GtkDrawingArea *da, cairo_t *cr,
                        int width, int height, gpointer user_data)
{
    ColData  *cd  = user_data;
    AppState *app = cd->app;
    (void)da;

    cairo_set_source_rgb(cr, 1.0, 1.0, 1.0);
    cairo_paint(cr);

    /* BLUR FIX [3/3]: save the widget-level matrix before body transform so
     * we can blit the cache back at 1:1 screen pixels.
     * ROLLBACK: delete this cairo_get_matrix line. */
    cairo_matrix_t device_matrix;
    cairo_get_matrix(cr, &device_matrix);
    /* END BLUR FIX [3/3 — continued in cache stamp below] */

    cairo_save(cr);
    apply_col_transform(cr, cd, width, height);

    /* Body outline */
    cairo_set_source_rgb(cr, 0.18, 0.18, 0.18);
    cairo_set_line_width(cr, 1.8);
    body_outline_draw(cr, cd->view);

    /* Overlay */
    if (app->overlay_visible && app->overlay_category != OVERLAY_NONE) {
        if (app->overlay_category == OVERLAY_DERMATOME ||
            app->overlay_category == OVERLAY_PERIPHERAL) {
            cairo_push_group(cr);
            if (app->overlay_category == OVERLAY_DERMATOME)
                overlay_svg_draw_derm(cr, (int)cd->view);
            else
                overlay_svg_draw_periph(cr, (int)cd->view);
            cairo_pop_group_to_source(cr);
            cairo_paint_with_alpha(cr, app->overlay_alpha);
        } else {
            const OverlayDef *ov = overlay_get(app->overlay_category,
                                               app->overlay_index);
            if (ov) overlay_draw(cr, ov, (int)cd->view, app->overlay_alpha);
        }
    }

    if (app->current_mode == APP_MODE_SUBJECTIVE) {
        /* ── Committed strokes/arrows via offscreen cache ──────────────────── *
         * BLUR FIX: cache is built at screen resolution with apply_col_transform,
         * so it blits 1:1 — no resampling.  Rebuilt whenever strokes, widget
         * size, zoom, or pan change.
         * ROLLBACK: replace the invalidation condition with just:
         *   if (cd->cache_stroke_version != app->stroke_version)
         * and replace the blit block with:
         *   cairo_save(cr);
         *   cairo_scale(cr, 0.5, 0.5);
         *   cairo_set_source_surface(cr, cd->stroke_cache, 0.0, 0.0);
         *   cairo_paint(cr);
         *   cairo_restore(cr);                                                */
        if (cd->cache_stroke_version != app->stroke_version ||
            cd->cache_w     != width                        ||
            cd->cache_h     != height                       ||
            cd->cache_zoom  != *cd->p_zoom                  ||
            cd->cache_pan_x != *cd->p_pan_x                 ||
            cd->cache_pan_y != *cd->p_pan_y)
            rebuild_stroke_cache(cd);

        if (cd->stroke_cache) {
            /* Restore widget-level matrix and blit 1:1 — zero resampling. */
            cairo_save(cr);
            cairo_set_matrix(cr, &device_matrix);
            cairo_set_source_surface(cr, cd->stroke_cache, 0.0, 0.0);
            cairo_paint(cr);
            cairo_restore(cr);
        }

        /* Active stroke (in-progress — rendered fresh every frame) */
        if (app->active_stroke && app->active_stroke->view == (int)cd->view)
            draw_stroke(cr, app->active_stroke,
                        &SYMPTOM_DEFS[app->active_stroke->type], app, *cd->p_zoom);

        /* Arrow preview while drawing */
        if (app->arrow_drawing && app->arrow_draw_view == (int)cd->view) {
            double cpx, cpy;
            arrow_get_cp(app, &cpx, &cpy);
            draw_arrow_body_space(cr, app->arrow_x1, app->arrow_y1,
                                  cpx, cpy,
                                  app->arrow_x2, app->arrow_y2);
        }
    } else if (app->current_mode == APP_MODE_OBJECTIVE) {
        obj_chart_render_body(app, cr, (int)cd->view);
        obj_chart_render_active_body(app, cr, (int)cd->view);
        obj_chart_render_ticks_body(app, cr, (int)cd->view);
        draw_pencil_strokes_body(app, cr, (int)cd->view, *cd->p_zoom);
        if (app->active_stroke && app->active_stroke->type == SYMPTOM_PENCIL &&
            app->active_stroke->view == (int)cd->view)
            draw_stroke(cr, app->active_stroke,
                        &SYMPTOM_DEFS[app->active_stroke->type], app, *cd->p_zoom);
    }

    cairo_restore(cr);

    double s  = col_base_scale(width, height) * (*cd->p_zoom);
    double cx = width  / 2.0 + (*cd->p_pan_x);
    double cy = height / 2.0 + (*cd->p_pan_y);

    if (app->current_mode == APP_MODE_SUBJECTIVE) {
        /* Note annotations and link summary in screen space */
        for (int i = 0; i < app->note_count; i++) {
            const NoteAnnotation *na = &app->notes[i];
            if (na->view != (int)cd->view) continue;
            double spot_sx = (na->bx - 100.0) * s + cx;
            double spot_sy = (na->by - 200.0) * s + cy;
            double lbx, lby;
            label_anchor_resolve(na, &lbx, &lby);
            draw_note_screen(cr, na, spot_sx, spot_sy,
                             (lbx - 100.0) * s + cx,
                             (lby - 200.0) * s + cy);
        }
        if (app->link_summary_active && cd->view == VIEW_ANTERIOR)
            draw_link_summary_screen(cr, app,
                                      (app->link_summary_bx - 100.0) * s + cx,
                                      (app->link_summary_by - 200.0) * s + cy);
    } else if (app->current_mode == APP_MODE_OBJECTIVE) {
        obj_chart_render_screen(app, cr, (int)cd->view, s, cx, cy);
    }

    /* Mode-specific legend on posterior view */
    if (cd->view == VIEW_POSTERIOR) {
        double lsx = (app->legend_bx - 100.0) * s + cx;
        double lsy = (app->legend_by - 200.0) * s + cy;
        if (app->current_mode == APP_MODE_SUBJECTIVE)
            draw_stroke_legend(cr, app, lsx, lsy);
        else
            draw_obj_legend(cr, app, lsx, lsy);
    }
}

/* ── Objective chart hit-testing (body-space) ────────────────────────────── */
static int obj_zone_hit_body(AppState *app, int view, double bx, double by)
{
    for (int i = app->obj_zone_count - 1; i >= 0; i--) {
        ObjZone *z = app->obj_zones[i];
        if (!z || z->view != view) continue;
        for (int j = 0; j < z->n; j++) {
            double dx = z->bx[j] - bx, dy = z->by[j] - by;
            if (dx*dx + dy*dy < 10.0 * 10.0) return i;
        }
    }
    return -1;
}

static int obj_point_hit_body(AppState *app, int view, double bx, double by)
{
    for (int i = app->obj_point_count - 1; i >= 0; i--) {
        ObjPoint *p = &app->obj_points[i];
        if (p->view != view) continue;
        double dx = p->bx - bx, dy = p->by - by;
        if (dx*dx + dy*dy < 12.0 * 12.0) return i;
    }
    return -1;
}

static int obj_tick_hit_body(AppState *app, int view, double bx, double by)
{
    for (int i = app->obj_tick_count - 1; i >= 0; i--) {
        ObjTick *t = &app->obj_ticks[i];
        if (t->view != view) continue;
        double dx = t->bx - bx, dy = t->by - by;
        if (dx*dx + dy*dy < 12.0 * 12.0) return i;
    }
    return -1;
}

/* Places a tick/cross immediately at (bx,by) using the currently-armed
 * obj_tick_type/obj_tick_state — no drag phase, no dialog, unlike zones
 * (drag-to-draw) and numeric points (click opens a value-entry dialog).
 * Direct user request: "I just want to select the purple tick and put it
 * in" — one click per marker. */
static void obj_place_tick(AppState *app, int view, double bx, double by, GtkWidget *da)
{
    if (app->obj_tick_count >= MAX_OBJ_TICKS) return;
    ObjTick *t = &app->obj_ticks[app->obj_tick_count++];
    t->bx    = bx;
    t->by    = by;
    t->view  = view;
    t->type  = app->obj_tick_type;
    t->state = app->obj_tick_state;
    if (app->obj_undo_type_top < 64)
        app->obj_undo_type_stack[app->obj_undo_type_top++] = 2;
    if (da) gtk_widget_queue_draw(da);
}

static void obj_commit_active_zone(AppState *app, GtkWidget *da)
{
    ObjZone *z = app->obj_active_zone;
    if (!z) return;
    app->obj_active_zone = NULL;
    if (z->n >= 3 && app->obj_zone_count < MAX_OBJ_ZONES) {
        app->obj_zones[app->obj_zone_count++] = z;
        if (app->obj_undo_type_top < 64)
            app->obj_undo_type_stack[app->obj_undo_type_top++] = 0;
    } else {
        obj_zone_free(z);
    }
    if (da) gtk_widget_queue_draw(da);
}

static gboolean obj_handle_erase(AppState *app, int view,
                                  double bx, double by, GtkWidget *da)
{
    int iz = obj_zone_hit_body(app, view, bx, by);
    if (iz >= 0) {
        obj_zone_free(app->obj_zones[iz]);
        for (int k = iz; k < app->obj_zone_count - 1; k++)
            app->obj_zones[k] = app->obj_zones[k + 1];
        app->obj_zone_count--;
        app->obj_zones[app->obj_zone_count] = NULL;
        if (app->obj_undo_type_top > 0 &&
            app->obj_undo_type_stack[app->obj_undo_type_top - 1] == 0)
            app->obj_undo_type_top--;
        gtk_widget_queue_draw(da);
        return TRUE;
    }
    int ip = obj_point_hit_body(app, view, bx, by);
    if (ip >= 0) {
        for (int k = ip; k < app->obj_point_count - 1; k++)
            app->obj_points[k] = app->obj_points[k + 1];
        app->obj_point_count--;
        if (app->obj_undo_type_top > 0 &&
            app->obj_undo_type_stack[app->obj_undo_type_top - 1] == 1)
            app->obj_undo_type_top--;
        gtk_widget_queue_draw(da);
        return TRUE;
    }
    int it = obj_tick_hit_body(app, view, bx, by);
    if (it >= 0) {
        for (int k = it; k < app->obj_tick_count - 1; k++)
            app->obj_ticks[k] = app->obj_ticks[k + 1];
        app->obj_tick_count--;
        if (app->obj_undo_type_top > 0 &&
            app->obj_undo_type_stack[app->obj_undo_type_top - 1] == 2)
            app->obj_undo_type_top--;
        gtk_widget_queue_draw(da);
        return TRUE;
    }
    /* Pencil strokes drawn while in Objective mode (2026-08-26) — same
     * proximity hit-test input_begin()'s own TOOL_ERASE case uses for
     * Subjective strokes, against app->obj_pencil_strokes (Objective's own
     * pencil layer, NOT app->strokes — see canvas.h's field comment). */
    for (int i = app->obj_pencil_strokes->n - 1; i >= 0; i--) {
        Stroke *s = app->obj_pencil_strokes->strokes[i];
        if ((int)s->view != view) continue;
        for (size_t j = 0; j < s->n_pts; j++) {
            double dx = s->pts[j].x - bx, dy = s->pts[j].y - by;
            if (sqrt(dx*dx + dy*dy) < 8.0) {
                stroke_free(s);
                for (int k = i; k < app->obj_pencil_strokes->n - 1; k++)
                    app->obj_pencil_strokes->strokes[k] = app->obj_pencil_strokes->strokes[k + 1];
                app->obj_pencil_strokes->n--;
                app->stroke_version++;
                if (app->obj_undo_type_top > 0 &&
                    app->obj_undo_type_stack[app->obj_undo_type_top - 1] == 3)
                    app->obj_undo_type_top--;
                gtk_widget_queue_draw(da);
                return TRUE;
            }
        }
    }
    return FALSE;
}

/* ── Pencil tool in Objective mode (2026-08-26) ──────────────────────────────
 * "Add a pencil tool to the objective fields, exactly the same as the
 * subjective" — rather than inventing a new Objective-specific freehand
 * construct, this reuses Subjective's own SYMPTOM_PENCIL stroke mechanism
 * outright (same Stroke struct, same input_begin/motion/end, same
 * app->strokes list — a pencil mark has no clinical typing of its own, so
 * there's no reason for it to need separate storage per mode). When this
 * predicate is true, every Objective-mode gesture branch below steps aside
 * (via `&& !obj_pencil_active(app)` on its current_mode check) so execution
 * falls through to the exact same generic code Subjective mode already
 * uses. Rendering is the one place that needs an ADDITION rather than a
 * bypass — see draw_pencil_strokes_body() — since Objective's own render
 * path doesn't otherwise touch app->strokes at all. */
gboolean obj_pencil_active(const AppState *app)
{
    return app->obj_pencil_mode && app->tool == TOOL_DRAW;
}

static void draw_pencil_strokes_body(AppState *app, cairo_t *cr, int view, double zoom)
{
    /* app->obj_pencil_strokes, NOT app->strokes — Objective's own pencil
     * marks are a separate annotation layer from Subjective's, even though
     * they share the same tool/drawing code. See canvas.h's field comment. */
    for (int i = 0; i < app->obj_pencil_strokes->n; i++) {
        Stroke *sk = app->obj_pencil_strokes->strokes[i];
        if (sk->view != view) continue;
        draw_stroke(cr, sk, &SYMPTOM_DEFS[sk->type], app, zoom);
    }
}

/* ── Pressure helper (raw GdkEvent — no gesture required) ───────────────── */
static double event_effective_pressure(GdkEvent *ev, const AppState *app)
{
    gdouble pressure = 0.5;
    gdk_event_get_axis(ev, GDK_AXIS_PRESSURE, &pressure);
    pressure = CLAMP(pressure, 0.0, 1.0);
    if (app->pen_tilt_weight > 0.0f) {
        gdouble xt = 0.0, yt = 0.0;
        gdk_event_get_axis(ev, GDK_AXIS_XTILT, &xt);
        gdk_event_get_axis(ev, GDK_AXIS_YTILT, &yt);
        double tilt = sqrt(xt * xt + yt * yt) * (1.0 / G_SQRT2);
        pressure = CLAMP(pressure + tilt * (double)app->pen_tilt_weight, 0.0, 1.0);
    }
    return pow(fmax(pressure, 0.01), (double)app->pen_gamma);
}

/* ── Single capture-phase stylus handler (replaces GtkGestureStylus) ────── *
 * Using GtkGestureStylus, the gesture state machine gets stuck after focus  *
 * switches: the compositor doesn't always deliver proximity-out on loss of  *
 * focus, leaving the gesture in DENIED/indeterminate state. A capture-phase *
 * GtkEventControllerLegacy receives raw GDK events before any gesture       *
 * processing, has no sequence tracking, and resets cleanly on every event.  *
 * Returning TRUE consumes the event so GtkGestureDrag never sees it.        */
static gboolean on_stylus_legacy(GtkEventControllerLegacy *ctrl,
                                  GdkEvent *event, gpointer d)
{
    (void)ctrl;

    /* Only handle pen / eraser tool events */
    GdkDeviceTool *tool = gdk_event_get_device_tool(event);
    if (!tool) return FALSE;
    GdkDeviceToolType tooltype = gdk_device_tool_get_tool_type(tool);
    if (tooltype != GDK_DEVICE_TOOL_TYPE_PEN &&
        tooltype != GDK_DEVICE_TOOL_TYPE_ERASER)
        return FALSE;

    ColData  *cd  = d;
    AppState *app = cd->app;

    double x = 0.0, y = 0.0;
    gdk_event_get_position(event, &x, &y);

    /* GtkEventControllerLegacy does no coordinate transformation — gdk_event_get_position()
     * returns surface (window) coordinates.  Convert to widget-local coordinates so that
     * screen_to_body() receives the same space as GtkGestureStylus signals used to. */
    {
        graphene_point_t src = { (float)x, (float)y };
        graphene_point_t dst;
        if (!gtk_widget_compute_point(
                GTK_WIDGET(gtk_widget_get_native(cd->da)), cd->da, &src, &dst))
            return FALSE;
        x = (double)dst.x;
        y = (double)dst.y;
    }

    /* Keep mouse_x/y current so scroll-zoom focal point works with stylus */
    cd->mouse_x = x;
    cd->mouse_y = y;

    /* ── BUTTON_PRESS ─────────────────────────────────────────────────────── */
    if (GDK_IS_EVENT_TYPE(event, GDK_BUTTON_PRESS)) {
        guint btn = gdk_button_event_get_button(event);

        if (btn >= 2) {
            /* Barrel button — toggle fine/wide mode */
            input_cancel(app);
            app->pen_wide_mode = !app->pen_wide_mode;
            if (app->toolbar_update_cb) app->toolbar_update_cb(app);
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }

        /* btn == 1: pen touch */
        app->current_view   = cd->view;
        app->last_stylus_us = g_get_monotonic_time();

        /* Physical eraser tip overrides current tool */
        if (tooltype == GDK_DEVICE_TOOL_TYPE_ERASER)
            app->tool = TOOL_ERASE;

        /* Legend drag (posterior only) */
        if (cd->view == VIEW_POSTERIOR) {
            gboolean leg_hit = (app->current_mode == APP_MODE_SUBJECTIVE)
                               ? legend_hit_screen(app, cd, x, y)
                               : obj_legend_hit_screen(app, cd, x, y);
            if (leg_hit) {
                double bx, by;
                screen_to_body(cd, x, y, &bx, &by);
                app->legend_drag_active = TRUE;
                app->legend_drag_bx_off = app->legend_bx - bx;
                app->legend_drag_by_off = app->legend_by - by;
                return TRUE;
            }
        }

        /* Sx mode: drag existing notes / link summary */
        if (app->current_mode == APP_MODE_SUBJECTIVE) {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            if (link_summary_hit_screen(app, cd, x, y)) {
                app->link_drag_active = TRUE;
                app->link_drag_bx_off = app->link_summary_bx - bx;
                app->link_drag_by_off = app->link_summary_by - by;
                return TRUE;
            }
            int hit = note_hit_screen(app, cd, x, y);
            if (hit >= 0) {
                double lbx, lby;
                label_anchor_resolve(&app->notes[hit], &lbx, &lby);
                app->note_drag_idx    = hit;
                app->note_drag_bx_off = lbx - bx;
                app->note_drag_by_off = lby - by;
                return TRUE;
            }
        }

        if (app->tool == TOOL_NOTE) {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            if (app->show_note_wizard_cb)
                app->show_note_wizard_cb(app, (int)cd->view, bx, by);
            return TRUE;
        }

        if (app->tool == TOOL_ARROW) {
            int hit = arrow_head_hit_screen(app, cd, x, y);
            if (hit >= 0) {
                for (int k = hit; k < app->arrow_count - 1; k++)
                    app->arrows[k] = app->arrows[k + 1];
                app->arrow_count--;
                if (app->undo_type_top > 0 &&
                    app->undo_type_stack[app->undo_type_top - 1] == 1)
                    app->undo_type_top--;
                app->stroke_version++;
                gtk_widget_queue_draw(cd->da);
                return TRUE;
            }
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            app->arrow_drawing   = TRUE;
            app->arrow_draw_view = (int)cd->view;
            app->arrow_x1 = app->arrow_x2 = bx;
            app->arrow_y1 = app->arrow_y2 = by;
            app->arrow_track_n   = 0;
            arrow_track_add(app, bx, by);
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }

        if (app->current_mode == APP_MODE_OBJECTIVE && !obj_pencil_active(app)) {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            if (app->tool == TOOL_ERASE) {
                obj_handle_erase(app, (int)cd->view, bx, by, cd->da);
                return TRUE;
            }
            if (app->obj_tick_mode) {
                obj_place_tick(app, (int)cd->view, bx, by, cd->da);
                return TRUE;
            }
            if (app->obj_point_mode) {
                int phit = obj_point_hit_screen(app, cd, x, y);
                if (phit >= 0) {
                    double plbx, plby;
                    obj_label_resolve(&app->obj_points[phit], &plbx, &plby);
                    app->obj_point_drag_idx    = phit;
                    app->obj_point_drag_bx_off = plbx - bx;
                    app->obj_point_drag_by_off = plby - by;
                    return TRUE;
                }
                if (app->show_ppt_entry_cb)
                    app->show_ppt_entry_cb(app, cd->da, x, y, (int)cd->view, bx, by);
                return TRUE;
            }
            if (app->obj_active_zone) {
                obj_zone_free(app->obj_active_zone);
                app->obj_active_zone = NULL;
            }
            app->obj_active_zone = obj_zone_new(app->obj_zone_type, (int)cd->view);
            obj_zone_add_pt(app->obj_active_zone, (float)bx, (float)by);
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }

        if (app->tool == TOOL_ERASE) {
            int hit = arrow_head_hit_screen(app, cd, x, y);
            if (hit >= 0) {
                for (int k = hit; k < app->arrow_count - 1; k++)
                    app->arrows[k] = app->arrows[k + 1];
                app->arrow_count--;
                if (app->undo_type_top > 0 &&
                    app->undo_type_stack[app->undo_type_top - 1] == 1)
                    app->undo_type_top--;
                app->stroke_version++;
                gtk_widget_queue_draw(cd->da);
                return TRUE;
            }
        }

        {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            input_begin(app, bx, by, event_effective_pressure(event, app));
        }
        gtk_widget_queue_draw(cd->da);
        return TRUE;
    }

    /* ── MOTION_NOTIFY ────────────────────────────────────────────────────── */
    if (GDK_IS_EVENT_TYPE(event, GDK_MOTION_NOTIFY)) {
        app->last_stylus_us = g_get_monotonic_time();

        if (app->legend_drag_active) {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            app->legend_bx = bx + app->legend_drag_bx_off;
            app->legend_by = by + app->legend_drag_by_off;
            canvas_invalidate(app);
            return TRUE;
        }
        if (app->note_drag_idx >= 0) {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            NoteAnnotation *na = &app->notes[app->note_drag_idx];
            na->label.lx     = bx + app->note_drag_bx_off;
            na->label.ly     = by + app->note_drag_by_off;
            na->label.placed = 1;
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }
        if (app->link_drag_active) {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            app->link_summary_bx   = bx + app->link_drag_bx_off;
            app->link_summary_by   = by + app->link_drag_by_off;
            app->link_summary_view = (int)cd->view;
            canvas_invalidate(app);
            return TRUE;
        }
        if (app->tool == TOOL_NOTE) return TRUE;

        if (app->obj_point_drag_idx >= 0) {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            ObjPoint *op = &app->obj_points[app->obj_point_drag_idx];
            op->anchor.lx     = bx + app->obj_point_drag_bx_off;
            op->anchor.ly     = by + app->obj_point_drag_by_off;
            op->anchor.placed = 1;
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }
        if (app->tool == TOOL_ARROW && app->arrow_drawing) {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            app->arrow_x2 = bx;
            app->arrow_y2 = by;
            arrow_track_add(app, bx, by);
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }
        if (app->current_mode == APP_MODE_OBJECTIVE && app->obj_active_zone) {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            obj_zone_add_pt(app->obj_active_zone, (float)bx, (float)by);
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }
        {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            input_motion(app, bx, by, event_effective_pressure(event, app));
        }
        gtk_widget_queue_draw(cd->da);
        return TRUE;
    }

    /* ── BUTTON_RELEASE ───────────────────────────────────────────────────── */
    if (GDK_IS_EVENT_TYPE(event, GDK_BUTTON_RELEASE)) {
        guint btn = gdk_button_event_get_button(event);
        if (btn != 1) return TRUE; /* consume barrel releases silently */
        app->last_stylus_us = g_get_monotonic_time();

        if (app->legend_drag_active) {
            app->legend_drag_active = FALSE;
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }
        if (app->note_drag_idx >= 0 || app->link_drag_active) {
            app->note_drag_idx    = -1;
            app->link_drag_active = FALSE;
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }
        if (app->tool == TOOL_NOTE) {
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }
        if (app->obj_point_drag_idx >= 0) {
            app->obj_point_drag_idx = -1;
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }
        if (app->tool == TOOL_ARROW && app->arrow_drawing) {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            app->arrow_x2 = bx; app->arrow_y2 = by;
            double adx = bx - app->arrow_x1, ady = by - app->arrow_y1;
            if (app->arrow_count < MAX_ARROWS &&
                sqrt(adx*adx + ady*ady) >= 2.0) {
                double cpx, cpy;
                arrow_get_cp(app, &cpx, &cpy);
                app->arrows[app->arrow_count] = (ArrowAnnotation){
                    .view = app->arrow_draw_view,
                    .x1 = app->arrow_x1, .y1 = app->arrow_y1,
                    .cx = cpx, .cy = cpy,
                    .x2 = bx,  .y2 = by
                };
                if (app->undo_type_top < 64)
                    app->undo_type_stack[app->undo_type_top++] = 1;
                app->arrow_count++;
                app->stroke_version++;
            }
            app->arrow_drawing = FALSE;
            app->arrow_track_n = 0;
            gtk_widget_queue_draw(cd->da);
            return TRUE;
        }
        if (app->current_mode == APP_MODE_OBJECTIVE && !obj_pencil_active(app)) {
            obj_commit_active_zone(app, cd->da);
            return TRUE;
        }
        input_end(app);
        gtk_widget_queue_draw(cd->da);
        return TRUE;
    }

    /* Consume all other pen/eraser events (proximity, etc.) to keep
     * GtkGestureDrag from seeing any stylus traffic. */
    return TRUE;
}

/* ── Drag gestures ───────────────────────────────────────────────────────── */
/* Drag gesture handles widget repositioning only — all drawing is stylus-only
 * via on_stylus_legacy.  This ensures capacitive-layer touch events from the
 * Wacom dual digitiser never trigger drawing operations. */
static void on_drag_begin(GtkGestureDrag *gd, double x, double y, gpointer d)
{
    ColData  *cd  = d;
    AppState *app = cd->app;
    (void)gd;

    /* Legend drag (posterior only, mode-specific hit test) */
    if (cd->view == VIEW_POSTERIOR) {
        gboolean leg_hit = (app->current_mode == APP_MODE_SUBJECTIVE)
                           ? legend_hit_screen(app, cd, x, y)
                           : obj_legend_hit_screen(app, cd, x, y);
        if (leg_hit) {
            double bx_hit, by_hit;
            screen_to_body(cd, x, y, &bx_hit, &by_hit);
            app->legend_drag_active = TRUE;
            app->legend_drag_bx_off = app->legend_bx - bx_hit;
            app->legend_drag_by_off = app->legend_by - by_hit;
            return;
        }
    }

    /* Sx mode: reposition existing note / link-summary if hit */
    if (app->current_mode == APP_MODE_SUBJECTIVE) {
        double bx_hit, by_hit;
        screen_to_body(cd, x, y, &bx_hit, &by_hit);
        if (link_summary_hit_screen(app, cd, x, y)) {
            app->link_drag_active = TRUE;
            app->link_drag_bx_off = app->link_summary_bx - bx_hit;
            app->link_drag_by_off = app->link_summary_by - by_hit;
            return;
        }
        int hit = note_hit_screen(app, cd, x, y);
        if (hit >= 0) {
            double lbx, lby;
            label_anchor_resolve(&app->notes[hit], &lbx, &lby);
            app->note_drag_idx    = hit;
            app->note_drag_bx_off = lbx - bx_hit;
            app->note_drag_by_off = lby - by_hit;
            return;
        }
    }

    /* Obj mode: reposition point label if hit */
    if (app->current_mode == APP_MODE_OBJECTIVE && app->obj_point_mode) {
        int phit = obj_point_hit_screen(app, cd, x, y);
        if (phit >= 0) {
            double bx, by;
            screen_to_body(cd, x, y, &bx, &by);
            double plbx, plby;
            obj_label_resolve(&app->obj_points[phit], &plbx, &plby);
            app->obj_point_drag_idx    = phit;
            app->obj_point_drag_bx_off = plbx - bx;
            app->obj_point_drag_by_off = plby - by;
            return;
        }
    }

    /* Finger / mouse drawing — stylus takes priority via palm rejection */
    if (app->pen_palm_reject &&
        (g_get_monotonic_time() - app->last_stylus_us) < 500000)
        return;

    app->current_view = cd->view;
    double bx, by;
    screen_to_body(cd, x, y, &bx, &by);

    if (app->tool == TOOL_NOTE) {
        if (app->show_note_wizard_cb)
            app->show_note_wizard_cb(app, (int)cd->view, bx, by);
        return;
    }

    if (app->tool == TOOL_ARROW) {
        int hit = arrow_head_hit_screen(app, cd, x, y);
        if (hit >= 0) {
            for (int k = hit; k < app->arrow_count - 1; k++)
                app->arrows[k] = app->arrows[k + 1];
            app->arrow_count--;
            if (app->undo_type_top > 0 &&
                app->undo_type_stack[app->undo_type_top - 1] == 1)
                app->undo_type_top--;
            app->stroke_version++;
            gtk_widget_queue_draw(cd->da);
            return;
        }
        app->arrow_drawing   = TRUE;
        app->arrow_draw_view = (int)cd->view;
        app->arrow_x1 = app->arrow_x2 = bx;
        app->arrow_y1 = app->arrow_y2 = by;
        app->arrow_track_n = 0;
        arrow_track_add(app, bx, by);
        cd->touch_drawing = TRUE;
        gtk_widget_queue_draw(cd->da);
        return;
    }

    if (app->current_mode == APP_MODE_OBJECTIVE && !obj_pencil_active(app)) {
        if (app->tool == TOOL_ERASE) {
            obj_handle_erase(app, (int)cd->view, bx, by, cd->da);
            return;
        }
        if (app->obj_tick_mode) {
            obj_place_tick(app, (int)cd->view, bx, by, cd->da);
            return;
        }
        if (app->obj_point_mode) {
            /* Placing a NEW numeric point (PPT/TS/Monofilament/2-PD) via
             * finger or mouse — this branch was missing entirely (found
             * live: touch/mouse could drag an EXISTING point's label, see
             * the phit>=0 branch above, but tapping empty space to place a
             * new one silently did nothing, only on_stylus_legacy's own
             * BUTTON_PRESS handler had this). Matches that handler exactly. */
            if (app->show_ppt_entry_cb)
                app->show_ppt_entry_cb(app, cd->da, x, y, (int)cd->view, bx, by);
            return;
        }
        if (app->obj_active_zone) {
            obj_zone_free(app->obj_active_zone);
            app->obj_active_zone = NULL;
        }
        app->obj_active_zone = obj_zone_new(app->obj_zone_type, (int)cd->view);
        obj_zone_add_pt(app->obj_active_zone, (float)bx, (float)by);
        cd->touch_drawing = TRUE;
        gtk_widget_queue_draw(cd->da);
        return;
    }

    input_begin(app, bx, by, 1.0);
    if (app->active_stroke)
        app->active_stroke->draw_zoom = *cd->p_zoom;
    cd->touch_drawing = TRUE;
    gtk_widget_queue_draw(cd->da);
}

static void on_drag_update(GtkGestureDrag *gd, double dx, double dy,
                            gpointer d)
{
    ColData  *cd  = d;
    AppState *app = cd->app;
    double sx, sy;
    gtk_gesture_drag_get_start_point(gd, &sx, &sy);
    double bx, by;
    screen_to_body(cd, sx + dx, sy + dy, &bx, &by);

    /* Legend drag (any mode) */
    if (app->legend_drag_active) {
        app->legend_bx = bx + app->legend_drag_bx_off;
        app->legend_by = by + app->legend_drag_by_off;
        canvas_invalidate(app);
        return;
    }

    /* Note label drag / link drag (any tool) */
    if (app->note_drag_idx >= 0) {
        NoteAnnotation *na = &app->notes[app->note_drag_idx];
        na->label.lx     = bx + app->note_drag_bx_off;
        na->label.ly     = by + app->note_drag_by_off;
        na->label.placed = 1;
        gtk_widget_queue_draw(cd->da);
        return;
    }
    if (app->link_drag_active) {
        app->link_summary_bx   = bx + app->link_drag_bx_off;
        app->link_summary_by   = by + app->link_drag_by_off;
        app->link_summary_view = (int)cd->view;
        canvas_invalidate(app);
        return;
    }
    /* Obj point label drag */
    if (app->obj_point_drag_idx >= 0) {
        ObjPoint *op = &app->obj_points[app->obj_point_drag_idx];
        op->anchor.lx     = bx + app->obj_point_drag_bx_off;
        op->anchor.ly     = by + app->obj_point_drag_by_off;
        op->anchor.placed = 1;
        gtk_widget_queue_draw(cd->da);
        return;
    }

    /* Finger / mouse drawing motion */
    if (cd->touch_drawing) {
        if (app->tool == TOOL_ARROW && app->arrow_drawing) {
            app->arrow_x2 = bx;
            app->arrow_y2 = by;
            arrow_track_add(app, bx, by);
        } else if (app->current_mode == APP_MODE_OBJECTIVE && app->obj_active_zone) {
            obj_zone_add_pt(app->obj_active_zone, (float)bx, (float)by);
        } else {
            input_motion(app, bx, by, 1.0);
        }
        gtk_widget_queue_draw(cd->da);
    }
}

static void on_drag_end(GtkGestureDrag *gd, double dx, double dy, gpointer d)
{
    ColData  *cd  = d;
    AppState *app = cd->app;

    /* Clear legend / note / link drag (any tool) */
    if (app->legend_drag_active) {
        app->legend_drag_active = FALSE;
        gtk_widget_queue_draw(cd->da);
        return;
    }
    if (app->note_drag_idx >= 0 || app->link_drag_active) {
        app->note_drag_idx      = -1;
        app->link_drag_active   = FALSE;
        gtk_widget_queue_draw(cd->da);
        return;
    }

    /* Clear obj point drag */
    if (app->obj_point_drag_idx >= 0) {
        app->obj_point_drag_idx = -1;
        gtk_widget_queue_draw(cd->da);
        return;
    }

    if (!cd->touch_drawing) return;
    cd->touch_drawing = FALSE;

    double sx, sy;
    gtk_gesture_drag_get_start_point(gd, &sx, &sy);
    double bx, by;
    screen_to_body(cd, sx + dx, sy + dy, &bx, &by);

    if (app->tool == TOOL_ARROW && app->arrow_drawing) {
        app->arrow_x2 = bx;
        app->arrow_y2 = by;
        double adx = bx - app->arrow_x1, ady = by - app->arrow_y1;
        if (app->arrow_count < MAX_ARROWS &&
            sqrt(adx*adx + ady*ady) >= 2.0) {
            double cpx, cpy;
            arrow_get_cp(app, &cpx, &cpy);
            app->arrows[app->arrow_count] = (ArrowAnnotation){
                .view = app->arrow_draw_view,
                .x1 = app->arrow_x1, .y1 = app->arrow_y1,
                .cx = cpx,           .cy = cpy,
                .x2 = bx,            .y2 = by
            };
            if (app->undo_type_top < 64)
                app->undo_type_stack[app->undo_type_top++] = 1;
            app->arrow_count++;
            app->stroke_version++;
        }
        app->arrow_drawing = FALSE;
        app->arrow_track_n = 0;
        gtk_widget_queue_draw(cd->da);
        return;
    }

    if (app->current_mode == APP_MODE_OBJECTIVE && !obj_pencil_active(app)) {
        obj_commit_active_zone(app, cd->da);
        return;
    }

    input_end(app);
    gtk_widget_queue_draw(cd->da);
}

/* ── Zoom reset ──────────────────────────────────────────────────────────── */
static void on_reset_zoom(GtkButton *btn, gpointer d)
{
    ColData *cd = d;
    (void)btn;
    *cd->p_zoom  = 1.0;
    *cd->p_pan_x = 0.0;
    *cd->p_pan_y = 0.0;
    gtk_button_set_label(GTK_BUTTON(cd->zoom_btn), "1×");
    gtk_widget_queue_draw(cd->da);
}

/* ── Pinch-to-zoom + two-finger pan ─────────────────────────────────────── */
static void on_zoom_begin(GtkGestureZoom *gz, GdkEventSequence *seq,
                           gpointer d)
{
    (void)seq;
    ColData *cd = d;
    cd->last_zoom_scale = 1.0;
    gtk_gesture_get_bounding_box_center(GTK_GESTURE(gz),
                                         &cd->last_cx, &cd->last_cy);
    input_cancel(cd->app);
    cd->touch_drawing           = FALSE;  /* cancel any in-progress finger draw */
    cd->app->note_drag_idx      = -1;
    cd->app->link_drag_active   = FALSE;
    cd->app->legend_drag_active = FALSE;
    cd->app->obj_point_drag_idx = -1;
    gtk_widget_queue_draw(cd->da);
}

static void on_zoom_changed(GtkGestureZoom *gz, gdouble scale, gpointer d)
{
    ColData  *cd  = d;

    double delta = scale / cd->last_zoom_scale;
    cd->last_zoom_scale = scale;

    double fx, fy;
    gtk_gesture_get_bounding_box_center(GTK_GESTURE(gz), &fx, &fy);

    /* Two-finger pan: translate by centroid movement */
    double pan_dx = fx - cd->last_cx;
    double pan_dy = fy - cd->last_cy;
    cd->last_cx = fx;
    cd->last_cy = fy;

    double w     = (double)gtk_widget_get_width(cd->da);
    double h     = (double)gtk_widget_get_height(cd->da);
    double old_z = *cd->p_zoom;
    double new_z = CLAMP(old_z * delta, 0.2, 20.0);

    /* Keep focal body-point under centroid, then apply pan */
    double cx = w / 2.0 + (*cd->p_pan_x);
    double cy = h / 2.0 + (*cd->p_pan_y);
    *cd->p_pan_x = fx + (new_z / old_z) * (cx - fx) - w / 2.0 + pan_dx;
    *cd->p_pan_y = fy + (new_z / old_z) * (cy - fy) - h / 2.0 + pan_dy;
    *cd->p_zoom  = new_z;

    if (cd->zoom_btn) {
        char buf[10];
        snprintf(buf, sizeof(buf), "%.1f×", new_z);
        gtk_button_set_label(GTK_BUTTON(cd->zoom_btn), buf);
    }

    gtk_widget_queue_draw(cd->da);
}

/* on_raw_event removed — merged into on_stylus_legacy above */

/* ── Mouse motion tracker (feeds scroll-zoom focal point) ────────────────── */
static void on_mouse_motion(GtkEventControllerMotion *ctrl,
                             double x, double y, gpointer d)
{
    (void)ctrl;
    ColData *cd = d;
    cd->mouse_x = x;
    cd->mouse_y = y;
}

/* ── Scroll-wheel zoom ───────────────────────────────────────────────────── */
static gboolean on_scroll(GtkEventControllerScroll *ctrl,
                           double dx, double dy, gpointer d)
{
    (void)ctrl; (void)dx;
    ColData *cd = d;

    double w = (double)gtk_widget_get_width(cd->da);
    double h = (double)gtk_widget_get_height(cd->da);
    if (w <= 0.0 || h <= 0.0) return FALSE;

    double mx = cd->mouse_x;
    double my = cd->mouse_y;

    double factor = (dy < 0) ? 1.12 : (1.0 / 1.12);
    double old_z = *cd->p_zoom;
    double new_z = CLAMP(old_z * factor, 0.2, 20.0);

    double cx = w / 2.0 + (*cd->p_pan_x);
    double cy = h / 2.0 + (*cd->p_pan_y);
    *cd->p_pan_x = mx + (new_z / old_z) * (cx - mx) - w / 2.0;
    *cd->p_pan_y = my + (new_z / old_z) * (cy - my) - h / 2.0;
    *cd->p_zoom  = new_z;

    if (cd->zoom_btn) {
        char buf[10];
        snprintf(buf, sizeof(buf), "%.1f\xc3\x97", new_z);
        gtk_button_set_label(GTK_BUTTON(cd->zoom_btn), buf);
    }
    gtk_widget_queue_draw(cd->da);
    return TRUE;
}

/* ── Middle-button pan ───────────────────────────────────────────────────── */
static void on_mid_drag_begin(GtkGestureDrag *gd, double x, double y, gpointer d)
{
    (void)gd; (void)x; (void)y;
    ColData *cd = d;
    input_cancel(cd->app);
    cd->mid_pan_x0 = *cd->p_pan_x;
    cd->mid_pan_y0 = *cd->p_pan_y;
}

static void on_mid_drag_update(GtkGestureDrag *gd, double dx, double dy, gpointer d)
{
    (void)gd;
    ColData *cd = d;
    *cd->p_pan_x = cd->mid_pan_x0 + dx;
    *cd->p_pan_y = cd->mid_pan_y0 + dy;
    gtk_widget_queue_draw(cd->da);
}

/* ── Build one drawing area with header + all gesture controllers ────────── */
static GtkWidget *make_drawing_area(AppState *app, ColData *cd,
                                     const char *label)
{
    GtkWidget *vbox = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_set_hexpand(vbox, TRUE);
    gtk_widget_set_vexpand(vbox, TRUE);

    /* Header bar */
    GtkWidget *hdr = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 4);
    gtk_widget_set_name(hdr, "col-header");

    GtkWidget *lbl = gtk_label_new(label);
    gtk_widget_set_hexpand(lbl, TRUE);
    gtk_label_set_xalign(GTK_LABEL(lbl), 0.0);
    gtk_widget_set_margin_start(lbl, 6);
    cd->header_label = lbl;
    gtk_box_append(GTK_BOX(hdr), lbl);

    GtkWidget *zbtn = gtk_button_new_with_label("1×");
    gtk_widget_set_name(zbtn, "zoom-btn");
    gtk_widget_set_size_request(zbtn, 44, 26);
    gtk_widget_set_margin_end(zbtn, 4);
    gtk_widget_set_margin_top(zbtn, 2);
    gtk_widget_set_margin_bottom(zbtn, 2);
    cd->zoom_btn = zbtn;
    g_signal_connect(zbtn, "clicked", G_CALLBACK(on_reset_zoom), cd);
    gtk_box_append(GTK_BOX(hdr), zbtn);
    gtk_box_append(GTK_BOX(vbox), hdr);

    /* Drawing area */
    GtkWidget *da = gtk_drawing_area_new();
    cd->da = da;
    gtk_drawing_area_set_draw_func(GTK_DRAWING_AREA(da), on_col_draw, cd, NULL);
    gtk_widget_set_hexpand(da, TRUE);
    gtk_widget_set_vexpand(da, TRUE);

    /* Capture-phase legacy controller handles all pen/eraser events directly.
     * This bypasses GTK's gesture state machine entirely — no sequence tracking,
     * no DENIED states, no focus-transition bugs.  Returns TRUE to consume pen
     * events so GtkGestureDrag never sees stylus traffic. */
    GtkEventController *stylus_raw = gtk_event_controller_legacy_new();
    gtk_event_controller_set_propagation_phase(stylus_raw, GTK_PHASE_CAPTURE);
    gtk_widget_add_controller(da, stylus_raw);
    g_signal_connect(stylus_raw, "event", G_CALLBACK(on_stylus_legacy), cd);

    /* Drag (mouse / single touch) */
    GtkGesture *drag = gtk_gesture_drag_new();
    gtk_gesture_single_set_touch_only(GTK_GESTURE_SINGLE(drag), FALSE);
    gtk_widget_add_controller(da, GTK_EVENT_CONTROLLER(drag));
    g_signal_connect(drag, "drag-begin",  G_CALLBACK(on_drag_begin),  cd);
    g_signal_connect(drag, "drag-update", G_CALLBACK(on_drag_update), cd);
    g_signal_connect(drag, "drag-end",    G_CALLBACK(on_drag_end),    cd);

    /* Pinch-zoom (also drives two-finger pan) */
    GtkGesture *zoom = gtk_gesture_zoom_new();
    gtk_widget_add_controller(da, GTK_EVENT_CONTROLLER(zoom));
    g_signal_connect(zoom, "begin",         G_CALLBACK(on_zoom_begin),   cd);
    g_signal_connect(zoom, "scale-changed", G_CALLBACK(on_zoom_changed), cd);

    /* Scroll-wheel zoom */
    GtkEventController *scroll = gtk_event_controller_scroll_new(
        GTK_EVENT_CONTROLLER_SCROLL_VERTICAL);
    gtk_widget_add_controller(da, scroll);
    g_signal_connect(scroll, "scroll", G_CALLBACK(on_scroll), cd);

    /* Mouse motion — keeps cd->mouse_x/y current for scroll zoom focal point */
    GtkEventController *motion = gtk_event_controller_motion_new();
    gtk_widget_add_controller(da, motion);
    g_signal_connect(motion, "motion", G_CALLBACK(on_mouse_motion), cd);

    /* Middle-button pan */
    GtkGesture *mid = gtk_gesture_drag_new();
    gtk_gesture_single_set_button(GTK_GESTURE_SINGLE(mid), 2);
    gtk_widget_add_controller(da, GTK_EVENT_CONTROLLER(mid));
    g_signal_connect(mid, "drag-begin",  G_CALLBACK(on_mid_drag_begin),  cd);
    g_signal_connect(mid, "drag-update", G_CALLBACK(on_mid_drag_update), cd);

    /* Stylus events are handled by stylus_raw (capture phase) above;
     * the old separate barrel-button raw controller has been merged into it. */

    gtk_box_append(GTK_BOX(vbox), da);

    (void)app;
    return vbox;
}

/* ── Floating goniometer-chart overlay layer ───────────────────────────── *
 * A transparent GtkDrawingArea sitting in a GtkOverlay above the whole
 * canvas stack, so ROM charts float over all four panels and the inter-
 * panel gutters with no clipping. Display only for now (can-target FALSE);
 * chart dragging is handled from the per-panel gesture handlers in a later
 * step, translating their local coords into this layer's space.            */
static void on_gonio_layer_draw(GtkDrawingArea *da, cairo_t *cr,
                                int width, int height, gpointer user_data)
{
    (void)da;
    AppState *app = user_data;
    if (app->current_mode != APP_MODE_OBJECTIVE) return;
    if (app->gonio_chart_count == 0) return;
    gonio_charts_render(app, cr, (double)width, (double)height, TRUE);
}

/* ── Public API ──────────────────────────────────────────────────────────── */

GtkWidget *canvas_new(AppState *app)
{
    app->note_drag_idx        = -1;
    app->link_drag_active     = FALSE;
    app->legend_drag_active   = FALSE;
    app->obj_point_drag_idx   = -1;
    app->gonio_chart_active_idx = -1;
    app->gonio_chart_drag_idx   = -1;
    if (app->legend_bx == 0.0 && app->legend_by == 0.0) {
        app->legend_bx = 135.0;
        app->legend_by = 378.0;
    }

    /* Initialise right slot views (can be overridden by settings before canvas_new) */
    if (app->right_slot_views[0] == 0 && app->right_slot_views[1] == 0) {
        app->right_slot_views[0] = VIEW_LATERAL_L;
        app->right_slot_views[1] = VIEW_LATERAL_R;
    }

    /* Initialise zoom/pan state */
    for (int i = 0; i < 4; i++) {
        app->col_zoom[i]    = app->single_zoom[i]    = 1.0;
        app->col_pan_x[i]   = app->single_pan_x[i]   = 0.0;
        app->col_pan_y[i]   = app->single_pan_y[i]   = 0.0;
        app->col_da[i]      = app->single_da[i]       = NULL;
    }

    /* Initialise ColData for quad slots (0-3) and single slots (4-7).
     * Free any existing cache surfaces in case canvas_new is called again. */
    for (int i = 0; i < 8; i++) {
        if (g_col[i].stroke_cache) {
            cairo_surface_destroy(g_col[i].stroke_cache);
            g_col[i].stroke_cache = NULL;
        }
    }
    for (int i = 0; i < 4; i++) {
        /* Quad right slots (2,3) use cyclable views; left slots and all singles are fixed */
        BodyView qview = (i < 2) ? SINGLE_SLOT_VIEWS[i] : app->right_slot_views[i - 2];
        g_col[i]   = (ColData){ .app = app, .view = qview,
                                 .p_zoom  = &app->col_zoom[i],
                                 .p_pan_x = &app->col_pan_x[i],
                                 .p_pan_y = &app->col_pan_y[i],
                                 .last_zoom_scale = 1.0,
                                 .stroke_cache = NULL,
                                 .cache_stroke_version = -1 };
        g_col[4+i] = (ColData){ .app = app, .view = SINGLE_SLOT_VIEWS[i],
                                 .p_zoom  = &app->single_zoom[i],
                                 .p_pan_x = &app->single_pan_x[i],
                                 .p_pan_y = &app->single_pan_y[i],
                                 .last_zoom_scale = 1.0,
                                 .stroke_cache = NULL,
                                 .cache_stroke_version = -1 };
    }

    /* GtkStack: one page per layout mode */
    GtkWidget *stack = gtk_stack_new();
    gtk_stack_set_transition_type(GTK_STACK(stack), GTK_STACK_TRANSITION_TYPE_NONE);
    gtk_widget_set_hexpand(stack, TRUE);
    gtk_widget_set_vexpand(stack, TRUE);

    /* ── Quad layout ── *
     * GtkGrid with 5 homogeneous columns × 2 homogeneous rows:            *
     *   cols 0-1 = anterior  (2 cols wide, full height)                   *
     *   cols 2-3 = posterior (2 cols wide, full height)                   *
     *   col  4, row 0 = lateral_l  (1 col wide, half height)              *
     *   col  4, row 1 = lateral_r  (1 col wide, half height)              *
     * Column homogeneity → 2:2:1 width ratio automatically.               */
    GtkWidget *grid = gtk_grid_new();
    gtk_grid_set_column_homogeneous(GTK_GRID(grid), TRUE);
    gtk_grid_set_row_homogeneous(GTK_GRID(grid), TRUE);
    gtk_widget_set_hexpand(grid, TRUE);
    gtk_widget_set_vexpand(grid, TRUE);

    GtkWidget *w;

    w = make_drawing_area(app, &g_col[0], "Anterior");
    app->col_da[0] = g_col[0].da;
    gtk_grid_attach(GTK_GRID(grid), w, 0, 0, 2, 2);

    w = make_drawing_area(app, &g_col[1], "Posterior");
    app->col_da[1] = g_col[1].da;
    gtk_grid_attach(GTK_GRID(grid), w, 2, 0, 2, 2);

    w = make_drawing_area(app, &g_col[2], "Left lateral");
    app->col_da[2] = g_col[2].da;
    gtk_grid_attach(GTK_GRID(grid), w, 4, 0, 1, 1);

    w = make_drawing_area(app, &g_col[3], "Right lateral");
    app->col_da[3] = g_col[3].da;
    gtk_grid_attach(GTK_GRID(grid), w, 4, 1, 1, 1);

    gtk_stack_add_named(GTK_STACK(stack), grid, "quad");

    /* ── Single-view pages ── */
    static const char *sv_labels[] = {
        "Anterior", "Posterior", "Left lateral", "Right lateral"
    };
    static const char *sv_names[] = {
        "anterior", "posterior", "lateral_l", "lateral_r"
    };
    for (int i = 0; i < 4; i++) {
        w = make_drawing_area(app, &g_col[4 + i], sv_labels[i]);
        app->single_da[i] = g_col[4 + i].da;
        gtk_stack_add_named(GTK_STACK(stack), w, sv_names[i]);
    }

    gtk_stack_set_visible_child_name(GTK_STACK(stack), "quad");
    app->layout_mode  = LAYOUT_QUAD;
    app->current_view = VIEW_ANTERIOR;
    app->canvas       = stack;

    /* Wrap the stack in an overlay carrying the floating ROM-chart layer.
     * canvas_set_layout() still drives app->canvas (the stack) directly, so
     * layout switching is unaffected. */
    GtkWidget *overlay = gtk_overlay_new();
    gtk_overlay_set_child(GTK_OVERLAY(overlay), stack);

    GtkWidget *layer = gtk_drawing_area_new();
    gtk_widget_set_can_target(layer, FALSE);          /* display only (step D-2) */
    gtk_widget_set_hexpand(layer, TRUE);
    gtk_widget_set_vexpand(layer, TRUE);
    gtk_drawing_area_set_draw_func(GTK_DRAWING_AREA(layer),
                                   on_gonio_layer_draw, app, NULL);
    gtk_overlay_add_overlay(GTK_OVERLAY(overlay), layer);
    app->gonio_layer_da = layer;

    return overlay;
}

void canvas_set_layout(AppState *app, LayoutMode mode)
{
    static const char *names[] = {
        "quad", "anterior", "posterior", "lateral_l", "lateral_r"
    };
    static const BodyView sv[] = {
        VIEW_ANTERIOR,  /* LAYOUT_QUAD — not used for current_view */
        VIEW_ANTERIOR,
        VIEW_POSTERIOR,
        VIEW_LATERAL_L,
        VIEW_LATERAL_R,
    };

    app->layout_mode = mode;
    if (mode != LAYOUT_QUAD)
        app->current_view = sv[mode];

    gtk_stack_set_visible_child_name(GTK_STACK(app->canvas), names[mode]);
}

void canvas_invalidate(AppState *app)
{
    for (int i = 0; i < 4; i++) {
        if (app->col_da[i])    gtk_widget_queue_draw(app->col_da[i]);
        if (app->single_da[i]) gtk_widget_queue_draw(app->single_da[i]);
    }
    if (app->gonio_layer_da) gtk_widget_queue_draw(app->gonio_layer_da);
}

void canvas_clear(AppState *app)
{
    stroke_list_clear(app->strokes);
    app->note_count          = 0;
    app->note_drag_idx       = -1;
    app->link_summary_active = FALSE;
    app->link_rel_count      = 0;
    app->arrow_count         = 0;
    app->arrow_drawing       = FALSE;
    app->undo_type_top       = 0;
    app->stroke_version++;

    for (int i = 0; i < app->obj_zone_count; i++) {
        obj_zone_free(app->obj_zones[i]);
        app->obj_zones[i] = NULL;
    }
    app->obj_zone_count = 0;
    app->obj_point_count = 0;
    app->obj_tick_count = 0;
    app->obj_undo_type_top = 0;
    gonio_charts_free_surfaces(app);
    app->gonio_chart_count      = 0;
    app->gonio_chart_active_idx = -1;
    app->gonio_chart_drag_idx   = -1;
    stroke_list_clear(app->obj_pencil_strokes);
    if (app->obj_active_zone) {
        obj_zone_free(app->obj_active_zone);
        app->obj_active_zone = NULL;
    }

    canvas_invalidate(app);
}

void canvas_undo(AppState *app)
{
    if (app->current_mode == APP_MODE_OBJECTIVE) {
        if (app->obj_undo_type_top > 0) {
            guint8 type = app->obj_undo_type_stack[--app->obj_undo_type_top];
            if (type == 1) {
                if (app->obj_point_count > 0) app->obj_point_count--;
            } else if (type == 2) {
                if (app->obj_tick_count > 0) app->obj_tick_count--;
            } else if (type == 3) {
                /* Pencil stroke committed while in Objective mode — see
                 * input_end()'s comment. Its own list (obj_pencil_strokes),
                 * NOT Subjective's app->strokes. */
                stroke_free(stroke_list_pop(app->obj_pencil_strokes));
                app->stroke_version++;
            } else {
                if (app->obj_zone_count > 0) {
                    obj_zone_free(app->obj_zones[--app->obj_zone_count]);
                    app->obj_zones[app->obj_zone_count] = NULL;
                }
            }
        }
        canvas_invalidate(app);
        return;
    }
    if (app->undo_type_top > 0) {
        guint8 type = app->undo_type_stack[--app->undo_type_top];
        if (type == 1) {
            if (app->arrow_count > 0) app->arrow_count--;
        } else {
            stroke_free(stroke_list_pop(app->strokes));
        }
    } else {
        stroke_free(stroke_list_pop(app->strokes));
    }
    app->stroke_version++;
    canvas_invalidate(app);
}

/* ── View name helpers ───────────────────────────────────────────────────── */
const char *canvas_view_name(BodyView v)
{
    static const char *names[] = {
        "Anterior", "Posterior", "Left lateral", "Right lateral"
    };
    return (unsigned)v < 4 ? names[v] : "?";
}

const char *canvas_view_short_name(BodyView v)
{
    static const char *names[] = { "Ant", "Post", "L lat", "R lat" };
    return (unsigned)v < 4 ? names[v] : "?";
}

/* ── Right column slot cycling ───────────────────────────────────────────── */
void canvas_cycle_right_slot(AppState *app, int slot)
{
    BodyView nv = (BodyView)((app->right_slot_views[slot] + 1) % 4);
    app->right_slot_views[slot] = nv;
    int ci = 2 + slot;
    g_col[ci].view = nv;
    if (GTK_IS_LABEL(g_col[ci].header_label))
        gtk_label_set_text(GTK_LABEL(g_col[ci].header_label),
                           canvas_view_name(nv));
    gtk_widget_queue_draw(g_col[ci].da);
}

void canvas_reset_all_zoom(AppState *app)
{
    for (int i = 0; i < 8; i++) {
        *g_col[i].p_zoom  = 1.0;
        *g_col[i].p_pan_x = 0.0;
        *g_col[i].p_pan_y = 0.0;
        if (g_col[i].zoom_btn)
            gtk_button_set_label(GTK_BUTTON(g_col[i].zoom_btn), "1\xc3\x97");
    }
    canvas_invalidate(app);
}

void canvas_screen_to_body(AppState *app, double sx, double sy,
                            double *bx, double *by)
{
    int base = (app->layout_mode == LAYOUT_QUAD) ? 0 : 4;
    for (int i = base; i < base + 4; i++) {
        if (g_col[i].view == app->current_view && g_col[i].da) {
            screen_to_body(&g_col[i], sx, sy, bx, by);
            return;
        }
    }
    *bx = sx;
    *by = sy;
}
