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


class Action(DependencySet):
    def asSQL(self):
        raise NotImplementedError


# Tables
class CreateTable(Action):
    def __init__(self, table):
        Action.__init__(self, table.getDependencies())
        self.table = table

    def __repr__(self):
        return 'CreateTable(%r)' % (self.table.name,)

    def asSQL(self):
        return self.table.asSQL()


class FieldAction(Action):
    def __init__(self, table, field):
        Action.__init__(self, field.getDependencies(table))
        self.table = table
        self.field = field

    def __repr__(self):
        return '%s(%r, %r)' % (self.__class__.__name__,
                self.table.name, self.field.name)


# Columns
class ColumnAction(FieldAction):
    pass


class AddColumn(ColumnAction):
    def asSQL(self):
        return SQL('ALTER TABLE %s ADD COLUMN %s;' % (
                quoteIdentifier(self.table.name),
                self.field.asSQL(table=self.table)))


class DropColumn(ColumnAction):
    def asSQL(self):
        return SQL('ALTER TABLE %s DROP COLUMN %s;' % (
                quoteIdentifier(self.table.name),
                quoteIdentifier(self.field.name)))


class AlterColumn(ColumnAction):
    def __init__(self, newTable, oldCol, newCol):
        ColumnAction.__init__(self, newTable, newCol)
        self.oldColumn = oldCol

    def _defaultChanged(self):
        return (type(self.oldColumn.default) != type(self.field.default) or
                self.oldColumn.default != self.field.default)

    def asSQL(self):
        ret = SQL('ALTER TABLE %s ' % (quoteIdentifier(self.table.name),) )
        old, new = self.oldColumn, self.field
        actions = []
        if old.asTuple(False) != new.asTuple(False):
            if old.default is not None and self._defaultChanged():
                # Always drop the default first if changing types.
                actions.append('DROP DEFAULT')
            actions.append('TYPE ' + new.typeAsSQL())
        if old.not_null != new.not_null:
            if new.not_null:
                actions.append('SET NOT NULL')
            else:
                actions.append('DROP NOT NULL')
        if self._defaultChanged():
            if new.default is not None:
                actions.append('SET DEFAULT ' + new.defaultAsSQL())
            elif 'DROP DEFAULT' not in actions:
                actions.append('DROP DEFAULT')

        assert actions # If nothing changed, why did we get called?
        alter = 'ALTER COLUMN %s ' % (quoteIdentifier(new.name),)
        ret += SQL.rjoin((alter + x for x in actions), ', ')
        return ret


# Indexes
class IndexAction(FieldAction):
    pass


class AddIndex(ColumnAction):
    def asSQL(self):
        return self.field.asSQL(table=self.table)
