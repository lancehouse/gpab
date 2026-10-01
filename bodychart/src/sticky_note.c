#include "sticky_note.h"
#include <json-c/json.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <errno.h>

#define STICKY_NOTE_W     190
#define STICKY_NOTE_H     190
#define STICKY_MAX_FONT   26.0
#define STICKY_MIN_FONT    9.0
#define STICKY_MAX_LINES    8

/* ── Storage ──────────────────────────────────────────────────────────────── */

static void sticky_note_path(char *buf, size_t len)
{
    /* GPAB_STICKY_NOTE_PATH override exists purely for isolated testing —
     * this file is a real, live, cross-session clinician preference (not
     * per-patient data), so a test run against any disposable session
     * would otherwise still read/write the SAME shared global file a
     * concurrently-running real gpabd/bodychart session is using. Added
     * after exactly that nearly clobbered a real dragged position during
     * testing — see git history. Unset in normal use, so this changes
     * nothing for the real app. */
    const char *override = g_getenv("GPAB_STICKY_NOTE_PATH");
    if (override && override[0]) {
        snprintf(buf, len, "%s", override);
        return;
    }
    snprintf(buf, len, "%s/.local/share/pab/sticky_note.json", g_get_home_dir());
}

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

void sticky_note_load(StickyNoteData *out)
{
    memset(out, 0, sizeof(*out));
    out->bc_x = out->subj_x = out->obj_x = 40.0;
    out->bc_y = out->subj_y = out->obj_y = 40.0;

    char path[512];
    sticky_note_path(path, sizeof(path));
    json_object *root = json_object_from_file(path);
    if (!root) return;

    json_object *j;
    if (json_object_object_get_ex(root, "text", &j))
        g_strlcpy(out->text, json_object_get_string(j), sizeof(out->text));

    struct { const char *key; gboolean *show; double *x; double *y; } locs[3] = {
        {"bodychart",  &out->show_bodychart,  &out->bc_x,   &out->bc_y},
        {"subjective", &out->show_subjective, &out->subj_x, &out->subj_y},
        {"objective",  &out->show_objective,  &out->obj_x,  &out->obj_y},
    };
    for (int i = 0; i < 3; i++) {
        json_object *loc;
        if (!json_object_object_get_ex(root, locs[i].key, &loc)) continue;
        json_object *v;
        if (json_object_object_get_ex(loc, "show", &v))
            *locs[i].show = json_object_get_boolean(v);
        if (json_object_object_get_ex(loc, "x", &v))
            *locs[i].x = json_object_get_double(v);
        if (json_object_object_get_ex(loc, "y", &v))
            *locs[i].y = json_object_get_double(v);
    }
    json_object_put(root);
}

static gboolean sticky_note_write(const StickyNoteData *d)
{
    if (!ensure_share_dir()) return FALSE;
    char path[512];
    sticky_note_path(path, sizeof(path));

    json_object *root = json_object_new_object();
    json_object_object_add(root, "text", json_object_new_string(d->text));

    struct { const char *key; gboolean show; double x, y; } locs[3] = {
        {"bodychart",  d->show_bodychart,  d->bc_x,   d->bc_y},
        {"subjective", d->show_subjective, d->subj_x, d->subj_y},
        {"objective",  d->show_objective,  d->obj_x,  d->obj_y},
    };
    for (int i = 0; i < 3; i++) {
        json_object *loc = json_object_new_object();
        json_object_object_add(loc, "show", json_object_new_boolean(locs[i].show));
        json_object_object_add(loc, "x", json_object_new_double(locs[i].x));
        json_object_object_add(loc, "y", json_object_new_double(locs[i].y));
        json_object_object_add(root, locs[i].key, loc);
    }

    char tmp[540];
    snprintf(tmp, sizeof(tmp), "%s.tmp", path);
    gboolean ok = (json_object_to_file(tmp, root) == 0);
    if (ok) ok = (rename(tmp, path) == 0);
    json_object_put(root);
    return ok;
}

