#pragma once
#include <gtk/gtk.h>
#include <time.h>
#include "stroke.h"
#include "overlays.h"
#include "body_outlines.h"
#include "input.h"
#include "obj_chart.h"
#include "report.h"
#include "svg_regions.h"

typedef enum {
    APP_MODE_SUBJECTIVE = 0,
    APP_MODE_OBJECTIVE,
    APP_MODE_COUNT
} AppMode;

typedef enum {
    LINK_NEITHER = 0,
    LINK_YES,
    LINK_NO
} LinkState;

typedef struct {
    int from;   /* 0-based note index */
    int to;     /* 0-based note index */
    int state;  /* LINK_YES or LINK_NO */
} LinkRel;

#define MAX_ARROWS 30
typedef struct {
    int    view;
    double x1, y1;
    double cx, cy;   /* quadratic bezier control point */
    double x2, y2;
} ArrowAnnotation;

typedef enum {
    LAYOUT_QUAD = 0,   /* 2 wide cols + 1 narrow col split 2 rows */
    LAYOUT_ANTERIOR,
    LAYOUT_POSTERIOR,
    LAYOUT_LATERAL_L,
    LAYOUT_LATERAL_R,
    LAYOUT_COUNT
} LayoutMode;

/* Barrel button action */
typedef enum {
    BTN_CYCLE_SYMPTOM = 0,  /* press = advance to next symptom type */
    BTN_ERASE               /* press = erase nearest stroke at tap position */
} BtnAction;

struct _AppState {
    /* Main window */
    GtkWidget       *window;
    GtkWidget       *canvas;        /* GtkStack */

    /* View / layout */
    BodyView         current_view;
    LayoutMode       layout_mode;

    /* Drawing state */
    ActiveTool       tool;
    SymptomType      symptom;
    StrokeList      *strokes;
    Stroke          *active_stroke;

    /* Overlay state */
    gboolean         overlay_visible;
    OverlayCategory  overlay_category;
    int              overlay_index;
    float            overlay_alpha;

    /* Link tool */
    gboolean         link_first_set;
    double           link_x1, link_y1;

    /* Legacy geometry */
    double           canvas_w, canvas_h;

    /* Quad-view drawing areas: 0=anterior 1=posterior 2=right_top 3=right_bot */
    GtkWidget       *col_da[4];
    double           col_zoom[4];
    double           col_pan_x[4];
    double           col_pan_y[4];

    /* Single-view drawing areas (same index order) */
    GtkWidget       *single_da[4];
    double           single_zoom[4];
    double           single_pan_x[4];
    double           single_pan_y[4];

    /* Severity per-region (8 views × 10 regions) */
    int              severity[8][10];

    /* ── Pen settings ──────────────────────────────────────────────────────── */
    float       pen_gamma;          /* pressure curve exponent; 0.5–4.0, default 2.0 */
    gboolean    pen_wide_mode;      /* FALSE=thin band, TRUE=wide band */
    gboolean    pen_palm_reject;    /* reject touch within 500ms of stylus; default TRUE */
    BtnAction   pen_btn_action;     /* barrel button behaviour */

    /* Pattern pen config — sizes in body units; tunable via settings.conf */
    float  pen_dot_radius;    /* P&N dot radius, default 1.0 */
    float  pen_dot_spacing;   /* P&N dot spacing along path, default 4.5 */
    float  pen_dash_len;      /* Anaesthesia short-dash half-width, default 2.0 */
    float  pen_dash_spacing;  /* Anaesthesia dash spacing along path, default 5.0 */
    float  pen_dash_width;    /* Anaesthesia stroke thickness, default 0.5 */
    float  pen_x_arm;         /* Deep ache X arm length, default 2.0 */
    float  pen_x_spacing;     /* Deep ache X spacing along path, default 6.0 */
    float  pen_x_width;       /* Deep ache X stroke thickness, default 0.5 */
    float  pen_tilt_weight;   /* How much pen tilt adds to effective pressure, default 0.0 */

    /* Palm rejection — last stylus event time */
    gint64      last_stylus_us;     /* g_get_monotonic_time() */

    /* Note annotations */
    NoteAnnotation   notes[MAX_NOTES];
    int              note_count;

    /* Arrow annotations */
    ArrowAnnotation  arrows[MAX_ARROWS];
    int              arrow_count;
    gboolean         arrow_drawing;    /* in-progress arrow preview */
    int              arrow_draw_view;
    double           arrow_x1, arrow_y1;
    double           arrow_x2, arrow_y2;
    double           arrow_track_x[32];  /* sampled path for bezier fit */
    double           arrow_track_y[32];
    int              arrow_track_n;

    /* Undo type stack: 0=stroke, 1=arrow */
    guint8           undo_type_stack[64];
    int              undo_type_top;

    /* Note/link-summary dragging state */
    int              note_drag_idx;      /* -1=none */
    double           note_drag_bx_off;
    double           note_drag_by_off;
    gboolean         link_drag_active;
    double           link_drag_bx_off;
    double           link_drag_by_off;

    /* Stroke legend position (body-space bottom-left anchor) */
    double           legend_bx, legend_by;
    gboolean         legend_drag_active;
    double           legend_drag_bx_off;
    double           legend_drag_by_off;

    /* Link relationships */
    int              link_matrix[MAX_NOTES][MAX_NOTES];  /* LinkState */
    gboolean         link_summary_active;
    int              link_summary_view;
    double           link_summary_bx, link_summary_by;

