#include "svg_regions.h"
#include <glib.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>

/* ── SVG path-data parser ─────────────────────────────────────────────────── *
 * Parses the 'd' attribute of SVG <path> elements into polygon approximations.*
 * Handles: M/m  L/l  H/h  V/v  Z/z  C/c  Q/q  (A/a arcs: endpoint only).   *
 * Bezier curves are sampled at BEZIER_STEPS intermediate points.             */

#define BEZIER_STEPS 8   /* samples per bezier segment */

static void layer_add_pt(SvgRegionLayer *ly, float x, float y)
{
    if (ly->n_pts < SVG_REGIONS_MAX_PTS) {
        ly->pts[ly->n_pts][0] = x;
        ly->pts[ly->n_pts][1] = y;
        ly->n_pts++;
    }
}

static float lerp(float a, float b, float t) { return a + (b - a) * t; }

static void sample_cubic(SvgRegionLayer *ly,
                          float x0, float y0,
                          float x1, float y1,
                          float x2, float y2,
                          float x3, float y3)
{
    for (int s = 1; s <= BEZIER_STEPS; s++) {
        float t  = (float)s / BEZIER_STEPS;
        float ax = lerp(x0, x1, t), ay = lerp(y0, y1, t);
        float bx = lerp(x1, x2, t), by = lerp(y1, y2, t);
        float cx = lerp(x2, x3, t), cy = lerp(y2, y3, t);
        float dx = lerp(ax, bx, t), dy = lerp(ay, by, t);
        float ex = lerp(bx, cx, t), ey = lerp(by, cy, t);
        layer_add_pt(ly, lerp(dx, ex, t), lerp(dy, ey, t));
    }
}

static void sample_quadratic(SvgRegionLayer *ly,
                              float x0, float y0,
                              float x1, float y1,
                              float x2, float y2)
{
    for (int s = 1; s <= BEZIER_STEPS; s++) {
        float t  = (float)s / BEZIER_STEPS;
        float ax = lerp(x0, x1, t), ay = lerp(y0, y1, t);
        float bx = lerp(x1, x2, t), by = lerp(y1, y2, t);
        layer_add_pt(ly, lerp(ax, bx, t), lerp(ay, by, t));
    }
}

/* Advance past whitespace and commas (SVG path token separators) */
static const char *skip_ws(const char *p)
{
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r' || *p == ',')
        p++;
    return p;
}

static const char *parse_float(const char *p, float *out)
{
    char *end;
    *out = strtof(p, &end);
    return end;
}

