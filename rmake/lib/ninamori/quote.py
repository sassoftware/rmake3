#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


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
