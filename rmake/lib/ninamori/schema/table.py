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

from rmake.lib.ninamori.quote import quoteIdentifier
from rmake.lib.ninamori.types import DependencySet, SQL
from rmake.lib.ninamori.schema import migrate


class Table(object):
    def __init__(self, name, columns=(), indexes=(), constraints=(),
            isTemporary=False):
        self.name = name
        self.columns = dict(columns)
        self.indexes = dict(indexes)
        self.constraints = dict(constraints)
        self.isTemporary = isTemporary

    def __repr__(self):
        return 'Table(%r, %r)' % (self.name, list(self.columns))

    def _tableDone(self):
        for field in (self.columns.values() + self.indexes.values() +
                self.constraints.values()):
            field._tableDone(self)

    def _reindexColumns(self):
        for n, field in enumerate(sorted(self.columns.values(),
                key=lambda x: x._serial)):
            field.index = n + 1

    def asSchemaDef(self):
        skipFields = set()
        kw = dict(table=self, skipFields=skipFields)
        fmt = '    %-27s = %s'

        out = ['class %s:' % self.name]
        for field in self._getOrderedColumns():
            out.append(fmt % (field.name, field.asSchemaDef(**kw)))

        if self.constraints:
            out.append('')
            for name, field in sorted(self.constraints.items()):
                if name in skipFields:
                    continue
                out.append(fmt % (field.name, field.asSchemaDef(**kw)))
            if not out[-1]:
                out.pop()

        if self.indexes:
            out.append('')
            for name, field in sorted(self.indexes.items()):
                if name in self.constraints or name in skipFields:
                    continue
                out.append(fmt % (field.name, field.asSchemaDef(**kw)))
            if not out[-1]:
                out.pop()

        out.append('')
        return '\n'.join(out)

    def asSQL(self, **kwargs):
        kw = dict(table=self)
        sql = SQL('CREATE%s TABLE %s (\n    ' % (
                (self.isTemporary and ' TEMPORARY' or ''),
                quoteIdentifier(self.name)))
        fields = []
        for field in self._getOrderedColumns():
            fields.append(field.asSQL(**kw))
        for _, field in sorted(self.constraints.items()):
            fields.append(field.asSQL(**kw))
        sql += SQL.rjoin(fields, ',\n    ') + '\n    )'
        return sql

    def asTuple(self):
        fields = []
        for _, field in sorted(self.columns.items()):
            fields.append(field.asTuple())
        for _, field in sorted(self.constraints.items()):
            fields.append(field.asTuple())
        for _, field in sorted(self.indexes.items()):
            fields.append(field.asTuple())
        return (self.__class__, self.name, fields)

    def getDependencies(self):
        deps = DependencySet([('table', self.name)])
        for field in (self.columns.values() + self.constraints.values() +
                self.indexes.values()):
            deps.update(field.getDependencies(self))
        return deps

    def diff(self, old=None):
        if old is None:
            out = [ migrate.CreateTable(self) ]
            for field in self.indexes.values():
                out.append(migrate.AddIndex(self, field))
            return out

        out = []
        oldCols = set(x.name for x in old.columns)
        newCols = set(x.name for x in self.columns)
        for name in oldCols - newCols:
            out.append(migrate.DropColumn(old, old[name]))
        for name in newCols - oldCols:
            out.append(migrate.AddColumn(self, self[name]))
        for name in oldCols & newCols:
            oldCol, newCol = old[name], self[name]
            if oldCol != newCol:
                out.append(migrate.AlterColumn(self, oldCol, newCol))

        return out

    def _getColumnByIndex(self, index):
        for field in self.columns.values():
            if field.index == index:
                return field
        raise IndexError(index)

    def _getOrderedColumns(self):
        return sorted(self.columns.values(), key=lambda x: x.index)
