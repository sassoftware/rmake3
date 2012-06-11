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


"""
This module contains miscellaneous tools for iterating over and manipulating
SQL cursors and result sets.
"""


def fold(items, numCols=1, numUniq=None):
    """
    Iterate over a sorted list of C{items}, grouping by the first C{numCols}
    elements of each tuple and yielding each time a new selector is
    encountered.
    
    If C{numUniq} is given, that many columns are tested for equality but all
    C{numCols} columns are returned as the "key". For example, C{fold(foo, 1,
    3)} groups based on the first column's value, but returns the first 3
    columns as a key.

    This is similar to L{itertools.groupby()}, but maps more directly to
    operations such as iterating over a SQL cursor.
    """
    if numUniq is None:
        numUniq = numCols
    assert numUniq <= numCols
    last, values = (), []
    for item in items:
        key, value = item[:numCols], item[numCols:]
        if key[:numUniq] != last[:numUniq]:
            if last:
                if numCols == 1:
                    last = last[0]
                yield last, values
            last, values = key, []
        values.append(value)
    if last:
        if numCols == 1:
            last = last[0]
        yield last, values
