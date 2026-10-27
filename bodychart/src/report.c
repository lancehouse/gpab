#include "report.h"
#include "canvas.h"
#include "obj_chart.h"
#include "stroke.h"
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <time.h>

/* ── Module statics ──────────────────────────────────────────────────────── */
static AppState      *g_rpt_app;
static GtkWidget     *g_text_view;
static GtkTextBuffer *g_buf;
static GtkWidget     *g_status_lbl;

/* ── Subjective field wizard statics ─────────────────────────────────────── */
#define MAX_PROMPT_OPTS  32
#define PROMPT_OPT_LEN   80

typedef struct {
    char text[PROMPT_OPT_LEN];
    int  depth;
} PromptOpt;

typedef struct {
    char      label[32];
    char      hint[160];
    PromptOpt opts[MAX_PROMPT_OPTS];
    int       n_opts;
} SubjFieldDef;

static SubjFieldDef g_prompts[SUBJ_FIELD_COUNT];
static const char  *SUBJ_FIELD_LABELS[SUBJ_FIELD_COUNT] = {
    "History", "Aggs", "Ease", "24hr Pattern"
};
static const char  *SUBJ_MARK_KEYS[SUBJ_FIELD_COUNT] = {
    "hist", "aggs", "ease", "24hr"
};

static GtkTextChildAnchor *g_note_btn_anchors[REPORT_MAX_NOTES];
static int                 g_note_btn_count;

static GtkPopover *g_cur_popover  = NULL;
static int         g_pop_note_idx = -1;
static int         g_pop_field_idx = -1;
static GtkWidget  *g_pop_tv       = NULL;

/* ── Forward declarations ────────────────────────────────────────────────── */
static void extract_editable_text(void);
static void gen_buf(void);
static void attach_note_btn_rows(void);

/* ── Quality labels ──────────────────────────────────────────────────────── */
static const char *QUALITY_LONG[NOTE_QUALITY_COUNT] = {
    "Throbbing",  "Pressure",  "Aching",     "Stabbing",
    "Tight",      "Burning",   "Freezing",   "Electrical",
    "Shooting",   "Pins & needles", "Numbness", "Itching",
    "Sharp",      "Dull"
};

/* ── Anatomical region lookup ────────────────────────────────────────────── */
static const char *body_region_name(int view, float bx, float by)
{
    if (view == VIEW_ANTERIOR || view == VIEW_POSTERIOR) {
        int post = (view == VIEW_POSTERIOR);
        if (by < 55  && bx > 62  && bx < 138) return "Head";
        if (by >= 55 && by < 78  && bx > 78  && bx < 122) return "Neck";
        if (by >= 58 && by < 102) {
            if (bx < 80)  return "L Shoulder";
            if (bx > 120) return "R Shoulder";
        }
        if (by >= 100 && by < 170) {
            if (bx < 68)  return "L Upper Arm";
            if (bx > 132) return "R Upper Arm";
        }
        if (by >= 170 && by < 235) {
            if (bx < 72)  return "L Forearm";
            if (bx > 128) return "R Forearm";
        }
        if (by >= 235 && by < 280) {
            if (bx < 74)  return "L Hand";
            if (bx > 126) return "R Hand";
        }
        if (by >= 78  && by < 148 && bx >= 64 && bx <= 136)
            return post ? "Upper Back / Thoracic" : "Chest";
        if (by >= 148 && by < 200 && bx >= 64 && bx <= 136)
            return post ? "Lumbar" : "Abdomen";
        if (by >= 200 && by < 228 && bx >= 64 && bx <= 136)
            return post ? "Sacrum" : "Pelvis";
        if (by >= 200 && by < 262) {
            if (bx < 88)  return post ? "L Gluteus" : "L Hip";
            if (bx > 112) return post ? "R Gluteus" : "R Hip";
        }
        if (by >= 228 && by < 312) {
            if (bx < 100) return post ? "L Hamstring" : "L Thigh";
            return             post ? "R Hamstring" : "R Thigh";
        }
        if (by >= 312 && by < 345) { return bx < 100 ? "L Knee" : "R Knee"; }
        if (by >= 345 && by < 388) {
            if (bx < 100) return post ? "L Calf" : "L Shin";
            return             post ? "R Calf" : "R Shin";
        }
        if (by >= 388) { return bx < 100 ? "L Foot" : "R Foot"; }
        return "Trunk";
    }
    /* Lateral — y-bands only */
    if (by < 55)  return "Head";
    if (by < 78)  return "Neck";
    if (by < 102) return "Shoulder";
    if (by < 145) return "Upper Arm / Thorax";
    if (by < 200) return "Forearm / Lumbar";
    if (by < 240) return "Hand / Hip";
    if (by < 312) return "Thigh";
    if (by < 345) return "Knee";
    if (by < 388) return "Lower Leg";
    return "Foot";
}

/* ── Chain analysis for natural-language distribution summaries ──────────── */
enum { CHAIN_NONE=0, CHAIN_L_LEG, CHAIN_R_LEG, CHAIN_L_ARM, CHAIN_R_ARM,
       CHAIN_SPINE, CHAIN_HEAD };
#define N_CHAINS 7

typedef struct { int min, max; const char *mn, *mx; gboolean used; } ChainExt;
typedef struct { int chain; int order; const char *name; } ChainNode;

static ChainNode region_node(const char *r)
{
    if (!r) return (ChainNode){CHAIN_NONE, 0, "?"};
    if (!strcmp(r,"L Hip")       || !strcmp(r,"L Gluteus"))   return (ChainNode){CHAIN_L_LEG, 0, "hip"};
    if (!strcmp(r,"L Thigh")     || !strcmp(r,"L Hamstring")) return (ChainNode){CHAIN_L_LEG, 1, "thigh"};
    if (!strcmp(r,"L Knee"))                                   return (ChainNode){CHAIN_L_LEG, 2, "knee"};
    if (!strcmp(r,"L Shin")      || !strcmp(r,"L Calf"))      return (ChainNode){CHAIN_L_LEG, 3, "lower leg"};
    if (!strcmp(r,"L Foot"))                                   return (ChainNode){CHAIN_L_LEG, 4, "foot"};
    if (!strcmp(r,"R Hip")       || !strcmp(r,"R Gluteus"))   return (ChainNode){CHAIN_R_LEG, 0, "hip"};
    if (!strcmp(r,"R Thigh")     || !strcmp(r,"R Hamstring")) return (ChainNode){CHAIN_R_LEG, 1, "thigh"};
    if (!strcmp(r,"R Knee"))                                   return (ChainNode){CHAIN_R_LEG, 2, "knee"};
    if (!strcmp(r,"R Shin")      || !strcmp(r,"R Calf"))      return (ChainNode){CHAIN_R_LEG, 3, "lower leg"};
    if (!strcmp(r,"R Foot"))                                   return (ChainNode){CHAIN_R_LEG, 4, "foot"};
    if (!strcmp(r,"L Shoulder"))                               return (ChainNode){CHAIN_L_ARM, 0, "shoulder"};
    if (!strcmp(r,"L Upper Arm"))                              return (ChainNode){CHAIN_L_ARM, 1, "upper arm"};
    if (!strcmp(r,"L Forearm"))                                return (ChainNode){CHAIN_L_ARM, 2, "forearm"};
    if (!strcmp(r,"L Hand"))                                   return (ChainNode){CHAIN_L_ARM, 3, "hand"};
    if (!strcmp(r,"R Shoulder"))                               return (ChainNode){CHAIN_R_ARM, 0, "shoulder"};
    if (!strcmp(r,"R Upper Arm"))                              return (ChainNode){CHAIN_R_ARM, 1, "upper arm"};
    if (!strcmp(r,"R Forearm"))                                return (ChainNode){CHAIN_R_ARM, 2, "forearm"};
    if (!strcmp(r,"R Hand"))                                   return (ChainNode){CHAIN_R_ARM, 3, "hand"};
    if (!strcmp(r,"Head"))                                            return (ChainNode){CHAIN_HEAD,  0, "head"};
    if (!strcmp(r,"Neck"))                                            return (ChainNode){CHAIN_SPINE, 0, "neck"};
    if (!strcmp(r,"Chest")||!strcmp(r,"Upper Back / Thoracic"))       return (ChainNode){CHAIN_SPINE, 1, "thoracic"};
    if (!strcmp(r,"Abdomen")||!strcmp(r,"Lumbar")||!strcmp(r,"Trunk"))return (ChainNode){CHAIN_SPINE, 2, "lumbar"};
    if (!strcmp(r,"Pelvis")||!strcmp(r,"Sacrum"))                     return (ChainNode){CHAIN_SPINE, 3, "sacrum"};
    return (ChainNode){CHAIN_NONE, 0, r};
}

