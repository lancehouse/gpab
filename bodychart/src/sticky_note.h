#pragma once
/* Floating "reminder to self" sticky note — a physio-wide (not per-patient)
 * preference the clinician sets once from the launch dialog and that then
 * persists across every session and every app restart until deliberately
 * changed there again. Read/written by both this app (this file) and gpab
 * (gpab_assessment/sticky_note.py, kept in sync by convention, matching the
 * same pattern already used for on-chart quality words vs mapping.py's
 * _QUALITY_TERMS — not a shared source, both sides just agree on the JSON
 * shape). See ~/.local/share/pab/sticky_note.json.
 *
 * Three independent "locations" (bodychart / subjective / objective), each
 * with its own show flag and its own remembered drag position — a
 * clinician might want it visible (and positioned differently) in the body
 * chart but not in Objective, for instance. This file only ever renders
 * the "bodychart" location; gpab's own sticky_note.py renders the other
 * two in its own window.
 */
#include <gtk/gtk.h>

typedef struct {
    char     text[256];
    gboolean show_bodychart, show_subjective, show_objective;
    double   bc_x,   bc_y;
    double   subj_x, subj_y;
    double   obj_x,  obj_y;
} StickyNoteData;

/* Reads ~/.local/share/pab/sticky_note.json, or sensible defaults (blank
 * text, all locations off, x=y=40) if it doesn't exist yet or fails to
 * parse. */
void sticky_note_load(StickyNoteData *out);

/* Read-modify-write: updates text + the three show flags, preserving
 * whatever x/y each location was last dragged to. Called from the launch
 * dialog's commit paths. */
gboolean sticky_note_save_text_and_flags(const char *text,
                                          gboolean show_bodychart,
                                          gboolean show_subjective,
                                          gboolean show_objective);

/* Read-modify-write: updates one location's x/y only, preserving text and
 * every show flag. `location` is "bodychart", "subjective", or
 * "objective". Called after a drag ends. */
gboolean sticky_note_save_position(const char *location, double x, double y);

/* The three launch-dialog widgets (label omitted — caller places its own
 * heading if wanted). Plain struct, not opaque: the caller (window.c's
 * LaunchData) embeds one and passes its address to both calls below. */
typedef struct {
    GtkWidget *text_entry;
    GtkWidget *cb_bodychart;
    GtkWidget *cb_subjective;
    GtkWidget *cb_objective;
} StickyNoteLaunchWidgets;

/* Appends the "Sticky note" label, text entry, and the three location
 * checkboxes to `outer` (a vertical GtkBox), pre-filled from disk. */
void sticky_note_build_launch_fields(GtkWidget *outer, StickyNoteLaunchWidgets *w);

/* Reads the current values out of the widgets built above and saves them.
 * Call once, right before the launch dialog is torn down (both
 * launch_commit_new and launch_commit_open). */
void sticky_note_commit_launch_fields(const StickyNoteLaunchWidgets *w);

/* Creates and adds the floating note to `overlay` for the "bodychart"
 * location, if (and only if) text is non-blank and that location's show
 * flag is set — silent no-op otherwise. Draggable (position persisted on
 * drag-end via sticky_note_save_position), with a corner close button that
 * hides it for this run only (in-memory; does not touch the persisted show
 * flag — see the launch dialog for the permanent on/off switch). */
void sticky_note_attach_bodychart(GtkOverlay *overlay);
