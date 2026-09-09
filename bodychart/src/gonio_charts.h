#pragma once
#include <cairo/cairo.h>
#include <glib.h>

typedef struct _AppState AppState;   /* full definition in canvas.h */

#define MAX_GONIO_CHARTS 24

/* One goniometer ROM chart PNG, imported by gpab's Ctrl+G flow into
 * <session_dir>/gonio_charts/ and shown free-floating over the Objective
 * canvas. gpab (Python) owns the PNG files; bodychart owns only the
 * placement, persisted in _session.json under objective.gonio_charts[].
 *
 * Position is stored as a fraction (0..1) of the Objective canvas area, not
 * pixels or body-space: the chart floats over ALL four panels on one
 * transparent overlay layer, so it has no single panel zoom/pan to follow,
 * and a fraction keeps it put across window resizes. `scale` is its own
 * zoom, independent of any panel. */
typedef struct {
    char     file[128];       /* basename only, e.g. "01_lumbar-flexion_AROM.png" */
    double   fx, fy;          /* top-left, fraction of the objective canvas area */
    double   scale;           /* display zoom; 1.0 = GONIO_CHART_BASE_FRAC of canvas width */
    gboolean visible;

    /* runtime only — not persisted */
    cairo_surface_t *surf;    /* lazily loaded, NULL until first draw / on load failure */
    gint64           surf_mtime;  /* st_mtime of the file when surf was built */
} GonioChart;

/* Natural width of a chart at scale 1.0, as a fraction of the objective
 * canvas width. A 1600x900 PNG at ~0.28 reads comfortably on the Yoga
 * without swamping the body. */
#define GONIO_CHART_BASE_FRAC 0.28

/* Sync app->gonio_charts[] with the PNGs actually in <session_dir>/gonio_charts/:
 *  - a new file with no entry  -> appended, staggered down the right side,
 *    scale 1.0, visible
 *  - an entry whose file is gone -> dropped (its cached surface freed)
 *  - an existing entry          -> keeps its saved fx/fy/scale/visible
 * Safe to call repeatedly; call on session load and on entering Objective mode. */
void gonio_charts_rescan(AppState *app);

/* Lazily (re)load gc->surf from disk, rebuilding if the file's mtime changed.
 * Returns NULL if the PNG can't be read. */
cairo_surface_t *gonio_chart_get_surface(AppState *app, GonioChart *gc);

/* Free every cached surface (on canvas_clear / session switch). Entries and
 * their placement stay; surfaces reload on next draw. */
void gonio_charts_free_surfaces(AppState *app);

/* Draw all visible charts onto `cr`, positioned within a `w` x `h` area.
 * Used by both the on-screen overlay (widget size) and the PNG/PDF export
 * (composite size). `interactive` adds the drag frame + hide affordance +
 * active highlight; the export pass passes FALSE. */
void gonio_charts_render(AppState *app, cairo_t *cr, double w, double h,
                         gboolean interactive);

/* Hit-test in the `w` x `h` area. Returns the topmost visible chart index at
 * (px, py), or -1. If it lands on that chart's hide (x) badge, *on_close is
 * set TRUE. */
int gonio_chart_hit(AppState *app, double w, double h,
                    double px, double py, gboolean *on_close);
