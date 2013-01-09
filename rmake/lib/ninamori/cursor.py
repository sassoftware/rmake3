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


import psycopg2
import sys
import weakref
from rmake.lib.ninamori import error
from rmake.lib.ninamori.types import Row, SQL


class _CursorPass(object):
    """
    Pass-through to the underlying driver's cursor object.
    """
    #pylint: disable-msg=R0903
    __slots__ = ('attr',)
    def __init__(self, attr):
        # Don't allow methods only defined in specific drivers.
        self.attr = attr
    def __get__(self, ownerInst, ownerClass):
        #pylint: disable-msg=W0212,W0613
        if ownerInst is None:
            return self
        return getattr(ownerInst._cu, self.attr)


class Cursor(object):
    __slots__ = ('__weakref__', '_txn', '_cu', '_conn')

    def __init__(self, txn, conn):
        self._txn = weakref.ref(txn)
        self._conn = conn
        self._cu = conn.cursor()

    def _tryCall(self, func, *args, **kwargs):
        """
        Check that the transaction is ready, then execute C{func}. If
        an error is raised, flag the transaction as "in error" then
        re-raise so that further statements will not be executed.
        """
        self._txn().ready()
        try:
            try:
                return func(*args, **kwargs)
            except psycopg2.DatabaseError:
                e_type, e_value, e_tb = sys.exc_info()
                # Re-throw with our more specific types
                pgcode = getattr(e_value, 'pgcode', None)
                if pgcode:
                    new_type = error.getExceptionFromCode(e_value.pgcode)
                else:
                    new_type = error.DatabaseError
                new_value = new_type(*e_value.args)
                new_value.err_code = pgcode
                raise new_type, new_value, e_tb
        except:
            self._txn().setInError()
            raise

    def _checkStatement(self, statement):
        """
        Transaction statements are not allowed via a cursor; only the
        transaction object can do these.
        """
        command = statement.split()[0].upper()
        if command in ('BEGIN', 'START', 'ROLLBACK', 'COMMIT',
                'SAVEPOINT', 'RELEASE', 'PREPARE'):
            raise error.TransactionError("%r may not be executed directly."
                    % (command,), self._txn())

    # Protected pass-throughs for queries and inserts
    def execute(self, statement, args=None):
        if isinstance(statement, SQL):
            assert not args
            statement, args = statement.statement, statement.args

        self._checkStatement(statement)
        self._tryCall(self._cu.execute, statement, args)
        return self

    def executemany(self, statement, arglist):
        self._checkStatement(statement)
        self._tryCall(self._cu.executemany, statement, arglist)
        return self

    #def bulkload(self, tableName, rows, columnNames):
    #    self._tryCall(self._conn.bulkload, tableName, rows, columnNames)

    # Data wrappers
    def binary(self, val):
        return self._txn().db().binary(val)

    # Unprotected pass-throughs for accessing results.
    def _row(self, data):
        if data is None:
            return None
        return Row(data, self.fields())

    def fetchone(self):
        return self._row(self._cu.fetchone())
    def fetchall(self):
        return [self._row(x) for x in self._cu.fetchall()]
    def fetchmany(self, count=1):
        return [self._row(x) for x in self._cu.fetchmany(count)]

    fetchone_dict = _CursorPass('fetchone_dict')
    fetchall_dict = _CursorPass('fetchall_dict')
    fetchmany_dict = _CursorPass('fetchmany_dict')

    # iterator/iterable protocol
    def __iter__(self):
        return self
    def next(self):
        return self._row(self._cu.next())

    # Cursor introspection methods.
    description = _CursorPass('description')

    def fields(self):
        desc = self._cu.description
        if desc is None:
            return None
        return [x[0] for x in desc]

    lastrowid = _CursorPass('lastrowid')
    rowcount = _CursorPass('rowcount')

    # Introspection helpers
    def getOne(self, exception):
        """
        Return a single row. If there are no rows to fetch, raise C{exception}.

        If there is more than one row to fetch, raise an assertion.  In other
        words, don't use this with queries that could return multiple rows.
        """
        res = self.fetchone()
        if res is None:
            raise exception
        assert self.fetchone() is None
        return res

    def getCount(self):
        """
        Returns the first field of the first row. Most useful for retrieving
        the result of a C{SELECT COUNT(*)}.
        """
        return self.fetchone()[0]

    # Execution helpers
    def insert(self, table, values=(), returning=()):
        items = dict(values).items()
        fields = ', '.join(x[0] for x in items)
        placeholders = ', '.join('%s' for x in items)
        values = [x[1] for x in items]
        sql = SQL("INSERT INTO %s ( %s ) VALUES ( %s )" % (table, fields,
            placeholders), *values)
        if returning:
            sql += SQL(" RETURNING " + returning)
        return self.execute(sql)
