#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

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
#define NOTE_QUALITY_COUNT 14

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
    int          temporal;        /* 0=Constant, 1=Intermittent, NOTE_UNSET */
    int          depth;           /* 0=Superficial, 1=Deep, NOTE_UNSET */
    int          qualities[3];    /* up to 3 quality indices; see NOTE_QUALITY_COUNT */
    int          quality_count;   /* 0-3 */
    int          low_intensity;   /* 0-10, or NOTE_UNSET */
    int          high_intensity;  /* 0-10 (== low for a single tap), or NOTE_UNSET */
    LabelAnchor  label;           /* draggable text-box position */
    char         text[400];       /* '\n'-delimited: header line + a body that
                                    * canvas.c's draw_note_screen() word-wraps
                                    * to several rows as needed (was a fixed
                                    * 2-line/256-byte layout; widened when the
                                    * quality codes and chart_note_text/
                                    * voice_note became full words instead of
                                    * abbreviations, see window.c/persistence.c) */
    char         voice_note[256]; /* verbatim voice transcript; empty if not used */
    char         chart_note_text[256]; /* clinician override typed in gpab's Assessment
                                         * "Brief (chart-facing)" box; empty if not used.
                                         * Written by gpab into _session.json (new as of
                                         * this field — see persistence.c's
                                         * persistence_reload_chart_note_overrides());
                                         * takes priority over voice_note in
                                         * regen_note_text() when present. */
} NoteAnnotation;

/* Note fields may be left unanswered (2026-10-27: the Note window became a
 * single any-order form that can be saved incomplete). Unset temporal/depth/
 * intensity are stored as NOTE_UNSET (-1) — written explicitly to JSON, so
 * the loader's absent-key default of 0 still only applies to legacy files.
 * Every formatter goes through these helpers so an unset field is simply
 * omitted rather than rendered as Constant/Superficial/0. */
#define NOTE_UNSET (-1)

static inline const char *note_temporal_name(int t)
{
    return t == 0 ? "Constant" : t == 1 ? "Intermittent" : NULL;
}

static inline const char *note_depth_name(int d)
{
    return d == 0 ? "Superficial" : d == 1 ? "Deep" : NULL;
}

/* "5/10" / "3-7/10", or "" when intensity wasn't answered. */
static inline const char *note_intensity_str(const NoteAnnotation *n,
                                             char *buf, size_t sz)
{
    if (n->low_intensity < 0 || n->high_intensity < 0) buf[0] = '\0';
    else if (n->low_intensity == n->high_intensity)
        snprintf(buf, sz, "%d/10", n->low_intensity);
    else
        snprintf(buf, sz, "%d-%d/10", n->low_intensity, n->high_intensity);
    return buf;
}

/* Appends piece to buf (sep-separated) if piece is non-NULL and non-empty. */
static inline void note_join(char *buf, size_t sz, const char *sep,
                             const char *piece)
{
    if (!piece || !piece[0]) return;
    size_t len = strlen(buf);
    snprintf(buf + len, sz > len ? sz - len : 0, "%s%s",
             len ? sep : "", piece);
}

/* Chart-pin header line: "(n)" + whichever of temporal/depth/intensity are set. */
static inline void note_format_header(const NoteAnnotation *n,
                                      char *buf, size_t sz)
{
    char fields[96] = {0}, ibuf[16];
    note_join(fields, sizeof(fields), " ", note_temporal_name(n->temporal));
    note_join(fields, sizeof(fields), " ", note_depth_name(n->depth));
    note_join(fields, sizeof(fields), " ", note_intensity_str(n, ibuf, sizeof(ibuf)));
    snprintf(buf, sz, "(%d)%s", n->number, fields);
}

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
    int           obj_pencil_color_type; /* -1 = default (SYMPTOM_PENCIL's own black); else
                                           * an ObjZoneType index (see obj_chart.h) whose
                                           * OBJ_ZONE_DEFS colour this Objective-mode pencil
                                           * mark uses instead — lets a clinician's freehand
                                           * note pick up the colour of whichever finding
                                           * type they had selected when they wrote it ("a
                                           * coloured pencil to write notes about findings").
                                           * Unused (-1) for every other stroke: Subjective
                                           * strokes/pencil marks have no such colour choice. */
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