static void describe_distribution(const char **rgns, int n, char *buf, int buf_len)
{
    if (n == 0) { snprintf(buf, buf_len, "—"); return; }
    if (n == 1) { snprintf(buf, buf_len, "%s", rgns[0]); return; }

    ChainExt ext[N_CHAINS] = {{0}};
    for (int i = 0; i < n; i++) {
        ChainNode cn = region_node(rgns[i]);
        if (cn.chain <= 0 || cn.chain >= N_CHAINS) continue;
        ChainExt *e = &ext[cn.chain];
        if (!e->used) {
            e->min = e->max = cn.order;
            e->mn  = e->mx  = cn.name;
            e->used = TRUE;
        } else {
            if (cn.order < e->min) { e->min = cn.order; e->mn = cn.name; }
            if (cn.order > e->max) { e->max = cn.order; e->mx = cn.name; }
        }
    }

    GString *gs = g_string_new(NULL);

    char spine_str[64] = "";
    if (ext[CHAIN_SPINE].used) {
        if (ext[CHAIN_SPINE].min == ext[CHAIN_SPINE].max)
            snprintf(spine_str, sizeof(spine_str), "%s", ext[CHAIN_SPINE].mx);
        else
            snprintf(spine_str, sizeof(spine_str), "%s to %s",
                     ext[CHAIN_SPINE].mn, ext[CHAIN_SPINE].mx);
    }

    #define LIMB_STR(e, side, type) do {                                          \
        if ((e)->min == 0 && (e)->max == full_end)                                \
            g_string_append_printf(gs, "entire %s %s into %s", side, type, (e)->mx); \
        else if ((e)->max == full_end)                                             \
            g_string_append_printf(gs, "%s %s from %s into %s",                  \
                                   side, type, (e)->mn, (e)->mx);                 \
        else if ((e)->min == (e)->max)                                             \
            g_string_append_printf(gs, "%s %s", side, (e)->mn);                  \
        else if ((e)->max - (e)->min == 1)                                        \
            g_string_append_printf(gs, "%s %s to %s", side, (e)->mn, (e)->mx);   \
        else                                                                       \
            g_string_append_printf(gs, "%s %s from %s to %s",                    \
                                   side, type, (e)->mn, (e)->mx);                 \
    } while(0)

    gboolean bi_leg = (ext[CHAIN_L_LEG].used && ext[CHAIN_R_LEG].used &&
                       abs(ext[CHAIN_L_LEG].min - ext[CHAIN_R_LEG].min) <= 1 &&
                       abs(ext[CHAIN_L_LEG].max - ext[CHAIN_R_LEG].max) <= 1);
    if (bi_leg) {
        if (gs->len == 0 && spine_str[0]) {
            g_string_append(gs, spine_str);
            g_string_append(gs, " radiating down ");
        }
        int full_end = 4;
        ChainExt *e = &ext[CHAIN_L_LEG];
        if (e->min == 0 && e->max == 4)
            g_string_append(gs, "bilateral legs into foot");
        else if (e->max == 4)
            g_string_append_printf(gs, "bilateral legs from %s into foot", e->mn);
        else if (e->min == e->max)
            g_string_append_printf(gs, "bilateral %s", e->mn);
        else if (e->max - e->min == 1)
            g_string_append_printf(gs, "bilateral %s to %s", e->mn, e->mx);
        else
            g_string_append_printf(gs, "bilateral legs from %s to %s", e->mn, e->mx);
        (void)full_end;
        ext[CHAIN_L_LEG].used = ext[CHAIN_R_LEG].used = FALSE;
        spine_str[0] = '\0';
    }

    const char *leg_sides[]  = {"L", "R"};
    int         leg_chains[] = {CHAIN_L_LEG, CHAIN_R_LEG};
    for (int s = 0; s < 2; s++) {
        if (!ext[leg_chains[s]].used) continue;
        if (gs->len > 0) g_string_append(gs, " + ");
        if (spine_str[0]) {
            g_string_append(gs, spine_str);
            g_string_append(gs, " radiating down ");
            spine_str[0] = '\0';
        }
        int full_end = 4;
        LIMB_STR(&ext[leg_chains[s]], leg_sides[s], "leg");
        (void)full_end;
        ext[leg_chains[s]].used = FALSE;
    }

    gboolean bi_arm = (ext[CHAIN_L_ARM].used && ext[CHAIN_R_ARM].used &&
                       abs(ext[CHAIN_L_ARM].min - ext[CHAIN_R_ARM].min) <= 1 &&
                       abs(ext[CHAIN_L_ARM].max - ext[CHAIN_R_ARM].max) <= 1);
    if (bi_arm) {
        if (gs->len > 0) g_string_append(gs, " + ");
        if (spine_str[0]) {
            g_string_append(gs, spine_str);
            g_string_append(gs, " radiating into ");
            spine_str[0] = '\0';
        }
        ChainExt *e = &ext[CHAIN_L_ARM];
        if (e->min == 0 && e->max == 3)
            g_string_append(gs, "bilateral arms into hand");
        else if (e->max == 3)
            g_string_append_printf(gs, "bilateral arms from %s into hand", e->mn);
        else if (e->min == e->max)
            g_string_append_printf(gs, "bilateral %s", e->mn);
        else
            g_string_append_printf(gs, "bilateral arms from %s to %s", e->mn, e->mx);
        ext[CHAIN_L_ARM].used = ext[CHAIN_R_ARM].used = FALSE;
    }

    const char *arm_sides[]  = {"L", "R"};
    int         arm_chains[] = {CHAIN_L_ARM, CHAIN_R_ARM};
    for (int s = 0; s < 2; s++) {
        if (!ext[arm_chains[s]].used) continue;
        if (gs->len > 0) g_string_append(gs, " + ");
        if (spine_str[0]) {
            g_string_append(gs, spine_str);
            g_string_append(gs, " radiating into ");
            spine_str[0] = '\0';
        }
        int full_end = 3;
        LIMB_STR(&ext[arm_chains[s]], arm_sides[s], "arm");
        (void)full_end;
        ext[arm_chains[s]].used = FALSE;
    }

    if (spine_str[0]) {
        if (gs->len > 0) g_string_append(gs, " + ");
        g_string_append(gs, spine_str);
    }

    if (ext[CHAIN_HEAD].used) {
        if (gs->len > 0) g_string_append(gs, " + ");
        g_string_append(gs, "head");
    }

    for (int i = 0; i < n; i++) {
        if (region_node(rgns[i]).chain != CHAIN_NONE) continue;
        if (gs->len > 0) g_string_append(gs, " + ");
        g_string_append(gs, rgns[i]);
    }

    if (gs->len == 0) {
        for (int i = 0; i < n; i++) {
            if (i) g_string_append(gs, ", ");
            g_string_append(gs, rgns[i]);
        }
    }

    g_snprintf(buf, buf_len, "%s", gs->str);
    g_string_free(gs, TRUE);

    #undef LIMB_STR
}

/* ── Note–stroke association ─────────────────────────────────────────────── */
static int assign_stroke_to_note(AppState *app, float cx, float cy, int view,
                                  const char *region)
{
    if (app->note_count == 0) return -1;

    ChainNode sk_cn = region_node(region);

    int  best1 = -1; float best1_d = 1e9f;
    for (int i = 0; i < app->note_count; i++) {
        const char *nr = body_region_name(app->notes[i].view,
                                          (float)app->notes[i].bx,
                                          (float)app->notes[i].by);
        ChainNode nc = region_node(nr);
        if (nc.chain != sk_cn.chain || nc.chain == CHAIN_NONE) continue;
        float dx = (float)app->notes[i].bx - cx;
        float dy = (float)app->notes[i].by - cy;
        float mul = (app->notes[i].view == view) ? 1.0f : 1.5f;
        float d = sqrtf(dx*dx + dy*dy) * mul;
        if (d < best1_d) { best1_d = d; best1 = i; }
    }
    if (best1 >= 0 && best1_d < 200.0f) return best1;

    int parent_chain = CHAIN_NONE;
    int min_spine_order = 0, max_spine_order = 3;
    if (sk_cn.chain == CHAIN_L_LEG || sk_cn.chain == CHAIN_R_LEG) {
        parent_chain = CHAIN_SPINE; min_spine_order = 2;
    } else if (sk_cn.chain == CHAIN_L_ARM || sk_cn.chain == CHAIN_R_ARM) {
        parent_chain = CHAIN_SPINE; max_spine_order = 1;
    }
    if (parent_chain != CHAIN_NONE) {
        int best2 = -1; int best2_ord = -1;
        for (int i = 0; i < app->note_count; i++) {
            const char *nr = body_region_name(app->notes[i].view,
                                              (float)app->notes[i].bx,
                                              (float)app->notes[i].by);
            ChainNode nc = region_node(nr);
            if (nc.chain != parent_chain) continue;
            if (nc.order < min_spine_order || nc.order > max_spine_order) continue;
            if (nc.order > best2_ord) { best2_ord = nc.order; best2 = i; }
        }
        if (best2 >= 0) return best2;
    }

    int best3 = -1; float best3_d = 80.0f;
    for (int i = 0; i < app->note_count; i++) {
        float dx = (float)app->notes[i].bx - cx;
        float dy = (float)app->notes[i].by - cy;
        float d  = sqrtf(dx*dx + dy*dy);
        if (d < best3_d) { best3_d = d; best3 = i; }
    }
    return best3;
}

