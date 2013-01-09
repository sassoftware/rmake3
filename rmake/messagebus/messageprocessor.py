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
