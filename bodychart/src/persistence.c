#include "persistence.h"
#include "stroke.h"
#include "window.h"
#include "obj_chart.h"
#include "report.h"
#include <json-c/json.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
#include <sys/stat.h>
#include <errno.h>

/* ── Path helpers ─────────────────────────────────────────────────────────── */

static void ensure_physio_root(char *buf, size_t len)
{
    snprintf(buf, len, "%s/PAB", g_get_home_dir());
    if (mkdir(buf, 0755) != 0 && errno != EEXIST) {
        snprintf(buf, len, "%s", g_get_home_dir());
    }
}

void persistence_build_paths(AppState *app, const char *patient_id,
                               const char *session_label)
{
    /* Sanitise patient_id: keep only alphanumeric + hyphen, max 16 chars */
    char safe_id[17] = {0};
    int out = 0;
    for (int i = 0; patient_id[i] && out < 16; i++) {
        char c = patient_id[i];
        if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
            (c >= '0' && c <= '9') || c == '-') {
            safe_id[out++] = c;
        }
    }
    if (out == 0) { safe_id[0] = 'X'; safe_id[1] = 'X'; out = 2; }

    strncpy(app->patient_id, safe_id, sizeof(app->patient_id) - 1);
    strncpy(app->session_label, session_label ? session_label : "",
            sizeof(app->session_label) - 1);

    time_t now = time(NULL);
    struct tm *t = localtime(&now);
    char ts[20];
    strftime(ts, sizeof(ts), "%d_%m_%Y_%H%M", t);

    snprintf(app->session_name, sizeof(app->session_name), "%s_%s", safe_id, ts);

    char root[512];
    ensure_physio_root(root, sizeof(root));
    g_snprintf(app->session_dir,  sizeof(app->session_dir),
               "%s/%s", root, app->session_name);
    g_snprintf(app->session_file, sizeof(app->session_file),
               "%s/%s_session.json", app->session_dir, app->session_name);

    app->session_created = now;
}

/* ── JSON write helpers ───────────────────────────────────────────────────── */

static json_object *strokes_to_json(StrokeList *sl)
{
    json_object *arr = json_object_new_array();
    for (int i = 0; i < sl->n; i++) {
        Stroke *sk = sl->strokes[i];
        json_object *s = json_object_new_object();
        json_object_object_add(s, "id",    json_object_new_int(sk->id));
        json_object_object_add(s, "type",  json_object_new_int(sk->type));
        json_object_object_add(s, "view",  json_object_new_int(sk->view));
        json_object_object_add(s, "wide",  json_object_new_boolean(sk->wide_mode));
        if (sk->draw_zoom > 0.0)
            json_object_object_add(s, "draw_zoom", json_object_new_double(sk->draw_zoom));
        json_object *pts = json_object_new_array();
        for (size_t j = 0; j < sk->n_pts; j++) {
            json_object *pt = json_object_new_array();
            json_object_array_add(pt, json_object_new_double(sk->pts[j].x));
            json_object_array_add(pt, json_object_new_double(sk->pts[j].y));
            json_object_array_add(pt, json_object_new_double(sk->pts[j].pressure));
            json_object_array_add(pts, pt);
        }
        json_object_object_add(s, "pts", pts);
        json_object_array_add(arr, s);
    }
    return arr;
}

static json_object *arrows_to_json(AppState *app)
{
    json_object *arr = json_object_new_array();
    for (int i = 0; i < app->arrow_count; i++) {
        ArrowAnnotation *a = &app->arrows[i];
        json_object *o = json_object_new_object();
        json_object_object_add(o, "view", json_object_new_int(a->view));
        json_object_object_add(o, "x1",   json_object_new_double(a->x1));
        json_object_object_add(o, "y1",   json_object_new_double(a->y1));
        json_object_object_add(o, "cx",   json_object_new_double(a->cx));
        json_object_object_add(o, "cy",   json_object_new_double(a->cy));
        json_object_object_add(o, "x2",   json_object_new_double(a->x2));
        json_object_object_add(o, "y2",   json_object_new_double(a->y2));
        json_object_array_add(arr, o);
    }
    return arr;
}

static json_object *link_relations_to_json(AppState *app)
{
    json_object *arr = json_object_new_array();
    for (int i = 0; i < app->link_rel_count; i++) {
        LinkRel *lr = &app->link_relations[i];
        json_object *o = json_object_new_object();
        json_object_object_add(o, "from",  json_object_new_int(lr->from));
        json_object_object_add(o, "to",    json_object_new_int(lr->to));
        json_object_object_add(o, "state", json_object_new_int(lr->state));
        json_object_array_add(arr, o);
    }
    return arr;
}

static json_object *link_matrix_to_json(AppState *app)
{
    json_object *rows = json_object_new_array();
    for (int i = 0; i < MAX_NOTES; i++) {
        json_object *row = json_object_new_array();
        for (int j = 0; j < MAX_NOTES; j++)
            json_object_array_add(row, json_object_new_int(app->link_matrix[i][j]));
        json_object_array_add(rows, row);
    }
    return rows;
}

/* Spatial association for Objective items (2026-08-26) — same
 * svg_regions_hit() lookup already used for Subjective strokes/notes
 * (see compute_clusters/notes_to_json above), extended here so Objective
 * zones/points/ticks also carry a region_label. This is the foundation for
 * gpab's cross-linking of bodychart findings into the Sensory/CRPS tabs
 * (an Objective-side counterpart to mapping.py's Subjective prefill) —
 * see CONVERSION_PLAN.md. Returns "" (never NULL) if regions aren't loaded
 * or nothing hits. */
static const char *obj_region_label(AppState *app, int view, double bx, double by)
{
    if (app->svg_regions.loaded) {
        const SvgRegionLayer *ly = svg_regions_hit(
            &app->svg_regions, view, (float)bx, (float)by);
        if (ly) return ly->name;
    }
    return "";
}

static json_object *obj_zones_to_json(AppState *app)
{
    json_object *arr = json_object_new_array();
    for (int i = 0; i < app->obj_zone_count; i++) {
        const ObjZone *z = app->obj_zones[i];
        if (!z) continue;
        json_object *o = json_object_new_object();
        json_object_object_add(o, "type", json_object_new_int((int)z->type));
        json_object_object_add(o, "view", json_object_new_int(z->view));
        json_object *pts = json_object_new_array();
        double cbx = 0.0, cby = 0.0;
        for (int j = 0; j < z->n; j++) {
            json_object *pt = json_object_new_array();
            json_object_array_add(pt, json_object_new_double(z->bx[j]));
            json_object_array_add(pt, json_object_new_double(z->by[j]));
            json_object_array_add(pts, pt);
            cbx += z->bx[j];
            cby += z->by[j];
        }
        json_object_object_add(o, "pts", pts);
        if (z->n > 0) {
            cbx /= z->n; cby /= z->n;
            json_object_object_add(o, "region_label",
                json_object_new_string(obj_region_label(app, z->view, cbx, cby)));
        }
        json_object_array_add(arr, o);
    }
    return arr;
}

static json_object *obj_points_to_json(AppState *app)
{
    json_object *arr = json_object_new_array();
    for (int i = 0; i < app->obj_point_count; i++) {
        const ObjPoint *p = &app->obj_points[i];
        json_object *o = json_object_new_object();
        json_object_object_add(o, "type",  json_object_new_int((int)p->type));
        json_object_object_add(o, "view",  json_object_new_int(p->view));
        json_object_object_add(o, "bx",    json_object_new_double(p->bx));
        json_object_object_add(o, "by",    json_object_new_double(p->by));
        json_object_object_add(o, "value", json_object_new_double(p->value));
        json_object_object_add(o, "label", json_object_new_string(p->label));
        json_object_object_add(o, "region_label",
            json_object_new_string(obj_region_label(app, p->view, p->bx, p->by)));
        if (p->anchor.placed) {
            json_object_object_add(o, "lx", json_object_new_double(p->anchor.lx));
            json_object_object_add(o, "ly", json_object_new_double(p->anchor.ly));
        }
        json_object_array_add(arr, o);
    }
    return arr;
}