static void parse_path_d(SvgRegionLayer *ly, const char *d)
{
    float cx = 0, cy = 0;   /* current point */
    float sx = 0, sy = 0;   /* subpath start (for Z) */
    float lx = 0, ly2 = 0;  /* last control point (for smooth curves) */
    char  cmd = 'M';

    const char *p = d;
    while (*p) {
        p = skip_ws(p);
        if (!*p) break;

        /* New command letter or implicit repetition */
        if ((*p >= 'A' && *p <= 'Z') || (*p >= 'a' && *p <= 'z')) {
            cmd = *p++;
        }

        p = skip_ws(p);

        float x, y, x1, y1, x2, y2;

        switch (cmd) {
        case 'M':
            p = parse_float(p, &x); p = skip_ws(p);
            p = parse_float(p, &y);
            cx = x; cy = y; sx = cx; sy = cy;
            layer_add_pt(ly, cx, cy);
            cmd = 'L';  /* implicit lineto after moveto */
            break;
        case 'm':
            p = parse_float(p, &x); p = skip_ws(p);
            p = parse_float(p, &y);
            cx += x; cy += y; sx = cx; sy = cy;
            layer_add_pt(ly, cx, cy);
            cmd = 'l';
            break;

        case 'L':
            p = parse_float(p, &x); p = skip_ws(p);
            p = parse_float(p, &y);
            cx = x; cy = y;
            layer_add_pt(ly, cx, cy);
            break;
        case 'l':
            p = parse_float(p, &x); p = skip_ws(p);
            p = parse_float(p, &y);
            cx += x; cy += y;
            layer_add_pt(ly, cx, cy);
            break;

        case 'H':
            p = parse_float(p, &x);
            cx = x;
            layer_add_pt(ly, cx, cy);
            break;
        case 'h':
            p = parse_float(p, &x);
            cx += x;
            layer_add_pt(ly, cx, cy);
            break;

        case 'V':
            p = parse_float(p, &y);
            cy = y;
            layer_add_pt(ly, cx, cy);
            break;
        case 'v':
            p = parse_float(p, &y);
            cy += y;
            layer_add_pt(ly, cx, cy);
            break;

        case 'C':
            p = parse_float(p, &x1); p = skip_ws(p);
            p = parse_float(p, &y1); p = skip_ws(p);
            p = parse_float(p, &x2); p = skip_ws(p);
            p = parse_float(p, &y2); p = skip_ws(p);
            p = parse_float(p, &x);  p = skip_ws(p);
            p = parse_float(p, &y);
            sample_cubic(ly, cx, cy, x1, y1, x2, y2, x, y);
            lx = x2; ly2 = y2;
            cx = x; cy = y;
            break;
        case 'c':
            p = parse_float(p, &x1); p = skip_ws(p);
            p = parse_float(p, &y1); p = skip_ws(p);
            p = parse_float(p, &x2); p = skip_ws(p);
            p = parse_float(p, &y2); p = skip_ws(p);
            p = parse_float(p, &x);  p = skip_ws(p);
            p = parse_float(p, &y);
            sample_cubic(ly, cx, cy,
                          cx + x1, cy + y1,
                          cx + x2, cy + y2,
                          cx + x,  cy + y);
            lx = cx + x2; ly2 = cy + y2;
            cx += x; cy += y;
            break;

        case 'S':
            p = parse_float(p, &x2); p = skip_ws(p);
            p = parse_float(p, &y2); p = skip_ws(p);
            p = parse_float(p, &x);  p = skip_ws(p);
            p = parse_float(p, &y);
            x1 = 2 * cx - lx; y1 = 2 * cy - ly2;
            sample_cubic(ly, cx, cy, x1, y1, x2, y2, x, y);
            lx = x2; ly2 = y2;
            cx = x; cy = y;
            break;
        case 's':
            p = parse_float(p, &x2); p = skip_ws(p);
            p = parse_float(p, &y2); p = skip_ws(p);
            p = parse_float(p, &x);  p = skip_ws(p);
            p = parse_float(p, &y);
            x1 = 2 * cx - lx; y1 = 2 * cy - ly2;
            sample_cubic(ly, cx, cy, x1, y1,
                          cx + x2, cy + y2,
                          cx + x,  cy + y);
            lx = cx + x2; ly2 = cy + y2;
            cx += x; cy += y;
            break;

        case 'Q':
            p = parse_float(p, &x1); p = skip_ws(p);
            p = parse_float(p, &y1); p = skip_ws(p);
            p = parse_float(p, &x);  p = skip_ws(p);
            p = parse_float(p, &y);
            sample_quadratic(ly, cx, cy, x1, y1, x, y);
            lx = x1; ly2 = y1;
            cx = x; cy = y;
            break;
        case 'q':
            p = parse_float(p, &x1); p = skip_ws(p);
            p = parse_float(p, &y1); p = skip_ws(p);
            p = parse_float(p, &x);  p = skip_ws(p);
            p = parse_float(p, &y);
            sample_quadratic(ly, cx, cy,
                              cx + x1, cy + y1,
                              cx + x,  cy + y);
            lx = cx + x1; ly2 = cy + y1;
            cx += x; cy += y;
            break;

        case 'A': case 'a': {
            /* Arc: skip rx,ry,x-rotation,large-arc-flag,sweep-flag; take endpoint */
            float rx, ry, xrot, laf, sf;
            p = parse_float(p, &rx);  p = skip_ws(p);
            p = parse_float(p, &ry);  p = skip_ws(p);
            p = parse_float(p, &xrot);p = skip_ws(p);
            p = parse_float(p, &laf); p = skip_ws(p);
            p = parse_float(p, &sf);  p = skip_ws(p);
            p = parse_float(p, &x);   p = skip_ws(p);
            p = parse_float(p, &y);
            (void)rx; (void)ry; (void)xrot; (void)laf; (void)sf;
            if (cmd == 'a') { cx += x; cy += y; } else { cx = x; cy = y; }
            layer_add_pt(ly, cx, cy);
            break;
        }

        case 'Z': case 'z':
            layer_add_pt(ly, sx, sy);
            cx = sx; cy = sy;
            break;

        default:
            p++;  /* skip unknown commands */
            break;
        }
    }
}

