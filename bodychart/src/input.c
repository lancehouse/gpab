#include "input.h"
#include "canvas.h"
#include "session.h"
#include "window.h"
#include "stroke.h"
#include "overlays.h"
#include <math.h>
#include <string.h>

/* ── Hotkey name table (config file keys) ────────────────────────────────── */
const char *const HOTKEY_NAMES[HK_COUNT] = {
    [HK_SYMPTOM_CONSTANT]     = "hotkey_symptom_constant",
    [HK_SYMPTOM_INTERMITTENT] = "hotkey_symptom_intermittent",
    [HK_SYMPTOM_PARAESTHESIA] = "hotkey_symptom_paraesthesia",
    [HK_SYMPTOM_ANAESTHESIA]  = "hotkey_symptom_anaesthesia",
    [HK_SYMPTOM_DEEP_ACHE]    = "hotkey_symptom_para",
    [HK_SYMPTOM_TICK]         = "hotkey_symptom_tick",
    [HK_TOOL_DRAW]            = "hotkey_tool_draw",
    [HK_TOOL_ERASE]           = "hotkey_tool_erase",
    [HK_TOOL_NOTE]            = "hotkey_tool_note",
    [HK_TOOL_LINK]            = "hotkey_tool_link",
    [HK_WIDE_MODE]            = "hotkey_wide_mode",
    [HK_UNDO]                 = "hotkey_undo",
    [HK_CLEAR]                = "hotkey_clear",
    [HK_OVERLAY_DERM]         = "hotkey_overlay_derm",
    [HK_OVERLAY_PERIPH]       = "hotkey_overlay_periph",
    [HK_OVERLAY_SOMATIC]      = "hotkey_overlay_somatic",
    [HK_OVERLAY_TOGGLE]       = "hotkey_overlay_toggle",
    [HK_OVERLAY_PREV]         = "hotkey_overlay_prev",
    [HK_OVERLAY_NEXT]         = "hotkey_overlay_next",
    [HK_VIEW_QUAD]            = "hotkey_view_quad",
    [HK_VIEW_ANTERIOR]        = "hotkey_view_anterior",
    [HK_VIEW_POSTERIOR]       = "hotkey_view_posterior",
    [HK_VIEW_LATERAL_L]       = "hotkey_view_lateral_l",
    [HK_VIEW_LATERAL_R]       = "hotkey_view_lateral_r",
    [HK_ZOOM_RESET]           = "hotkey_zoom_reset",
    [HK_SAVE_SVG]             = "hotkey_save_svg",
    [HK_SAVE_PNG]             = "hotkey_save_png",
    [HK_SAVE_PDF]             = "hotkey_save_pdf",
};

/* ── Default key bindings ────────────────────────────────────────────────── */
static const struct { HotkeyAction action; guint val; GdkModifierType mod; }
DEFAULTS[] = {
    { HK_SYMPTOM_CONSTANT,     GDK_KEY_1,             0 },
    { HK_SYMPTOM_INTERMITTENT, GDK_KEY_2,             0 },
    { HK_SYMPTOM_PARAESTHESIA, GDK_KEY_3,             0 },
    { HK_SYMPTOM_ANAESTHESIA,  GDK_KEY_4,             0 },
    { HK_SYMPTOM_DEEP_ACHE,    GDK_KEY_5,             0 },
    { HK_SYMPTOM_TICK,         GDK_KEY_6,             0 },
    { HK_TOOL_DRAW,            GDK_KEY_d,             0 },
    { HK_TOOL_ERASE,           GDK_KEY_e,             0 },
    { HK_TOOL_NOTE,            GDK_KEY_n,             0 },
    { HK_TOOL_LINK,            GDK_KEY_l,             0 },
    { HK_WIDE_MODE,            GDK_KEY_b,             0 },
    { HK_UNDO,                 GDK_KEY_z,             GDK_CONTROL_MASK },
    { HK_CLEAR,                GDK_KEY_Delete,        GDK_CONTROL_MASK },
    { HK_OVERLAY_DERM,         GDK_KEY_F5,            0 },
    { HK_OVERLAY_PERIPH,       GDK_KEY_F6,            0 },
    { HK_OVERLAY_SOMATIC,      GDK_KEY_F7,            0 },
    { HK_OVERLAY_TOGGLE,       GDK_KEY_o,             0 },
    { HK_OVERLAY_PREV,         GDK_KEY_bracketleft,   0 },
    { HK_OVERLAY_NEXT,         GDK_KEY_bracketright,  0 },
    { HK_VIEW_QUAD,            GDK_KEY_F9,            0 },
    { HK_VIEW_ANTERIOR,        GDK_KEY_F1,            0 },
    { HK_VIEW_POSTERIOR,       GDK_KEY_F2,            0 },
    { HK_VIEW_LATERAL_L,       GDK_KEY_F3,            0 },
    { HK_VIEW_LATERAL_R,       GDK_KEY_F4,            0 },
    { HK_ZOOM_RESET,           GDK_KEY_Home,          0 },
    { HK_SAVE_SVG,             GDK_KEY_s,             GDK_CONTROL_MASK },
    { HK_SAVE_PNG,             GDK_KEY_s,             GDK_CONTROL_MASK | GDK_SHIFT_MASK },
    { HK_SAVE_PDF,             GDK_KEY_p,             GDK_CONTROL_MASK },
};

