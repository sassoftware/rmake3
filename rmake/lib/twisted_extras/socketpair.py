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

import socket
from twisted.internet import fdesc
from twisted.internet import tcp


class Paired(tcp.Connection):

    def __init__(self, sock, protocol, reactor):
        tcp.Connection.__init__(self, sock, protocol, reactor)
        self.startReading()
        self.connected = 1


def socketpair(protocol, family=socket.AF_UNIX, reactor=None):
    """
    Create a socket pair, binding the given protocol to one of the sockets and
    returning the other socket.
    """
    if not reactor:
        from twisted.internet import reactor
    sock1, sock2 = socket.socketpair(family, socket.SOCK_STREAM)
    transport = _makesock(reactor, sock1, protocol)
    return transport, sock2


def _makesock(reactor, sock, protocol):
    fdesc._setCloseOnExec(sock.fileno())
    transport = Paired(sock, protocol, reactor)
    protocol.makeConnection(transport)
    return transport
