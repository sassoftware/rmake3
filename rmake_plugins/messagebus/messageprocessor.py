#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import StringIO
import cPickle
import xmlrpclib

from rmake_plugins.messagebus import envelope
from rmake_plugins.messagebus import messages

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
