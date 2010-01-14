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
rMake messagebus client implementation for Twisted.

This includes a client protocol, factory, and XMLRPC proxy.
"""


import logging
from twisted.application.service import Service
from twisted.internet.defer import Deferred
from twisted.internet.protocol import ReconnectingClientFactory
from rmake.lib import apirpc
from rmake.messagebus import messages
from rmake.messagebus.protocol import BusProtocol, NotConnectedError
from zope.interface import Interface, implements

log = logging.getLogger(__name__)


class BusClientProtocol(BusProtocol):

    """Twisted protocol for messagebus clients."""

    def __init__(self):
        self.queries = {}

    def connectionMade(self):
        msg = messages.ConnectionRequest()
        msg.set(self.factory.user, self.factory.password,
                self.factory.sessionClass, '', self.factory.subscriptions)
        self.sendMessage(msg, force=True)

    def connectionLost(self, reason):
        # Notify any pending queries that the connection has died.
        for query in self.queries.values():
            query.errback(reason)

        self.factory.busLost()

    def sendMessage(self, message, force=False):
        if not self.sessionId and not force:
            raise NotConnectedError("Not connected")
        BusProtocol.sendMessage(self, message)

    def sendMethodCall(self, targetId, methodName, params):
        if not self.sessionId:
            raise NotConnectedError("Not connected")
        msg = messages.MethodCall(targetId, methodName, params)
        self._stamp(msg)
        self.queries[msg.getMessageId()] = deferred = Deferred()
        self.sendMessage(msg)
        return deferred

    def messageReceived(self, message):
        if isinstance(message, messages.ConnectedResponse):
            # Message bus was kind enough to assign us an identity.
            self.sessionId = message.headers.sessionId
            self.factory.busConnected(self)

        elif isinstance(message, messages.MethodResponse):
            # Reply from some previous RPC query.
            query = self.queries.get(message.getResponseTo())
            if query:
                query.callback(message)
                if message.isFinal():
                    del self.queries[message.getResponseTo()]

        else:
            # Some other message.
            self.factory.messageReceived(message)


class BusClientFactory(ReconnectingClientFactory):

    """Twisted factory for messagebus clients."""

    protocol = BusClientProtocol
    maxDelay = 15

    subscriptions = ()

    def __init__(self, sessionClass='', user='', password='', service=None):
        self.connection = None
        self.didConnect = False
        if service:
            self.service = IBusClientService(service)
        else:
            self.service = None

        self.sessionClass = sessionClass
        self.user = user
        self.password = password

    def busConnected(self, connection):
        if self.didConnect:
            log.info("Re-established connection to message bus")
        else:
            log.debug("Connected to message bus")
            self.didConnect = True
        self.resetDelay()
        self.connection = connection

        if self.service:
            self.service.busConnected()

    def busLost(self):
        self.connection = None
        if self.service:
            if self.continueTrying:
                self.service.busLost()
            else:
                self.service.busDisconnected()

    def messageReceived(self, message):
        if self.service:
            self.service.messageReceived(message)

    def disconnect(self):
        self.stopTrying()
        if self.connection:
            self.connection.transport.loseConnection()

    def getProxy(self, apiClass, targetId):
        return BusClientProxy(apiClass, self, targetId)


class BusClientProxy(apirpc.ApiProxy):

    """XMLRPC proxy which serializes to a messagebus target."""

    def __init__(self, apiClass, factory, targetId):
        apirpc.ApiProxy.__init__(self, apiClass)
        self.factory = factory
        self.targetId = targetId

    def _request(self, method, params):
        args, apiInfo = self._pre_request(method, params)
        conn = self.factory.connection
        if not conn:
            raise NotConnectedError("Not connected")
        # TODO: loopback case
        toCaller = Deferred()
        fromProtocol = conn.sendMethodCall(self.targetId, method, args)
        fromProtocol.addCallback(self._request_finished, toCaller, apiInfo)
        fromProtocol.addErrback(toCaller.errback)
        return toCaller

    def _request_finished(self, msg, toCaller, apiInfo):
        try:
            result = self._post_request(not msg.isError(), msg.getReturnValue(),
                    apiInfo)
        except:
            # TODO: figure out how to produce a stack trace from when the call
            # was originally invoked. The stack here is completely worthless.
            toCaller.errback()
        else:
            toCaller.callback(result)


class IBusClientService(Interface):

    """Methods that a bus client is expected to implement."""

    def busConnected():
        """Called when the bus is first connected."""

    def busLost():
        """Called if the connection to the bus is unexpectedly lost."""

    def busDisconnected():
        """Called when the bus connection is finished disconnecting."""

    def messageReceived():
        """Called when an unsolicited message arrives."""


class BusClientService(Service):

    """Base class for services that maintain a messagebus client."""

    implements(IBusClientService)

    sessionClass = None
    subscriptions = ()

    def __init__(self, reactor, busAddress):
        self._reactor = reactor
        self._busAddress = busAddress
        self._connection = None
        self.client = BusClientFactory(self.sessionClass)
        self.client.subscriptions = self.subscriptions

    def startService(self):
        Service.startService(self)
        host, port = self._busAddress
        self._connection = self._reactor.connectTCP(host, port, self.client)
        self.client.service = self

    def stopService(self):
        Service.stopService(self)
        self.client.service = None
        if self._connection is not None:
            self._connection.disconnect()
            self._connection = None

    def busConnected(self):
        pass

    def busLost(self):
        pass

    def busDisconnected(self):
        pass

    def messageReceived(self, message):
        pass
