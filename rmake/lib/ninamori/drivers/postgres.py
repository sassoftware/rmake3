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

import psycopg2
from psycopg2 import extensions
from rmake.lib.ninamori.connection import DatabaseConnection
from rmake.lib.ninamori.decorators import helper, readOnly
from rmake.lib.ninamori.itools import fold
from rmake.lib.ninamori.schema import types as schematypes
from rmake.lib.ninamori.schema.schema import Schema
from rmake.lib.ninamori.schema.table import Table
from rmake.lib.ninamori.schema.parse_schema import parseColumnType
from rmake.lib.ninamori.types import namedtuple


class PostgresConnection(DatabaseConnection):
    __slots__ = ()
    driver = 'postgres'
    isolation_level = extensions.ISOLATION_LEVEL_READ_COMMITTED

    @classmethod
    def connect(cls, connectString):
        args = connectString.asDict(exclude=('driver',))
        args['database'] = args.pop('dbname')

        conn = psycopg2.connect(**args)
        conn.set_isolation_level(extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        extensions.register_type(extensions.UNICODE, conn)
        return cls(conn)

    @helper
    def _loadMeta(self, cu):
        cu.execute("""
            SELECT t.relname
                FROM pg_class t
                JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE t.relkind = 'r'
                AND nspname = ANY ( pg_catalog.current_schemas(false) )
            """)
        self._tables = frozenset(x[0] for x in cu)

    @readOnly
    def getSchema(self, cu):
        schema = Schema()
        schema.tables = {}
        tableMap = {}

        # Tables and columns
        cu.execute("""
            SELECT t.oid, t.relname,
                    a.attnum, a.attname, a.attnotnull,
                    pg_catalog.format_type(a.atttypid, a.atttypmod),
                    ( SELECT pg_catalog.pg_get_expr(d.adbin, d.adrelid)
                        FROM pg_attrdef d WHERE d.adrelid = a.attrelid AND
                        d.adnum = a.attnum AND a.atthasdef )
                FROM pg_class t
                JOIN pg_namespace n ON n.oid = t.relnamespace
                JOIN pg_attribute a ON a.attrelid = t.oid
            WHERE t.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
                AND nspname = ANY ( pg_catalog.current_schemas(false) )
            ORDER BY t.oid
            """)
        for (oid, name), columns in fold(cu, 2):
            outCols = {}
            for colNum, colName, colNotNull, colType, colDef in columns:
                col = parseColumnType(colType)
                col.index = colNum
                col.name = colName
                col.not_null = colNotNull
                if colDef:
                    if (colDef.isdigit()
                            or colDef.startswith('-') and colDef[1:].isdigit()):
                        # -1234
                        col.default = int(colDef)
                    elif (colDef.startswith('(-') and colDef.endswith(')')
                            and colDef[2:-1].isdigit()):
                        # (-1234)
                        col.default = int(colDef[1:-1])
                    elif colDef.startswith('nextval('):
                        # nextval('foo_seq'::regclass)
                        if col.width == 8:
                            col.__class__ = schematypes.BigSerial
                        else:
                            col.__class__ = schematypes.Serial
                    elif colDef.endswith('::character varying'):
                        # 'foo bar'::character varying
                        col.default = colDef[1:-20]
                    elif colDef.endswith('::text'):
                        # 'foo bar'::text
                        col.default = colDef[1:-7]
                    else:
                        col.default = schematypes.Expression(colDef)
                outCols[colName] = col
            schema.tables[name] = tableMap[oid] = Table(name, outCols)

        if not tableMap:
            return schema
        oids = ', '.join('%d' % x for x in tableMap)

        # Constraints
        cu.execute("""
            SELECT r.oid, r.conrelid, r.conname, r.contype, r.conkey,
                r.confrelid, r.confupdtype, r.confdeltype, r.confkey,
                pg_get_expr(r.conbin, r.conrelid, true)
            FROM pg_constraint r
            WHERE r.conrelid IN ( %s )
            """ % (oids,))
        for (oid, tableOID, name, conType, keys, fOID, fOnUpdate, fOnDelete,
                fKeys, conExpr) in cu:
            table = tableMap[tableOID]

            keys = tuple(table._getColumnByIndex(int(x)) for x in keys)

            if conType == 'p':
                # PRIMARY KEY
                constraint = schematypes.PrimaryKey(*keys)
            elif conType == 'u':
                # UNIQUE
                constraint = schematypes.Unique(*keys)
            elif conType == 'f':
                # FOREIGN KEY
                fTable = tableMap[fOID]
                fKeys = tuple(fTable._getColumnByIndex(int(x)).name
                        for x in fKeys)
                fOnUpdate = FKEY_ACTION_MAP.get(fOnUpdate)
                fOnDelete = FKEY_ACTION_MAP.get(fOnDelete)

                constraint = schematypes.ForeignKey(keys, fTable.name, fKeys,
                        fOnUpdate, fOnDelete)
            elif conType == 'c':
                # CHECK
                constraint = schematypes.Check(conExpr)
            else:
                continue

            constraint.name = name

            table.constraints[name] = constraint

        # Indexes
        cu.execute("""
            SELECT x.indexrelid, x.indrelid, i.relname,
                x.indisunique, x.indisprimary, x.indkey,
                pg_get_expr(x.indexprs, x.indrelid, true)
            FROM pg_index x
                JOIN pg_class i ON i.oid = x.indexrelid
            WHERE x.indrelid IN ( %s )
            """ % (oids,))
        for oid, tableOID, name, isUnique, isPrimary, keys, expr in cu:
            table = tableMap[tableOID]
            # NB: indkey is an "int2vector", which psycopg2 represents as a
            # string of space-separated numbers.
            keys = tuple(int(x) for x in keys.split())
            if keys == (0,):
                # Expression index
                assert expr is not None
                keys = ( schematypes.Expression(expr), )
            else:
                keys = tuple(table._getColumnByIndex(int(x)) for x in keys)
            itype = isUnique and schematypes.UniqueIndex or schematypes.Index

            if name in table.constraints:
                # Ignore indexes implied by a constraint.
                assert table.constraints[name].keys == keys
                continue

            table.indexes[name] = itype(*keys)
            table.indexes[name].name = name

        for table in tableMap.values():
            table._tableDone()
        return schema

    @staticmethod
    def binary(val):
        return psycopg2.Binary(val)


CONSTRAINT_MAP = {
        'p': 'PRIMARY KEY',
        'u': 'UNIQUE',
        'f': 'FOREIGN KEY',
        'c': 'CHECK',
        }


FKEY_ACTION_MAP = {
        'a': schematypes.FKeyActions.NO_ACTION,
        'r': schematypes.FKeyActions.RESTRICT,
        'c': schematypes.FKeyActions.CASCADE,
        'n': schematypes.FKeyActions.SET_NULL,
        'd': schematypes.FKeyActions.SET_DEFAULT,
        }


PostgresTable = namedtuple('PostgresTable',
        'name schema oid columns isTemporary indexes constraints')
PostgresColumn = namedtuple('PostgresColumn',
        'name type isNotNull')
PostgresIndex = namedtuple('PostgresIndex',
        'name oid isUnique isPrimary keys')
PostgresConstraint = namedtuple('PostgresConstraint',
        'name oid type keys fTable fKeys fOnUpdate fOnDelete check')
