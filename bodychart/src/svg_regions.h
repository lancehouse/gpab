#pragma once
#include <glib.h>

/* Region SVG filenames are listed in svg_regions.c (SVG_REGION_FILES[]).
 * file_index matches BodyView: 0=anterior, 1=posterior, 2=lateral_r, 3=lateral_l.
 * Add lateral entries there when those SVGs are ready.
 * Search path is identical to svg_views_init(): user overrides first,
 * then system dirs, then dev tree. */

/* Maximum number of distinct named layers across all region SVGs */
#define SVG_REGIONS_MAX_LAYERS 256

/* Maximum polygon vertices stored per layer (bezier curves are sampled) */
#define SVG_REGIONS_MAX_PTS 1024

typedef struct {
    char  name[80];              /* layer label, e.g. "r posterior shoulder" */
    float pts[SVG_REGIONS_MAX_PTS][2];   /* polygon approximation in SVG coords */
    int   n_pts;
    int   file_index;            /* which SVG file: 0=anterior, 1=posterior, etc. */
    float svg_w;                 /* viewBox width of the source SVG (e.g. 873) */
    float svg_h;                 /* viewBox height of the source SVG (e.g. 1974) */
    float min_x, min_y, max_x, max_y;   /* polygon bbox in SVG coords (set after load) */
} SvgRegionLayer;

typedef struct {
    SvgRegionLayer layers[SVG_REGIONS_MAX_LAYERS];
    int            n_layers;
    gboolean       loaded;
} SvgRegions;

/* Load and parse all region SVGs.  Safe to call at startup even if files
 * don't exist — loaded will be FALSE and all region queries return NULL. */
void svg_regions_load(SvgRegions *sr);

/* Return the layer whose polygon contains body-space point (bx, by), or NULL.
 * file_index selects which view to test (0=anterior, 1=posterior, etc.).
 * bx/by are in body coordinates (0–200 × 0–400). */
const SvgRegionLayer *svg_regions_hit(const SvgRegions *sr, int file_index,
                                      float bx, float by);

/* As svg_regions_hit(), but a point inside no region is given the region
 * whose outline is nearest, if within max_bu body units — drawing routinely
 * runs a little past the body outline or into the gaps between regions. */
const SvgRegionLayer *svg_regions_hit_near(const SvgRegions *sr, int file_index,
                                           float bx, float by, float max_bu);

/* Vertical position of body-space y within the layer's bbox: 0 = top edge,
 * 1 = bottom edge (clamped). For limbs/trunk this is proximal → distal. */
float svg_regions_frac_y(const SvgRegionLayer *ly, float by);
