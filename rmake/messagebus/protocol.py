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

This includes the base protocol only. See the client and server modules for
more useful implementations.
"""


import time
from StringIO import StringIO
from twisted.internet import protocol
from rmake.messagebus import envelope, messages


class NotConnectedError(Exception):
    pass


class BusProtocol(protocol.Protocol):

    """Superclass for client and server messagebus channels."""

    factory = None

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