void input_hotkeys_init(AppState *app)
{
    for (int i = 0; i < (int)(sizeof(DEFAULTS)/sizeof(DEFAULTS[0])); i++) {
        app->hotkey_val[DEFAULTS[i].action] = DEFAULTS[i].val;
        app->hotkey_mod[DEFAULTS[i].action] = DEFAULTS[i].mod;
    }
}

/* Match incoming key event against the hotkey table.
 * Both sides are lowercased so 'D' and 'd' match the same binding. */
static HotkeyAction find_action(AppState *app, guint keyval, GdkModifierType mods)
{
    GdkModifierType m = mods & (GDK_CONTROL_MASK | GDK_SHIFT_MASK | GDK_ALT_MASK);
    guint kl = gdk_keyval_to_lower(keyval);
    for (int i = 0; i < HK_COUNT; i++) {
        if (app->hotkey_val[i] == 0) continue;
        if (gdk_keyval_to_lower(app->hotkey_val[i]) == kl &&
            app->hotkey_mod[i] == m)
            return (HotkeyAction)i;
    }
    return HK_COUNT;
}

/* ── Drawing input ───────────────────────────────────────────────────────── */
void input_begin(AppState *app, double x, double y, double pressure)
{
    switch (app->tool) {
        case TOOL_DRAW: {
            app->active_stroke            = stroke_new(app->symptom, app->current_view);
            app->active_stroke->wide_mode = app->pen_wide_mode;
            double p_eff = pow(fmax(pressure, 0.01), app->pen_gamma);
            stroke_add_point(app->active_stroke, (float)x, (float)y, (float)p_eff);
            break;
        }
        case TOOL_ERASE:
            for (int i = app->strokes->n - 1; i >= 0; i--) {
                Stroke *s = app->strokes->strokes[i];
                if ((int)s->view != (int)app->current_view) continue;
                for (size_t j = 0; j < s->n_pts; j++) {
                    double dx = s->pts[j].x - x;
                    double dy = s->pts[j].y - y;
                    if (sqrt(dx*dx + dy*dy) < 8.0) {
                        stroke_free(s);
                        for (int k = i; k < app->strokes->n - 1; k++)
                            app->strokes->strokes[k] = app->strokes->strokes[k+1];
                        app->strokes->n--;
                        app->stroke_version++;  /* stroke erased — invalidate cache */
                        return;
                    }
                }
            }
            break;
        case TOOL_LINK:
            if (!app->link_first_set) {
                app->link_x1 = x;
                app->link_y1 = y;
                app->link_first_set = TRUE;
            } else {
                app->link_first_set = FALSE;
            }
            break;
        case TOOL_NOTE:
        case TOOL_ARROW:
            break;
    }
}

void input_motion(AppState *app, double x, double y, double pressure)
{
    if (app->tool == TOOL_DRAW && app->active_stroke) {
        if (app->active_stroke->type == SYMPTOM_TICK) return;  /* single stamp per tap */
        double p_eff = pow(fmax(pressure, 0.01), app->pen_gamma);
        stroke_add_point(app->active_stroke, (float)x, (float)y, (float)p_eff);
    }
}

void input_end(AppState *app)
{
    if (app->tool == TOOL_DRAW && app->active_stroke) {
        gboolean keep = app->active_stroke->n_pts > 1 ||
                        (app->active_stroke->type == SYMPTOM_TICK &&
                         app->active_stroke->n_pts >= 1);
        if (keep) {
            app->active_stroke->id = app->next_stroke_id++;
            stroke_list_push(app->strokes, app->active_stroke);
            /* Pencil tool in Objective mode (2026-08-26, see obj_pencil_active()
             * in canvas.c) reuses this exact same Stroke/undo mechanism — but
             * canvas_undo() dispatches on current_mode BEFORE ever looking at
             * app->undo_type_stack, so an entry pushed there while in
             * Objective mode would sit unreachable until a Sx-mode undo
             * happened to fall through to it. Record it on Objective's own
             * obj_undo_type_stack instead (type 3 = pencil stroke), so the
             * Obj sidebar's own Undo button can reach it immediately. */
            if (app->current_mode == APP_MODE_OBJECTIVE) {
                if (app->obj_undo_type_top < 64)
                    app->obj_undo_type_stack[app->obj_undo_type_top++] = 3;
            } else if (app->undo_type_top < 64) {
                app->undo_type_stack[app->undo_type_top++] = 0;
            }
            app->stroke_version++;  /* new committed stroke — invalidate cache */
        } else {
            stroke_free(app->active_stroke);
        }
        app->active_stroke = NULL;
    }
}