/* ── Region list (deduplicated) ──────────────────────────────────────────── */
#define MAX_ASSOC_REGIONS 48
typedef struct { const char *r[MAX_ASSOC_REGIONS]; int n; } RegionList;

static void rlist_add(RegionList *rl, const char *region)
{
    for (int i = 0; i < rl->n; i++)
        if (!strcmp(rl->r[i], region)) return;
    if (rl->n < MAX_ASSOC_REGIONS)
        rl->r[rl->n++] = region;
}

/* ── Subjective template ─────────────────────────────────────────────────── */
static const char SUBJ_TEMPLATE_DEFAULT[] =
    "# Subjective Interview Prompts\n"
    "<!-- PhysioChart subjective template v1. Edit freely in Obsidian or any editor. -->\n"
    "<!-- ## heading = field name, > = hint text, - bullet = option, "
         "  - (2-space indent) = sub-option -->\n"
    "\n"
    "## History\n"
    "> Onset, mechanism, duration, previous episodes, relevant medical history.\n"
    "- Onset\n"
    "  - Gradual\n"
    "  - Sudden / trauma\n"
    "- Mechanism\n"
    "  - Work-related\n"
    "  - MVA / road traffic\n"
    "- Prior episodes\n"
    "  - None\n"
    "  - Resolved\n"
    "  - Recurrent\n"
    "- Chronic — >3 months\n"
    "\n"
    "## Aggs\n"
    "> Activities or postures that aggravate symptoms.\n"
    "- Prolonged sitting\n"
    "- Prolonged standing\n"
    "- Walking\n"
    "- Bending / lumbar flexion\n"
    "- Extension / backward bending\n"
    "- Lifting\n"
    "- Morning stiffness — first 30 min\n"
    "- All activity\n"
    "- Rest pain\n"
    "- Night pain\n"
    "\n"
    "## Ease\n"
    "> Activities or postures that relieve symptoms.\n"
    "- Rest / lying down\n"
    "- Walking short distances\n"
    "- Position change\n"
    "- Heat application\n"
    "- Cold application\n"
    "- Analgesia / medication\n"
    "- Stretching\n"
    "- Nothing helps\n"
    "\n"
    "## 24hr Pattern\n"
    "> How symptoms vary throughout the day and night.\n"
    "- Worse in morning, eases through day\n"
    "- Constant throughout day\n"
    "- Worse with sustained activity, better with rest\n"
    "- Worse at end of day\n"
    "- Night pain — disturbs sleep\n"
    "- Wakes from sleep\n"
    "- No clear pattern\n";

static void write_default_template(const char *path)
{
    FILE *f = fopen(path, "w");
    if (!f) return;
    fwrite(SUBJ_TEMPLATE_DEFAULT, 1, strlen(SUBJ_TEMPLATE_DEFAULT), f);
    fclose(f);
}

static void load_subj_template(void)
{
    memset(g_prompts, 0, sizeof(g_prompts));
    for (int fi = 0; fi < SUBJ_FIELD_COUNT; fi++)
        g_strlcpy(g_prompts[fi].label, SUBJ_FIELD_LABELS[fi], sizeof(g_prompts[fi].label));

    const char *cfg = g_get_user_config_dir();
    char dir[512], path[512];
    snprintf(dir,  sizeof(dir),  "%s/pab", cfg);
    snprintf(path, sizeof(path), "%s/pab/subjective_prompts.md", cfg);

    g_mkdir_with_parents(dir, 0755);

    FILE *tf = fopen(path, "r");
    if (!tf) { write_default_template(path); tf = fopen(path, "r"); }
    if (!tf) return;

    int cur_field = -1;
    char line[512];
    while (fgets(line, sizeof(line), tf)) {
        int ln = (int)strlen(line);
        while (ln > 0 && (line[ln-1] == '\n' || line[ln-1] == '\r')) line[--ln] = '\0';

        if (strncmp(line, "<!--", 4) == 0) continue;

        if (strncmp(line, "## ", 3) == 0) {
            const char *lbl = line + 3;
            cur_field = -1;
            for (int fi = 0; fi < SUBJ_FIELD_COUNT; fi++) {
                if (g_ascii_strcasecmp(lbl, SUBJ_FIELD_LABELS[fi]) == 0) {
                    cur_field = fi;
                    break;
                }
            }
            continue;
        }

        if (cur_field < 0) continue;
        SubjFieldDef *fd = &g_prompts[cur_field];

        if (strncmp(line, "> ", 2) == 0) {
            g_strlcpy(fd->hint, line + 2, sizeof(fd->hint));
            continue;
        }

        if (strncmp(line, "  - ", 4) == 0) {
            if (fd->n_opts < MAX_PROMPT_OPTS) {
                g_strlcpy(fd->opts[fd->n_opts].text, line + 4, PROMPT_OPT_LEN);
                fd->opts[fd->n_opts].depth = 1;
                fd->n_opts++;
            }
            continue;
        }

        if (strncmp(line, "- ", 2) == 0) {
            if (fd->n_opts < MAX_PROMPT_OPTS) {
                g_strlcpy(fd->opts[fd->n_opts].text, line + 2, PROMPT_OPT_LEN);
                fd->opts[fd->n_opts].depth = 0;
                fd->n_opts++;
            }
            continue;
        }
    }
    fclose(tf);
}

/* ── Subjective wizard UI ────────────────────────────────────────────────── */
typedef struct { int note_idx; int field_idx; } BtnCtx;
typedef struct { char text[PROMPT_OPT_LEN]; } OptCtx;

static void closure_free(gpointer data, GClosure *cl) { (void)cl; g_free(data); }

static void on_opt_btn_clicked(GtkButton *btn, gpointer data)
{
    (void)btn;
    if (!g_pop_tv) return;
    OptCtx *ctx = data;
    GtkTextBuffer *pb = gtk_text_view_get_buffer(GTK_TEXT_VIEW(g_pop_tv));
    GtkTextIter ps, pe;
    gtk_text_buffer_get_bounds(pb, &ps, &pe);
    char *cur = gtk_text_buffer_get_text(pb, &ps, &pe, FALSE);
    int clen = (int)strlen(cur);
    while (clen > 0 && cur[clen-1] == '\n') cur[--clen] = '\0';
    if (clen > 0) {
        char newtext[REPORT_NOTE_FIELD_LEN];
        snprintf(newtext, sizeof(newtext), "%s\n%s", cur, ctx->text);
        gtk_text_buffer_set_text(pb, newtext, -1);
    } else {
        gtk_text_buffer_set_text(pb, ctx->text, -1);
    }
    g_free(cur);
    GtkTextIter end;
    gtk_text_buffer_get_end_iter(pb, &end);
    gtk_text_buffer_place_cursor(pb, &end);
    gtk_widget_grab_focus(g_pop_tv);
}

