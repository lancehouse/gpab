#ifndef PY_EMBED_H
#define PY_EMBED_H

typedef struct _AppState AppState;

/* merged-app spike (2026-08-25) — embeds gpab's Python assessment app
 * directly inside this process, replacing the separate-process
 * gapplication/D-Bus approach (see integration.c's own header comment for
 * why: Wayland blocks one process from forcing focus onto a DIFFERENT
 * process's window, so Ctrl+B's "raise gpab" never actually worked over
 * D-Bus — same-process window raising isn't subject to that restriction).
 *
 * Call order from main.c: py_embed_init() once, at startup, before
 * anything else touches Python. py_embed_open_session() once a session
 * file is known (mirrors integration_create_tui_window's old timing).
 * py_embed_present_gpab()/py_embed_close_gpab() from window.c's Ctrl+B key
 * handler and integration.c's close-coupling respectively, any number of
 * times. py_embed_shutdown() once, at the very end of main(), after
 * g_application_run() returns.
 */

void py_embed_init(AppState *app);
void py_embed_open_session(const char *session_file);
void py_embed_present_gpab(void);
void py_embed_close_gpab(void);
void py_embed_shutdown(void);

#endif
