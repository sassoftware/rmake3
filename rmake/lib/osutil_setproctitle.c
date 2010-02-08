/*
 * Copyright (c) 2010 rPath, Inc.
 * Copyright (c) 2000-2008, PostgreSQL Global Development Group
 *
 * Permission to use, copy, modify, and distribute this software and its
 * documentation for any purpose, without fee, and without a written agreement
 * is hereby granted, provided that the above copyright notice and this
 * paragraph and the following two paragraphs appear in all copies.
 *
 * IN NO EVENT SHALL THE UNIVERSITY OF CALIFORNIA BE LIABLE TO ANY PARTY FOR
 * DIRECT, INDIRECT, SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES, INCLUDING
 * LOST PROFITS, ARISING OUT OF THE USE OF THIS SOFTWARE AND ITS
 * DOCUMENTATION, EVEN IF THE UNIVERSITY OF CALIFORNIA HAS BEEN ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 *
 * THE UNIVERSITY OF CALIFORNIA SPECIFICALLY DISCLAIMS ANY WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS FOR A PARTICULAR PURPOSE.  THE SOFTWARE PROVIDED HEREUNDER IS
 * ON AN "AS IS" BASIS, AND THE UNIVERSITY OF CALIFORNIA HAS NO OBLIGATIONS TO
 * PROVIDE MAINTENANCE, SUPPORT, UPDATES, ENHANCEMENTS, OR MODIFICATIONS.
 */

#include <Python.h>

#include <string.h>

#include "pycompat.h"


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


char osutil_setproctitle__doc__[] = PyDoc_STR(
        "osutil_setproctitle(title)\n"
        "Change the current process' title, as it appears in `ps`.");

PyObject *
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


/* vim: set sts=4 sw=4 expandtab : */