static gboolean on_pop_tv_key(GtkEventControllerKey *ctrl, guint keyval,
                               guint keycode, GdkModifierType state, gpointer data)
{
    (void)ctrl; (void)keycode; (void)data;
    if (keyval == GDK_KEY_Return && (state & GDK_SHIFT_MASK)) {
        if (!g_pop_tv || !g_rpt_app) return TRUE;
        GtkTextBuffer *pb = gtk_text_view_get_buffer(GTK_TEXT_VIEW(g_pop_tv));
        GtkTextIter ps, pe;
        gtk_text_buffer_get_bounds(pb, &ps, &pe);
        char *t = gtk_text_buffer_get_text(pb, &ps, &pe, FALSE);
        int tlen = (int)strlen(t);
        while (tlen > 0 && t[tlen-1] == '\n') t[--tlen] = '\0';
        if (g_pop_note_idx >= 0 && g_pop_note_idx < g_rpt_app->note_count
            && g_pop_field_idx >= 0 && g_pop_field_idx < SUBJ_FIELD_COUNT) {
            g_strlcpy(g_rpt_app->report.note_subj[g_pop_note_idx].fields[g_pop_field_idx],
                      t, REPORT_NOTE_FIELD_LEN);
        }
        g_free(t);
        /* Close popover BEFORE gen_buf — gen_buf deletes child anchors which
           destroys the button that was the old popover's parent */
        GtkPopover *closing = g_cur_popover;
        g_cur_popover  = NULL;
        g_pop_tv       = NULL;
        g_pop_note_idx  = -1;
        g_pop_field_idx = -1;
        if (closing) gtk_popover_popdown(closing);
        extract_editable_text();
        gen_buf();
        attach_note_btn_rows();
        return TRUE;
    }
    return FALSE;
}

static void on_popover_closed(GtkPopover *pop, gpointer data)
{
    (void)data;
    if (g_cur_popover == pop) {
        g_cur_popover  = NULL;
        g_pop_tv       = NULL;
        g_pop_note_idx  = -1;
        g_pop_field_idx = -1;
    }
    gtk_widget_unparent(GTK_WIDGET(pop));
}

static void show_subj_popover(GtkWidget *btn, int ni, int fi, const char *cur_content)
{
    (void)btn;
    if (g_cur_popover) {
        gtk_popover_popdown(g_cur_popover);
        g_cur_popover = NULL;
    }

    GtkWidget *pop = gtk_popover_new();
    /* Parent to text view so position is stable regardless of which note button was tapped */
    gtk_widget_set_parent(pop, g_text_view);
    gtk_popover_set_has_arrow(GTK_POPOVER(pop), FALSE);
    /* Fixed position: right side of the text view, near the top */
    GdkRectangle rect = { 24, 100, 2, 2 };
    gtk_popover_set_pointing_to(GTK_POPOVER(pop), &rect);
    gtk_popover_set_position(GTK_POPOVER(pop), GTK_POS_RIGHT);

    GtkWidget *vbox = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
    gtk_widget_set_margin_start(vbox, 8);
    gtk_widget_set_margin_end(vbox, 8);
    gtk_widget_set_margin_top(vbox, 8);
    gtk_widget_set_margin_bottom(vbox, 8);

    SubjFieldDef *fd = &g_prompts[fi];
    if (fd->hint[0]) {
        GtkWidget *hint_lbl = gtk_label_new(fd->hint);
        gtk_label_set_wrap(GTK_LABEL(hint_lbl), TRUE);
        gtk_label_set_max_width_chars(GTK_LABEL(hint_lbl), 60);
        gtk_widget_set_name(hint_lbl, "subj-hint");
        gtk_box_append(GTK_BOX(vbox), hint_lbl);
    }

    if (fd->n_opts > 0) {
        GtkWidget *fb = gtk_flow_box_new();
        gtk_flow_box_set_max_children_per_line(GTK_FLOW_BOX(fb), 4);
        gtk_flow_box_set_selection_mode(GTK_FLOW_BOX(fb), GTK_SELECTION_NONE);
        gtk_widget_set_name(fb, "subj-opt-row");
        for (int i = 0; i < fd->n_opts; i++) {
            GtkWidget *obtn = gtk_button_new_with_label(fd->opts[i].text);
            gtk_widget_set_name(obtn, fd->opts[i].depth == 0 ? "subj-opt-btn" : "subj-opt-sub");
            OptCtx *ctx = g_new(OptCtx, 1);
            g_strlcpy(ctx->text, fd->opts[i].text, PROMPT_OPT_LEN);
            g_signal_connect_data(obtn, "clicked", G_CALLBACK(on_opt_btn_clicked),
                                  ctx, closure_free, 0);
            gtk_flow_box_append(GTK_FLOW_BOX(fb), obtn);
        }
        gtk_box_append(GTK_BOX(vbox), fb);
    }

    GtkWidget *sc2 = gtk_scrolled_window_new();
    gtk_widget_set_size_request(sc2, 480, 160);
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(sc2),
                                   GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);

    GtkWidget *ptv = gtk_text_view_new();
    gtk_widget_set_name(ptv, "subj-tv");
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(ptv), GTK_WRAP_WORD_CHAR);
    gtk_text_view_set_monospace(GTK_TEXT_VIEW(ptv), TRUE);
    gtk_text_view_set_left_margin(GTK_TEXT_VIEW(ptv),  6);
    gtk_text_view_set_right_margin(GTK_TEXT_VIEW(ptv), 6);
    gtk_text_view_set_top_margin(GTK_TEXT_VIEW(ptv),   4);
    gtk_text_view_set_bottom_margin(GTK_TEXT_VIEW(ptv),4);

    if (cur_content && cur_content[0])
        gtk_text_buffer_set_text(gtk_text_view_get_buffer(GTK_TEXT_VIEW(ptv)),
                                 cur_content, -1);

    GtkEventController *kc = gtk_event_controller_key_new();
    g_signal_connect(kc, "key-pressed", G_CALLBACK(on_pop_tv_key), NULL);
    gtk_widget_add_controller(ptv, kc);

    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(sc2), ptv);
    gtk_box_append(GTK_BOX(vbox), sc2);

    GtkWidget *hint2 = gtk_label_new("Shift+Enter to save");
    gtk_widget_set_name(hint2, "subj-hint");
    gtk_box_append(GTK_BOX(vbox), hint2);

    gtk_popover_set_child(GTK_POPOVER(pop), vbox);
    g_signal_connect(pop, "closed", G_CALLBACK(on_popover_closed), NULL);

    g_cur_popover  = GTK_POPOVER(pop);
    g_pop_note_idx  = ni;
    g_pop_field_idx = fi;
    g_pop_tv       = ptv;

    gtk_popover_popup(GTK_POPOVER(pop));
    gtk_widget_grab_focus(ptv);
}

static void on_subj_btn_clicked(GtkButton *btn, gpointer data)
{
    BtnCtx *ctx = data;
    int ni = ctx->note_idx;
    int fi = ctx->field_idx;
    if (!g_rpt_app || ni < 0 || ni >= g_rpt_app->note_count) return;
    const char *cur = g_rpt_app->report.note_subj[ni].fields[fi];
    show_subj_popover(GTK_WIDGET(btn), ni, fi, cur);
}

static GtkWidget *make_note_btn_row(int ni)
{
    GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 4);
    gtk_widget_set_name(row, "subj-btn-row");
    gtk_widget_set_margin_start(row, 8);
    gtk_widget_set_margin_top(row, 2);
    gtk_widget_set_margin_bottom(row, 2);
    for (int f = 0; f < SUBJ_FIELD_COUNT; f++) {
        GtkWidget *btn = gtk_button_new_with_label(SUBJ_FIELD_LABELS[f]);
        gtk_widget_set_name(btn, "subj-btn");
        BtnCtx *ctx = g_new(BtnCtx, 1);
        ctx->note_idx  = ni;
        ctx->field_idx = f;
        g_signal_connect_data(btn, "clicked", G_CALLBACK(on_subj_btn_clicked),
                              ctx, closure_free, 0);
        gtk_box_append(GTK_BOX(row), btn);
    }
    return row;
}

static void attach_note_btn_rows(void)
{
    if (!g_text_view) return;
    for (int i = 0; i < g_note_btn_count; i++) {
        GtkWidget *row = make_note_btn_row(i);
        gtk_text_view_add_child_at_anchor(GTK_TEXT_VIEW(g_text_view),
                                          row, g_note_btn_anchors[i]);
    }
}

