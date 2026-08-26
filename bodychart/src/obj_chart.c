#include "obj_chart.h"
#include "canvas.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>

/* ── Appearance tables ───────────────────────────────────────────────────── */
const ObjZoneDef OBJ_ZONE_DEFS[OBJ_ZONE_COUNT] = {
    { 0.96f, 0.82f, 0.00f, "Static Allodynia",   "Static Allodynia"   },
    { 0.94f, 0.47f, 0.13f, "Hyperalgesia",       "Hyperalgesia"       },
    { 0.91f, 0.38f, 0.48f, "Erythema",           "Erythema"           },
    { 0.25f, 0.63f, 0.88f, "Temp Cool",          "Temp Cool"          },
    { 0.75f, 0.19f, 0.19f, "Temp Warm",          "Temp Warm"          },
    { 0.69f, 0.69f, 0.75f, "Reduced Sensation",  "Reduced Sensation"  },
    { 0.60f, 0.31f, 0.75f, "Oedema",             "Oedema"             },
    { 0.70f, 0.44f, 0.19f, "Trophic",            "Trophic"            },
    /* Appended 2026-08-26 — see obj_chart.h's ObjZoneType comment on why
     * these are appended, not interleaved with the renumbering-sensitive
     * block above. */
    { 0.20f, 0.70f, 0.65f, "Dynamic Allodynia",  "Dynamic Allodynia"  },
    { 0.90f, 0.25f, 0.15f, "Heat Hyperalgesia",  "Heat Hyperalgesia"  },
    { 0.30f, 0.35f, 0.85f, "Cold Hyperalgesia",  "Cold Hyperalgesia"  },
    { 0.35f, 0.55f, 0.55f, "Body Perception",    "Body Perception"    },
};

const ObjPointDef OBJ_POINT_DEFS[OBJ_POINT_COUNT] = {
    { 0.15f, 0.40f, 0.80f, "PPT"           },   /* OBJ_POINT_PPT            */
    { 0.55f, 0.15f, 0.65f, "Temporal Sum"  },   /* OBJ_POINT_TEMPORAL_SUM   */
    { 0.20f, 0.65f, 0.45f, "Monofilament"  },   /* OBJ_POINT_MONOFILAMENT   */
    { 0.85f, 0.55f, 0.10f, "2-PD"          },   /* OBJ_POINT_TWO_PD         */
};

const ObjTickDef OBJ_TICK_DEFS[OBJ_TICK_TYPE_COUNT] = {
    { 0.55f, 0.20f, 0.90f, "Vibration"              },  /* OBJ_TICK_VIBRATION             */
    { 0.15f, 0.65f, 0.55f, "Proprioception"         },  /* OBJ_TICK_PROPRIOCEPTION        */
    { 0.80f, 0.55f, 0.05f, "Nerve Trunk Palpation"  },  /* OBJ_TICK_NERVE_TRUNK_PALPATION */
};

/* ── ObjZone lifecycle ───────────────────────────────────────────────────── */

ObjZone *obj_zone_new(ObjZoneType type, int view)
{
    ObjZone *z = g_malloc0(sizeof(ObjZone));
    z->type = type;
    z->view = view;
    z->cap  = 64;
    z->bx   = g_malloc(z->cap * sizeof(float));
    z->by   = g_malloc(z->cap * sizeof(float));
    return z;
}

void obj_zone_add_pt(ObjZone *z, float bx, float by)
{
    if (z->n >= z->cap) {
        z->cap *= 2;
        if (z->cap > MAX_OBJ_ZONE_PTS) z->cap = MAX_OBJ_ZONE_PTS;
        z->bx = g_realloc(z->bx, z->cap * sizeof(float));
        z->by = g_realloc(z->by, z->cap * sizeof(float));
    }
    if (z->n < MAX_OBJ_ZONE_PTS) {
        z->bx[z->n] = bx;
        z->by[z->n] = by;
        z->n++;
    }
}

void obj_zone_free(ObjZone *z)
{
    if (!z) return;
    g_free(z->bx);
    g_free(z->by);
    g_free(z);
}

/* ── Zone path drawing helper ────────────────────────────────────────────── */

static void draw_zone_body(cairo_t *cr, const ObjZone *z,
                            float r, float g, float b)
{
    if (z->n < 2) return;

    cairo_save(cr);
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
    cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND);

    cairo_move_to(cr, z->bx[0], z->by[0]);
    for (int i = 1; i < z->n; i++)
        cairo_line_to(cr, z->bx[i], z->by[i]);

    if (z->n >= 3) {
        cairo_close_path(cr);
        cairo_set_source_rgba(cr, r, g, b, 0.35);
        cairo_fill_preserve(cr);
    }
    cairo_set_source_rgba(cr, r, g, b, 0.80);
    cairo_set_line_width(cr, 1.2);
    cairo_stroke(cr);

    cairo_restore(cr);
}

