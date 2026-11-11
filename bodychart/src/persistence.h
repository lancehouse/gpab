#pragma once
#include "canvas.h"

#define PERSIST_RECENT_MAX 20

typedef struct {
    char   patient_id[32];
    char   session_label[64];
    char   session_name[80];
    char   path[512];       /* full path to _session.json */
    time_t modified;
} PersistRecent;

/* Populate session_name / session_dir / session_file from patient_id + label.
 * Uses current wall-clock time for the timestamp component.  Call this when
 * creating a brand-new session; never call it when loading an existing one. */
void     persistence_build_paths(AppState *app, const char *patient_id,
                                  const char *session_label);

/* Save all AppState data to app->session_file (JSON).
 * Creates session_dir if it does not exist.  Returns FALSE on I/O error. */
gboolean persistence_save(AppState *app);

/* Rebuild a note's on-chart text (header + body) from its fields. Body
 * precedence: chart_note_text (gpab Brief) > voice_note > quality words. */
void     persistence_regen_note_text(NoteAnnotation *n);

/* Load AppState data from a session JSON file.
 * Clears all existing strokes/notes/arrows/links before loading.
 * Also sets app->session_file / session_dir / session_name from the path.
 * Returns FALSE if the file cannot be parsed. */
gboolean persistence_load(AppState *app, const char *path);

/* Scan ~/PhysioChart/ for recent session files.  Fills `out` (caller-allocated
 * array of at least `max` entries), sorted newest-first by modification time.
 * Returns actual count found (≤ max). */
int      persistence_scan_recent(PersistRecent *out, int max);

/* Write simplified session_current.json to ~/.local/share/physio-bodychart/
 * for integration with physio-assessment. Returns FALSE on I/O error. */
gboolean persistence_write_session_current(AppState *app);

/* Start watching the session JSON file for external changes (from physio-assessment).
 * Only reloads the assessment block, preserving in-progress drawing. */
void     persistence_monitor_start(AppState *app);

/* Stop watching the session JSON file and release the monitor. Safe to call
 * even if no monitor is active. */
void     persistence_monitor_stop(AppState *app);

/* Reload only the assessment block from the session JSON file, without
 * touching subjective/objective drawing data. */
void     persistence_reload_assessment(AppState *app);
