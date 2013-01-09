#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
