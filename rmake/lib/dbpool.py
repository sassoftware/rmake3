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
import sys
import thread
from ninamori import connect
from ninamori.connection import ConnectString
from twisted.internet import task
from twisted.internet import threads
from twisted.python import threadpool

log = logging.getLogger(__name__)


class PooledDatabaseProxy(object):

    def __init__(self, pool):
        self.pool = pool

    def __getattr__(self, key):
        return getattr(self.pool._connect(), key)


class ConnectionPool(object):

    min = 2
    max = 5

    def __init__(self, path):
        self.path = ConnectString.parse(path)
        self.threadpool = ThreadPool(self.min, self.max)
        self.running = False
        self.connections = {}

        from twisted.internet import reactor
        self.reactor = reactor
        self.startID = reactor.callWhenRunning(self._start)
        self.shutdownID = None

    # Pool control

    def _start(self):
        if self.running:
            return
        self.startID = None
        self.threadpool.start()
        self.cleanupTask = task.LoopingCall(self.threadpool.trimWorkers)
        self.cleanupTask.start(5)
        self.shutdownID = self.reactor.addSystemEventTrigger('during',
                'shutdown', self._finalClose)
        self.running = True

    def close(self):
        if self.shutdownID:
            self.reactor.removeSystemEventTrigger(self.shutdownID)
            self.shutdownID = None
        if self.startID:
            self.reactor.removeSystemEventTrigger(self.startID)
            self.startID = None
        self._finalClose()

    def _finalClose(self):
        self.shutdownID = None
        self.cleanupTask.stop()
        self.threadpool.stop()
        self.running = False
        for conn in self.connections.values():
            self._closeConn(conn)
        self.connections.clear()

    def _connect(self):
        tid = thread.get_ident()
        conn = self.connections.get(tid)
        if conn is None:
            print 'dbpool: opening a connection'
            conn = self.connections[tid] = connect(self.path)
        return conn

    def _disconnect(self):
        tid = thread.get_ident()
        conn = self.connections.get(tid)
        if conn is not None:
            self._closeConn(conn)
            del self.connections[tid]

    def _closeConn(self, conn):
        print 'dbpool: closing %r' % conn
        try:
            conn.close()
        except:
            log.exception("Failed to close connection:")

    # Running queries

    def runWithTransaction(self, func, *args, **kwargs):
        return threads.deferToThreadPool(self.reactor, self.threadpool,
                self._runWithTransaction, func, *args, **kwargs)

    def _runWithTransaction(self, func, *args, **kwargs):
        db = self._connect()
        assert not db._stack
        txn = db.begin()
        try:
            ret = func(*args, **kwargs)
            txn.commit()
            return ret
        except:
            e_type, e_value, e_tb = sys.exc_info()
            try:
                txn.rollback()
            except:
                log.exception("Error rolling back transaction:")
            raise e_type, e_value, e_tb


class ThreadPool(threadpool.ThreadPool):

    def trimWorkers(self):
        if self.q.qsize():
            return
        while self.workers > max(self.min, len(self.working)):
            print 'trimming a thread'
            self.stopAWorker()

    def _worker(self):
        threadpool.ThreadPool._worker(self)
        self.cleanup()