gboolean sticky_note_save_text_and_flags(const char *text,
                                          gboolean show_bodychart,
                                          gboolean show_subjective,
                                          gboolean show_objective)
{
    StickyNoteData d;
    sticky_note_load(&d);   /* preserve existing x/y for every location */
    g_strlcpy(d.text, text ? text : "", sizeof(d.text));
    d.show_bodychart  = show_bodychart;
    d.show_subjective = show_subjective;
    d.show_objective  = show_objective;
    return sticky_note_write(&d);
}

gboolean sticky_note_save_position(const char *location, double x, double y)
{
    StickyNoteData d;
    sticky_note_load(&d);
    if (strcmp(location, "bodychart") == 0)       { d.bc_x   = x; d.bc_y   = y; }
    else if (strcmp(location, "subjective") == 0) { d.subj_x = x; d.subj_y = y; }
    else if (strcmp(location, "objective") == 0)  { d.obj_x  = x; d.obj_y  = y; }
    else return FALSE;
    return sticky_note_write(&d);
}

/* ── Launch dialog fields ─────────────────────────────────────────────────── */

void sticky_note_build_launch_fields(GtkWidget *outer, StickyNoteLaunchWidgets *w)
{
    StickyNoteData d;
    sticky_note_load(&d);

    GtkWidget *lbl = gtk_label_new("Sticky note (reminder to self)");
    gtk_widget_set_name(lbl, "launch-label");
    gtk_label_set_xalign(GTK_LABEL(lbl), 0.0);
    gtk_box_append(GTK_BOX(outer), lbl);

    w->text_entry = gtk_entry_new();
    gtk_widget_set_name(w->text_entry, "launch-entry");
    gtk_entry_set_max_length(GTK_ENTRY(w->text_entry), 200);
    gtk_entry_set_placeholder_text(GTK_ENTRY(w->text_entry),
                                   "e.g. Same ; Better ; Worse  (blank = off)");
    gtk_editable_set_text(GTK_EDITABLE(w->text_entry), d.text);
    gtk_widget_set_hexpand(w->text_entry, TRUE);
    gtk_box_append(GTK_BOX(outer), w->text_entry);

    GtkWidget *cb_row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 10);
    gtk_widget_set_margin_top(cb_row, 2);
    w->cb_bodychart  = gtk_check_button_new_with_label("Body Chart");
    w->cb_subjective = gtk_check_button_new_with_label("Subjective");
    w->cb_objective  = gtk_check_button_new_with_label("Objective");
    gtk_check_button_set_active(GTK_CHECK_BUTTON(w->cb_bodychart),  d.show_bodychart);
    gtk_check_button_set_active(GTK_CHECK_BUTTON(w->cb_subjective), d.show_subjective);
    gtk_check_button_set_active(GTK_CHECK_BUTTON(w->cb_objective),  d.show_objective);
    gtk_widget_set_name(w->cb_bodychart,  "launch-checkbox");
    gtk_widget_set_name(w->cb_subjective, "launch-checkbox");
    gtk_widget_set_name(w->cb_objective,  "launch-checkbox");
    gtk_box_append(GTK_BOX(cb_row), w->cb_bodychart);
    gtk_box_append(GTK_BOX(cb_row), w->cb_subjective);
    gtk_box_append(GTK_BOX(cb_row), w->cb_objective);
    gtk_box_append(GTK_BOX(outer), cb_row);
}

void sticky_note_commit_launch_fields(const StickyNoteLaunchWidgets *w)
{
    const char *text = gtk_editable_get_text(GTK_EDITABLE(w->text_entry));
    sticky_note_save_text_and_flags(
        text,
        gtk_check_button_get_active(GTK_CHECK_BUTTON(w->cb_bodychart)),
        gtk_check_button_get_active(GTK_CHECK_BUTTON(w->cb_subjective)),
        gtk_check_button_get_active(GTK_CHECK_BUTTON(w->cb_objective)));
}

