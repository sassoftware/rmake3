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

from rmake.lib.ninamori.quote import quoteIdentifier, quoteString
from rmake.lib.ninamori.types import constants, DependencySet, SQL


_FIELD_SERIAL = 0


# Flags for schema column definitions
ColFlags = constants('ColFlags', 'NOT_NULL', prefix=False)

# Foreign key actions.
FKeyActions = constants('FKeyActions',
        'NO_ACTION RESTRICT CASCADE SET_NULL SET_DEFAULT', prefix=False)


class _Field(object):
    index = None
    name = None

    _args = ()
    _extra_args = ()

    def _format(self, forSchema=False):
        if forSchema:
            # Strip trailing None values
            args = self._formatArgsForSQL()
        else:
            # Use keyword arguments
            keys = ('name',) + self._extra_args + self._args
            values = [getattr(self, x) for x in keys]
            args = ', '.join('%s=%r' % (key, value)
                    for (key, value) in zip(keys, values)
                    if value is not None)

        return '%s(%s)' % (self.__class__.__name__, args)

    def _formatArgsForSQL(self):
        values = [getattr(self, x) for x in self._args]
        while values and values[-1] is None:
            values.pop()
        return ', '.join(repr(x) for x in values)

    def __repr__(self):
        return self._format()

    def __eq__(self, other):
        return isinstance(other, _Field) and self.asTuple() == other.asTuple()

    def __ne__(self, other):
        return (not isinstance(other, _Field)
                or self.asTuple() != other.asTuple())

    def canInline(self, table, column):
        return False

    def getDefaultName(self, table):
        return None

    def asSchemaDef(self, **kwargs):
        raise NotImplementedError

    def asSQL(self, **kwargs):
        raise NotImplementedError

    def asTuple(self, extra=True):
        args = ('__class__', 'name')
        if extra:
            args += self._extra_args
        args += self._args
        return tuple(getattr(self, x) for x in args)

    @staticmethod
    def _resolveColumns(columns):
        columns = list(columns)
        for n, col in enumerate(columns):
            if isinstance(col, tuple):
                col = col[0]
            if isinstance(col, _Column):
                assert col.name is not None
                columns[n] = col.name
        return tuple(columns)

    @staticmethod
    def _displayColumns(columns, table=None, likeTuple=False):
        if table:
            colnames = list(table.columns)
        else:
            colnames = []

        out = []
        for col in columns:
            if col in colnames:
                out.append(col)
            else:
                out.append(repr(col))

        if likeTuple and len(out) == 1:
            out.append('')

        return ', '.join(out).rstrip()

    @staticmethod
    def _quoteColumns(columns):
        return ', '.join(quoteIdentifier(x) for x in columns)

    def _tableDone(self, table):
        pass

    def getDependencies(self, table):
        return DependencySet()


# Column bases

class _Column(_Field):
    auto_increment = False
    not_null = False
    default = None
    _extra_args = ('not_null', 'default')

    def __init__(self):
        global _FIELD_SERIAL
        _FIELD_SERIAL += 1
        self._serial = _FIELD_SERIAL

    def asSchemaDef(self, **kwargs):
        ret = [self._format(forSchema=True)]
        if self.not_null:
            ret.append('NOT_NULL')
        if self.default is not None:
            ret.append('Default(%r)' % (self.default,))

        table = kwargs.get('table')
        skipFields = kwargs.get('skipFields', set())
        if table:
            for field in table.constraints.values() + table.indexes.values():
                if not field.canInline(table, self):
                    continue
                if isinstance(field, PrimaryKey) and self.not_null:
                    ret.remove('NOT_NULL')
                ret.append(field.asSchemaDef(table=table, inline=True))
                skipFields.add(field.name)

        return ', '.join(ret)

    def typeAsSQL(self, **kwargs):
        if hasattr(self, 'type'):
            ret = self.type
        elif hasattr(self, '_names'):
            ret = self._names[0]
        else:
            raise RuntimeError("No SQL type defined for %r" % (self,))
        if getattr(self, '_args', ()):
            args = self._formatArgsForSQL()
            if args:
                ret += '(%s)' % (args,)
        return SQL(ret)

    def defaultAsSQL(self, **kwargs):
        if self.default is None:
            return None
        elif isinstance(self.default, basestring):
            ret = quoteString(self.default)
        elif isinstance(self.default, (int, long, float)):
            ret = str(self.default)
        elif isinstance(self.default, Expression):
            ret = self.default.expr
        else:
            raise TypeError("Bad default value %r" % (self.default,))
        return SQL(ret)

    def asSQL(self, **kwargs):
        ret = SQL(quoteIdentifier(self.name) + ' ')
        ret += self.typeAsSQL(**kwargs)
        if self.not_null:
            ret += ' NOT NULL'
        if self.default is not None:
            ret += ' DEFAULT ' + self.defaultAsSQL(**kwargs)
        return ret

    def getDependencies(self, table):
        return DependencySet([('column', table.name, self.name)])