static json_object *obj_ticks_to_json(AppState *app)
{
    json_object *arr = json_object_new_array();
    for (int i = 0; i < app->obj_tick_count; i++) {
        const ObjTick *t = &app->obj_ticks[i];
        json_object *o = json_object_new_object();
        json_object_object_add(o, "type",  json_object_new_int((int)t->type));
        json_object_object_add(o, "state", json_object_new_int((int)t->state));
        json_object_object_add(o, "view",  json_object_new_int(t->view));
        json_object_object_add(o, "bx",    json_object_new_double(t->bx));
        json_object_object_add(o, "by",    json_object_new_double(t->by));
        json_object_object_add(o, "region_label",
            json_object_new_string(obj_region_label(app, t->view, t->bx, t->by)));
        json_object_array_add(arr, o);
    }
    return arr;
}

/* Goniometer ROM chart placement. The PNGs themselves are gpab-owned
 * (<session_dir>/gonio_charts/); we persist only where the user parked each
 * one. gonio_charts_rescan() reconciles this list with the files on disk
 * after load. */
static json_object *gonio_charts_to_json(AppState *app)
{
    json_object *arr = json_object_new_array();
    for (int i = 0; i < app->gonio_chart_count; i++) {
        const GonioChart *gc = &app->gonio_charts[i];
        json_object *o = json_object_new_object();
        json_object_object_add(o, "file",    json_object_new_string(gc->file));
        json_object_object_add(o, "fx",      json_object_new_double(gc->fx));
        json_object_object_add(o, "fy",      json_object_new_double(gc->fy));
        json_object_object_add(o, "scale",   json_object_new_double(gc->scale));
        json_object_object_add(o, "visible", json_object_new_boolean(gc->visible));
        json_object_array_add(arr, o);
    }
    return arr;
}

/* ── Stroke clustering ────────────────────────────────────────────────────── *
 * Groups strokes into clusters: same SymptomType + same view + padded bbox   *
 * overlap (Option B — no point-to-point proximity).                          *
 * Clusters are derived data recomputed on every save — not stored in AppState.*/

#define STROKE_CLUSTER_PADDING_BU 5.0f
#define NOTE_ASSOC_THRESHOLD_BU   30.0f  /* max body-unit dist: note → cluster centroid */

typedef struct {
    int    id;
    int    view;
    int    type;
    double centroid_bx;
    double centroid_by;
    char   region_label[80];
    int   *stroke_ids;
    int    n_stroke_ids;
} ClusterMeta;

static void cluster_meta_free(ClusterMeta *meta, int n)
{
    for (int i = 0; i < n; i++)
        g_free(meta[i].stroke_ids);
    g_free(meta);
}

static void stroke_bbox(const Stroke *s,
                        float *x0, float *y0, float *x1, float *y1)
{
    *x0 = *y0 =  1e9f;
    *x1 = *y1 = -1e9f;
    for (size_t i = 0; i < s->n_pts; i++) {
        if (s->pts[i].x < *x0) *x0 = s->pts[i].x;
        if (s->pts[i].y < *y0) *y0 = s->pts[i].y;
        if (s->pts[i].x > *x1) *x1 = s->pts[i].x;
        if (s->pts[i].y > *y1) *y1 = s->pts[i].y;
    }
}

static gboolean bboxes_overlap_padded(float ax0, float ay0, float ax1, float ay1,
                                      float bx0, float by0, float bx1, float by1,
                                      float pad)
{
    return (ax0 - pad <= bx1 + pad) && (ax1 + pad >= bx0 - pad) &&
           (ay0 - pad <= by1 + pad) && (ay1 + pad >= by0 - pad);
}

static int uf_find(int *parent, int i)
{
    while (parent[i] != i) {
        parent[i] = parent[parent[i]];
        i = parent[i];
    }
    return i;
}

static void uf_union(int *parent, int i, int j)
{
    i = uf_find(parent, i);
    j = uf_find(parent, j);
    if (i != j) parent[j] = i;
}

/* Compute clusters, returning heap-allocated ClusterMeta array (caller frees
 * via cluster_meta_free).  Returns NULL when there are no strokes. */
static ClusterMeta *compute_clusters(AppState *app, int *n_out)
{
    int n = app->strokes->n;
    *n_out = 0;
    if (n == 0) return NULL;

    float *x0     = g_malloc(n * sizeof(float));
    float *y0     = g_malloc(n * sizeof(float));
    float *x1     = g_malloc(n * sizeof(float));
    float *y1     = g_malloc(n * sizeof(float));
    int   *parent = g_malloc(n * sizeof(int));

    for (int i = 0; i < n; i++) {
        stroke_bbox(app->strokes->strokes[i], &x0[i], &y0[i], &x1[i], &y1[i]);
        parent[i] = i;
    }

    for (int i = 0; i < n; i++) {
        for (int j = i + 1; j < n; j++) {
            Stroke *si = app->strokes->strokes[i];
            Stroke *sj = app->strokes->strokes[j];
            if (si->type != sj->type || si->view != sj->view) continue;
            if (bboxes_overlap_padded(x0[i], y0[i], x1[i], y1[i],
                                      x0[j], y0[j], x1[j], y1[j],
                                      STROKE_CLUSTER_PADDING_BU))
                uf_union(parent, i, j);
        }
    }

    /* Collect unique roots in first-occurrence order */
    int *roots   = g_malloc(n * sizeof(int));
    int  n_roots = 0;
    for (int i = 0; i < n; i++) {
        int r = uf_find(parent, i);
        gboolean found = FALSE;
        for (int k = 0; k < n_roots; k++)
            if (roots[k] == r) { found = TRUE; break; }
        if (!found) roots[n_roots++] = r;
    }

    ClusterMeta *meta = g_malloc(n_roots * sizeof(ClusterMeta));

    for (int ci = 0; ci < n_roots; ci++) {
        int root = roots[ci];
        ClusterMeta *m = &meta[ci];
        m->id            = ci;
        m->view          = app->strokes->strokes[root]->view;
        m->type          = app->strokes->strokes[root]->type;
        m->centroid_bx   = 0.0;
        m->centroid_by   = 0.0;
        m->region_label[0] = '\0';
        m->stroke_ids    = NULL;
        m->n_stroke_ids  = 0;

        /* Count member strokes first, then allocate */
        int n_sk = 0;
        for (int i = 0; i < n; i++)
            if (uf_find(parent, i) == root) n_sk++;
        m->stroke_ids = g_malloc(n_sk * sizeof(int));

        int pt_count = 0;
        for (int i = 0; i < n; i++) {
            if (uf_find(parent, i) != root) continue;
            Stroke *sk = app->strokes->strokes[i];
            m->stroke_ids[m->n_stroke_ids++] = sk->id;
            for (size_t p = 0; p < sk->n_pts; p++) {
                m->centroid_bx += sk->pts[p].x;
                m->centroid_by += sk->pts[p].y;
                pt_count++;
            }
        }
        if (pt_count > 0) {
            m->centroid_bx /= pt_count;
            m->centroid_by /= pt_count;
        }

        if (app->svg_regions.loaded) {
            const SvgRegionLayer *ly = svg_regions_hit(
                &app->svg_regions, m->view,
                (float)m->centroid_bx, (float)m->centroid_by);
            if (ly) g_strlcpy(m->region_label, ly->name, sizeof(m->region_label));
        }
    }

    g_free(x0); g_free(y0); g_free(x1); g_free(y1);
    g_free(parent); g_free(roots);
    *n_out = n_roots;
    return meta;
}

