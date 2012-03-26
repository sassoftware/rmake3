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

#include "pycompat.h"


extern char osutil_setproctitle__doc__[];
PyObject *osutil_setproctitle(PyObject *self, PyObject *args);


/* module boilerplate */

static PyMethodDef OSMethods[] = {
    { "setproctitle", osutil_setproctitle, METH_VARARGS, osutil_setproctitle__doc__ },
    { NULL }
};


PYMODULE_DECLARE(osutil, "miscellaneous OS utilities", OSMethods);

/* vim: set sts=4 sw=4 expandtab : */
