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
