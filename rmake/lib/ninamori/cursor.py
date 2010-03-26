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

import weakref
from rmake.lib.ninamori.error import TransactionError
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
            return func(*args, **kwargs)
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
            raise TransactionError("%r may not be executed directly."
                    % (command,), self._txn())

    # Protected pass-throughs for queries and inserts
    def execute(self, statement, args=()):
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