/* ── Floating widget ──────────────────────────────────────────────────────── */

typedef struct {
    GtkOverlay *overlay;
    GtkWidget  *box;
    double      x, y;                 /* current top-left; persisted on drag-end */
    double      grab_dx, grab_dy;     /* press point, offset from box's own top-left */
    char        location[16];
} StickyNoteWidgetState;

/* Greedy word-wrap at the given font size; returns FALSE if it doesn't fit
 * (a line too wide, too many lines, or total height over max_h) so the
 * caller can retry at a smaller size. Same technique as canvas.c's
 * wrap_note_body() for the on-chart note labels, reimplemented here rather
 * than shared — different box/measurement shape (auto-*shrinking* to fit a
 * fixed box, not wrapping to a fixed number of rows of unknown width). */
static gboolean sticky_text_fits(cairo_t *cr, const char *text, double font_size,
                                  double max_w, double max_h,
                                  char lines_out[STICKY_MAX_LINES][160], int *n_lines_out)
{
    cairo_set_font_size(cr, font_size);

    char buf[256];
    g_strlcpy(buf, text, sizeof(buf));

    int n = 0;
    char cur[160] = {0};
    char *saveptr = NULL;
    char *word = strtok_r(buf, " ", &saveptr);

    while (word) {
        char trial[160];
        if (cur[0])
            snprintf(trial, sizeof(trial), "%s %s", cur, word);
        else
            snprintf(trial, sizeof(trial), "%s", word);

        cairo_text_extents_t te;
        cairo_text_extents(cr, trial, &te);

        if ((te.width - te.x_bearing) <= max_w || !cur[0]) {
            g_strlcpy(cur, trial, sizeof(cur));
        } else {
            if (n >= STICKY_MAX_LINES) return FALSE;
            g_strlcpy(lines_out[n++], cur, 160);
            g_strlcpy(cur, word, sizeof(cur));
            cairo_text_extents(cr, cur, &te);
            if ((te.width - te.x_bearing) > max_w) return FALSE;  /* one word too wide even alone */
        }
        word = strtok_r(NULL, " ", &saveptr);
    }
    if (cur[0]) {
        if (n >= STICKY_MAX_LINES) return FALSE;
        g_strlcpy(lines_out[n++], cur, 160);
    }

    cairo_font_extents_t fe;
    cairo_font_extents(cr, &fe);
    if (fe.height * n > max_h) return FALSE;

    *n_lines_out = n;
    return TRUE;
}

static void draw_sticky_text(GtkDrawingArea *area, cairo_t *cr,
                              int width, int height, gpointer data)
{
    (void)area;
    const char *text = data;
    if (!text || !text[0]) return;

    cairo_select_font_face(cr, "Sans", CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD);

    double pad = 10.0;
    double max_w = width  - 2.0 * pad;
    double max_h = height - 2.0 * pad;

    char lines[STICKY_MAX_LINES][160];
    int n_lines = 0;
    double font_size = STICKY_MAX_FONT;
    gboolean fitted = FALSE;
    for (; font_size >= STICKY_MIN_FONT; font_size -= 1.0) {
        if (sticky_text_fits(cr, text, font_size, max_w, max_h, lines, &n_lines)) {
            fitted = TRUE;
            break;
        }
    }
    if (!fitted) {
        /* Floor reached and it still doesn't fit (a genuinely long note) —
         * best-effort render at the floor size anyway rather than showing
         * nothing; realistically this app is for short reminder phrases,
         * so this is a rare, acceptable edge rather than something worth
         * adding ellipsis-truncation for. */
        font_size = STICKY_MIN_FONT;
        sticky_text_fits(cr, text, font_size, max_w, max_h, lines, &n_lines);
        if (n_lines == 0) return;
    }

    cairo_set_font_size(cr, font_size);
    cairo_font_extents_t fe;
    cairo_font_extents(cr, &fe);
    double total_h = fe.height * n_lines;
    double start_y = (height - total_h) / 2.0 + fe.ascent;

    cairo_set_source_rgba(cr, 0.30, 0.24, 0.04, 1.0);  /* dark ink on yellow */
    for (int i = 0; i < n_lines; i++) {
        cairo_text_extents_t te;
        cairo_text_extents(cr, lines[i], &te);
        double x = (width - (te.width - te.x_bearing)) / 2.0;
        cairo_move_to(cr, x, start_y + fe.height * i);
        cairo_show_text(cr, lines[i]);
    }
}

