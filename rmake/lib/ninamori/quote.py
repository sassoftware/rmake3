#
# Copyright (c) 2009 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.

import re


_QID_CACHE = {}
SAFE_IDENTIFIER = re.compile('^[a-z_][a-z0-9_]*$')


def quoteIdentifier(name):
    if name in _QID_CACHE:
        return _QID_CACHE[name]

    if '"' in name:
        raise ValueError("Double quotes cannot appear in SQL identifiers.")

    if SAFE_IDENTIFIER.search(name):
        quoted = name
    else:
        quoted = '"%s"' % (name,)

    _QID_CACHE[name] = quoted
    return quoted


def quoteString(val):
    # TODO: implement this!
    return repr(val)