/* ── GMarkup SAX parser state ─────────────────────────────────────────────── */

typedef struct {
    SvgRegions *sr;
    int         depth;          /* XML nesting depth */
    int         layer_depth;    /* depth at which the current layer <g> sits */
    int         cur_layer;      /* index into sr->layers, -1 if not in a layer */
    int         file_index;     /* which SVG file is being parsed */
    float       svg_w;          /* viewBox width from <svg> element */
    float       svg_h;          /* viewBox height from <svg> element */
} ParseState;

static void on_start_element(GMarkupParseContext *ctx,
                              const gchar         *element_name,
                              const gchar        **attr_names,
                              const gchar        **attr_values,
                              gpointer             user_data,
                              GError             **error)
{
    (void)ctx; (void)error;
    ParseState *ps = user_data;
    ps->depth++;

    if (g_strcmp0(element_name, "svg") == 0) {
        /* Parse viewBox to get the native SVG coordinate dimensions */
        for (int i = 0; attr_names[i]; i++) {
            if (g_strcmp0(attr_names[i], "viewBox") == 0) {
                float vx, vy, vw, vh;
                if (sscanf(attr_values[i], "%f %f %f %f", &vx, &vy, &vw, &vh) == 4) {
                    ps->svg_w = vw;
                    ps->svg_h = vh;
                }
                break;
            }
        }
        return;
    }

    if (g_strcmp0(element_name, "g") == 0) {
        /* Look for inkscape:label (preferred) or id as layer name */
        const char *label = NULL;
        const char *gmode = NULL;
        for (int i = 0; attr_names[i]; i++) {
            const char *an = attr_names[i];
            /* inkscape:label may appear with namespace prefix stripped */
            if (g_strcmp0(an, "inkscape:label") == 0 ||
                g_strcmp0(an, "label") == 0)
                label = attr_values[i];
            if (g_strcmp0(an, "inkscape:groupmode") == 0 ||
                g_strcmp0(an, "groupmode") == 0)
                gmode = attr_values[i];
            /* Fall back to id if no label found yet */
            if (g_strcmp0(an, "id") == 0 && !label)
                label = attr_values[i];
        }

        /* Accept Inkscape layers; exclude known reference/background layers
         * whose names contain "bodychart" (case-insensitive). */
        gboolean is_layer = (gmode && g_strcmp0(gmode, "layer") == 0);
        if (is_layer && label) {
            gchar *lower = g_ascii_strdown(label, -1);
            if (strstr(lower, "bodychart")) is_layer = FALSE;
            g_free(lower);
        }

        if (is_layer && label && ps->cur_layer == -1 &&
            ps->sr->n_layers < SVG_REGIONS_MAX_LAYERS) {
            int idx = ps->sr->n_layers++;
            SvgRegionLayer *ly = &ps->sr->layers[idx];
            g_strlcpy(ly->name, label, sizeof(ly->name));
            ly->n_pts      = 0;
            ly->file_index = ps->file_index;
            ly->svg_w      = ps->svg_w;
            ly->svg_h      = ps->svg_h;
            ps->cur_layer   = idx;
            ps->layer_depth = ps->depth;
        }
        return;
    }

    /* Collect path geometry when inside a layer */
    if (ps->cur_layer < 0) return;

    if (g_strcmp0(element_name, "path") == 0) {
        for (int i = 0; attr_names[i]; i++) {
            if (g_strcmp0(attr_names[i], "d") == 0) {
                parse_path_d(&ps->sr->layers[ps->cur_layer], attr_values[i]);
                break;
            }
        }
    } else if (g_strcmp0(element_name, "rect") == 0) {
        float x = 0, y = 0, w = 0, h = 0;
        for (int i = 0; attr_names[i]; i++) {
            if (g_strcmp0(attr_names[i], "x") == 0)      x = strtof(attr_values[i], NULL);
            if (g_strcmp0(attr_names[i], "y") == 0)      y = strtof(attr_values[i], NULL);
            if (g_strcmp0(attr_names[i], "width") == 0)  w = strtof(attr_values[i], NULL);
            if (g_strcmp0(attr_names[i], "height") == 0) h = strtof(attr_values[i], NULL);
        }
        SvgRegionLayer *ly = &ps->sr->layers[ps->cur_layer];
        layer_add_pt(ly, x,     y);
        layer_add_pt(ly, x + w, y);
        layer_add_pt(ly, x + w, y + h);
        layer_add_pt(ly, x,     y + h);
        layer_add_pt(ly, x,     y);
    } else if (g_strcmp0(element_name, "polygon") == 0 ||
               g_strcmp0(element_name, "polyline") == 0) {
        for (int i = 0; attr_names[i]; i++) {
            if (g_strcmp0(attr_names[i], "points") == 0) {
                /* polyline/polygon points share path-data token format */
                const char *p = attr_values[i];
                while (*p) {
                    p = skip_ws(p);
                    if (!*p) break;
                    float px, py;
                    p = parse_float(p, &px); p = skip_ws(p);
                    p = parse_float(p, &py);
                    layer_add_pt(&ps->sr->layers[ps->cur_layer], px, py);
                }
                break;
            }
        }
    }
}