/* ── Tag / insert helpers ────────────────────────────────────────────────── */
static void create_tags(void)
{
    GtkTextTagTable *tbl = gtk_text_buffer_get_tag_table(g_buf);
    struct { const char *name; const char *fg; int bold; } defs[] = {
        { "section",  "#ffcc44", 1 },
        { "divider",  "#252538", 0 },
        { "heading",  "#4ac8ff", 1 },
        { "muted",    "#555570", 0 },
        { "auto",     "#7878a8", 0 },
        { "value",    "#7fc8a0", 0 },
        { "edit",     "#d0d0e8", 0 },
    };
    for (size_t i = 0; i < sizeof(defs)/sizeof(defs[0]); i++) {
        if (gtk_text_tag_table_lookup(tbl, defs[i].name)) continue;
        GtkTextTag *tag = gtk_text_buffer_create_tag(g_buf, defs[i].name, NULL);
        if (defs[i].fg)   g_object_set(tag, "foreground", defs[i].fg, NULL);
        if (defs[i].bold) g_object_set(tag, "weight", PANGO_WEIGHT_BOLD, NULL);
    }
}

static void ins(GtkTextIter *it, const char *text, const char *tag)
{
    if (tag)
        gtk_text_buffer_insert_with_tags_by_name(g_buf, it, text, -1, tag, NULL);
    else
        gtk_text_buffer_insert(g_buf, it, text, -1);
}

static GtkTextMark *place_mark(const char *name, GtkTextIter *it, gboolean lg)
{
    GtkTextMark *m = gtk_text_buffer_get_mark(g_buf, name);
    if (m) gtk_text_buffer_delete_mark(g_buf, m);
    return gtk_text_buffer_create_mark(g_buf, name, it, lg);
}

static void ins_edit_region(GtkTextIter *it,
                             const char *ms, const char *me,
                             const char *init)
{
    place_mark(ms, it, TRUE);
    if (init && init[0]) ins(it, init, "edit");
    ins(it, "\n", "edit");
    place_mark(me, it, FALSE);
}

/* ── Extract user text from mark pairs → AppState ────────────────────────── */
static void extract_editable_text(void)
{
    if (!g_buf || !g_rpt_app) return;
#define EXTRACT(ms, me, field) do {                                         \
    GtkTextMark *ma = gtk_text_buffer_get_mark(g_buf, ms);                  \
    GtkTextMark *mb = gtk_text_buffer_get_mark(g_buf, me);                  \
    if (ma && mb) {                                                           \
        GtkTextIter ia, ib;                                                   \
        gtk_text_buffer_get_iter_at_mark(g_buf, &ia, ma);                    \
        gtk_text_buffer_get_iter_at_mark(g_buf, &ib, mb);                    \
        char *t = gtk_text_buffer_get_text(g_buf, &ia, &ib, FALSE);          \
        g_strlcpy(g_rpt_app->report.field, t, REPORT_SECTION_LEN);           \
        g_free(t);                                                            \
    }                                                                         \
} while(0)
    EXTRACT("assess_s","assess_e", assessment);
    EXTRACT("plan_s",  "plan_e",   plan);
    EXTRACT("notes_s", "notes_e",  clinical_notes);
#undef EXTRACT

    /* Extract per-note subjective fields */
    int nc = g_rpt_app->note_count;
    if (nc > REPORT_MAX_NOTES) nc = REPORT_MAX_NOTES;
    for (int ni = 0; ni < nc; ni++) {
        for (int f = 0; f < SUBJ_FIELD_COUNT; f++) {
            char ms[32], me[32];
            snprintf(ms, sizeof(ms), "subj_%d_%s_s", ni, SUBJ_MARK_KEYS[f]);
            snprintf(me, sizeof(me), "subj_%d_%s_e", ni, SUBJ_MARK_KEYS[f]);
            GtkTextMark *ma = gtk_text_buffer_get_mark(g_buf, ms);
            GtkTextMark *mb = gtk_text_buffer_get_mark(g_buf, me);
            if (!ma || !mb) continue;
            GtkTextIter ia, ib;
            gtk_text_buffer_get_iter_at_mark(g_buf, &ia, ma);
            gtk_text_buffer_get_iter_at_mark(g_buf, &ib, mb);
            char *t = gtk_text_buffer_get_text(g_buf, &ia, &ib, FALSE);
            int tlen = (int)strlen(t);
            while (tlen > 0 && t[tlen-1] == '\n') t[--tlen] = '\0';
            g_strlcpy(g_rpt_app->report.note_subj[ni].fields[f], t, REPORT_NOTE_FIELD_LEN);
            g_free(t);
        }
    }
}