class Column(_Column):
    _args = ('type',)

    def __init__(self, coltype):
        _Column.__init__(self)
        self.type = coltype


# Integers

class Integer(_Column):
    width = 4
    _names = ('integer', 'int', 'int4')

class SmallInt(Integer):
    width = 2
    _names = ('smallint', 'int2')

class BigInt(Integer):
    width = 8
    _names = ('bigint', 'int8')

class Serial(Integer):
    auto_increment = True
    _names = ('serial',)

class BigSerial(BigInt):
    auto_increment = True
    _names = ('bigserial',)

class Boolean(_Column):
    _names = ('bool', 'boolean')


# Other numeric

class Numeric(_Column):
    _names = ('numeric', 'decimal')
    _args = ('precision', 'scale')

    def __init__(self, precision=None, scale=None):
        _Column.__init__(self)
        self.precision = precision
        self.scale = scale


# Character data

class String(_Column):
    _names = ('varchar', 'character varying')
    _args = ('width',)

    def __init__(self, width=None):
        _Column.__init__(self)
        self.width = width


class FixedString(String):
    _names = ('char', 'character',)


class Text(_Column):
    _names = ('text',)


# Binary data

class Bytes(_Column):
    _names = ('bytea', 'blob')


# Dates and times
class Date(_Column):
    _names = ('date',)

class Timestamp(_Column):
    _names = ('timestamp', 'timestamp without time zone')

class TimestampWithZone(_Column):
    _names = ('timestamp with time zone')


# Indexes

class Index(_Field):
    _args = ('columns', 'expression')
    unique = False

    def __init__(self, *columns):
        _Field.__init__(self)
        if len(columns) == 1 and isinstance(columns[0], Expression):
            self.columns, self.expression = None, columns[0]
        else:
            assert columns
            self.columns, self.expression = columns, None
        
    def _tableDone(self, table):
        if self.columns:
            self.columns = self._resolveColumns(self.columns)

    def asSchemaDef(self, table=None, **kwargs):
        cname = self.__class__.__name__
        if kwargs.get('inline'):
            return '%s()' % (cname,)
        elif self.columns:
            columns = self._displayColumns(self.columns, table)
            return '%s(%s)' % (cname, columns)
        else:
            return '%s(%r)' % (cname, self.expression)

    def asSQL(self, table, **kwargs):
        if self.columns:
            expression = self._quoteColumns(self.columns)
        else:
            expression = self.expression.expr
        return SQL('CREATE%s INDEX %s ON %s ( %s )' % (
                (self.unique and ' UNIQUE' or ''), self.name, table.name,
                expression))

    def getDependencies(self, table):
        ret = DependencySet([('index', table.name, self.name)])
        if self.columns:
            ret.requires.add((('column', table.name, x) for x in self.columns))
        else:
            ret.requires.add(('table', table.name))
        return ret


class UniqueIndex(Index):
    unique = True


# Constraints

class _Constraint(_Field):
    keys = None

    def canInline(self, table, column):
        if not self.keys or len(self.keys) != 1 or self.keys[0] != column.name:
            return False
        if self.getDefaultName(table) != self.name:
            return False
        return True

    def getDependencies(self, table):
        return DependencySet([('constraint', table.name, self.name)])


class Unique(_Constraint):
    _args = ('keys',)
    _sql_name = 'UNIQUE'

    def __init__(self, *keys):
        _Constraint.__init__(self)
        self.keys = keys

    def _tableDone(self, table):
        self.keys = self._resolveColumns(self.keys)

    def asSchemaDef(self, table=None, inline=False, **kwargs):
        cname = self.__class__.__name__
        if inline:
            return '%s()' % cname
        else:
            keys = self._displayColumns(self.keys, table)
            return '%s(%s)' % (cname, keys)

    def asSQL(self, **kwargs):
        return SQL('CONSTRAINT %s %s ( %s )' % (quoteIdentifier(self.name),
                self._sql_name, self._quoteColumns(self.keys)))

    def getDefaultName(self, table):
        if len(self.keys) == 1:
            return '%s_%s_key' % (table.name, self.keys[0])
        return None

    def getDependencies(self, table):
        return DependencySet(
                provides=[('constraint', table.name, self.name)],
                requires=(('column', table.name, x) for x in self.keys))