static json_object *clusters_meta_to_json(const ClusterMeta *meta, int n)
{
    json_object *arr = json_object_new_array();
    for (int ci = 0; ci < n; ci++) {
        const ClusterMeta *m = &meta[ci];
        json_object *c = json_object_new_object();
        json_object_object_add(c, "id",           json_object_new_int(m->id));
        json_object_object_add(c, "view",         json_object_new_int(m->view));
        json_object_object_add(c, "type",         json_object_new_int(m->type));
        json_object_object_add(c, "centroid_bx",  json_object_new_double(m->centroid_bx));
        json_object_object_add(c, "centroid_by",  json_object_new_double(m->centroid_by));
        json_object_object_add(c, "region_label", json_object_new_string(m->region_label));
        json_object *ids = json_object_new_array();
        for (int k = 0; k < m->n_stroke_ids; k++)
            json_object_array_add(ids, json_object_new_int(m->stroke_ids[k]));
        json_object_object_add(c, "stroke_ids", ids);
        json_object_array_add(arr, c);
    }
    return arr;
}

static json_object *notes_to_json(AppState *app,
                                   const ClusterMeta *clusters, int n_clusters)
{
    json_object *arr = json_object_new_array();
    for (int i = 0; i < app->note_count; i++) {
        NoteAnnotation *n = &app->notes[i];
        json_object *o = json_object_new_object();
        json_object_object_add(o, "stable_id",json_object_new_int(n->stable_id));
        json_object_object_add(o, "view",    json_object_new_int(n->view));
        json_object_object_add(o, "bx",      json_object_new_double(n->bx));
        json_object_object_add(o, "by",      json_object_new_double(n->by));
        json_object_object_add(o, "number",  json_object_new_int(n->number));
        json_object_object_add(o, "temporal",json_object_new_int(n->temporal));
        json_object_object_add(o, "depth",   json_object_new_int(n->depth));
        json_object *quals = json_object_new_array();
        for (int q = 0; q < n->quality_count; q++)
            json_object_array_add(quals, json_object_new_int(n->qualities[q]));
        json_object_object_add(o, "qualities", quals);
        json_object_object_add(o, "low",     json_object_new_int(n->low_intensity));
        json_object_object_add(o, "high",    json_object_new_int(n->high_intensity));
        if (n->label.placed) {
            json_object_object_add(o, "lx",     json_object_new_double(n->label.lx));
            json_object_object_add(o, "ly",     json_object_new_double(n->label.ly));
        }
        if (n->voice_note[0])
            json_object_object_add(o, "voice_note",
                                   json_object_new_string(n->voice_note));
        if (n->chart_note_text[0])
            json_object_object_add(o, "chart_note_text",
                                   json_object_new_string(n->chart_note_text));

        /* Spatial association: region the note dot sits in */
        const char *region_label = "";
        if (app->svg_regions.loaded) {
            const SvgRegionLayer *ly = svg_regions_hit(
                &app->svg_regions, n->view, (float)n->bx, (float)n->by);
            if (ly) region_label = ly->name;
        }
        json_object_object_add(o, "region_label", json_object_new_string(region_label));

        /* Clusters within threshold distance → associated_cluster_ids + distribution_labels */
        json_object *assoc_ids = json_object_new_array();
        json_object *dist_arr  = json_object_new_array();
        char seen[16][80];
        int  n_seen = 0;
        double thresh2 = NOTE_ASSOC_THRESHOLD_BU * NOTE_ASSOC_THRESHOLD_BU;
        for (int ci = 0; ci < n_clusters; ci++) {
            const ClusterMeta *m = &clusters[ci];
            if (m->view != n->view) continue;
            double dx = m->centroid_bx - n->bx;
            double dy = m->centroid_by - n->by;
            if (dx * dx + dy * dy > thresh2) continue;
            json_object_array_add(assoc_ids, json_object_new_int(m->id));
            if (m->region_label[0] && n_seen < 16) {
                gboolean found = FALSE;
                for (int k = 0; k < n_seen; k++)
                    if (strcmp(seen[k], m->region_label) == 0) { found = TRUE; break; }
                if (!found) {
                    g_strlcpy(seen[n_seen++], m->region_label, 80);
                    json_object_array_add(dist_arr,
                        json_object_new_string(m->region_label));
                }
            }
        }
        json_object_object_add(o, "associated_cluster_ids", assoc_ids);
        json_object_object_add(o, "distribution_labels",    dist_arr);

        json_object_array_add(arr, o);
    }
    return arr;
}

/* Cluster IDs with no note within NOTE_ASSOC_THRESHOLD_BU — the TUI misc bucket. */
static json_object *misc_cluster_ids_json(AppState *app,
                                           const ClusterMeta *clusters,
                                           int n_clusters)
{
    double thresh2 = NOTE_ASSOC_THRESHOLD_BU * NOTE_ASSOC_THRESHOLD_BU;
    json_object *arr = json_object_new_array();
    for (int ci = 0; ci < n_clusters; ci++) {
        const ClusterMeta *m = &clusters[ci];
        gboolean claimed = FALSE;
        for (int ni = 0; ni < app->note_count && !claimed; ni++) {
            NoteAnnotation *na = &app->notes[ni];
            if (na->view != m->view) continue;
            double dx = m->centroid_bx - na->bx;
            double dy = m->centroid_by - na->by;
            if (dx * dx + dy * dy <= thresh2) claimed = TRUE;
        }
        if (!claimed)
            json_object_array_add(arr, json_object_new_int(m->id));
    }
    return arr;
}

/* ── Save ─────────────────────────────────────────────────────────────────── */