/* ── Buffer generation ───────────────────────────────────────────────────── */
static void gen_buf(void)
{
    if (!g_rpt_app || !g_buf) return;
    AppState *app = g_rpt_app;

    g_note_btn_count = 0;

    gtk_text_buffer_begin_irreversible_action(g_buf);
    GtkTextIter start, end;
    gtk_text_buffer_get_bounds(g_buf, &start, &end);
    gtk_text_buffer_delete(g_buf, &start, &end);

    GtkTextIter it;
    gtk_text_buffer_get_start_iter(g_buf, &it);

    /* ── Header ── */
    ins(&it, "══════════════════════════════════════════════════════════════════\n", "divider");
    ins(&it, "  PHYSIOCHART REPORT", "section");
    if (app->patient_id[0]) {
        time_t ct = app->session_created ? app->session_created : time(NULL);
        struct tm *t = localtime(&ct);
        char ds[20]; strftime(ds, sizeof(ds), "%d/%m/%Y", t);
        char pi[96]; snprintf(pi, sizeof(pi), "                    %s · %s\n", app->patient_id, ds);
        ins(&it, pi, "auto");
    } else {
        ins(&it, "\n", NULL);
    }
    if (app->session_label[0]) {
        char sl[80]; snprintf(sl, sizeof(sl), "  %s\n", app->session_label);
        ins(&it, sl, "muted");
    }
    ins(&it, "══════════════════════════════════════════════════════════════════\n\n", "divider");

    /* ══ SUBJECTIVE ══════════════════════════════════════════════════════════ */
    ins(&it, "── SUBJECTIVE ", "section");
    ins(&it, "─────────────────────────────────────────────────────────\n\n", "muted");

    RegionList note_rgns[MAX_NOTES][SYMPTOM_COUNT];
    RegionList ungrouped[SYMPTOM_COUNT];
    memset(note_rgns, 0, sizeof(note_rgns));
    memset(ungrouped, 0, sizeof(ungrouped));

    for (int i = 0; i < app->strokes->n; i++) {
        Stroke *sk = app->strokes->strokes[i];
        if (sk->type == SYMPTOM_TICK) continue;
        if (sk->view < 0 || sk->view >= 8) continue;
        if (sk->type < 0 || sk->type >= SYMPTOM_COUNT) continue;
        if (sk->n_pts == 0) continue;

        double cx = 0, cy = 0;
        for (size_t j = 0; j < sk->n_pts; j++) { cx += sk->pts[j].x; cy += sk->pts[j].y; }
        cx /= (double)sk->n_pts; cy /= (double)sk->n_pts;

        const char *rgn = body_region_name(sk->view, (float)cx, (float)cy);
        int ni = assign_stroke_to_note(app, (float)cx, (float)cy, sk->view, rgn);
        if (ni >= 0 && ni < app->note_count)
            rlist_add(&note_rgns[ni][sk->type], rgn);
        else
            rlist_add(&ungrouped[sk->type], rgn);
    }

    /* ── Per-note sections ── */
    if (app->note_count > 0) {
        for (int ni = 0; ni < app->note_count; ni++) {
            NoteAnnotation *n = &app->notes[ni];
            /* Build quality string — prefer voice transcript over coded terms */
            char qbuf[256] = {0};
            if (n->voice_note[0]) {
                g_strlcpy(qbuf, n->voice_note, sizeof(qbuf));
            } else {
                for (int q = 0; q < n->quality_count; q++) {
                    if (q > 0) strncat(qbuf, " + ", sizeof(qbuf) - strlen(qbuf) - 1);
                    int qi = n->qualities[q];
                    const char *ql = (qi >= 0 && qi < NOTE_QUALITY_COUNT)
                                     ? QUALITY_LONG[qi] : "?";
                    strncat(qbuf, ql, sizeof(qbuf) - strlen(qbuf) - 1);
                }
            }
            const char *nrgn = body_region_name(n->view, (float)n->bx, (float)n->by);

            char fields[320] = {0}, ibuf[16];
            note_join(fields, sizeof(fields), " · ", nrgn);
            note_join(fields, sizeof(fields), " · ", canvas_view_name((BodyView)n->view));
            note_join(fields, sizeof(fields), " · ", note_temporal_name(n->temporal));
            note_join(fields, sizeof(fields), " · ", note_depth_name(n->depth));
            note_join(fields, sizeof(fields), " · ", qbuf);
            note_join(fields, sizeof(fields), " · ", note_intensity_str(n, ibuf, sizeof(ibuf)));
            char hdr[360];
            snprintf(hdr, sizeof(hdr), "  NOTE (%d)  %s\n", n->number, fields);
            ins(&it, hdr, "heading");

            gboolean any_sym = FALSE;
            char dist[256];
            for (int s = 0; s < SYMPTOM_COUNT; s++) {
                if (s == SYMPTOM_TICK) continue;
                RegionList *rl = &note_rgns[ni][s];
                if (rl->n == 0) continue;
                describe_distribution(rl->r, rl->n, dist, sizeof(dist));
                char line[320];
                snprintf(line, sizeof(line), "    %-24s%s\n",
                         SYMPTOM_DEFS[s].label, dist);
                ins(&it, line, "auto");
                any_sym = TRUE;
            }
            if (!any_sym)
                ins(&it, "    (no symptoms mapped near this note)\n", "muted");

            /* Button row anchor (wizard buttons inline) */
            if (g_note_btn_count < REPORT_MAX_NOTES) {
                GtkTextChildAnchor *anch = gtk_text_buffer_create_child_anchor(g_buf, &it);
                g_note_btn_anchors[g_note_btn_count++] = anch;
            }
            ins(&it, "\n", NULL);

            /* Subjective field edit regions — only if non-empty */
            for (int f = 0; f < SUBJ_FIELD_COUNT; f++) {
                const char *fld = app->report.note_subj[ni].fields[f];
                if (!fld[0]) continue;
                char lbl[48];
                snprintf(lbl, sizeof(lbl), "    %s: ", SUBJ_FIELD_LABELS[f]);
                ins(&it, lbl, "heading");
                char ms[32], me[32];
                snprintf(ms, sizeof(ms), "subj_%d_%s_s", ni, SUBJ_MARK_KEYS[f]);
                snprintf(me, sizeof(me), "subj_%d_%s_e", ni, SUBJ_MARK_KEYS[f]);
                ins_edit_region(&it, ms, me, fld);
            }

            ins(&it, "\n", NULL);
        }
    }

    /* ── Ungrouped symptoms ── */
    gboolean any_ug = FALSE;
    for (int s = 0; s < SYMPTOM_COUNT; s++) {
        if (s == SYMPTOM_TICK) continue;
        if (ungrouped[s].n > 0) { any_ug = TRUE; break; }
    }
    if (any_ug) {
        ins(&it, "  Other symptoms  (no associated note):\n", "heading");
        char dist[256];
        for (int s = 0; s < SYMPTOM_COUNT; s++) {
            if (s == SYMPTOM_TICK) continue;
            RegionList *rl = &ungrouped[s];
            if (rl->n == 0) continue;
            describe_distribution(rl->r, rl->n, dist, sizeof(dist));
            char line[320];
            snprintf(line, sizeof(line), "    %-24s%s\n", SYMPTOM_DEFS[s].label, dist);
            ins(&it, line, "auto");
        }
        ins(&it, "\n", NULL);
    }

    if (app->note_count == 0 && !any_ug) {
        ins(&it, "  (no symptoms mapped)\n\n", "muted");
    }

    /* Link relations */
    if (app->link_rel_count > 0) {
        ins(&it, "  Connections:\n", "heading");
        for (int i = 0; i < app->link_rel_count; i++) {
            LinkRel *lr = &app->link_relations[i];
            char line[64];
            snprintf(line, sizeof(line),
                     lr->state == LINK_YES
                         ? "    Note %d  →  Note %d\n"
                         : "    Note %d  ─/→  Note %d\n",
                     lr->from + 1, lr->to + 1);
            ins(&it, line, "auto");
        }
        ins(&it, "\n", NULL);
    }

    /* ══ ASSESSMENT ══════════════════════════════════════════════════════════ */
    ins(&it, "── ASSESSMENT ", "section");
    ins(&it, "──────────────────────────────────────────────────────────\n", "muted");
    ins_edit_region(&it, "assess_s", "assess_e", app->report.assessment);

    /* ══ OBJECTIVE ═══════════════════════════════════════════════════════════ */
    ins(&it, "── OBJECTIVE ", "section");
    ins(&it, "───────────────────────────────────────────────────────────\n", "muted");

    gboolean any_obj_output = FALSE;

    if (app->obj_zone_count > 0) {
        RegionList zone_rgns[OBJ_ZONE_COUNT];
        memset(zone_rgns, 0, sizeof(zone_rgns));
        for (int i = 0; i < app->obj_zone_count; i++) {
            ObjZone *z = app->obj_zones[i];
            if (!z || z->n == 0) continue;
            int step = z->n > 8 ? z->n / 8 : 1;
            for (int j = 0; j < z->n; j += step) {
                const char *rgn = body_region_name(z->view, z->bx[j], z->by[j]);
                rlist_add(&zone_rgns[(int)z->type], rgn);
            }
        }
        ins(&it, "  Zones:\n", "heading");
        char dist[256];
        for (int t = 0; t < OBJ_ZONE_COUNT; t++) {
            if (zone_rgns[t].n == 0) continue;
            describe_distribution(zone_rgns[t].r, zone_rgns[t].n, dist, sizeof(dist));
            char line[320];
            snprintf(line, sizeof(line), "    %-20s%s\n", OBJ_ZONE_DEFS[t].name, dist);
            ins(&it, line, "auto");
            any_obj_output = TRUE;
        }
        ins(&it, "\n", NULL);
    }

    gboolean any_ppt = FALSE;
    for (int i = 0; i < app->obj_point_count; i++)
        if (app->obj_points[i].type == OBJ_POINT_PPT) { any_ppt = TRUE; break; }
    if (any_ppt) {
        ins(&it, "  PPT  (kg/cm²):\n", "heading");
        RegionList ppt_rgns; memset(&ppt_rgns, 0, sizeof(ppt_rgns));
        for (int i = 0; i < app->obj_point_count; i++) {
            ObjPoint *p = &app->obj_points[i];
            if (p->type != OBJ_POINT_PPT) continue;
            rlist_add(&ppt_rgns, body_region_name(p->view, (float)p->bx, (float)p->by));
        }
        for (int r = 0; r < ppt_rgns.n; r++) {
            char rh[80]; snprintf(rh, sizeof(rh), "    %s\n", ppt_rgns.r[r]);
            ins(&it, rh, "auto");
            for (int i = 0; i < app->obj_point_count; i++) {
                ObjPoint *p = &app->obj_points[i];
                if (p->type != OBJ_POINT_PPT) continue;
                if (strcmp(body_region_name(p->view, (float)p->bx, (float)p->by), ppt_rgns.r[r])) continue;
                char line[80]; snprintf(line, sizeof(line), "      %-20s", p->label[0] ? p->label : "—");
                ins(&it, line, "auto");
                char val[24]; snprintf(val, sizeof(val), "%.1f\n", p->value);
                ins(&it, val, "value");
            }
        }
        ins(&it, "\n", NULL);
        any_obj_output = TRUE;
    }

    gboolean any_ts = FALSE;
    for (int i = 0; i < app->obj_point_count; i++)
        if (app->obj_points[i].type == OBJ_POINT_TEMPORAL_SUM) { any_ts = TRUE; break; }
    if (any_ts) {
        ins(&it, "  Temporal summation  (0–10):\n", "heading");
        RegionList ts_rgns; memset(&ts_rgns, 0, sizeof(ts_rgns));
        for (int i = 0; i < app->obj_point_count; i++) {
            ObjPoint *p = &app->obj_points[i];
            if (p->type != OBJ_POINT_TEMPORAL_SUM) continue;
            rlist_add(&ts_rgns, body_region_name(p->view, (float)p->bx, (float)p->by));
        }
        for (int r = 0; r < ts_rgns.n; r++) {
            char rh[80]; snprintf(rh, sizeof(rh), "    %s\n", ts_rgns.r[r]);
            ins(&it, rh, "auto");
            for (int i = 0; i < app->obj_point_count; i++) {
                ObjPoint *p = &app->obj_points[i];
                if (p->type != OBJ_POINT_TEMPORAL_SUM) continue;
                if (strcmp(body_region_name(p->view, (float)p->bx, (float)p->by), ts_rgns.r[r])) continue;
                char line[80]; snprintf(line, sizeof(line), "      %-20s", p->label[0] ? p->label : "—");
                ins(&it, line, "auto");
                char val[24]; snprintf(val, sizeof(val), "%.0f/10\n", p->value);
                ins(&it, val, "value");
            }
        }
        ins(&it, "\n", NULL);
        any_obj_output = TRUE;
    }

    if (!any_obj_output)
        ins(&it, "  (no objective findings)\n\n", "muted");

    /* ══ PLAN ════════════════════════════════════════════════════════════════ */
    ins(&it, "── PLAN ", "section");
    ins(&it, "──────────────────────────────────────────────────────────────\n", "muted");
    ins_edit_region(&it, "plan_s", "plan_e", app->report.plan);

    /* ══ CLINICAL NOTES ══════════════════════════════════════════════════════ */
    ins(&it, "── CLINICAL NOTES ", "section");
    ins(&it, "──────────────────────────────────────────────────────────\n", "muted");
    ins_edit_region(&it, "notes_s", "notes_e", app->report.clinical_notes);

    ins(&it, "══════════════════════════════════════════════════════════════════\n", "divider");

    gtk_text_buffer_end_irreversible_action(g_buf);
    gtk_text_buffer_set_modified(g_buf, FALSE);
}

