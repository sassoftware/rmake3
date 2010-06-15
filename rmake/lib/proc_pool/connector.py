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
from twisted.internet import defer
from twisted.internet import error
from twisted.internet import protocol

log = logging.getLogger(__name__)


TO_CHILD = 3
FROM_CHILD = 4


class ProcessConnector(protocol.ProcessProtocol):
    """
    Present a stream-like transport interface to a wrapped protocol instance,
    while routing the inbound and outbound data over a pair of pipes attached
    to the parent process transport.
    """

    disconnecting = False

    def __init__(self, prot, out_fd=TO_CHILD, in_fd=FROM_CHILD):
        self.finished = defer.Deferred()
        self.protocol = prot
        self.out_fd = out_fd
        self.in_fd = in_fd
        self.pid = None

    def __repr__(self):
        return '<ProcessConnector %s>' % (self.pid or hex(id(self)))

    # For parent transport

    def signalProcess(self, sig):
        self.transport.signalProcess(sig)

    def connectionMade(self):
        self.protocol.makeConnection(self)
        self.pid = self.transport.pid

    def childDataReceived(self, childFD, data):
        if childFD == self.in_fd:
            self.protocol.dataReceived(data)
        else:
            self.errReceived(data)

    def errReceived(self, data):
        for line in data.splitlines():
            if line == '\x1b[?1034h':
                # Silly readline, this is not a terminal!
                continue
            log.debug("worker %d: %s", self.pid, line)

    def processEnded(self, status):
        self.protocol.connectionLost(status)
        if status.check(error.ProcessDone):
            self.finished.callback(None)
        else:
            self.finished.errback(status)

    # For child protocol

    def write(self, data):
        self.transport.writeToChild(self.out_fd, data)

    def loseConnection(self):
        self.transport.closeChildFD(self.out_fd)
        self.transport.closeChildFD(self.in_fd)
        self.transport.loseConnection()

    def getPeer(self):
        return ('subprocess',)

    def getHost(self):
        return ('no host',)

    # For other callers

    def callRemote(self, command, **kwargs):
        return self.protocol.callRemote(command, **kwargs)
