#
# Copyright (c) 2010 rPath, Inc.
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
#

import logging
import psycopg2
from rmake.lib.ninamori import error as nerror
from rmake.lib.ninamori.connection import ConnectString
from rmake.lib.ninamori.types import Row, SQL
from rmake.lib.twisted_extras import deferred_service
from psycopg2 import extensions
from rmake.lib.dbextensions import register_types
from twisted.internet import defer
from twisted.internet import task
from twisted.python import failure
from txpostgres import txpostgres

log = logging.getLogger(__name__)


class Cursor(txpostgres.Cursor):

    def execute(self, statement, args=None):
        if isinstance(statement, SQL):
            assert not args
            statement, args = statement.statement, statement.args
        d = txpostgres.Cursor.execute(self, statement, args)
        d.addErrback(self._convertErrors)
        return d

    def query(self, statement, args=None):
        d = self.execute(statement, args)
        d.addCallback(lambda cu: cu.fetchall())
        return d

    @staticmethod
    def _convertErrors(reason):
        reason.trap(psycopg2.DatabaseError)
        exc_value = reason.value
        if getattr(exc_value, 'pgcode', None):
            exc_type = nerror.getExceptionFromCode(reason.value.pgcode)
            exc_value = exc_type(*exc_value.args)
            exc_value.err_code = reason.value.pgcode
            new = failure.Failure(exc_value, exc_type)
            new.frames = reason.frames
            new.stack = reason.stack
            return new
        return reason

    def fields(self):
        desc = self.description
        if desc is not None:
            return [x[0] for x in desc]
        else:
            return None

    def _row(self, data):
        if data is None:
            return None
        return Row(data, self.fields())

    def fetchone(self):
        return self._row(self._cursor.fetchone())

    def fetchall(self):
        return [self._row(x) for x in self._cursor.fetchall()]


class Connection(txpostgres.Connection):

    cursorFactory = Cursor

    def connect(self, path):
        params = path.asDict(exclude=('driver',))
        params['database'] = params.pop('dbname')
        d = txpostgres.Connection.connect(self, **params)
        def cb_connected(result):
            extensions.register_type(extensions.UNICODE, self._connection)
            return register_types(self)
        d.addCallback(cb_connected)
        return d


class ConnectionPool(deferred_service.Service):

    min = 3

    connectionFactory = Connection

    def __init__(self, path, min=None):
        self.path = ConnectString.parse(path)
        self.pool_running = False
        self.shutdownID = None
        self.cleanupTask = None

        if min:
            self.min = min

        self.connections = set()
        self.ready = set()
        self.semaphore = defer.DeferredSemaphore(1)
        self.semaphore.tokens = self.semaphore.limit = 0

        from twisted.internet import reactor
        self.reactor = reactor

    def postStartService(self):
        return self.start()

    def stopService(self):
        deferred_service.Service.stopService(self)
        self.close()

    # Pool control

    def start(self):
        if self.pool_running:
            return
        self.shutdownID = self.reactor.addSystemEventTrigger('during',
                'shutdown', self._finalClose)
        self.pool_running = True

        d = self.rebalance()
        def cb_connected(result):
            self.cleanupTask = task.LoopingCall(self.rebalance)
            self.cleanupTask.start(5, now=False)
            return result
        d.addCallback(cb_connected)
        return d

    def close(self):
        if self.shutdownID:
            self.reactor.removeSystemEventTrigger(self.shutdownID)
            self.shutdownID = None
        self._finalClose()

    def _finalClose(self):
        for conn in self.connections:
            conn.close()
        self.shutdownID = None
        if self.cleanupTask:
            self.cleanupTask.stop()
        self.pool_running = False

    def rebalance(self):
        dfrs = []
        for x in range(self.min - len(self.connections)):
            dfrs.append(self._addOne())

        d = defer.DeferredList(dfrs, fireOnOneErrback=True, consumeErrors=True)
        def eb_connect_failed(reason):
            # Pull the real error out of the FirstError DL slaps on
            return reason.value.subFailure
        d.addErrback(eb_connect_failed)
        return d

    def _addOne(self):
        conn = self.connectionFactory(self.reactor)
        self.connections.add(conn)

        log.debug("Connecting asynchronously to %s", self.path.asDSN())
        d = conn.connect(self.path)

        def cb_connected(dummy):
            log.debug("Database is connected")

            self.ready.add(conn)
            self.semaphore.limit += 1
            self.semaphore.release()
        d.addCallback(cb_connected)

        def eb_cleanup(reason):
            self.connections.remove(conn)
            return reason
        d.addErrback(eb_cleanup)

        return d

    # Running queries

    def runQuery(self, statement, args=None):
        """Execute a query and callback the result."""
        return self.semaphore.run(self._runQuery, statement, args)

    def runOperation(self, statement, args=None):
        """Execute a statement and callback C{None} when done."""
        return self.semaphore.run(self._runOperation, statement, args)

    def runInteraction(self, func, *args, **kwargs):
        """Run function in a transaction and callback the result."""
        return self.semaphore.run(self._runInteraction, func, *args, **kwargs)


    def _queryDone(self, result, conn):
        self.ready.add(conn)
        return result

    def _runQuery(self, statement, args):
        conn = self.ready.pop()
        d = conn.runQuery(statement, args)
        return d.addBoth(self._queryDone, conn)

    def _runOperation(self, statement, args):
        conn = self.ready.pop()
        d = conn.runOperation(statement, args)
        return d.addBoth(self._queryDone, conn)

    def _runInteraction(self, *args, **kwargs):
        conn = self.ready.pop()
        d = conn.runInteraction(*args, **kwargs)
        return d.addBoth(self._queryDone, conn)
