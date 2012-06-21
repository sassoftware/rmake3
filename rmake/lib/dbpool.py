#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
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

    def __init__(self, reactor, pool):
        txpostgres.Connection.__init__(self, reactor)
        self.pool = pool

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
        self.connQueue = defer.DeferredQueue()

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
            try:
                conn.close()
            except psycopg2.InterfaceError:
                # Connection already closed
                pass
        self.shutdownID = None
        if self.cleanupTask:
            self.cleanupTask.stop()
        self.pool_running = False

    def rebalance(self):
        dfrs = []
        for x in range(self.min - len(self.connections)):
            dfrs.append(self._startOne())

        d = defer.DeferredList(dfrs, fireOnOneErrback=True, consumeErrors=True)
        def eb_connect_failed(reason):
            # Pull the real error out of the FirstError DL slaps on
            return reason.value.subFailure
        d.addErrback(eb_connect_failed)
        return d

    def _startOne(self):
        conn = self.connectionFactory(self.reactor, self)

        log.debug("Connecting asynchronously to %s", self.path.asDSN())
        d = conn.connect(self.path)

        def cb_connected(dummy):
            log.debug("Database is connected")
            self._add(conn)
        d.addCallback(cb_connected)
        return d

    def _add(self, conn):
        self.connections.add(conn)
        self.connQueue.put(conn)

    def _remove(self, conn):
        self.connections.discard(conn)
        if conn in self.connQueue.pending:
            self.connQueue.pending.remove(conn)

    # Running queries

    def runQuery(self, statement, args=None):
        """Execute a query and callback the result."""
        return self._runWithConn('runQuery', statement, args)

    def runOperation(self, statement, args=None):
        """Execute a statement and callback C{None} when done."""
        return self._runWithConn('runOperation', statement, args)

    def runInteraction(self, func, *args, **kwargs):
        """Run function in a transaction and callback the result."""
        return self._runWithConn('runInteraction', func, *args, **kwargs)


    def _runWithConn(self, funcName, *args, **kwargs):
        if self.connQueue.pending:
            d = defer.succeed(None)
        else:
            d = self.rebalance()
        d.addCallback(lambda _: self.connQueue.get())

        def gotConn(conn):
            func = getattr(conn, funcName)
            d2 = defer.maybeDeferred(func, *args, **kwargs)
            def handleConnClosed(reason):
                reason.trap(psycopg2.DatabaseError, psycopg2.InterfaceError)
                msg = reason.value.pgerror
                if msg and ('server closed ' in msg
                        or 'connection already closed' in msg):
                    # Connection was closed
                    self._remove(conn)
                    log.info("Lost connection to database")
                return reason
            d2.addErrback(handleConnClosed)
            def releaseAndReturn(result):
                # Only put the connection back in the queue if it is also still
                # in the pool. This keeps it from being requeued if the
                # connection was terminated during the operation.
                if conn in self.connections:
                    self.connQueue.put(conn)
                return result
            d2.addBoth(releaseAndReturn)
            return d2
        d.addCallback(gotConn)
        return d