static gboolean on_sticky_get_child_position(GtkOverlay *overlay, GtkWidget *widget,
                                              GdkRectangle *alloc, gpointer user_data)
{
    (void)overlay;
    StickyNoteWidgetState *st = user_data;
    if (widget != st->box) return FALSE;
    alloc->x = (int)st->x;
    alloc->y = (int)st->y;
    alloc->width = STICKY_NOTE_W;
    alloc->height = STICKY_NOTE_H;
    return TRUE;
}

static void on_sticky_drag_begin(GtkGestureDrag *g, double sx, double sy, gpointer data)
{
    (void)g;
    StickyNoteWidgetState *st = data;
    /* sx,sy: press point, offset from box's own top-left, in box-local
     * coordinates — stays valid as a "grab offset" for the rest of the
     * gesture regardless of where box later moves to (unlike GTK's own
     * cumulative dx/dy, see drag-update below). */
    st->grab_dx = sx;
    st->grab_dy = sy;
}

static void on_sticky_drag_update(GtkGestureDrag *g, double dx, double dy, gpointer data)
{
    /* GTK's own cumulative dx/dy (relative to drag-begin, in box's LOCAL
     * frame) is unusable here: box is the same widget being repositioned
     * every update, via get-child-position below. GTK re-derives each
     * event's local coordinates from box's CURRENT (already-partway-moved)
     * allocation, so the reported delta under-counts real pointer motion
     * every frame — converges to roughly half the actual drag distance
     * with visible jitter as it oscillates (reported after both the first,
     * naive version of this and a since-reverted "stationary GtkFixed
     * stage" attempt — that one fixed the jitter but broke input to the
     * note entirely, because can_target(FALSE) on a container in GTK4
     * blocks picking for its whole subtree, not just the container's own
     * empty area — so it's back to a direct GtkOverlay child, correct
     * click-through by construction since box only ever occupies its own
     * small rect and nothing else claims the rest of the overlay).
     *
     * Fix: recompute box's ABSOLUTE position fresh on every event, via a
     * true geometric transform (gtk_widget_compute_point, not a cached
     * delta), so there is nothing to accumulate and nothing that can drift. */
    (void)dx; (void)dy;
    StickyNoteWidgetState *st = data;

    double cur_x, cur_y;
    if (!gtk_gesture_get_point(GTK_GESTURE(g), NULL, &cur_x, &cur_y))
        return;

    graphene_point_t local_pt = GRAPHENE_POINT_INIT((float)cur_x, (float)cur_y);
    graphene_point_t overlay_pt;
    if (!gtk_widget_compute_point(st->box, GTK_WIDGET(st->overlay), &local_pt, &overlay_pt))
        return;

    double nx = overlay_pt.x - st->grab_dx;
    double ny = overlay_pt.y - st->grab_dy;

    int win_w = gtk_widget_get_width(GTK_WIDGET(st->overlay));
    int win_h = gtk_widget_get_height(GTK_WIDGET(st->overlay));
    if (win_w > STICKY_NOTE_W) nx = CLAMP(nx, 0, win_w - STICKY_NOTE_W);
    if (win_h > STICKY_NOTE_H) ny = CLAMP(ny, 0, win_h - STICKY_NOTE_H);

    st->x = nx;
    st->y = ny;
    gtk_widget_queue_allocate(GTK_WIDGET(st->overlay));
}