gboolean persistence_save(AppState *app)
{
    if (!app->session_file[0]) return FALSE;

    /* Ensure session directory exists */
    if (mkdir(app->session_dir, 0755) != 0 && errno != EEXIST)
        return FALSE;

    /*
     * Load the existing file so we can preserve Python TUI assessment fields
     * (consent, subjective, medical, pain_classification, outcome_measures,
     * diagnosis, barriers, scratchpad, sections_complete, sections_last_modified).
     * We extract those fields, then build a fresh JSON tree (as before) and
     * re-inject them.  This avoids in-place mutation of borrowed json-c objects.
     */
    json_object *existing      = json_object_from_file(app->session_file);
    json_object *existing_assess = NULL;
    if (existing)
        json_object_object_get_ex(existing, "assessment", &existing_assess);

    /* Python-TUI-owned sub-keys inside the assessment block */
    static const char * const PYTHON_ASSESS_KEYS[] = {
        "consent", "subjective", "medical", "pain_classification",
        "outcome_measures", "diagnosis", "barriers", "scratchpad", NULL
    };
    /* Python-TUI-owned root-level keys */
    static const char * const PYTHON_ROOT_KEYS[] = {
        "sections_complete", "sections_last_modified", NULL
    };

    json_object *root = json_object_new_object();

    /* Metadata */
    json_object_object_add(root, "version",       json_object_new_int(3));
    json_object_object_add(root, "patient_id",    json_object_new_string(app->patient_id));
    json_object_object_add(root, "session_label", json_object_new_string(app->session_label));
    json_object_object_add(root, "session_name",  json_object_new_string(app->session_name));
    json_object_object_add(root, "created",       json_object_new_int64((int64_t)app->session_created));
    json_object_object_add(root, "modified",      json_object_new_int64((int64_t)time(NULL)));

    /* UI state */
    json_object *ui = json_object_new_object();
    json_object_object_add(ui, "layout_mode", json_object_new_int((int)app->layout_mode));
    json_object *rsv = json_object_new_array();
    json_object_array_add(rsv, json_object_new_int((int)app->right_slot_views[0]));
    json_object_array_add(rsv, json_object_new_int((int)app->right_slot_views[1]));
    json_object_object_add(ui, "right_slot_views", rsv);
    json_object_object_add(root, "ui", ui);

    /* Subjective chart — compute clusters once, share with notes serialiser */
    int          n_clusters = 0;
    ClusterMeta *clusters   = compute_clusters(app, &n_clusters);

    json_object *subj = json_object_new_object();
    json_object_object_add(subj, "strokes",
        strokes_to_json(app->strokes));
    json_object_object_add(subj, "stroke_clusters",
        clusters_meta_to_json(clusters, n_clusters));
    json_object_object_add(subj, "misc_cluster_ids",
        misc_cluster_ids_json(app, clusters, n_clusters));
    json_object_object_add(subj, "notes",
        notes_to_json(app, clusters, n_clusters));
    json_object_object_add(subj, "arrows",          arrows_to_json(app));
    json_object_object_add(subj, "link_matrix",    link_matrix_to_json(app));
    json_object_object_add(subj, "link_relations", link_relations_to_json(app));
    json_object_object_add(subj, "link_summary_active",
        json_object_new_boolean(app->link_summary_active));
    json_object_object_add(subj, "link_summary_view",
        json_object_new_int(app->link_summary_view));
    json_object_object_add(subj, "link_summary_bx",
        json_object_new_double(app->link_summary_bx));
    json_object_object_add(subj, "link_summary_by",
        json_object_new_double(app->link_summary_by));
    json_object_object_add(subj, "legend_bx",
        json_object_new_double(app->legend_bx));
    json_object_object_add(subj, "legend_by",
        json_object_new_double(app->legend_by));
    json_object_object_add(root, "subjective", subj);

    /* Objective chart */
    json_object *obj = json_object_new_object();
    json_object_object_add(obj, "zones",  obj_zones_to_json(app));
    json_object_object_add(obj, "points", obj_points_to_json(app));
    json_object_object_add(obj, "ticks",  obj_ticks_to_json(app));
    json_object_object_add(obj, "pencil_strokes", strokes_to_json(app->obj_pencil_strokes));
    json_object_object_add(obj, "gonio_charts", gonio_charts_to_json(app));
    json_object_object_add(root, "objective", obj);
    json_object_object_add(root, "neuro", json_object_new_object());

    /* Assessment block — GTK flat fields plus preserved Python TUI sub-objects */
    json_object *assess = json_object_new_object();
    json_object_object_add(assess, "history",
        json_object_new_string(app->report.history));
    json_object_object_add(assess, "agg_factors",
        json_object_new_string(app->report.agg_factors));
    json_object_object_add(assess, "ease_factors",
        json_object_new_string(app->report.ease_factors));
    json_object_object_add(assess, "behaviour_24hr",
        json_object_new_string(app->report.behaviour_24hr));
    json_object_object_add(assess, "diagnosis",
        json_object_new_string(app->report.assessment));
    json_object_object_add(assess, "plan",
        json_object_new_string(app->report.plan));
    json_object_object_add(assess, "clinical_notes",
        json_object_new_string(app->report.clinical_notes));
    json_object_object_add(assess, "modified",
        json_object_new_int64((int64_t)time(NULL)));

    /* Re-inject Python TUI sub-objects — json_object_get bumps refcount so
       both the existing tree and the new assess safely share the object until
       existing is freed below. */
    if (existing_assess) {
        for (int i = 0; PYTHON_ASSESS_KEYS[i]; i++) {
            json_object *val = NULL;
            if (json_object_object_get_ex(existing_assess, PYTHON_ASSESS_KEYS[i], &val) && val) {
                json_object_get(val);
                json_object_object_add(assess, PYTHON_ASSESS_KEYS[i], val);
            }
        }
    }
    json_object_object_add(root, "assessment", assess);

    /* Re-inject root-level Python TUI keys (sections_complete, sections_last_modified) */
    if (existing) {
        for (int i = 0; PYTHON_ROOT_KEYS[i]; i++) {
            json_object *val = NULL;
            if (json_object_object_get_ex(existing, PYTHON_ROOT_KEYS[i], &val) && val) {
                json_object_get(val);
                json_object_object_add(root, PYTHON_ROOT_KEYS[i], val);
            }
        }
        json_object_put(existing);   /* release; Python sub-objects still live via new tree */
    }

    json_object *rpt = json_object_new_object();
    json_object_object_add(rpt, "assessment",
        json_object_new_string(app->report.assessment));
    json_object_object_add(rpt, "plan",
        json_object_new_string(app->report.plan));
    json_object_object_add(rpt, "clinical_notes",
        json_object_new_string(app->report.clinical_notes));
    {
        static const char *KEYS[SUBJ_FIELD_COUNT] = {"hist","aggs","ease","24hr"};
        json_object *ns_arr = json_object_new_array();
        for (int ni = 0; ni < app->note_count; ni++) {
            json_object *ns = json_object_new_object();
            for (int f = 0; f < SUBJ_FIELD_COUNT; f++)
                json_object_object_add(ns, KEYS[f],
                    json_object_new_string(app->report.note_subj[ni].fields[f]));
            json_object_array_add(ns_arr, ns);
        }
        json_object_object_add(rpt, "note_subj", ns_arr);
    }
    json_object_object_add(root, "report", rpt);

    /* Record timestamp of this save for debouncing file monitor */
    app->last_own_save_us = g_get_monotonic_time();

    /* Write to file */
    const char *json_str = json_object_to_json_string_ext(root,
        JSON_C_TO_STRING_PLAIN);
    FILE *f = fopen(app->session_file, "w");
    if (!f) {
        json_object_put(root);
        fprintf(stderr, "persistence_save: cannot open %s\n", app->session_file);
        return FALSE;
    }
    fputs(json_str, f);
    fclose(f);
    json_object_put(root);
    cluster_meta_free(clusters, n_clusters);
    fprintf(stderr, "persistence_save: %s\n", app->session_file);
    return TRUE;
}

/* ── JSON read helpers ────────────────────────────────────────────────────── */

static int ji(json_object *o, const char *k, int def)
{
    json_object *v;
    return json_object_object_get_ex(o, k, &v) ? json_object_get_int(v) : def;
}

static double jd(json_object *o, const char *k, double def)
{
    json_object *v;
    return json_object_object_get_ex(o, k, &v) ? json_object_get_double(v) : def;
}

static gboolean jb(json_object *o, const char *k, gboolean def)
{
    json_object *v;
    return json_object_object_get_ex(o, k, &v) ?
        (gboolean)json_object_get_boolean(v) : def;
}

static const char *js(json_object *o, const char *k)
{
    json_object *v;
    return json_object_object_get_ex(o, k, &v) ? json_object_get_string(v) : "";
}

/* Forward declaration for note text regeneration */
extern const char *QUALITY_SHORT_EXTERN[];

/* One shared copy for this file (persistence_load's load loop and
 * persistence_reload_chart_note_overrides() below both need it) — was
 * previously a load()-local static, duplicated here rather than pulled
 * from window.c's own QUALITY_SHORT[] (that cross-file duplication is
 * pre-existing, not introduced by this change; left alone for now). */
static const char *const NOTE_QUALITY_SHORT[NOTE_QUALITY_COUNT] = {
    "Throb","Press","Ache","Stab",
    "Tight","Burn","Freez","Elec",
    "Shot","P+N","Numb","Itch"
};

static void regen_note_text(NoteAnnotation *n, const char *const *qs)
{
    char line2[128] = {0};
    if (n->chart_note_text[0]) {
        /* Clinician's own Assessment-side wording wins over everything else,
         * same precedence voice_note already had over the short codes. */
        snprintf(line2, sizeof(line2), "%.44s%s",
                 n->chart_note_text,
                 strlen(n->chart_note_text) > 44 ? "…" : "");
    } else if (n->voice_note[0]) {
        snprintf(line2, sizeof(line2), "%.44s%s",
                 n->voice_note,
                 strlen(n->voice_note) > 44 ? "…" : "");
    } else {
        char qual_buf[64] = {0};
        for (int q = 0; q < n->quality_count; q++) {
            if (q > 0) strncat(qual_buf, "+",
                               sizeof(qual_buf) - strlen(qual_buf) - 1);
            strncat(qual_buf, qs[n->qualities[q]],
                    sizeof(qual_buf) - strlen(qual_buf) - 1);
        }
        if (n->quality_count == 0)
            strncat(qual_buf, "?", sizeof(qual_buf) - strlen(qual_buf) - 1);
        g_strlcpy(line2, qual_buf, sizeof(line2));
    }

    snprintf(n->text, sizeof(n->text), "(%d)%s %s %d-%d/10\n%s",
             n->number,
             n->temporal == 0 ? "Con" : "Int",
             n->depth    == 0 ? "Sup" : "Dep",
             n->low_intensity, n->high_intensity,
             line2);
}