static void on_end_element(GMarkupParseContext *ctx,
                            const gchar         *element_name,
                            gpointer             user_data,
                            GError             **error)
{
    (void)ctx; (void)error;
    ParseState *ps = user_data;

    if (g_strcmp0(element_name, "g") == 0 &&
        ps->cur_layer >= 0 &&
        ps->depth == ps->layer_depth) {
        ps->cur_layer   = -1;
        ps->layer_depth = -1;
    }
    ps->depth--;
}

static const GMarkupParser g_parser = {
    .start_element = on_start_element,
    .end_element   = on_end_element,
};

/* ── Region SVG file list ─────────────────────────────────────────────────── *
 * Add lateral entries when those SVGs are ready; NULL slots are skipped.     */
static const char * const SVG_REGION_FILES[] = {
    "anterior-regions.svg",
    "posterior-regions.svg",
    NULL,   /* lateral_l-regions.svg — add filename when ready */
    NULL,   /* lateral_r-regions.svg — add filename when ready */
};

/* ── Search and load ──────────────────────────────────────────────────────── */

static gboolean try_load(SvgRegions *sr, const char *dir,
                          const char *filename, int file_index)
{
    char path[1024];
    snprintf(path, sizeof(path), "%s/%s", dir, filename);

    gchar   *contents = NULL;
    gsize    length   = 0;
    GError  *err      = NULL;

    if (!g_file_get_contents(path, &contents, &length, &err)) {
        if (err) g_error_free(err);
        return FALSE;
    }

    ParseState ps = {
        .sr = sr, .depth = 0, .layer_depth = -1, .cur_layer = -1,
        .file_index = file_index, .svg_w = 0.0f, .svg_h = 0.0f
    };
    GMarkupParseContext *ctx =
        g_markup_parse_context_new(&g_parser, G_MARKUP_DEFAULT_FLAGS, &ps, NULL);

    if (!g_markup_parse_context_parse(ctx, contents, (gssize)length, &err) ||
        !g_markup_parse_context_end_parse(ctx, &err)) {
        fprintf(stderr, "svg_regions: parse error in %s: %s\n",
                path, err ? err->message : "unknown");
        if (err) g_error_free(err);
        g_markup_parse_context_free(ctx);
        g_free(contents);
        return FALSE;
    }

    g_markup_parse_context_free(ctx);
    g_free(contents);

    fprintf(stderr, "svg_regions: loaded %d layer(s) from %s\n",
            sr->n_layers, path);
    return TRUE;
}

