/*
 * Copyright (c) rPath, Inc.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */


#include <Python.h>

#include <sched.h>
#include <signal.h>
#include <unistd.h>
#include <sys/capability.h>
#include <sys/prctl.h>

#include "pycompat.h"


static PyObject *
pycap_set_keepcaps(PyObject *self, PyObject *args) {
    int keep_caps;

    if (!PyArg_ParseTuple(args, "i", &keep_caps)) {
        return NULL;
    }

    /* make sure it is exactly 0 or 1 */
    keep_caps = !!keep_caps;

    if (prctl(PR_SET_KEEPCAPS, keep_caps, 0, 0, 0)) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }

    Py_RETURN_NONE;
}


static PyObject *
pycap_set_proc(PyObject *self, PyObject *args) {
    char *cap_str;
    cap_t cap;

    if (!PyArg_ParseTuple(args, "s", &cap_str)) {
        return NULL;
    }

    if ((cap = cap_from_text(cap_str)) == NULL) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }

    if (cap_set_proc(cap)) {
        PyErr_SetFromErrno(PyExc_OSError);
        cap_free(cap);
        return NULL;
    }
    cap_free(cap);
    Py_RETURN_NONE;
}


static PyObject *
pycap_get_proc(PyObject *self, PyObject *noargs) {
    char *cap_str;
    cap_t cap;
    ssize_t cap_str_len;

    if ((cap = cap_get_proc()) == NULL) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }

    if ((cap_str = cap_to_text(cap, &cap_str_len)) == NULL) {
        PyErr_SetFromErrno(PyExc_OSError);
        cap_free(cap);
        return NULL;
    }
    cap_free(cap);

    return PyString_FromStringAndSize(cap_str, cap_str_len);
}


static PyMethodDef CapMethods[] = {
    { "set_keepcaps", pycap_set_keepcaps, METH_VARARGS,
        "Set the \"keep capabilities\" flag on the current process" },
    { "cap_set_proc", pycap_set_proc, METH_VARARGS,
        "Set the capability flags for the current process" },
    { "cap_get_proc", pycap_get_proc, METH_NOARGS,
        "Get the capability flags for the current process" },
    { NULL }
};


PYMODULE_DECLARE(pycap, "python wrapper for libcap", CapMethods);

/* vim: set sts=4 sw=4 expandtab : */