/* ── Load ─────────────────────────────────────────────────────────────────── */

static void load_obj_data(AppState *app, json_object *obj_j)
{
    for (int i = 0; i < app->obj_zone_count; i++) {
        obj_zone_free(app->obj_zones[i]);
        app->obj_zones[i] = NULL;
    }
    app->obj_zone_count    = 0;
    app->obj_point_count   = 0;
    app->obj_tick_count    = 0;
    app->obj_undo_type_top = 0;

    json_object *zones_arr;
    if (json_object_object_get_ex(obj_j, "zones", &zones_arr)) {
        int n = (int)json_object_array_length(zones_arr);
        for (int i = 0; i < n && app->obj_zone_count < MAX_OBJ_ZONES; i++) {
            json_object *o = json_object_array_get_idx(zones_arr, i);
            int type = ji(o, "type", 0);
            int view = ji(o, "view", 0);
            if (type < 0 || type >= OBJ_ZONE_COUNT) continue;
            ObjZone *z = obj_zone_new((ObjZoneType)type, view);
            json_object *pts;
            if (json_object_object_get_ex(o, "pts", &pts)) {
                int np = (int)json_object_array_length(pts);
                for (int j = 0; j < np; j++) {
                    json_object *pt = json_object_array_get_idx(pts, j);
                    if (json_object_array_length(pt) >= 2) {
                        float bx = (float)json_object_get_double(
                                       json_object_array_get_idx(pt, 0));
                        float by = (float)json_object_get_double(
                                       json_object_array_get_idx(pt, 1));
                        obj_zone_add_pt(z, bx, by);
                    }
                }
            }
            app->obj_zones[app->obj_zone_count++] = z;
        }
    }

    json_object *points_arr;
    if (json_object_object_get_ex(obj_j, "points", &points_arr)) {
        int n = (int)json_object_array_length(points_arr);
        for (int i = 0; i < n && app->obj_point_count < MAX_OBJ_POINTS; i++) {
            json_object *o = json_object_array_get_idx(points_arr, i);
            int type = ji(o, "type", 0);
            if (type < 0 || type >= OBJ_POINT_COUNT) continue;
            ObjPoint *p = &app->obj_points[app->obj_point_count++];
            p->type  = (ObjPointType)type;
            p->view  = ji(o, "view",  0);
            p->bx    = jd(o, "bx",    100.0);
            p->by    = jd(o, "by",    200.0);
            p->value = jd(o, "value", 0.0);
            strncpy(p->label, js(o, "label"), sizeof(p->label) - 1);
            json_object *lx_j;
            if (json_object_object_get_ex(o, "lx", &lx_j)) {
                p->anchor.lx     = jd(o, "lx", p->bx + 6.0);
                p->anchor.ly     = jd(o, "ly", p->by - 5.0);
                p->anchor.placed = 1;
            } else {
                p->anchor.placed = 0;
            }
        }
    }

    json_object *ticks_arr;
    if (json_object_object_get_ex(obj_j, "ticks", &ticks_arr)) {
        int n = (int)json_object_array_length(ticks_arr);
        for (int i = 0; i < n && app->obj_tick_count < MAX_OBJ_TICKS; i++) {
            json_object *o = json_object_array_get_idx(ticks_arr, i);
            int type = ji(o, "type", 0);
            if (type < 0 || type >= OBJ_TICK_TYPE_COUNT) continue;
            int state = ji(o, "state", 0);
            ObjTick *t = &app->obj_ticks[app->obj_tick_count++];
            t->type  = (ObjTickType)type;
            t->state = (state == OBJ_TICK_STATE_CROSS) ? OBJ_TICK_STATE_CROSS : OBJ_TICK_STATE_TICK;
            t->view  = ji(o, "view", 0);
            t->bx    = jd(o, "bx", 100.0);
            t->by    = jd(o, "by", 200.0);
        }
    }

    /* Pencil tool in Objective mode (2026-08-26) — its own stroke list,
     * NOT app->strokes (see canvas.h's field comment). Same shape
     * strokes_to_json()/the Subjective stroke loader use. */
    stroke_list_clear(app->obj_pencil_strokes);
    json_object *pencil_arr;
    if (json_object_object_get_ex(obj_j, "pencil_strokes", &pencil_arr)) {
        int n = (int)json_object_array_length(pencil_arr);
        for (int i = 0; i < n; i++) {
            json_object *s = json_object_array_get_idx(pencil_arr, i);
            int type = ji(s, "type", SYMPTOM_PENCIL);
            int view = ji(s, "view", 0);
            int wide = jb(s, "wide", FALSE);
            double draw_zoom_val = jd(s, "draw_zoom", 0.0);
            int sid  = ji(s, "id", -1);
            if (type < 0 || type >= SYMPTOM_COUNT) continue;
            Stroke *sk = stroke_new((SymptomType)type, view);
            sk->wide_mode = wide;
            sk->draw_zoom = draw_zoom_val;
            if (sid >= 0) {
                sk->id = sid;
                if (sid >= app->next_stroke_id) app->next_stroke_id = sid + 1;
            } else {
                sk->id = app->next_stroke_id++;
            }
            json_object *pts;
            if (json_object_object_get_ex(s, "pts", &pts)) {
                int np = (int)json_object_array_length(pts);
                for (int j = 0; j < np; j++) {
                    json_object *pt = json_object_array_get_idx(pts, j);
                    if (json_object_array_length(pt) < 3) continue;
                    float x = (float)json_object_get_double(json_object_array_get_idx(pt, 0));
                    float y = (float)json_object_get_double(json_object_array_get_idx(pt, 1));
                    float p = (float)json_object_get_double(json_object_array_get_idx(pt, 2));
                    stroke_add_point(sk, x, y, p);
                }
            }
            if (sk->n_pts > 0)
                stroke_list_push(app->obj_pencil_strokes, sk);
            else
                stroke_free(sk);
        }
    }

    /* Goniometer ROM chart placement — restore saved positions; a following
     * gonio_charts_rescan() (persistence_load's tail) reconciles this list
     * against the PNGs actually present in <session_dir>/gonio_charts/. */
    app->gonio_chart_count = 0;
    json_object *gc_arr;
    if (json_object_object_get_ex(obj_j, "gonio_charts", &gc_arr)) {
        int n = (int)json_object_array_length(gc_arr);
        for (int i = 0; i < n && app->gonio_chart_count < MAX_GONIO_CHARTS; i++) {
            json_object *o = json_object_array_get_idx(gc_arr, i);
            const char *file = js(o, "file");
            if (!file || !file[0]) continue;
            GonioChart *gc = &app->gonio_charts[app->gonio_chart_count++];
            memset(gc, 0, sizeof(*gc));
            g_strlcpy(gc->file, file, sizeof(gc->file));
            gc->fx      = jd(o, "fx", 0.70);
            gc->fy      = jd(o, "fy", 0.05);
            gc->scale   = jd(o, "scale", 1.0);
            gc->visible = jb(o, "visible", TRUE);
        }
    }
}