void input_cancel(AppState *app)
{
    if (app->active_stroke) {
        stroke_free(app->active_stroke);
        app->active_stroke = NULL;
    }
    app->link_first_set = FALSE;
    app->arrow_drawing  = FALSE;
}

/* ── Keyboard handler ────────────────────────────────────────────────────── */
gboolean input_key_pressed(AppState *app, guint keyval, GdkModifierType mods)
{
    HotkeyAction a = find_action(app, keyval, mods);
    if (a == HK_COUNT) return FALSE;

    switch (a) {
        /* Symptom selection — also switches to draw tool */
        case HK_SYMPTOM_CONSTANT:
            app->symptom = SYMPTOM_PAIN_CONSTANT;     app->tool = TOOL_DRAW; break;
        case HK_SYMPTOM_INTERMITTENT:
            app->symptom = SYMPTOM_PAIN_INTERMITTENT; app->tool = TOOL_DRAW; break;
        case HK_SYMPTOM_PARAESTHESIA:
            app->symptom = SYMPTOM_PARAESTHESIA;      app->tool = TOOL_DRAW; break;
        case HK_SYMPTOM_ANAESTHESIA:
            app->symptom = SYMPTOM_ANAESTHESIA;       app->tool = TOOL_DRAW; break;
        case HK_SYMPTOM_DEEP_ACHE:
            app->symptom = SYMPTOM_DEEP_ACHE;         app->tool = TOOL_DRAW; break;
        case HK_SYMPTOM_TICK:
            app->symptom = SYMPTOM_TICK;              app->tool = TOOL_DRAW; break;

        /* Tool selection */
        case HK_TOOL_DRAW:  app->tool = TOOL_DRAW;  break;
        case HK_TOOL_ERASE: app->tool = TOOL_ERASE; break;
        case HK_TOOL_NOTE:  app->tool = TOOL_NOTE;  break;
        case HK_TOOL_LINK:  app->tool = TOOL_LINK;  break;

        /* Pen */
        case HK_WIDE_MODE:
            app->pen_wide_mode = !app->pen_wide_mode; break;

        /* History */
        case HK_UNDO:  canvas_undo(app);  break;
        case HK_CLEAR:
            if (app->request_clear_cb) app->request_clear_cb(app);
            break;

        /* Overlay category toggles (click same key again to hide) */
        case HK_OVERLAY_DERM:
            if (app->overlay_category == OVERLAY_DERMATOME && app->overlay_visible)
                app->overlay_visible = FALSE;
            else { app->overlay_category = OVERLAY_DERMATOME; app->overlay_visible = TRUE; }
            break;
        case HK_OVERLAY_PERIPH:
            if (app->overlay_category == OVERLAY_PERIPHERAL && app->overlay_visible)
                app->overlay_visible = FALSE;
            else { app->overlay_category = OVERLAY_PERIPHERAL; app->overlay_visible = TRUE; }
            break;
        case HK_OVERLAY_SOMATIC:
            if (app->overlay_category == OVERLAY_SOMATIC && app->overlay_visible)
                app->overlay_visible = FALSE;
            else { app->overlay_category = OVERLAY_SOMATIC; app->overlay_visible = TRUE; }
            break;
        case HK_OVERLAY_TOGGLE:
            app->overlay_visible = !app->overlay_visible; break;
        case HK_OVERLAY_PREV: {
            int n = overlay_count(app->overlay_category);
            if (n > 0) {
                app->overlay_index = (app->overlay_index - 1 + n) % n;
                app->overlay_visible = TRUE;
            }
            break;
        }
        case HK_OVERLAY_NEXT: {
            int n = overlay_count(app->overlay_category);
            if (n > 0) {
                app->overlay_index = (app->overlay_index + 1) % n;
                app->overlay_visible = TRUE;
            }
            break;
        }

        /* View / layout */
        case HK_VIEW_QUAD:       canvas_set_layout(app, LAYOUT_QUAD);       break;
        case HK_VIEW_ANTERIOR:   canvas_set_layout(app, LAYOUT_ANTERIOR);   break;
        case HK_VIEW_POSTERIOR:  canvas_set_layout(app, LAYOUT_POSTERIOR);  break;
        case HK_VIEW_LATERAL_L:  canvas_set_layout(app, LAYOUT_LATERAL_L);  break;
        case HK_VIEW_LATERAL_R:  canvas_set_layout(app, LAYOUT_LATERAL_R);  break;

        /* Navigation */
        case HK_ZOOM_RESET: canvas_reset_all_zoom(app); break;

        /* Save / export */
        case HK_SAVE_SVG: window_do_export("svg"); break;
        case HK_SAVE_PNG: window_do_export("png"); break;
        case HK_SAVE_PDF: window_do_export("pdf"); break;

        default: return FALSE;
    }

    if (app->toolbar_update_cb) app->toolbar_update_cb(app);
    canvas_invalidate(app);
    return TRUE;
}
