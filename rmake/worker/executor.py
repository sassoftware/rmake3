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
The executor is responsible for handling a particular unit of subwork, either
in-process or by forking off additional tasks.

It communicates with the dispatcher through a UNIX domain socket handed to it
by the launcher on startup.
"""

import logging
import socket
from rmake.lib.twisted_extras.pickle_proto import PickleProtocol
from rmake.lib.twisted_extras.socketpair import makesock
from rmake.messagebus import message
from twisted.application.service import Service
from twisted.internet.error import ReactorNotRunning

log = logging.getLogger(__name__)


class ExecutorService(Service):

    def __init__(self, sock):
        self.cfg = None
        self.net = LauncherSocket(self)
        self.sock = sock

    def startService(self):
        Service.startService(self)
        makesock(self.sock, self.net)
        self.sock = None

    def stopService(self):
        Service.stopService(self)
        return self.net.transport.loseConnection()

    def startWork(self, cfg):
        self.cfg = cfg
        log.info("Starting work!")
        from twisted.internet import reactor
        def later():
            log.info("Work's done!")
            reactor.stop()
        import random
        reactor.callLater(random.uniform(0, 10), later)


class LauncherSocket(PickleProtocol):

    def __init__(self, executor):
        self.executor = executor

    def messageReceived(self, msg):
        if isinstance(msg, message.StartWork):
            self.executor.startWork(msg.cfg)
        else:
            print 'msg: %r' % (msg,)

    def connectionLost(self, reason):
        from twisted.internet import reactor
        try:
            reactor.stop()
        except ReactorNotRunning:
            pass


def main():
    sock = socket.fromfd(3, socket.AF_UNIX, socket.SOCK_STREAM)

    from rmake.lib.logger import setupLogging
    setupLogging(consoleLevel=logging.WARNING, consoleFormat='file',
            withTwisted=True)

    from twisted.internet import reactor
    service = ExecutorService(sock)
    service.startService()
    reactor.run()


if __name__ == '__main__':
    main()
