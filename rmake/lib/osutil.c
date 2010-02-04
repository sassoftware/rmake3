/*
 *
 * Copyright (c) 2010 rPath, Inc.
 *
 * This program is distributed under the terms of the Common Public License,
 * version 1.0. A copy of this license should have been distributed with this
 * source file in a file called LICENSE. If it is not present, the license
 * is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
 *
 * This program is distributed in the hope that it will be useful, but
 * without any warranty; without even the implied warranty of merchantability
 * or fitness for a particular purpose. See the Common Public License for
 * full details.
 *
 * setproctitle: portions Copyright (c) 2000-2010, PostgreSQL Global Development Group
 */

#include <Python.h>

#include <string.h>

#include "pycompat.h"


/* setproctitle */
static char *ps_buffer = 0;
static size_t ps_buffer_size;

extern char **environ;

void Py_GetArgcArgv(int *argc, char ***argv);

int
setproctitle_init() {
    int argc, i;
    char **argv;
    char *end_of_area = NULL;
    char **new_environ;

    if (ps_buffer) {
        /* Already done. */
        return 0;
    }

    Py_GetArgcArgv(&argc, &argv);
    if (!argv) {
        PyErr_SetString(PyExc_RuntimeError,
                "setproctitle_init failed: argv not available");
        return -1;
    }

    /* The idea here is to find the biggest chunk of contiguous memory
     * starting at argv[0] and extending through the rest of the arguments
     * and all of the environment, which will usually be adjacent. Then
     * we allocate a new place for environ to live and overwrite argv[0]
     * with anything we want, as long as it doesn't go past the end of the
     * old environ.
     */

    /* check for contiguous argv strings */
    for (i = 0; i < argc; i++) {
        if (i == 0 || end_of_area + 1 == argv[i]) {
            end_of_area = argv[i] + strlen(argv[i]);
        }
    }

    if (end_of_area == NULL) {
        PyErr_SetString(PyExc_RuntimeError,
                "setproctitle_init failed (empty environment?)");
        return -1;
    }

    /* check for contiguous environ strings following argv */
    for (i = 0; environ[i] != NULL; i++) {
        if (end_of_area + 1 == environ[i]) {
            end_of_area = environ[i] + strlen(environ[i]);
        }
    }

    /* move the environment out of the way */
    new_environ = malloc((i + 1) * sizeof(char *));
    for (i = 0; environ[i] != NULL; i++) {
        new_environ[i] = strdup(environ[i]);
    }
    new_environ[i] = NULL;
    environ = new_environ;

    ps_buffer = argv[0];
    ps_buffer_size = end_of_area - argv[0];

    /* make extra argv slots point at end_of_area (a NUL) */
    for (i = 1; i < argc; i++) {
        argv[i] = end_of_area;
    }

    return 0;
}


PyDoc_STRVAR(osutil_setproctitle__doc__,
        "osutil_setproctitle(title)\n"
        "Change the current process' title, as it appears in `ps`.");

static PyObject *
osutil_setproctitle(PyObject *self, PyObject *args) {
    char *title;

    if (!PyArg_ParseTuple(args, "s", &title)) {
        return NULL;
    }

    if (setproctitle_init()) {
        return NULL;
    }

    ps_buffer[ps_buffer_size - 1] = 0;
    /* note that strncpy pads unused space with null bytes */
    strncpy(ps_buffer, title, ps_buffer_size - 1);

    Py_RETURN_NONE;
}


/* module boilerplate */

static PyMethodDef OSMethods[] = {
    { "setproctitle", osutil_setproctitle, METH_VARARGS, osutil_setproctitle__doc__ },
    { NULL }
};


PYMODULE_DECLARE(osutil, "rmake.lib.osutil",
        "miscellaneous OS utilities", OSMethods);

/* vim: set sts=4 sw=4 expandtab : */