void svg_regions_load(SvgRegions *sr)
{
    memset(sr, 0, sizeof(*sr));

    const char *home   = g_get_home_dir();
    int         loaded = 0;

    static const char *SEARCH_DIRS[] = {
#ifdef GPAB_REGIONS_DIR
        GPAB_REGIONS_DIR,   /* this checkout's own views/ (see meson.build) */
#endif
        NULL,   /* filled from home below */
        "/usr/local/share/pab/views",
        "/usr/share/pab/views",
        NULL,   /* filled from home below */
        "data/views",
    };
    char home_user[512], home_dev[512];
    snprintf(home_user, sizeof(home_user),
             "%s/.local/share/pab/views", home);
    snprintf(home_dev,  sizeof(home_dev),
             "%s/Projects/pab/bodychart/views", home);
#ifdef GPAB_REGIONS_DIR
    const int off = 1;
#else
    const int off = 0;
#endif
    SEARCH_DIRS[0 + off] = home_user;
    SEARCH_DIRS[3 + off] = home_dev;

    int n_dirs  = (int)(sizeof(SEARCH_DIRS) / sizeof(SEARCH_DIRS[0]));
    int n_files = (int)(sizeof(SVG_REGION_FILES) / sizeof(SVG_REGION_FILES[0]));

    for (int fi = 0; fi < n_files; fi++) {
        if (!SVG_REGION_FILES[fi]) continue;   /* slot not yet filled */
        gboolean found = FALSE;
        for (int di = 0; di < n_dirs && !found; di++) {
            if (!SEARCH_DIRS[di]) continue;
            if (try_load(sr, SEARCH_DIRS[di], SVG_REGION_FILES[fi], fi))
                found = TRUE;
        }
        if (found)
            loaded++;
        else
            fprintf(stderr, "svg_regions: %s not found in any search dir\n",
                    SVG_REGION_FILES[fi]);
    }

    for (int i = 0; i < sr->n_layers; i++) {
        SvgRegionLayer *ly = &sr->layers[i];
        ly->min_x = ly->min_y =  1e9f;
        ly->max_x = ly->max_y = -1e9f;
        for (int p = 0; p < ly->n_pts; p++) {
            ly->min_x = fminf(ly->min_x, ly->pts[p][0]);
            ly->max_x = fmaxf(ly->max_x, ly->pts[p][0]);
            ly->min_y = fminf(ly->min_y, ly->pts[p][1]);
            ly->max_y = fmaxf(ly->max_y, ly->pts[p][1]);
        }
    }

    sr->loaded = (loaded > 0);
    if (sr->loaded)
        fprintf(stderr, "svg_regions: %d file(s) loaded, %d region layer(s) total\n",
                loaded, sr->n_layers);
}

/* ── Hit test ─────────────────────────────────────────────────────────────── */