gboolean persistence_load(AppState *app, const char *path)
{
    json_object *root = json_object_from_file(path);
    if (!root) {
        fprintf(stderr, "persistence_load: cannot parse %s\n", path);
        return FALSE;
    }

    /* Clear existing drawing data */
    stroke_list_clear(app->strokes);
    app->note_count      = 0;
    app->arrow_count     = 0;
    app->arrow_drawing   = FALSE;
    app->link_rel_count  = 0;
    app->link_summary_active = FALSE;
    app->undo_type_top   = 0;
    memset(app->link_matrix, 0, sizeof(app->link_matrix));
    app->next_stroke_id  = 0;
    app->next_note_id    = 0;

    /* Set paths from loaded file */
    strncpy(app->session_file, path, sizeof(app->session_file) - 1);

    /* Derive session_dir (parent directory) */
    {
        char tmp[512];
        strncpy(tmp, path, sizeof(tmp) - 1);
        char *slash = strrchr(tmp, '/');
        if (slash) { *slash = '\0'; g_snprintf(app->session_dir, sizeof(app->session_dir), "%s", tmp); }
    }

    /* Derive session_name (filename without _session.json) */
    {
        const char *fname = strrchr(path, '/');
        fname = fname ? fname + 1 : path;
        size_t flen = strlen(fname);
        const char *suf = "_session.json";
        size_t slen = strlen(suf);
        if (flen > slen && strcmp(fname + flen - slen, suf) == 0) {
            size_t nlen = flen - slen;
            if (nlen >= sizeof(app->session_name)) nlen = sizeof(app->session_name) - 1;
            memcpy(app->session_name, fname, nlen);
            app->session_name[nlen] = '\0';
        }
    }

    /* Metadata */
    strncpy(app->patient_id,    js(root, "patient_id"),    sizeof(app->patient_id)    - 1);
    strncpy(app->session_label, js(root, "session_label"), sizeof(app->session_label) - 1);
    {
        json_object *v;
        app->session_created = json_object_object_get_ex(root, "created", &v) ?
            (time_t)json_object_get_int64(v) : time(NULL);
    }

    /* UI state */
    json_object *ui;
    if (json_object_object_get_ex(root, "ui", &ui)) {
        int lm = ji(ui, "layout_mode", 0);
        if (lm >= 0 && lm < LAYOUT_COUNT) app->layout_mode = (LayoutMode)lm;
        json_object *rsv;
        if (json_object_object_get_ex(ui, "right_slot_views", &rsv) &&
            json_object_array_length(rsv) >= 2) {
            int v0 = json_object_get_int(json_object_array_get_idx(rsv, 0));
            int v1 = json_object_get_int(json_object_array_get_idx(rsv, 1));
            if (v0 >= 0 && v0 < 4) app->right_slot_views[0] = (BodyView)v0;
            if (v1 >= 0 && v1 < 4) app->right_slot_views[1] = (BodyView)v1;
        }
    }

    /* Subjective */
    json_object *subj;
    if (!json_object_object_get_ex(root, "subjective", &subj)) {
        json_object_put(root);
        gonio_charts_rescan(app);   /* session_dir is set by now */
        return TRUE;  /* empty but valid */
    }

    /* Strokes */
    json_object *strokes_arr;
    if (json_object_object_get_ex(subj, "strokes", &strokes_arr)) {
        int n = (int)json_object_array_length(strokes_arr);
        for (int i = 0; i < n; i++) {
            json_object *s = json_object_array_get_idx(strokes_arr, i);
            int type  = ji(s, "type",  0);
            int view  = ji(s, "view",  0);
            int wide  = jb(s, "wide",  FALSE);
            double draw_zoom_val = jd(s, "draw_zoom", 0.0);
            int sid   = ji(s, "id",    -1);
            if (type < 0 || type >= SYMPTOM_COUNT) continue;
            Stroke *sk = stroke_new((SymptomType)type, view);
            sk->wide_mode    = wide;
            sk->draw_zoom = draw_zoom_val;
            if (sid >= 0) {
                sk->id = sid;
                if (sid >= app->next_stroke_id) app->next_stroke_id = sid + 1;
            } else {
                sk->id = app->next_stroke_id++;  /* back-compat: old sessions without id */
            }
            json_object *pts;
            if (json_object_object_get_ex(s, "pts", &pts)) {
                int np = (int)json_object_array_length(pts);
                for (int j = 0; j < np; j++) {
                    json_object *pt = json_object_array_get_idx(pts, j);
                    if (json_object_array_length(pt) < 3) continue;
                    float x = (float)json_object_get_double(json_object_array_get_idx(pt, 0));
                    float y = (float)json_object_get_double(json_object_array_get_idx(pt, 1));
                    float p = (float)json_object_get_double(json_object_array_get_idx(pt, 2));
                    stroke_add_point(sk, x, y, p);
                }
            }
            if (sk->n_pts > 0)
                stroke_list_push(app->strokes, sk);
            else
                stroke_free(sk);
        }
    }

    /* Notes — need quality strings for text regeneration */
    const char *const *qs = NOTE_QUALITY_SHORT;
    json_object *notes_arr;
    if (json_object_object_get_ex(subj, "notes", &notes_arr)) {
        int n = (int)json_object_array_length(notes_arr);
        if (n > MAX_NOTES) n = MAX_NOTES;
        for (int i = 0; i < n; i++) {
            json_object *o = json_object_array_get_idx(notes_arr, i);
            NoteAnnotation *na = &app->notes[app->note_count];
            na->view            = ji(o, "view",      0);
            na->bx              = jd(o, "bx",        0.0);
            na->by              = jd(o, "by",        0.0);
            na->number          = ji(o, "number",    i + 1);
            {
                int sid = ji(o, "stable_id", -1);
                if (sid >= 0) {
                    na->stable_id = sid;
                    if (sid >= app->next_note_id) app->next_note_id = sid + 1;
                } else {
                    na->stable_id = app->next_note_id++;
                }
            }
            na->temporal        = ji(o, "temporal",0);
            na->depth           = ji(o, "depth",   0);
            /* Load qualities — new array format; fall back to legacy "quality" int */
            json_object *quals_j;
            if (json_object_object_get_ex(o, "qualities", &quals_j)
                    && json_object_get_type(quals_j) == json_type_array) {
                int qc = (int)json_object_array_length(quals_j);
                if (qc > 3) qc = 3;
                na->quality_count = qc;
                for (int q = 0; q < qc; q++) {
                    int qv = (int)json_object_get_int(json_object_array_get_idx(quals_j, q));
                    na->qualities[q] = (qv >= 0 && qv < NOTE_QUALITY_COUNT) ? qv : 0;
                }
            } else {
                /* legacy: single "quality" int */
                int qv = ji(o, "quality", 0);
                na->qualities[0]  = (qv >= 0 && qv < NOTE_QUALITY_COUNT) ? qv : 0;
                na->quality_count = 1;
            }
            /* Load intensity — new low/high format; fall back to legacy avg/worst */
            if (json_object_object_get_ex(o, "low", NULL)) {
                na->low_intensity  = ji(o, "low",   0);
                na->high_intensity = ji(o, "high",  0);
            } else {
                na->low_intensity  = ji(o, "avg",   0);
                na->high_intensity = ji(o, "worst", 0);
            }
            /* Label anchor — absent in old sessions → placed=0 (default offset) */
            json_object *lx_j;
            if (json_object_object_get_ex(o, "lx", &lx_j)) {
                na->label.lx     = jd(o, "lx", na->bx + 12.0);
                na->label.ly     = jd(o, "ly", na->by - 8.0);
                na->label.placed = 1;
            } else {
                na->label.placed = 0;
            }
            /* Voice transcript — absent in sessions recorded before voice support */
            g_strlcpy(na->voice_note, js(o, "voice_note"), sizeof(na->voice_note));
            /* gpab Assessment override — absent unless the clinician has typed
             * into the "Brief (chart-facing)" box for this note */
            g_strlcpy(na->chart_note_text, js(o, "chart_note_text"), sizeof(na->chart_note_text));
            regen_note_text(na, qs);
            app->note_count++;
        }
    }

    /* Arrows */
    json_object *arrows_arr;
    if (json_object_object_get_ex(subj, "arrows", &arrows_arr)) {
        int n = (int)json_object_array_length(arrows_arr);
        if (n > MAX_ARROWS) n = MAX_ARROWS;
        for (int i = 0; i < n; i++) {
            json_object *o = json_object_array_get_idx(arrows_arr, i);
            ArrowAnnotation *a = &app->arrows[app->arrow_count];
            a->view = ji(o, "view", 0);
            a->x1   = jd(o, "x1",  0.0);
            a->y1   = jd(o, "y1",  0.0);
            a->cx   = jd(o, "cx",  0.0);
            a->cy   = jd(o, "cy",  0.0);
            a->x2   = jd(o, "x2",  0.0);
            a->y2   = jd(o, "y2",  0.0);
            app->arrow_count++;
        }
    }

    /* Link matrix */
    json_object *lm;
    if (json_object_object_get_ex(subj, "link_matrix", &lm)) {
        int rows = (int)json_object_array_length(lm);
        if (rows > MAX_NOTES) rows = MAX_NOTES;
        for (int i = 0; i < rows; i++) {
            json_object *row = json_object_array_get_idx(lm, i);
            int cols = (int)json_object_array_length(row);
            if (cols > MAX_NOTES) cols = MAX_NOTES;
            for (int j = 0; j < cols; j++)
                app->link_matrix[i][j] =
                    json_object_get_int(json_object_array_get_idx(row, j));
        }
    }

    /* Link relations */
    json_object *lr_arr;
    if (json_object_object_get_ex(subj, "link_relations", &lr_arr)) {
        int n = (int)json_object_array_length(lr_arr);
        int max = MAX_NOTES * MAX_NOTES;
        if (n > max) n = max;
        for (int i = 0; i < n; i++) {
            json_object *o = json_object_array_get_idx(lr_arr, i);
            app->link_relations[app->link_rel_count].from  = ji(o, "from",  0);
            app->link_relations[app->link_rel_count].to    = ji(o, "to",    0);
            app->link_relations[app->link_rel_count].state = ji(o, "state", 0);
            app->link_rel_count++;
        }
    }

    /* Link summary position */
    app->link_summary_active = jb(subj, "link_summary_active", FALSE);
    app->link_summary_view   = ji(subj, "link_summary_view",   0);
    app->link_summary_bx     = jd(subj, "link_summary_bx",    12.0);
    app->link_summary_by     = jd(subj, "link_summary_by",   378.0);
    app->legend_bx           = jd(subj, "legend_bx",         135.0);
    app->legend_by           = jd(subj, "legend_by",         378.0);

    /* Objective chart */
    json_object *obj_j;
    if (json_object_object_get_ex(root, "objective", &obj_j))
        load_obj_data(app, obj_j);

    /* Report (legacy) */
    json_object *rpt_j;
    if (json_object_object_get_ex(root, "report", &rpt_j)) {
        g_strlcpy(app->report.assessment,
                  js(rpt_j, "assessment"),   REPORT_SECTION_LEN);
        g_strlcpy(app->report.plan,
                  js(rpt_j, "plan"),          REPORT_SECTION_LEN);
        g_strlcpy(app->report.clinical_notes,
                  js(rpt_j, "clinical_notes"), REPORT_SECTION_LEN);
        static const char *KEYS[SUBJ_FIELD_COUNT] = {"hist","aggs","ease","24hr"};
        json_object *ns_arr;
        if (json_object_object_get_ex(rpt_j, "note_subj", &ns_arr)) {
            int nse = (int)json_object_array_length(ns_arr);
            if (nse > REPORT_MAX_NOTES) nse = REPORT_MAX_NOTES;
            for (int ni = 0; ni < nse; ni++) {
                json_object *ns = json_object_array_get_idx(ns_arr, ni);
                for (int f = 0; f < SUBJ_FIELD_COUNT; f++)
                    g_strlcpy(app->report.note_subj[ni].fields[f],
                              js(ns, KEYS[f]), REPORT_NOTE_FIELD_LEN);
            }
        }
    }

    /* Assessment block (Python-owned, takes precedence if newer) */
    json_object *assess_j;
    if (json_object_object_get_ex(root, "assessment", &assess_j)) {
        g_strlcpy(app->report.history,
                  js(assess_j, "history"),        REPORT_SECTION_LEN);
        g_strlcpy(app->report.agg_factors,
                  js(assess_j, "agg_factors"),    REPORT_NOTE_FIELD_LEN);
        g_strlcpy(app->report.ease_factors,
                  js(assess_j, "ease_factors"),   REPORT_NOTE_FIELD_LEN);
        g_strlcpy(app->report.behaviour_24hr,
                  js(assess_j, "behaviour_24hr"), REPORT_NOTE_FIELD_LEN);
        g_strlcpy(app->report.assessment,
                  js(assess_j, "diagnosis"),      REPORT_SECTION_LEN);
        g_strlcpy(app->report.plan,
                  js(assess_j, "plan"),           REPORT_SECTION_LEN);
        g_strlcpy(app->report.clinical_notes,
                  js(assess_j, "clinical_notes"), REPORT_SECTION_LEN);
    }

    json_object_put(root);

    /* Reconcile restored gonio-chart placement with the PNGs on disk
     * (new imports since last save appear; deleted ones drop out). */
    gonio_charts_rescan(app);

    /* Invalidate per-view stroke caches: strokes/arrows changed. */
    app->stroke_version++;

    fprintf(stderr, "persistence_load: %s\n", path);
    return TRUE;
}