/* ── Rendering — body space (after apply_col_transform) ─────────────────── */

void obj_chart_render_body(AppState *app, cairo_t *cr, int view)
{
    for (int i = 0; i < app->obj_zone_count; i++) {
        const ObjZone *z = app->obj_zones[i];
        if (!z || z->view != view) continue;
        const ObjZoneDef *d = &OBJ_ZONE_DEFS[z->type];
        draw_zone_body(cr, z, d->r, d->g, d->b);
    }
}

void obj_chart_render_active_body(AppState *app, cairo_t *cr, int view)
{
    ObjZone *z = app->obj_active_zone;
    if (!z || z->view != view || z->n < 1) return;

    const ObjZoneDef *d = &OBJ_ZONE_DEFS[z->type];
    cairo_save(cr);
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
    cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND);
    cairo_move_to(cr, z->bx[0], z->by[0]);
    for (int i = 1; i < z->n; i++)
        cairo_line_to(cr, z->bx[i], z->by[i]);
    cairo_set_source_rgba(cr, d->r, d->g, d->b, 0.70);
    cairo_set_line_width(cr, 1.5);
    cairo_stroke(cr);
    cairo_restore(cr);
}

/* ── Tick/cross marker rendering — body space ────────────────────────────── */

void obj_chart_render_ticks_body(AppState *app, cairo_t *cr, int view)
{
    for (int i = 0; i < app->obj_tick_count; i++) {
        const ObjTick *t = &app->obj_ticks[i];
        if (t->view != view) continue;
        const ObjTickDef *d = &OBJ_TICK_DEFS[t->type];

        cairo_save(cr);
        /* White halo behind the dot, same convention as obj point spots. */
        cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 0.90);
        cairo_arc(cr, t->bx, t->by, 8.0, 0, 2 * G_PI);
        cairo_fill(cr);
        cairo_set_source_rgba(cr, d->r, d->g, d->b, 0.95);
        cairo_arc(cr, t->bx, t->by, 7.0, 0, 2 * G_PI);
        cairo_fill(cr);

        /* Glyph distinguishes tick vs cross — colour is per-TYPE only, not
         * per-state (explicitly not a red=abnormal/green=normal semantic
         * here, per direct user feedback). */
        cairo_select_font_face(cr, "Sans", CAIRO_FONT_SLANT_NORMAL,
                               CAIRO_FONT_WEIGHT_BOLD);
        cairo_set_font_size(cr, 11.0);
        const char *glyph = (t->state == OBJ_TICK_STATE_TICK) ? "\xe2\x9c\x93" : "\xe2\x9c\x97";
        cairo_text_extents_t ext;
        cairo_text_extents(cr, glyph, &ext);
        cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 1.0);
        cairo_move_to(cr, t->bx - ext.width / 2.0 - ext.x_bearing,
                          t->by - ext.height / 2.0 - ext.y_bearing);
        cairo_show_text(cr, glyph);
        cairo_restore(cr);
    }
}

/* ── Label anchor resolver ───────────────────────────────────────────────── */

void obj_label_resolve(const ObjPoint *p, double *out_lbx, double *out_lby)
{
    if (p->anchor.placed) {
        *out_lbx = p->anchor.lx;
        *out_lby = p->anchor.ly;
    } else {
        *out_lbx = p->bx + 6.0;
        *out_lby = p->by - 5.0;
    }
}

/* ── Connector (line + arrowhead from label box edge to spot dot) ────────── */

static void draw_obj_connector(cairo_t *cr,
                                double spot_sx, double spot_sy,
                                double box_lx,  double box_ly,
                                double bw,       double bh,
                                double dr, double dg, double db)
{
    double box_cx = box_lx + bw / 2.0;
    double box_cy = box_ly + bh / 2.0;
    double dx = spot_sx - box_cx, dy = spot_sy - box_cy;
    double dist = sqrt(dx * dx + dy * dy);
    if (dist < 8.0) return;

    double ux = dx / dist, uy = dy / dist;

    /* Exact rectangle-edge start point */
    double tx = (ux != 0.0) ? (bw / 2.0) / fabs(ux) : 1e9;
    double ty = (uy != 0.0) ? (bh / 2.0) / fabs(uy) : 1e9;
    double t  = fmin(tx, ty);
    double start_x = box_cx + ux * t;
    double start_y = box_cy + uy * t;

    double spot_r = 6.0;
    double end_x  = spot_sx - ux * spot_r;
    double end_y  = spot_sy - uy * spot_r;

    double head = 12.0, hw = 5.0;
    double px   = -uy, py = ux;
    double hbx  = end_x - ux * head, hby = end_y - uy * head;

    cairo_set_source_rgba(cr, dr, dg, db, 0.85);
    cairo_set_line_width(cr, 2.0);
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
    cairo_move_to(cr, start_x, start_y);
    cairo_line_to(cr, hbx, hby);
    cairo_stroke(cr);

    cairo_move_to(cr, end_x, end_y);
    cairo_line_to(cr, hbx + px * hw, hby + py * hw);
    cairo_line_to(cr, hbx - px * hw, hby - py * hw);
    cairo_close_path(cr);
    cairo_fill(cr);
}

