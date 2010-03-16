#
# Copyright (c) 2009-2010 rPath, Inc.
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
from rmake.lib.ninamori.types import DependencySet


class Schema(object):
    def __init__(self):
        self.version = None
        self.tables = None

    def diff(self, old=None, newOnly=False):
        out = []
        for name, table in self.tables.items():
            oldTable = old and old.tables.get(name)
            if newOnly and oldTable is not None:
                # Ignore overlapping tables as long as they have the same
                # definition.
                oldHash = oldTable.asTuple()
                newHash = table.asTuple()
                if oldHash != newHash:
                    # TODO: use a real exception
                    import epdb;epdb.st()
                    raise RuntimeError("Conflicting definitions for table %r "
                            "while creating schema" % (name,))
                continue
            out.extend(table.diff(oldTable))
        if old and not newOnly:
            for name in set(old.tables) - set(self.tables):
                oldTable = old[table]
                out.extend(oldTable.drop())
        return out

    def getDependencies(self):
        deps = DependencySet()
        for table in self.tables.values():
            deps.update(table.getDependencies())
        return deps


class SchemaVersion(tuple):
    """Representation of a schema version as a tuple of tuples of integers.

    A version consists of a number of underscore-separated elements, each of
    which are a dotted sequence of integers, e.g. 5.2_18. These elemenents map
    directly to tuples, e.g. ((5, 2), (18,)).
    """

    def __new__(cls, val):
        ret = []
        if isinstance(val, basestring):
            # String form
            for element in val.split('_'):
                subout = []
                for sub in element.split('.'):
                    if not sub.isdigit():
                        raise ValueError("Invalid schema version %r" % (val,))
                    subout.append(int(sub))
                ret.append(tuple(subout))
        else:
            # Tuple form
            for element in val:
                for sub in element:
                    if not isinstance(sub, int) or sub < 0:
                        raise ValueError("Invalid schema version %r" % (val,))
                ret.append(tuple(element))
        return tuple.__new__(cls, ret)

    def asString(self):
        return '_'.join('.'.join(str(y) for y in x) for x in self)
    __str__ = asString

    def __repr__(self):
        return 'SchemaVersion(%r)' % (self.asString(),)