    /* Graphical link relations (replaces text summary) */
    LinkRel          link_relations[MAX_NOTES * MAX_NOTES];
    int              link_rel_count;

    /* Cyclable right column views */
    BodyView         right_slot_views[2];

    /* Hotkeys — populated by input_hotkeys_init(), overridable via settings.conf */
    guint            hotkey_val[HK_COUNT];
    GdkModifierType  hotkey_mod[HK_COUNT];

    /* Toolbar refresh callback — set by window.c */
    void (*toolbar_update_cb)(AppState *);

    /* Note wizard callback — set by window.c */
    void (*show_note_wizard_cb)(AppState *, int view, double bx, double by);

    /* Clear confirmation callback — set by window.c */
    void (*request_clear_cb)(AppState *);

    /* ── Mode / session ──────────────────────────────────────────────────────── */
    AppMode  current_mode;
    char     patient_id[32];      /* short ID/initials, e.g. "JB" */
    char     session_label[64];   /* human description, e.g. "Lower back follow-up" */
    char     session_name[80];    /* derived filename base, e.g. "JB_01_05_2026_1430" */
    char     session_dir[512];    /* ~/PhysioChart/JB_01_05_2026_1430 */
    char     session_file[512];   /* full path to _session.json */
    time_t   session_created;
    GFileMonitor *session_file_monitor;  /* file watcher for session JSON */
    GtkWidget   *tui_window;             /* unused since the 2026-08-23 gpab integration change */
    GtkWidget   *tui_terminal;           /* unused since the 2026-08-23 gpab integration change */
    GPid         gpab_pid;               /* PID of the spawned gpab process, 0 if none running */
    gint64   last_own_save_us;           /* timestamp of last persistence_save() call */
    int      next_stroke_id;             /* monotonic counter — never decremented on undo */
    int      next_note_id;              /* monotonic counter — never decremented on undo */

    /* Body region SVG — loaded once at startup, used for spatial association */
    SvgRegions svg_regions;

    /* ── Objective chart ─────────────────────────────────────────────────────── */
    ObjZone  *obj_zones[MAX_OBJ_ZONES];
    int       obj_zone_count;
    ObjZone  *obj_active_zone;      /* in-progress zone being drawn */
    ObjPoint  obj_points[MAX_OBJ_POINTS];
    int       obj_point_count;
    ObjTick   obj_ticks[MAX_OBJ_TICKS];
    int       obj_tick_count;
    ObjZoneType   obj_zone_type;    /* currently selected zone type */
    ObjPointType  obj_point_type;   /* currently selected point type */
    ObjTickType   obj_tick_type;    /* currently armed tick/cross type */
    ObjTickState  obj_tick_state;   /* currently armed tick/cross state */
    gboolean  obj_point_mode;       /* TRUE = point tool, FALSE = zone tool */
    gboolean  obj_tick_mode;        /* TRUE = tick/cross tool armed — takes
                                      * priority over obj_point_mode/zone tool;
                                      * one click places+commits immediately,
                                      * no drag/dialog, see canvas.c */
    gboolean  obj_pencil_mode;      /* TRUE = pencil tool selected in Objective
                                      * mode — see canvas.c's obj_pencil_active().
                                      * A dedicated flag, not just "app->symptom
                                      * == SYMPTOM_PENCIL", so a stale leftover
                                      * symptom value from Subjective mode can
                                      * never make Objective's zone/point/tick
                                      * tools misbehave as pencil drawing. */
    gboolean  obj_erase_mode;       /* TRUE = erase obj items */
    gboolean  obj_wide_mode;        /* wide-band zone drawing */
    /* Objective undo: 0=zone, 1=point, 2=tick */
    guint8    obj_undo_type_stack[64];
    int       obj_undo_type_top;
    /* Callback: show PPT value entry dialog; set by window.c */
    void (*show_ppt_entry_cb)(AppState *, GtkWidget *da, double screen_x, double screen_y,
                              int view, double bx, double by);

    /* Obj point drag state */
    int     obj_point_drag_idx;
    double  obj_point_drag_bx_off;
    double  obj_point_drag_by_off;

    /* Stroke cache version counter — incremented whenever committed strokes
     * or arrows change (stroke commit/undo/clear/load, arrow add/delete).
     * Each ColData compares its own cache_stroke_version against this to
     * decide whether to re-render the offscreen cache surface. */
    int     stroke_version;

    /* ── Report ─────────────────────────────────────────────────────────────── */
    ReportData  report;
};

GtkWidget  *canvas_new(AppState *app);
void        canvas_invalidate(AppState *app);
void        canvas_clear(AppState *app);
void        canvas_undo(AppState *app);
void        canvas_set_layout(AppState *app, LayoutMode mode);
void        canvas_cycle_right_slot(AppState *app, int slot);
void        canvas_reset_all_zoom(AppState *app);
const char *canvas_view_name(BodyView v);
const char *canvas_view_short_name(BodyView v);

void canvas_screen_to_body(AppState *app, double sx, double sy,
                            double *bx, double *by);

/* Render one body view into any Cairo context at the given pixel size. */
void canvas_render_view(AppState *app, cairo_t *cr, BodyView view,
                        double w, double h,
                        double zoom, double pan_x, double pan_y);

/* Pencil tool in Objective mode (2026-08-26) — see canvas.c's own comment
 * on obj_pencil_active(). Exposed here so window.c's sidebar button-state
 * update can check it too. */
gboolean obj_pencil_active(const AppState *app);