/* ── Toolbar callbacks ───────────────────────────────────────────────────── */
static void close_popover_safe(void)
{
    if (!g_cur_popover) return;
    GtkPopover *closing = g_cur_popover;
    g_cur_popover  = NULL;
    g_pop_tv       = NULL;
    g_pop_note_idx  = -1;
    g_pop_field_idx = -1;
    gtk_popover_popdown(closing);
}

static void on_regen_clicked(GtkButton *btn, gpointer data)
{
    (void)btn; (void)data;
    close_popover_safe();
    extract_editable_text();
    gen_buf();
    attach_note_btn_rows();
    if (g_status_lbl) gtk_label_set_text(GTK_LABEL(g_status_lbl), "Regenerated");
}
static void on_copyall_clicked(GtkButton *btn, gpointer data)
{
    (void)btn; (void)data;
    if (g_rpt_app) report_copy_all(g_rpt_app);
}
static void on_export_md_clicked(GtkButton *btn, gpointer data)
{
    (void)btn; (void)data;
    if (!g_rpt_app) return;
    extract_editable_text(); report_save_md(g_rpt_app);
}

/* ── Public API ──────────────────────────────────────────────────────────── */
GtkWidget *report_view_new(AppState *app)
{
    g_rpt_app = app;
    load_subj_template();

    GtkWidget *vbox = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_set_name(vbox, "report-root");
    gtk_widget_set_hexpand(vbox, TRUE);
    gtk_widget_set_vexpand(vbox, TRUE);

    GtkWidget *tb = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
    gtk_widget_set_name(tb, "report-toolbar");
    gtk_widget_set_margin_start(tb, 8);  gtk_widget_set_margin_end(tb, 8);
    gtk_widget_set_margin_top(tb, 4);    gtk_widget_set_margin_bottom(tb, 4);

    GtkWidget *regen_btn  = gtk_button_new_with_label("↺  Regenerate  F5");
    GtkWidget *copy_btn   = gtk_button_new_with_label("⎘  Copy All  Ctrl+Shift+C");
    GtkWidget *export_btn = gtk_button_new_with_label("↓  Export .md");
    gtk_widget_set_name(regen_btn, "rpt-btn");
    gtk_widget_set_name(copy_btn,  "rpt-btn");
    gtk_widget_set_name(export_btn,"rpt-btn");
    g_signal_connect(regen_btn,  "clicked", G_CALLBACK(on_regen_clicked),    NULL);
    g_signal_connect(copy_btn,   "clicked", G_CALLBACK(on_copyall_clicked),  NULL);
    g_signal_connect(export_btn, "clicked", G_CALLBACK(on_export_md_clicked),NULL);

    g_status_lbl = gtk_label_new("");
    gtk_widget_set_name(g_status_lbl, "report-status");
    gtk_widget_set_hexpand(g_status_lbl, TRUE);
    gtk_label_set_xalign(GTK_LABEL(g_status_lbl), 1.0);

    gtk_box_append(GTK_BOX(tb), regen_btn);
    gtk_box_append(GTK_BOX(tb), copy_btn);
    gtk_box_append(GTK_BOX(tb), export_btn);
    gtk_box_append(GTK_BOX(tb), g_status_lbl);
    gtk_box_append(GTK_BOX(vbox), tb);
    gtk_box_append(GTK_BOX(vbox), gtk_separator_new(GTK_ORIENTATION_HORIZONTAL));

    GtkWidget *sc = gtk_scrolled_window_new();
    gtk_widget_set_hexpand(sc, TRUE);
    gtk_widget_set_vexpand(sc, TRUE);

    GtkWidget *tv = gtk_text_view_new();
    gtk_widget_set_name(tv, "report-tv");
    gtk_text_view_set_monospace(GTK_TEXT_VIEW(tv), TRUE);
    gtk_text_view_set_editable(GTK_TEXT_VIEW(tv), TRUE);
    gtk_text_view_set_cursor_visible(GTK_TEXT_VIEW(tv), TRUE);
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(tv), GTK_WRAP_WORD_CHAR);
    gtk_text_view_set_left_margin(GTK_TEXT_VIEW(tv),   16);
    gtk_text_view_set_right_margin(GTK_TEXT_VIEW(tv),  16);
    gtk_text_view_set_top_margin(GTK_TEXT_VIEW(tv),    12);
    gtk_text_view_set_bottom_margin(GTK_TEXT_VIEW(tv), 12);

    g_text_view = tv;
    g_buf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(tv));
    create_tags();

    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(sc), tv);
    gtk_box_append(GTK_BOX(vbox), sc);
    return vbox;
}

void report_activate(AppState *app)
{
    g_rpt_app = app;
    if (!g_buf) return;
    close_popover_safe();
    extract_editable_text();
    gen_buf();
    attach_note_btn_rows();
    GtkTextMark *m = gtk_text_buffer_get_mark(g_buf, "assess_s");
    if (m && g_text_view) {
        GtkTextIter it;
        gtk_text_buffer_get_iter_at_mark(g_buf, &it, m);
        gtk_text_buffer_place_cursor(g_buf, &it);
        gtk_text_view_scroll_to_mark(GTK_TEXT_VIEW(g_text_view), m, 0.0, FALSE, 0.0, 0.0);
        gtk_widget_grab_focus(g_text_view);
    }
    if (g_status_lbl) gtk_label_set_text(GTK_LABEL(g_status_lbl), "");
}

void report_deactivate(AppState *app)
{
    g_rpt_app = app;
    extract_editable_text();
}

void report_copy_all(AppState *app)
{
    (void)app;
    if (!g_buf) return;
    GtkTextIter s, e;
    gtk_text_buffer_get_bounds(g_buf, &s, &e);
    char *text = gtk_text_buffer_get_text(g_buf, &s, &e, FALSE);
    GdkClipboard *cb = gdk_display_get_clipboard(gdk_display_get_default());
    gdk_clipboard_set_text(cb, text);
    g_free(text);
    if (g_status_lbl) gtk_label_set_text(GTK_LABEL(g_status_lbl), "Copied to clipboard");
}