/* ── Recent sessions ─────────────────────────────────────────────────────── */

int persistence_scan_recent(PersistRecent *out, int max)
{
    char root[512];
    ensure_physio_root(root, sizeof(root));

    GDir *dir = g_dir_open(root, 0, NULL);
    if (!dir) return 0;

    int count = 0;
    const gchar *entry;
    while ((entry = g_dir_read_name(dir)) != NULL && count < max) {
        char json_path[512];
        g_snprintf(json_path, sizeof(json_path), "%s/%s/%s_session.json",
                   root, entry, entry);
        if (!g_file_test(json_path, G_FILE_TEST_IS_REGULAR)) continue;

        json_object *meta = json_object_from_file(json_path);
        if (!meta) continue;

        PersistRecent *r = &out[count];
        memset(r, 0, sizeof(*r));
        g_snprintf(r->path, sizeof(r->path), "%s", json_path);
        strncpy(r->patient_id,    js(meta, "patient_id"),    sizeof(r->patient_id)    - 1);
        strncpy(r->session_label, js(meta, "session_label"), sizeof(r->session_label) - 1);
        strncpy(r->session_name,  js(meta, "session_name"),  sizeof(r->session_name)  - 1);
        {
            json_object *v;
            r->modified = json_object_object_get_ex(meta, "modified", &v) ?
                (time_t)json_object_get_int64(v) : 0;
        }
        json_object_put(meta);
        count++;
    }
    g_dir_close(dir);

    /* Insertion sort: newest (largest modified) first */
    for (int i = 1; i < count; i++) {
        PersistRecent tmp = out[i];
        int j = i - 1;
        while (j >= 0 && out[j].modified < tmp.modified) {
            out[j + 1] = out[j];
            j--;
        }
        out[j + 1] = tmp;
    }

    return count;
}

/* ── Write simplified session file for physio-assessment integration ─────────── */

static gboolean ensure_share_dir(void)
{
    char path[512];
    const char *home = g_get_home_dir();
    snprintf(path, sizeof(path), "%s/.local", home);
    if (mkdir(path, 0755) != 0 && errno != EEXIST) return FALSE;

    snprintf(path, sizeof(path), "%s/.local/share", home);
    if (mkdir(path, 0755) != 0 && errno != EEXIST) return FALSE;

    snprintf(path, sizeof(path), "%s/.local/share/pab", home);
    if (mkdir(path, 0755) != 0 && errno != EEXIST) return FALSE;

    return TRUE;
}

