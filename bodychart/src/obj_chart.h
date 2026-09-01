#pragma once
#include <cairo/cairo.h>
#include "stroke.h"   /* LabelAnchor */

typedef struct _AppState AppState;   /* full definition in canvas.h */

#define MAX_OBJ_ZONES    60
#define MAX_OBJ_ZONE_PTS 512
#define MAX_OBJ_POINTS   60
#define MAX_OBJ_TICKS    60

/* Zone type values are load-bearing — they're the "type" int already saved
 * in every real patient session's _session.json. Existing indices (0–7)
 * are NEVER renumbered or reassigned to a different meaning, even when
 * reorganised into Sensory/CRPS sidebar groups (2026-08-26) — only display
 * name/grouping changed for those; a session saved before this change must
 * still load identically. New types (2026-08-26) are appended at the end
 * (8+) rather than interleaved, so old files can never silently reinterpret
 * an existing zone as something else. Sidebar display order/grouping
 * (Sensory vs CRPS) is a UI concern, kept separate in window.c — it does
 * NOT need to match this enum's declaration order. */
typedef enum {
    OBJ_ZONE_ALLODYNIA    = 0,   /* yellow    #F5D100 — now "Static Allodynia" */
    OBJ_ZONE_HYPERALGESIA,       /* orange    #F07820 — pin-prick hyperalgesia */
    OBJ_ZONE_ERYTHEMA,           /* pink      #E8607A — CRPS vasomotor */
    OBJ_ZONE_TEMP_COOL,          /* blue      #40A0E0 — CRPS vasomotor (cool skin) */
    OBJ_ZONE_TEMP_WARM,          /* deep-red  #C03030 — CRPS vasomotor (warm skin) */
    OBJ_ZONE_NUMB,               /* cool grey #B0B0C0 — now "Reduced Sensation" */
    OBJ_ZONE_OEDEMA,             /* purple    #9950C0 — CRPS */
    OBJ_ZONE_TROPHIC,            /* brown     #B37030 — CRPS */
    /* ── Appended 2026-08-26 (Sensory-tab realignment) — see CONVERSION_PLAN.md ── */
    OBJ_ZONE_ALLODYNIA_DYNAMIC,  /* distinct from static — different finding, own zone */
    OBJ_ZONE_HEAT_HYPERALGESIA,  /* red family — thermal PAIN response, distinct shade
                                   * from OBJ_ZONE_TEMP_WARM's vasomotor skin-warmth */
    OBJ_ZONE_COLD_HYPERALGESIA,  /* blue family — thermal PAIN response, distinct shade
                                   * from OBJ_ZONE_TEMP_COOL's vasomotor skin-coolness */
    OBJ_ZONE_BODY_PERCEPTION,    /* CRPS — distorted body perception / neglect-like */
    OBJ_ZONE_COUNT
} ObjZoneType;

typedef enum {
    OBJ_POINT_PPT = 0,           /* Pressure Pain Threshold, kg/cm² */
    OBJ_POINT_TEMPORAL_SUM,      /* Temporal summation score, 0–10 */
    OBJ_POINT_MONOFILAMENT,      /* Semmes-Weinstein monofilament, g */
    OBJ_POINT_TWO_PD,            /* Two-point discrimination, mm */
    OBJ_POINT_COUNT
} ObjPointType;

/* Tick/cross markers (new 2026-08-26) — a third Objective marker kind
 * alongside zones (drawn areas) and points (numeric value + label). These
 * are simple pass/fail findings tested at a specific site, not an area and
 * not a measured value: placed with ONE click via a dedicated tick/cross
 * button pair per type (no intermediate dialog, unlike OBJ_POINT_*'s
 * value-entry flow — direct user request: "I just want to select the
 * purple tick and put it in"). Colour is purely a per-type identifier, not
 * a pass/fail semantic (explicitly NOT red=abnormal/green=normal here) —
 * both states of one type share the same colour; only the glyph differs. */
typedef enum {
    OBJ_TICK_VIBRATION = 0,
    OBJ_TICK_PROPRIOCEPTION,
    OBJ_TICK_NERVE_TRUNK_PALPATION,
    OBJ_TICK_TYPE_COUNT
} ObjTickType;

typedef enum {
    OBJ_TICK_STATE_TICK  = 0,    /* ✓ */
    OBJ_TICK_STATE_CROSS = 1,    /* ✗ */
} ObjTickState;

typedef struct {
    float       *bx, *by;        /* body-space path (dynamic array) */
    int          n, cap;
    int          view;
    ObjZoneType  type;
} ObjZone;

typedef struct {
    double       bx, by;         /* body-space spot (clinical measurement site) */
    double       value;
    int          view;
    ObjPointType type;
    char         label[20];      /* e.g. "4.2" for PPT */
    LabelAnchor  anchor;         /* draggable text-box position */
} ObjPoint;

typedef struct {
    double        bx, by;        /* body-space spot */
    int           view;
    ObjTickType   type;
    ObjTickState  state;
} ObjTick;

typedef struct {
    float        r, g, b;
    const char  *name;
    const char  *short_name;     /* for sidebar button */
} ObjZoneDef;

typedef struct {
    float        r, g, b;       /* dot / connector colour */
    const char  *name;
} ObjPointDef;

typedef struct {
    float        r, g, b;       /* marker colour — same for tick and cross */
    const char  *name;
} ObjTickDef;

extern const ObjZoneDef  OBJ_ZONE_DEFS[OBJ_ZONE_COUNT];
extern const ObjPointDef OBJ_POINT_DEFS[OBJ_POINT_COUNT];
extern const ObjTickDef  OBJ_TICK_DEFS[OBJ_TICK_TYPE_COUNT];

ObjZone *obj_zone_new(ObjZoneType type, int view);
void     obj_zone_add_pt(ObjZone *z, float bx, float by);
void     obj_zone_free(ObjZone *z);

/* Resolve label position — also used by canvas.c for hit-testing */
void obj_label_resolve(const ObjPoint *p, double *out_lbx, double *out_lby);

/* Render objective layer — called from canvas.c */
void obj_chart_render_body(AppState *app, cairo_t *cr, int view);
void obj_chart_render_screen(AppState *app, cairo_t *cr, int view,
                              double s, double cx, double cy);
void obj_chart_render_active_body(AppState *app, cairo_t *cr, int view);
void obj_chart_render_ticks_body(AppState *app, cairo_t *cr, int view);