static void on_sticky_drag_end(GtkGestureDrag *g, double dx, double dy, gpointer data)
{
    (void)g; (void)dx; (void)dy;
    StickyNoteWidgetState *st = data;
    sticky_note_save_position(st->location, st->x, st->y);
}

/* Corner "x" — hides the note for this run only (in-memory). Does NOT touch
 * the persisted show flag, so it comes back on the next launch — see
 * sticky_note.h. That's deliberate: this note is meant to keep nagging
 * until the clinician goes and turns it off from the launch dialog. */
static void on_sticky_close_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    StickyNoteWidgetState *st = data;
    gtk_widget_set_visible(st->box, FALSE);
}

void sticky_note_attach_bodychart(GtkOverlay *overlay)
{
    StickyNoteData d;
    sticky_note_load(&d);
    if (!d.text[0] || !d.show_bodychart) return;

    StickyNoteWidgetState *st = g_new0(StickyNoteWidgetState, 1);
    st->overlay = overlay;
    st->x = d.bc_x;
    st->y = d.bc_y;
    g_strlcpy(st->location, "bodychart", sizeof(st->location));

    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_add_css_class(box, "sticky-note");
    gtk_widget_set_size_request(box, STICKY_NOTE_W, STICKY_NOTE_H);
    gtk_widget_set_halign(box, GTK_ALIGN_START);
    gtk_widget_set_valign(box, GTK_ALIGN_START);
    st->box = box;

    GtkWidget *top = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    GtkWidget *close_btn = gtk_button_new_with_label("\xc3\x97");  /* × */
    gtk_widget_add_css_class(close_btn, "sticky-note-close");
    gtk_widget_set_halign(close_btn, GTK_ALIGN_END);
    gtk_widget_set_hexpand(close_btn, TRUE);
    g_signal_connect(close_btn, "clicked", G_CALLBACK(on_sticky_close_clicked), st);
    gtk_box_append(GTK_BOX(top), close_btn);
    gtk_box_append(GTK_BOX(box), top);

    GtkWidget *area = gtk_drawing_area_new();
    gtk_widget_set_hexpand(area, TRUE);
    gtk_widget_set_vexpand(area, TRUE);
    gtk_drawing_area_set_draw_func(GTK_DRAWING_AREA(area), draw_sticky_text,
                                    g_strdup(d.text), g_free);
    gtk_box_append(GTK_BOX(box), area);

    GtkGesture *drag = gtk_gesture_drag_new();
    /* GtkGestureSingle handles mouse AND touch by default (touch_only only
     * needs setting when mouse should be EXCLUDED, never for touch to be
     * included) — this app runs on a touchscreen laptop, so made explicit
     * here rather than leaving it an unstated default. */
    gtk_gesture_single_set_touch_only(GTK_GESTURE_SINGLE(drag), FALSE);
    g_signal_connect(drag, "drag-begin",  G_CALLBACK(on_sticky_drag_begin),  st);
    g_signal_connect(drag, "drag-update", G_CALLBACK(on_sticky_drag_update), st);
    g_signal_connect(drag, "drag-end",    G_CALLBACK(on_sticky_drag_end),    st);
    gtk_widget_add_controller(box, GTK_EVENT_CONTROLLER(drag));

    /* box is a direct GtkOverlay child, sized/positioned only to its own
     * 190x190 rect via get-child-position — nothing else in the overlay
     * claims the rest of that plane, so clicks outside the note fall
     * through to the canvas/sidebar beneath it with no extra plumbing
     * needed (no can_target tricks — see drag-update's comment for why an
     * earlier attempt at those broke input to the note entirely). */
    g_signal_connect(overlay, "get-child-position",
                     G_CALLBACK(on_sticky_get_child_position), st);
    gtk_overlay_add_overlay(overlay, box);
}