/* Ray-casting point-in-polygon.  pts are in SVG (viewBox) coordinates. */
static gboolean point_in_polygon(const float pts[][2], int n, float x, float y)
{
    gboolean inside = FALSE;
    for (int i = 0, j = n - 1; i < n; j = i++) {
        float xi = pts[i][0], yi = pts[i][1];
        float xj = pts[j][0], yj = pts[j][1];
        if (((yi > y) != (yj > y)) &&
            (x < (xj - xi) * (y - yi) / (yj - yi) + xi))
            inside = !inside;
    }
    return inside;
}

/* bx/by are body-space (0–200 × 0–400).  Converts to SVG coords before testing. */
const SvgRegionLayer *svg_regions_hit(const SvgRegions *sr, int file_index,
                                      float bx, float by)
{
    if (!sr->loaded) return NULL;
    for (int i = 0; i < sr->n_layers; i++) {
        const SvgRegionLayer *ly = &sr->layers[i];
        if (ly->file_index != file_index) continue;
        if (ly->n_pts < 3)               continue;
        if (ly->svg_w <= 0.0f || ly->svg_h <= 0.0f) continue;
        float sx = bx * (ly->svg_w / 200.0f);
        float sy = by * (ly->svg_h / 400.0f);
        if (sx < ly->min_x || sx > ly->max_x || sy < ly->min_y || sy > ly->max_y)
            continue;   /* bbox reject — this now runs per stroke point on save */
        if (point_in_polygon(ly->pts, ly->n_pts, sx, sy))
            return ly;
    }
    return NULL;
}

/* Squared distance from (x,y) to segment (ax,ay)-(bx,by). */
static float seg_dist2(float x, float y, float ax, float ay, float bx, float by)
{
    float dx = bx - ax, dy = by - ay;
    float l2 = dx * dx + dy * dy;
    float t = l2 > 0.0f ? ((x - ax) * dx + (y - ay) * dy) / l2 : 0.0f;
    if (t < 0.0f) t = 0.0f; else if (t > 1.0f) t = 1.0f;
    float px = ax + t * dx - x, py = ay + t * dy - y;
    return px * px + py * py;
}

const SvgRegionLayer *svg_regions_hit_near(const SvgRegions *sr, int file_index,
                                           float bx, float by, float max_bu)
{
    const SvgRegionLayer *hit = svg_regions_hit(sr, file_index, bx, by);
    if (hit || !sr->loaded || max_bu <= 0.0f) return hit;

    const SvgRegionLayer *best = NULL;
    float best_d2 = 1e30f;
    for (int i = 0; i < sr->n_layers; i++) {
        const SvgRegionLayer *ly = &sr->layers[i];
        if (ly->file_index != file_index || ly->n_pts < 3) continue;
        if (ly->svg_w <= 0.0f || ly->svg_h <= 0.0f) continue;
        float kx = ly->svg_w / 200.0f, ky = ly->svg_h / 400.0f;
        float sx = bx * kx, sy = by * ky;
        float mx = max_bu * kx, my = max_bu * ky;
        if (sx < ly->min_x - mx || sx > ly->max_x + mx ||
            sy < ly->min_y - my || sy > ly->max_y + my) continue;
        /* Measure in body units so x/y scale differences don't skew it */
        for (int p = 0, q = ly->n_pts - 1; p < ly->n_pts; q = p++) {
            float d2 = seg_dist2(bx, by,
                                 ly->pts[q][0] / kx, ly->pts[q][1] / ky,
                                 ly->pts[p][0] / kx, ly->pts[p][1] / ky);
            if (d2 < best_d2) { best_d2 = d2; best = ly; }
        }
    }
    return (best && best_d2 <= max_bu * max_bu) ? best : NULL;
}

float svg_regions_frac_y(const SvgRegionLayer *ly, float by)
{
    if (!ly || ly->svg_h <= 0.0f || ly->max_y <= ly->min_y) return 0.5f;
    float sy = by * (ly->svg_h / 400.0f);
    float f = (sy - ly->min_y) / (ly->max_y - ly->min_y);
    return f < 0.0f ? 0.0f : (f > 1.0f ? 1.0f : f);
}