void report_save_md(AppState *app)
{
    if (!app->session_dir[0] || !app->session_name[0]) return;
    extract_editable_text();

    char path[700];
    snprintf(path, sizeof(path), "%s/%s_report.md", app->session_dir, app->session_name);

    FILE *f = fopen(path, "w");
    if (!f) {
        if (g_status_lbl) gtk_label_set_text(GTK_LABEL(g_status_lbl), "Export failed");
        return;
    }

    time_t ct = app->session_created ? app->session_created : time(NULL);
    struct tm *t = localtime(&ct);
    char ds[20]; strftime(ds, sizeof(ds), "%d/%m/%Y", t);
    fprintf(f, "# PhysioChart Report\n\n");
    if (app->patient_id[0])    fprintf(f, "**Patient:** %s  \n", app->patient_id);
    if (app->session_label[0]) fprintf(f, "**Session:** %s  \n", app->session_label);
    fprintf(f, "**Date:** %s\n\n---\n\n## Subjective\n\n", ds);

    RegionList note_rgns[MAX_NOTES][SYMPTOM_COUNT];
    RegionList ungrouped[SYMPTOM_COUNT];
    memset(note_rgns, 0, sizeof(note_rgns));
    memset(ungrouped, 0, sizeof(ungrouped));
    for (int i = 0; i < app->strokes->n; i++) {
        Stroke *sk = app->strokes->strokes[i];
        if (sk->type == SYMPTOM_TICK) continue;
        if (sk->view < 0 || sk->view >= 8 || sk->type < 0 || sk->type >= SYMPTOM_COUNT) continue;
        if (sk->n_pts == 0) continue;
        double cx = 0, cy = 0;
        for (size_t j = 0; j < sk->n_pts; j++) { cx += sk->pts[j].x; cy += sk->pts[j].y; }
        cx /= (double)sk->n_pts; cy /= (double)sk->n_pts;
        const char *rgn = body_region_name(sk->view, (float)cx, (float)cy);
        int ni = assign_stroke_to_note(app, (float)cx, (float)cy, sk->view, rgn);
        if (ni >= 0 && ni < app->note_count) rlist_add(&note_rgns[ni][sk->type], rgn);
        else rlist_add(&ungrouped[sk->type], rgn);
    }

    for (int ni = 0; ni < app->note_count; ni++) {
        NoteAnnotation *n = &app->notes[ni];
        char qbuf[256] = {0};
        if (n->voice_note[0]) {
            g_strlcpy(qbuf, n->voice_note, sizeof(qbuf));
        } else {
            for (int q = 0; q < n->quality_count; q++) {
                if (q > 0) strncat(qbuf, " + ", sizeof(qbuf) - strlen(qbuf) - 1);
                int qi = n->qualities[q];
                const char *ql = (qi >= 0 && qi < NOTE_QUALITY_COUNT)
                                 ? QUALITY_LONG[qi] : "?";
                strncat(qbuf, ql, sizeof(qbuf) - strlen(qbuf) - 1);
            }
        }
        char fields[320] = {0}, ibuf[16];
        note_join(fields, sizeof(fields), " · ",
                  body_region_name(n->view, (float)n->bx, (float)n->by));
        note_join(fields, sizeof(fields), " · ", canvas_view_name((BodyView)n->view));
        note_join(fields, sizeof(fields), " · ", note_temporal_name(n->temporal));
        note_join(fields, sizeof(fields), " · ", note_depth_name(n->depth));
        note_join(fields, sizeof(fields), " · ", qbuf);
        note_join(fields, sizeof(fields), " · ", note_intensity_str(n, ibuf, sizeof(ibuf)));
        fprintf(f, "### Note (%d) — %s\n\n", n->number, fields);
        gboolean any = FALSE;
        char dist[256];
        for (int s = 0; s < SYMPTOM_COUNT; s++) {
            if (s == SYMPTOM_TICK) continue;
            if (!note_rgns[ni][s].n) continue;
            describe_distribution(note_rgns[ni][s].r, note_rgns[ni][s].n, dist, sizeof(dist));
            fprintf(f, "- **%s**: %s\n", SYMPTOM_DEFS[s].label, dist);
            any = TRUE;
        }
        if (!any) fprintf(f, "*(no symptoms mapped near this note)*\n");

        /* Subjective interview fields */
        for (int fi = 0; fi < SUBJ_FIELD_COUNT; fi++) {
            const char *fld = app->report.note_subj[ni].fields[fi];
            if (!fld[0]) continue;
            fprintf(f, "\n**%s:** %s", SUBJ_FIELD_LABELS[fi], fld);
        }
        fprintf(f, "\n\n");
    }

    gboolean any_ug = FALSE;
    for (int s = 0; s < SYMPTOM_COUNT; s++)
        if (s != SYMPTOM_TICK && ungrouped[s].n) { any_ug = TRUE; break; }
    if (any_ug) {
        fprintf(f, "### Other symptoms\n\n");
        char dist[256];
        for (int s = 0; s < SYMPTOM_COUNT; s++) {
            if (s == SYMPTOM_TICK || !ungrouped[s].n) continue;
            describe_distribution(ungrouped[s].r, ungrouped[s].n, dist, sizeof(dist));
            fprintf(f, "- **%s**: %s\n", SYMPTOM_DEFS[s].label, dist);
        }
        fprintf(f, "\n");
    }

    if (app->link_rel_count > 0) {
        fprintf(f, "### Connections\n\n");
        for (int i = 0; i < app->link_rel_count; i++) {
            LinkRel *lr = &app->link_relations[i];
            fprintf(f, "- Note %d %s Note %d\n",
                    lr->from+1, lr->state==LINK_YES ? "→" : "─/→", lr->to+1);
        }
        fprintf(f, "\n");
    }

    fprintf(f, "## Assessment\n\n%s\n\n", app->report.assessment[0] ? app->report.assessment : "");
    fprintf(f, "## Objective\n\n");

    gboolean obj_md_any = FALSE;
    if (app->obj_zone_count > 0) {
        RegionList zone_rgns[OBJ_ZONE_COUNT];
        memset(zone_rgns, 0, sizeof(zone_rgns));
        for (int i = 0; i < app->obj_zone_count; i++) {
            ObjZone *z = app->obj_zones[i];
            if (!z || z->n == 0) continue;
            int step = z->n > 8 ? z->n / 8 : 1;
            for (int j = 0; j < z->n; j += step) {
                const char *rgn = body_region_name(z->view, z->bx[j], z->by[j]);
                rlist_add(&zone_rgns[(int)z->type], rgn);
            }
        }
        fprintf(f, "### Zones\n\n");
        char dist[256];
        for (int t = 0; t < OBJ_ZONE_COUNT; t++) {
            if (zone_rgns[t].n == 0) continue;
            describe_distribution(zone_rgns[t].r, zone_rgns[t].n, dist, sizeof(dist));
            fprintf(f, "- **%s**: %s\n", OBJ_ZONE_DEFS[t].name, dist);
        }
        fprintf(f, "\n");
        obj_md_any = TRUE;
    }

    RegionList ppt_md; memset(&ppt_md, 0, sizeof(ppt_md));
    for (int i = 0; i < app->obj_point_count; i++) {
        ObjPoint *p = &app->obj_points[i];
        if (p->type == OBJ_POINT_PPT)
            rlist_add(&ppt_md, body_region_name(p->view, (float)p->bx, (float)p->by));
    }
    if (ppt_md.n > 0) {
        fprintf(f, "### PPT (kg/cm²)\n\n");
        for (int r = 0; r < ppt_md.n; r++) {
            fprintf(f, "**%s**\n\n", ppt_md.r[r]);
            for (int i = 0; i < app->obj_point_count; i++) {
                ObjPoint *p = &app->obj_points[i];
                if (p->type != OBJ_POINT_PPT) continue;
                if (strcmp(body_region_name(p->view, (float)p->bx, (float)p->by), ppt_md.r[r])) continue;
                fprintf(f, "- %s: **%.1f**\n", p->label[0] ? p->label : "—", p->value);
            }
            fprintf(f, "\n");
        }
        obj_md_any = TRUE;
    }

    RegionList ts_md; memset(&ts_md, 0, sizeof(ts_md));
    for (int i = 0; i < app->obj_point_count; i++) {
        ObjPoint *p = &app->obj_points[i];
        if (p->type == OBJ_POINT_TEMPORAL_SUM)
            rlist_add(&ts_md, body_region_name(p->view, (float)p->bx, (float)p->by));
    }
    if (ts_md.n > 0) {
        fprintf(f, "### Temporal Summation (0–10)\n\n");
        for (int r = 0; r < ts_md.n; r++) {
            fprintf(f, "**%s**\n\n", ts_md.r[r]);
            for (int i = 0; i < app->obj_point_count; i++) {
                ObjPoint *p = &app->obj_points[i];
                if (p->type != OBJ_POINT_TEMPORAL_SUM) continue;
                if (strcmp(body_region_name(p->view, (float)p->bx, (float)p->by), ts_md.r[r])) continue;
                fprintf(f, "- %s: **%.0f/10**\n", p->label[0] ? p->label : "—", p->value);
            }
            fprintf(f, "\n");
        }
        obj_md_any = TRUE;
    }

    if (!obj_md_any) fprintf(f, "*(no objective findings)*\n\n");

    fprintf(f, "## Plan\n\n%s\n\n", app->report.plan[0] ? app->report.plan : "");
    fprintf(f, "## Clinical Notes\n\n%s\n", app->report.clinical_notes[0] ? app->report.clinical_notes : "");

    fclose(f);
    if (g_status_lbl) {
        char msg[120];
        snprintf(msg, sizeof(msg), "Exported → %s_report.md", app->session_name);
        gtk_label_set_text(GTK_LABEL(g_status_lbl), msg);
    }
}
