#pragma once
#include <stdint.h>
#include <stddef.h>

/* ── Symptom types ──────────────────────────────────────────────────────── */
typedef enum {
    SYMPTOM_PAIN_CONSTANT    = 0,
    SYMPTOM_PAIN_INTERMITTENT,
    SYMPTOM_PARAESTHESIA,
    SYMPTOM_ANAESTHESIA,
    SYMPTOM_DEEP_ACHE,
    SYMPTOM_TICK,             /* green checkmark — symptom-free region */
    SYMPTOM_PENCIL,           /* black narrow line — freehand writing  */
    SYMPTOM_COUNT
} SymptomType;

typedef enum {
    FILL_SOLID = 0,       /* continuous pressure-sensitive line — constant pain */
    FILL_DASHED,          /* dashed pressure-sensitive line — intermittent pain  */
    FILL_DOTS_SPACED,     /* evenly-spaced filled dots — paraesthesia            */
    FILL_H_STROKES,       /* short horizontal strokes — anaesthesia              */
    FILL_XMARKS,          /* X marks — deep ache / other                        */
    FILL_TICK,            /* checkmarks — symptom-free stamp                     */
    FILL_PENCIL,          /* narrow solid line — freehand writing, ignores wide_mode */
} FillPattern;

/* ── Note annotations ───────────────────────────────────────────────────── */
#define MAX_NOTES 10

/* Quality indices — must match QUALITY_SHORT[] in window.c */
#define NOTE_QUALITY_COUNT 12

/* Reusable: decouples a text-label position from its anchor spot.
 * Embed in any annotation that needs a draggable label box.
 * When placed==0 the renderer applies a default offset from the spot. */
typedef struct {
    double lx, ly;   /* body-space label position */
    int    placed;   /* 0=use default offset from spot, 1=user-positioned */
} LabelAnchor;

typedef struct {
    int          view;
    double       bx, by;          /* body-space spot (where user tapped) */
    int          stable_id;       /* monotonic, never reused after undo */
    int          number;          /* sequential 1-10 */
    int          temporal;        /* 0=Constant, 1=Intermittent */
    int          depth;           /* 0=Superficial, 1=Deep */
    int          qualities[3];    /* up to 3 quality indices; see NOTE_QUALITY_COUNT */
    int          quality_count;   /* 1-3 */
    int          low_intensity;   /* 0-10, first selected */
    int          high_intensity;  /* 0-10, second selected */
    LabelAnchor  label;           /* draggable text-box position */
    char         text[256];       /* '\n'-delimited, 2 lines */
    char         voice_note[256]; /* verbatim voice transcript; empty if not used */
    char         chart_note_text[256]; /* clinician override typed in gpab's Assessment
                                         * "Brief (chart-facing)" box; empty if not used.
                                         * Written by gpab into _session.json (new as of
                                         * this field — see persistence.c's
                                         * persistence_reload_chart_note_overrides());
                                         * takes priority over voice_note in
                                         * regen_note_text() when present. */
} NoteAnnotation;

typedef struct {
    const char  *label;
    float        r, g, b;   /* 0–1 */
    FillPattern  pattern;
} SymptomDef;

extern const SymptomDef SYMPTOM_DEFS[SYMPTOM_COUNT];

/* ── A single drawn point ───────────────────────────────────────────────── */
typedef struct {
    float x, y;
    float pressure;          /* 0.0–1.0 */
} StrokePoint;

/* ── A complete stroke (finger-down → finger-up) ───────────────────────── */
typedef struct {
    StrokePoint  *pts;
    size_t        n_pts;
    size_t        cap;
    SymptomType   type;
    int           view;       /* which body view this belongs to */
    int           wide_mode;  /* 1 = wide band (2–7 bu), 0 = thin (0.8–4.5 bu) */
    double        draw_zoom;  /* zoom level when drawn by touch; 0.0 = stylus (no compensation) */
    int           id;         /* monotonic, never reused after undo */
} Stroke;

/* ── The undo stack ─────────────────────────────────────────────────────── */
typedef struct {
    Stroke  **strokes;
    int       n;
    int       cap;
} StrokeList;

Stroke     *stroke_new(SymptomType type, int view);
void        stroke_add_point(Stroke *s, float x, float y, float pressure);
void        stroke_free(Stroke *s);

StrokeList *stroke_list_new(void);
void        stroke_list_push(StrokeList *sl, Stroke *s);
Stroke     *stroke_list_pop(StrokeList *sl);   /* for undo */
void        stroke_list_clear(StrokeList *sl);
void        stroke_list_free(StrokeList *sl);