gboolean persistence_write_session_current(AppState *app)
{
    if (!ensure_share_dir()) return FALSE;

    char path[512];
    snprintf(path, sizeof(path), "%s/.local/share/pab/session_current.json",
             g_get_home_dir());

    json_object *root = json_object_new_object();

    json_object_object_add(root, "schema_version", json_object_new_int(4));
    json_object_object_add(root, "gtk_pid", json_object_new_int((int)getpid()));

    if (app->session_file[0])
        json_object_object_add(root, "session_file",
            json_object_new_string(app->session_file));

    json_object_object_add(root, "session_id",
        json_object_new_string(app->patient_id[0] ? app->patient_id : ""));

    if (app->session_label[0])
        json_object_object_add(root, "session_label",
            json_object_new_string(app->session_label));

    char iso8601_date[32];
    time_t now = time(NULL);
    struct tm *t = gmtime(&now);
    strftime(iso8601_date, sizeof(iso8601_date), "%Y-%m-%dT%H:%M:%SZ", t);
    json_object_object_add(root, "date", json_object_new_string(iso8601_date));

    json_object *body_chart = json_object_new_object();
    json_object_object_add(body_chart, "strokes", strokes_to_json(app->strokes));

    json_object *symptom_types = json_object_new_array();
    for (int i = 0; i < app->strokes->n; i++) {
        int type = app->strokes->strokes[i]->type;
        gboolean found = FALSE;
        for (size_t j = 0; j < json_object_array_length(symptom_types); j++) {
            if (json_object_get_int(json_object_array_get_idx(symptom_types, j)) == type) {
                found = TRUE;
                break;
            }
        }
        if (!found) {
            json_object_array_add(symptom_types, json_object_new_int(type));
        }
    }
    json_object_object_add(body_chart, "symptom_types_used", symptom_types);

    json_object_object_add(body_chart, "active_overlay",
        app->overlay_visible ? json_object_new_int(app->overlay_category) : NULL);
    json_object_object_add(body_chart, "overlay_category",
        app->overlay_visible ? json_object_new_int(app->overlay_category) : NULL);
    json_object_object_add(body_chart, "overlay_index",
        app->overlay_visible ? json_object_new_int(app->overlay_index) : NULL);

    json_object *views_drawn = json_object_new_array();
    json_object_array_add(views_drawn, json_object_new_int(app->current_view));
    json_object_object_add(body_chart, "views_drawn", views_drawn);

    json_object_object_add(root, "body_chart", body_chart);

    gboolean ok = json_object_to_file(path, root) == 0;
    json_object_put(root);

    return ok;
}

/* Picks up gpab-side edits to a note's "Brief (chart-facing)" box — the only
 * field in _session.json that gpab writes (everything else in this file
 * remains bodychart-owned, see bodychart/CLAUDE.md). Reload here rather than
 * a full persistence_load(): this runs mid-session, on the live AppState,
 * and must not disturb undo history, in-progress strokes, or anything else
 * — only chart_note_text (matched by stable_id) and the derived na->text are
 * touched. Without this, gpab's write would be silently lost the next time
 * window_autosave()'s 30s timer serializes bodychart's own (stale, unaware
 * of the edit) in-memory copy over it — the same race persistence_reload_
 * assessment() above already exists to avoid, just for a field that's
 * actually live now (see that function's docstring-equivalent comment). */
static void persistence_reload_chart_note_overrides(AppState *app)
{
    if (!app->session_file[0]) return;

    json_object *root = json_object_from_file(app->session_file);
    if (!root) return;

    json_object *subj = json_object_object_get(root, "subjective");
    json_object *notes_arr = subj ? json_object_object_get(subj, "notes") : NULL;
    if (!notes_arr) { json_object_put(root); return; }

    int n = (int)json_object_array_length(notes_arr);
    for (int i = 0; i < n; i++) {
        json_object *o = json_object_array_get_idx(notes_arr, i);
        int sid = ji(o, "stable_id", -1);
        if (sid < 0) continue;
        const char *override_text = js(o, "chart_note_text");

        for (int ni = 0; ni < app->note_count; ni++) {
            NoteAnnotation *na = &app->notes[ni];
            if (na->stable_id != sid) continue;
            if (strcmp(na->chart_note_text, override_text) != 0) {
                g_strlcpy(na->chart_note_text, override_text, sizeof(na->chart_note_text));
                regen_note_text(na, NOTE_QUALITY_SHORT);
            }
            break;
        }
    }

    json_object_put(root);
}

/* ── File Watcher for Session JSON (integration with physio-assessment) ────── */

static void on_session_file_changed(GFileMonitor *m, GFile *f, GFile *other,
                                     GFileMonitorEvent ev, gpointer data)
{
    (void)m; (void)f; (void)other;
    if (ev != G_FILE_MONITOR_EVENT_CHANGES_DONE_HINT) return;

    AppState *app = (AppState *)data;
    gint64 age_us = g_get_monotonic_time() - app->last_own_save_us;
    if (age_us < 2000000) return;  /* ignore our own writes (within 2 seconds) */

    persistence_reload_assessment(app);
    persistence_reload_chart_note_overrides(app);
    if (app->toolbar_update_cb) app->toolbar_update_cb(app);
    canvas_invalidate(app);
}

void persistence_monitor_start(AppState *app)
{
    if (!app->session_file[0]) return;  /* no session active */
    if (app->session_file_monitor) return;  /* already running */

    GFile *f = g_file_new_for_path(app->session_file);
    GError *err = NULL;
    app->session_file_monitor = g_file_monitor_file(f, G_FILE_MONITOR_NONE, NULL, &err);
    if (!app->session_file_monitor) {
        fprintf(stderr, "persistence_monitor_start: g_file_monitor_file failed: %s\n",
                err ? err->message : "unknown error");
        if (err) g_error_free(err);
        g_object_unref(f);
        return;
    }
    g_signal_connect(app->session_file_monitor, "changed",
                     G_CALLBACK(on_session_file_changed), app);
    g_object_unref(f);
}

void persistence_monitor_stop(AppState *app)
{
    if (!app->session_file_monitor) return;
    g_file_monitor_cancel(app->session_file_monitor);
    g_object_unref(app->session_file_monitor);
    app->session_file_monitor = NULL;
}

void persistence_reload_assessment(AppState *app)
{
    if (!app->session_file[0]) return;

    json_object *root = json_object_from_file(app->session_file);
    if (!root) {
        fprintf(stderr, "persistence_reload_assessment: failed to parse %s\n",
                app->session_file);
        return;
    }

    json_object *assessment = json_object_object_get(root, "assessment");
    if (assessment) {
        json_object *jstr = json_object_object_get(assessment, "history");
        if (jstr)
            snprintf(app->report.history, sizeof(app->report.history), "%s",
                     json_object_get_string(jstr));

        jstr = json_object_object_get(assessment, "agg_factors");
        if (jstr)
            snprintf(app->report.agg_factors, sizeof(app->report.agg_factors), "%s",
                     json_object_get_string(jstr));

        jstr = json_object_object_get(assessment, "ease_factors");
        if (jstr)
            snprintf(app->report.ease_factors, sizeof(app->report.ease_factors), "%s",
                     json_object_get_string(jstr));

        jstr = json_object_object_get(assessment, "behaviour_24hr");
        if (jstr)
            snprintf(app->report.behaviour_24hr, sizeof(app->report.behaviour_24hr), "%s",
                     json_object_get_string(jstr));

        jstr = json_object_object_get(assessment, "plan");
        if (jstr)
            snprintf(app->report.plan, sizeof(app->report.plan), "%s",
                     json_object_get_string(jstr));

        jstr = json_object_object_get(assessment, "clinical_notes");
        if (jstr)
            snprintf(app->report.clinical_notes, sizeof(app->report.clinical_notes), "%s",
                     json_object_get_string(jstr));
    }

    json_object_put(root);
}
