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
rMake messagebus implementation for Twisted.

This includes the base protocol and a client subclass, plus a client factory
and XMLRPC proxy.
"""


import logging
import time
from StringIO import StringIO
from twisted.internet import defer, protocol
from twisted.python import failure
from rmake.lib import apirpc
from rmake.lib import rpcproxy
from rmake.messagebus import envelope, messages

log = logging.getLogger(__name__)


class NotConnectedError(Exception):
    pass


class BusProtocol(protocol.Protocol):

    """Superclass for client and server messagebus channels."""

    buffer = ''
    nextLead = None
    nextHeader = None

    sessionId = None
    messageCount = 0

    def dataReceived(self, data):
        self.buffer += data
        while self._getMessage():
            pass

    def _getMessage(self):
        # Parse lead
        if self.nextLead is None:
            if len(self.buffer) < 32:
                return False
            leadStream = envelope.PLead()
            leadStream.thawString(self.buffer[:32])
            self.nextLead = ( leadStream.msgHeaderSize(),
                    leadStream.msgPayloadSize() )
            self.buffer = self.buffer[32:]

        headerSize, payloadSize = self.nextLead

        # Parse header
        if self.nextHeader is None:
            if len(self.buffer) < headerSize:
                return False
            headerStream = envelope.PHeader()
            headerStream.thawString(self.buffer[:headerSize])
            self.nextHeader = headerStream.headers
            self.buffer = self.buffer[headerSize:]

        # Parse payload
        if len(self.buffer) < payloadSize:
            return False
        payloadStream = StringIO(self.buffer[:payloadSize])
        self.buffer = self.buffer[payloadSize:]

        # Construct and dispatch message
        message = messages.thawMessage(self.nextHeader, payloadStream,
                payloadSize)
        self.nextLead = self.nextHeader = None
        self.messageReceived(message)
        return True

    def messageReceived(self, message):
        raise NotImplementedError

    def _stamp(self, message):
        messageId = '%s:%s' % (self.sessionId, self.messageCount)
        self.messageCount += 1
        message.stamp(messageId, self.sessionId, time.time())

    def sendMessage(self, message):
        if self.sessionId and not message.headers.timeStamp:
            self._stamp(message)

        headers, payload, size = message.freeze()
        e = envelope.Envelope()
        e.setHeaders(headers)
        e.setPayloadStream(payload)
        e.setPayloadSize(size)
        self.transport.write(e.freeze())


class BusClientProtocol(BusProtocol):

    """Twisted protocol for messagebus clients."""

    def __init__(self):
        self.queries = {}

    def connectionMade(self):
        msg = messages.ConnectionRequest()
        msg.set(self.factory.user, self.factory.password,
                self.factory.sessionClass)
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
        self.queries[msg.getMessageId()] = deferred = defer.Deferred()
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


class BusClientFactory(protocol.ReconnectingClientFactory):

    """Twisted factory for messagebus clients."""

    protocol = BusClientProtocol
    maxDelay = 15

    def __init__(self, sessionClass='', user='', password=''):
        self.connection = None
        self.connectCallbacks = []
        self.didConnect = False

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

        for deferred in self.connectCallbacks:
            deferred.callback(connection)
        self.connectCallbacks = []

    def busLost(self):
        self.connection = None

    def deferUntilConnected(self):
        deferred = defer.Deferred()
        if self.connection:
            deferred.callback(self.connection)
        else:
            self.connectCallbacks.append(deferred)
        return deferred

    def getProxy(self, apiClass, targetId):
        return BusClientProxy(apiClass, self, targetId)


class BusClientProxy(apirpc.ApiProxy):

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
        toCaller = defer.Deferred()
        fromProtocol = conn.sendMethodCall(self.targetId, method, args)
        fromProtocol.addCallback(self._request_finished, toCaller, apiInfo)
        fromProtocol.addErrback(toCaller.errback)
        return toCaller

    def _request_finished(self, msg, toCaller, apiInfo):
        try:
            result = self._post_request(not msg.isError(), msg.getReturnValue(),
                    apiInfo)
        except Exception:
            # TODO: figure out how to produce a stack trace from when the call
            # was originally invoked. The stack here is completely worthless.
            toCaller.errback()
        else:
            toCaller.callback(result)
