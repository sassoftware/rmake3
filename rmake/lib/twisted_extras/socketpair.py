#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
