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


import os
import socket
from twisted.internet import fdesc
from twisted.internet import tcp


class Paired(tcp.Connection):

    def __init__(self, sock, protocol, reactor):
        tcp.Connection.__init__(self, sock, protocol, reactor)
        self.startReading()
        self.connected = 1

    def getHost(self):
        sockstat = os.fstat(self.socket.fileno())
        return '[%s]' % (sockstat.st_ino,)

    def getPeer(self):
        sockstat = os.fstat(self.socket.fileno())
        return '[peer of %s]' % (sockstat.st_ino,)


def socketpair(protocol, family=socket.AF_UNIX, reactor=None):
    """
    Create a socket pair, binding the given protocol to one of the sockets and
    returning the other socket.
    """
    if not reactor:
        from twisted.internet import reactor
    sock1, sock2 = socket.socketpair(family, socket.SOCK_STREAM)
    transport = makesock(sock1, protocol, reactor)
    return transport, sock2


def makesock(sock, protocol, reactor=None):
    if not reactor:
        from twisted.internet import reactor
    fdesc._setCloseOnExec(sock.fileno())
    transport = Paired(sock, protocol, reactor)
    protocol.makeConnection(transport)
    return transport
