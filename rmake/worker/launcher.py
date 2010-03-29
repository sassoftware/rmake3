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

"""
The launcher is the root process of a worker node. It forks to handle incoming
jobs and accumulates messages to and distributes messages from the dispatcher
to the worker processes via a UNIX socket.

The launcher must re-exec after forking to prevent Twisted state from escaping
into the worker process.
"""

import os
import socket
import struct
import sys
from rmake.lib.twisted_extras.socketpair import socketpair
from rmake.messagebus.client import BusClientService
from twisted.application.service import Service
from twisted.internet.protocol import ProcessProtocol
from twisted.protocols.basic import Int32StringReceiver


class LauncherService(Service):

    def __init__(self):
        self.workers = {}
        self.bus = LauncherClien

    def launch(self, data):
        from twisted.internet import reactor

        worker = LaunchedWorker(self)
        transport, sock = socketpair(worker.net, socket.AF_UNIX, reactor)

        args = [sys.executable, __file__, '--worker']
        reactor.spawnProcess(worker, sys.executable, args,
                os.environ, childFDs={0:0, 1:1, 2:2, 3:sock.fileno()})

        sock.close()


class LaunchedWorker(ProcessProtocol):

    def __init__(self, launcher):
        self.launcher = launcher
        self.net = LaunchedWorkerSocket(self)

    def connectionMade(self):
        print 'up'

    def processEnded(self, status):
        print 'down'


class LaunchedWorkerSocket(Int32StringReceiver):

    def __init__(self, worker):
        self.worker = worker

    def stringReceived(self, msg):
        print 'msg: %r' % msg


def main():
    from twisted.internet import reactor

    if sys.argv[1:2] == ['--worker']:
        service = WorkerService()
    else:
        service = LauncherService()
    service.startService()
    reactor.run()


main()
