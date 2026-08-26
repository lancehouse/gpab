#include "py_embed.h"
#include "canvas.h"   /* full AppState definition (app->window) */
#include <Python.h>
#include <gtk/gtk.h>

/* Hardcoded to this worktree — matches how GPAB_PYTHON/GPAB_WORKDIR worked
 * before the dev/stable split's wrapper-script indirection (see
 * integration.c's history), but that trick doesn't apply here: embedding
 * is direct in-process linkage, not a spawned subprocess, so there's no
 * "just change one $PATH-resolved command name" lever — the interpreter
 * and its sys.path have to be correct before Py_Initialize() even runs.
 * These two paths are meant to differ per worktree, same shape as
 * integration.c's GPAB_LAUNCHER divergence between dev and main — when
 * this is ever promoted to gpab-stable/main, that copy of this file needs
 * s/\/Projects\/gpab\//\/Projects\/gpab\/gpab-stable\// on both lines (see
 * CLAUDE.md's "Branch and deployment rules"). */
#define GPAB_SITE_PACKAGES "/home/lance/Projects/gpab/assessment_gtk/.venv/lib/python3.14/site-packages"
#define GPAB_APP_ROOT      "/home/lance/Projects/gpab/assessment_gtk"

static AppState *g_app = NULL;
static PyObject *g_gpab_window = NULL;  /* strong ref to the TrialWindow instance */

/* ── bodychart_bridge — the C extension module exposed TO Python ────────── */

static PyObject *bb_present(PyObject *self, PyObject *Py_UNUSED(args))
{
    (void)self;
    if (g_app && g_app->window)
        gtk_window_present(GTK_WINDOW(g_app->window));
    Py_RETURN_NONE;
}

static PyObject *bb_close(PyObject *self, PyObject *Py_UNUSED(args))
{
    (void)self;
    if (g_app && g_app->window)
        gtk_window_close(GTK_WINDOW(g_app->window));
    Py_RETURN_NONE;
}

static PyMethodDef bb_methods[] = {
    {"present", bb_present, METH_NOARGS, "Raise bodychart's window."},
    {"close",   bb_close,   METH_NOARGS, "Close bodychart's window."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef bb_module_def = {
    PyModuleDef_HEAD_INIT, "bodychart_bridge",
    "Direct in-process calls back into bodychart's own C GTK window — see "
    "py_embed.h and app.py::build_embedded.",
    -1, bb_methods
};

static PyObject *PyInit_bodychart_bridge(void)
{
    return PyModule_Create(&bb_module_def);
}

/* ── Public API ───────────────────────────────────────────────────────── */

void py_embed_init(AppState *app)
{
    g_app = app;

    /* Must run before Py_Initialize() — this is the documented way to add
     * a built-in extension module that plain Python code can `import`
     * without it existing as a .so on disk anywhere. */
    PyImport_AppendInittab("bodychart_bridge", PyInit_bodychart_bridge);

    Py_Initialize();

    PyRun_SimpleString(
        "import sys\n"
        "sys.path.insert(0, '" GPAB_SITE_PACKAGES "')\n"
        "sys.path.insert(0, '" GPAB_APP_ROOT "')\n"
    );
}

void py_embed_open_session(const char *session_file)
{
    PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject *app_module = PyImport_ImportModule("gpab_assessment.app");
    if (!app_module) {
        g_warning("py_embed_open_session: failed to import gpab_assessment.app");
        PyErr_Print();
        PyGILState_Release(gstate);
        return;
    }

    PyObject *build_func = PyObject_GetAttrString(app_module, "build_embedded");
    Py_DECREF(app_module);
    if (!build_func) {
        g_warning("py_embed_open_session: gpab_assessment.app.build_embedded not found");
        PyErr_Print();
        PyGILState_Release(gstate);
        return;
    }

    PyObject *arg = PyUnicode_FromString(session_file);
    PyObject *win = PyObject_CallFunctionObjArgs(build_func, arg, NULL);
    Py_DECREF(arg);
    Py_DECREF(build_func);

    if (!win) {
        g_warning("py_embed_open_session: build_embedded() raised");
        PyErr_Print();
        PyGILState_Release(gstate);
        return;
    }

    if (g_gpab_window)
        Py_DECREF(g_gpab_window);
    g_gpab_window = win;  /* takes ownership of the reference */

    PyGILState_Release(gstate);
}

void py_embed_present_gpab(void)
{
    if (!g_gpab_window) return;
    PyGILState_STATE gstate = PyGILState_Ensure();
    PyObject *res = PyObject_CallMethod(g_gpab_window, "present", NULL);
    if (!res) {
        g_warning("py_embed_present_gpab: .present() raised");
        PyErr_Print();
    } else {
        Py_DECREF(res);
    }
    PyGILState_Release(gstate);
}

void py_embed_close_gpab(void)
{
    if (!g_gpab_window) return;
    PyGILState_STATE gstate = PyGILState_Ensure();
    PyObject *res = PyObject_CallMethod(g_gpab_window, "close", NULL);
    if (!res) {
        g_warning("py_embed_close_gpab: .close() raised");
        PyErr_Print();
    } else {
        Py_DECREF(res);
    }
    PyGILState_Release(gstate);
}

void py_embed_shutdown(void)
{
    if (g_gpab_window) {
        Py_DECREF(g_gpab_window);
        g_gpab_window = NULL;
    }
    if (Py_IsInitialized())
        Py_Finalize();
}
