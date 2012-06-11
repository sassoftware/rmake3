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
        self.logBase = self.stdoutLog = self.stderrLog = None
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
        logobj = None
        if childFD == self.in_fd:
            self.protocol.dataReceived(data)
            return
        elif childFD == 1:
            logobj = self.stdoutLog
        elif childFD == 2:
            logobj = self.stderrLog
        else:
            return

        if not logobj:
            return

        for line in data.splitlines():
            logobj.debug(line)

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

    def setLogBase(self, logBase):
        self.logBase = logBase
        if logBase:
            self.stdoutLog = logging.getLogger(logBase + '.stdout')
            self.stderrLog = logging.getLogger(logBase + '.stderr')
        else:
            self.stdoutLog = self.stderrLog = None