class PrimaryKey(Unique):
    _sql_name = 'PRIMARY KEY'

    def _tableDone(self, table):
        Unique._tableDone(self, table)
        for key in self.keys:
            table.columns[key].not_null = True

    def getDefaultName(self, table):
        return '%s_pkey' % (table.name)


class ForeignKey(_Constraint):
    _args = ('keys', 'fTable', 'fKeys', 'onUpdate', 'onDelete')

    def __init__(self, keys, fTable, fKeys=None,
            onUpdate=FKeyActions.NO_ACTION, onDelete=FKeyActions.NO_ACTION):
        _Constraint.__init__(self)
        self.keys = keys
        self.fTable = fTable
        self.fKeys = fKeys
        self.onUpdate = onUpdate
        self.onDelete = onDelete

    def _tableDone(self, table):
        self.keys = self._resolveColumns(self.keys)
        if self.fKeys:
            self.fKeys = self._resolveColumns(self.fKeys)
        else:
            self.fKeys = self.keys

    def asSchemaDef(self, table=None, inline=False, **kwargs):
        out = []
        if inline:
            cname = 'References'
        else:
            cname = 'ForeignKey'
            out.append('(%s)' % self._displayColumns(self.keys, table, True))
        out.append(repr(self.fTable))
        if self.fKeys != self.keys:
            out.append('(%s)' % self._displayColumns(self.fKeys, table, True))
        if self.onUpdate != FKeyActions.NO_ACTION:
            out.append('onUpdate=%s' % self.onUpdate)
        if self.onDelete != FKeyActions.NO_ACTION:
            out.append('onDelete=%s' % self.onDelete)
        return '%s(%s)' % (cname, ', '.join(out))

    def asSQL(self, **kwargs):
        ret = 'CONSTRAINT %s FOREIGN KEY ( %s ) REFERENCES %s ( %s )' % (
                quoteIdentifier(self.name), self._quoteColumns(self.keys),
                quoteIdentifier(self.fTable), self._quoteColumns(self.fKeys))
        if self.onDelete != FKeyActions.NO_ACTION:
            ret += ' ON DELETE ' + str(self.onDelete).replace('_', ' ')
        if self.onUpdate != FKeyActions.NO_ACTION:
            ret += ' ON UPDATE ' + str(self.onUpdate).replace('_', ' ')
        return SQL(ret)

    def getDefaultName(self, table):
        if len(self.keys) == 1:
            return '%s_%s_fkey' % (table.name, self.keys[0])
        return None

    def getDependencies(self, table):
        return DependencySet(
                provides=[('constraint', table.name, self.name)],
                requires=
                    set(('column', table.name, x) for x in self.keys) |
                    set(('column', self.fTable, x) for x in self.fKeys)
                    )


class Check(_Constraint):
    _args = ('check',)

    def __init__(self, check):
        _Constraint.__init__(self)
        self.check = check

    def asSchemaDef(self, **kwargs):
        return 'Check(%r)' % (self.check,)

    def asSQL(self, **kwargs):
        return SQL('CONSTRAINT %s CHECK ( %s )' % (quoteIdentifier(self.name),
                self.check))


# Column modifiers
class _Modifier(object):
    def __init__(self, value):
        self.value = value


class Default(_Modifier):
    pass


def References(fTable, fKeys=None,
        onUpdate=FKeyActions.NO_ACTION, onDelete=FKeyActions.NO_ACTION):
    return ForeignKey(None, fTable, fKeys,
                onUpdate=onUpdate, onDelete=onDelete)


# Tools

class Expression(object):
    """Wrapper around a SQL expression, esp. as a column default."""
    def __init__(self, expr):
        self.expr = expr

    def __repr__(self):
        return 'Expression(%r)' % (self.expr,)

    def __eq__(self, other):
        return isinstance(other, Expression) and self.expr == other.expr
    def __ne__(self, other):
        return not isinstance(other, Expression) or self.expr != other.expr
