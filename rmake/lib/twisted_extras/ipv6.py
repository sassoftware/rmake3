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

"""
IPv6 transport for twisted.
"""


import socket
from twisted.application.internet import _AbstractServer
from twisted.internet.interfaces import IAddress
from twisted.internet.tcp import Port as _Port
from twisted.internet.tcp import Server as _Server
from zope.interface import implements


class _IPAddress(object):

    implements(IAddress)

    def __init__(self, type, host, port):
        assert type in ('TCP', 'UDP')
        self.type = type
        self.host = host
        self.port = port

    def __eq__(self, other):
        if type(self) == type(other):
            a = (self.type, self.host, self.port)
            b = (other.type, other.host, other.port)
            return a == b
        else:
            return False

    def __repr__(self):
        return '%s(%r, %r, %d)' % (self.__class__.__name__, self.type,
                self.host, self.port)


class IPv4Address(_IPAddress):

    def __str__(self):
        return '%s:%d' % (self.host, self.port)


class IPv6Address(_IPAddress):

    def __str__(self):
        return '[%s]:%d' % (self.host, self.port)

    @classmethod
    def _fromName(cls, type, (host, port, flowinfo, scope_id)):
        if host.startswith('::ffff:'):
            # IPv4 connection on an IPv6 socket
            return IPv4Address(type, host[7:], port)
        else:
            return cls(type, host, port)


class Server(_Server):

    def getHost(self):
        return IPv6Address._fromName('TCP', self.socket.getsockname())

    def getPeer(self):
        return IPv6Address._fromName('TCP', self.client)


class Port(_Port):

    transport = Server
    addressFamily = socket.AF_INET6

    def _buildAddr(self, sockname):
        return IPv6Address._fromName('TCP', sockname)

    def getHost(self):
        return IPv6Address._fromName('TCP', self.socket.getsockname())


class TCP6Server(_AbstractServer):

    def _getPort(self):
        if self.reactor is None:
            from twisted.internet import reactor
        else:
            reactor = self.reactor
        kwargs = self.kwargs.copy()
        kwargs['reactor'] = reactor
        port = Port(*self.args, **kwargs)
        port.startListening()
        return port
