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
