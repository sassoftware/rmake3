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


import StringIO
import cPickle
import xmlrpclib

from rmake.messagebus import envelope
from rmake.messagebus import messages

class MessageProcessor(object):
    def __init__(self):
        self.messageQueue = []
        self.partialReadEnvelope = None
        self.partialWriteEnvelope = None

    def processData(self, streamReader, maxRead):
        if self.partialReadEnvelope:
            e = self.partialReadEnvelope
        else:
            e = envelope.Envelope()

        if e.thawFromStream(streamReader):
            self.partialReadEnvelope = None
            m = self.extractMessage(e)
            return m
        else:
            self.partialReadEnvelope = e
            return None

    def extractMessage(self, envelope):
        m = messages.thawMessage(envelope.getHeaders(),
                                 envelope.getPayloadStream(),
                                 envelope.getPayloadSize())
        return m

    def sendMessage(self, message):
        headers, payloadStream, payloadSize = message.freeze()
        e = envelope.Envelope()
        e.setHeaders(headers)
        e.setPayloadStream(payloadStream)
        e.setPayloadSize(payloadSize)
        self.messageQueue.append(e)

    def getQueuedMessages(self):
        return self.messageQueue

    def hasData(self):
        return bool(self.messageQueue or self.partialWriteEnvelope)

    def sendData(self, socket):
        if self.partialWriteEnvelope:
            e, writer = self.partialWriteEnvelope
        elif self.messageQueue:
            e = self.messageQueue.pop(0)
            writer = e.getWriter()
        else:
            return

        finished = writer(socket.send)
        if not finished:
            self.partialWriteEnvelope = (e, writer)
        else:
            self.partialWriteEnvelope = None