/* ── Rendering — screen space ────────────────────────────────────────────── */

void obj_chart_render_screen(AppState *app, cairo_t *cr, int view,
                               double s, double cx, double cy)
{
    for (int i = 0; i < app->obj_point_count; i++) {
        const ObjPoint *p = &app->obj_points[i];
        if (p->view != view) continue;

        /* Spot screen coords */
        double spot_sx = (p->bx - 100.0) * s + cx;
        double spot_sy = (p->by - 200.0) * s + cy;

        /* Label screen coords */
        double lbx, lby;
        obj_label_resolve(p, &lbx, &lby);
        double label_sx = (lbx - 100.0) * s + cx;
        double label_sy = (lby - 200.0) * s + cy;

        /* Per-type colours */
        double dr, dg, db;     /* dot / connector colour */
        double tr, tg, tb;     /* text colour */
        const char *prefix, *unit;
        if (p->type == OBJ_POINT_PPT) {
            dr = 0.15; dg = 0.40; db = 0.80;
            tr = 0.70; tg = 0.88; tb = 1.00;
            prefix = "PPT: "; unit = " kg/cm²";
        } else if (p->type == OBJ_POINT_MONOFILAMENT) {
            dr = 0.20; dg = 0.65; db = 0.45;
            tr = 0.55; tg = 1.00; tb = 0.80;
            prefix = "MF: ";  unit = " g";
        } else if (p->type == OBJ_POINT_TWO_PD) {
            dr = 0.85; dg = 0.55; db = 0.10;
            tr = 1.00; tg = 0.88; tb = 0.50;
            prefix = "2PD: "; unit = " mm";
        } else {
            dr = 0.55; dg = 0.15; db = 0.65;
            tr = 0.90; tg = 0.75; tb = 1.00;
            prefix = "TS: ";  unit = "";
        }

        char buf[48];
        snprintf(buf, sizeof(buf), "%s%s%s", prefix, p->label, unit);

        cairo_save(cr);
        cairo_select_font_face(cr, "Sans", CAIRO_FONT_SLANT_NORMAL,
                               CAIRO_FONT_WEIGHT_BOLD);
        cairo_set_font_size(cr, 13.5);

        /* Measure label text */
        cairo_text_extents_t ext;
        cairo_text_extents(cr, buf, &ext);
        double pad = 4.0;
        double bw  = ext.width  - ext.x_bearing + 2.0 * pad;
        double bh  = -ext.y_bearing + ext.height + 2.0 * pad;
        double box_lx = label_sx;
        double box_ly = label_sy - bh;

        /* Connector (drawn behind box) */
        draw_obj_connector(cr, spot_sx, spot_sy, box_lx, box_ly, bw, bh, dr, dg, db);

        /* Dark label box */
        cairo_set_source_rgba(cr, 0.04, 0.04, 0.10, 0.82);
        cairo_rectangle(cr, box_lx, box_ly, bw, bh);
        cairo_fill(cr);

        /* Coloured border */
        cairo_set_source_rgba(cr, dr, dg, db, 0.75);
        cairo_set_line_width(cr, 1.2);
        cairo_rectangle(cr, box_lx, box_ly, bw, bh);
        cairo_stroke(cr);

        /* Spot dot — white halo + type colour fill */
        cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 0.90);
        cairo_arc(cr, spot_sx, spot_sy, 7.0, 0, 2 * G_PI);
        cairo_fill(cr);
        cairo_set_source_rgba(cr, dr, dg, db, 0.95);
        cairo_arc(cr, spot_sx, spot_sy, 5.5, 0, 2 * G_PI);
        cairo_fill(cr);

        /* Label text */
        cairo_set_source_rgba(cr, tr, tg, tb, 1.0);
        cairo_move_to(cr, box_lx + pad - ext.x_bearing,
                          box_ly + pad - ext.y_bearing);
        cairo_show_text(cr, buf);
        cairo_restore(cr);
    }
}
