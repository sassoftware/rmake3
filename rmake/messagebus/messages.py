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
import sys
import types
import xmlrpclib


class MessageHeaders(object):
    def __setattr__(self, key, value):
        if value is None:
            value = ''
        if not isinstance(value, (str, int, float)):
            raise RuntimeError('Bad value %r for key %s: '
                'Only strings can go in headers' % (value, key))
        return object.__setattr__(self, key, value)

    def __str__(self):
        lines = []
        for key, value in sorted(self.__dict__.iteritems()):
            if key.startswith('_'):
                continue
            lines.append('%s: %s\n' % (key, value))
        return ''.join(lines)

class MessagePayload(object):
    def __init__(self):
        self._thawed = True
        self._thawing = False
        self._stream = None
        self._streamSize = 0

    def getStream(self):
        return self._stream

    def setStream(self, stream, size):
        self._stream = stream
        self._streamSize = size
        self._thawed = False

    def getStreamSize(self):
        return self._streamSize

    def __setattr__(self, key, value):
        if not key.startswith('_'):
            if self._stream and self._thawed:
                self._stream.close()
                self._stream = None
                self._streamSize = 0
        return object.__setattr__(self, key, value)

class PayloadWrapper(object):
    def __init__(self, payload, thawMethod):
        self._payload = payload
        self._thawMethod = thawMethod

    def __getattr__(self, key):
        if not hasattr(self._payload, key):
            stream = self._payload.getStream()
            stream.seek(0)
            frz = stream.read(self._payload.getStreamSize())
            self._payload._thawed = True
            self._thawMethod(frz)
        obj = getattr(self._payload, key)
        return obj

    def __setattr__(self, key, value):
        if key.startswith('_'):
            return object.__setattr__(self, key, value)
        return setattr(self._payload, key, value)


_messageTypes = {}
class MessageTypeRegistrar(type):
    def __init__(self, name, bases, dict):
        type.__init__(self, name, bases, dict)
        _messageTypes[self.messageType] = self


class _Message:
    __metaclass__ = MessageTypeRegistrar
    messageType = 'UNKNOWN'
    def __init__(self, *args, **kw):
        self.headers = MessageHeaders()
        self.headers.messageType = self.messageType
        self._payload = MessagePayload()
        self.payloadStream = None
        self.payloadSize = 0
        self.headers.messageId = '<no messageId>'
        self.headers.sessionId ='<no sessionId>'
        self.headers.timeStamp = 0
        if args or kw:
            self.set(*args, **kw)


    def _getPayloadWrapper(self):
        if not self._payload._thawed:
            return PayloadWrapper(self._payload, self.loadPayloadFromString)
        return self._payload
    payload = property(_getPayloadWrapper)

    def stamp(self, messageId, senderId, timeStamp):
        self.headers.messageId = messageId
        self.headers.sessionId = senderId
        self.headers.timeStamp = timeStamp

    def getHeaders(self):
        return self.headers

    def getSessionId(self):
        return self.headers.sessionId

    def getMessageId(self):
        return self.headers.messageId

    def getDestination(self):
        return self.headers.destination

    def setDestination(self, destination):
        self.headers.destination = destination

    def getTargetId(self):
        return getattr(self.headers, 'targetId', None)

    def getTimestamp(self):
        return float(self.headers.timeStamp)

    def thawPayloadStream(self):
        if self._payload._thawed:
            return
        stream = self.getPayloadStream()
        stream.seek(0)
        frz = stream.read(self.getPayloadStreamSize())
        self.loadPayloadFromString(frz)

    def loadPayloadFromDict(self, d):
        self._payload.__dict__.update(d)

    def loadPayloadFromString(self, frz):
        d = xmlrpclib.loads(frz)[0][0]
        self.loadPayloadFromDict(d)
        self.payload._thawed = True

    def payloadToString(self):
        return xmlrpclib.dumps((self.payloadToDict(),), allow_none=True)

    def payloadToDict(self):
        return dict((x[0], x[1]) for x in 
                     self.payload.__dict__.iteritems() if not x[0][0] == '_')

    def getPayloadStream(self):
        if not self.payload.getStream():
            frz = self.payloadToString()
            s = StringIO.StringIO()
            s.write(frz)
            s.seek(0, 0)
            self.payload.setStream(s, len(frz))
        return self.payload.getStream()

    def getPayloadStreamSize(self):
        self.getPayloadStream()
        return self.payload.getStreamSize()

    def updateHeaders(self, dict):
        for key, value in dict.iteritems():
            if value != None:
                setattr(self.headers, key, value)

    def setHeaders(self, dict):
        self.headers = MessageHeaders()
        self.updateHeaders(dict)

    def setPayloadStream(self, stream, size):
        self.payload.setStream(stream, size)

    def freeze(self):
        return ( self.headers.__dict__, self.getPayloadStream(),
                 self.getPayloadStreamSize() )

    def thaw(self, headers, payload):
        self.headers = headers
        self._payload = payload

    def __str__(self):
        x = str(self.headers)
        x += 'payload length: %s chars' % self.payloadSize
        return x

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self.getMessageId())

class ConnectionRequest(_Message):
    messageType = 'CONNECT'

    def set(self, user, password, sessionClass='', sessionId='',
            subscriptions=None):
        self.headers.user = user
        self.headers.password = password
        self.headers.requestedSessionId = sessionId
        self.headers.sessionClass = sessionClass
        if subscriptions is None:
            subscriptions = []
        self.payload.subscriptions = subscriptions

    def getSessionClass(self):
        return self.headers.sessionClass

    def getSubscriptions(self):
        return self.payload.subscriptions

class ConnectedResponse(_Message):
    messageType = 'CONNECTED'

    def set(self, sessionId):
        self.headers.sessionId = sessionId

class SubscribeRequest(_Message):
    messageType = 'SUBSCRIBE'

    def set(self, destination):
        self.headers.destination = destination

class MethodCall(_Message):
    messageType = 'METHOD'

    def set(self, targetId, methodName, params):
        self.headers.targetId = targetId
        self.headers.methodName = methodName
        self.payload.params = params

    def getMethodName(self):
        return self.headers.methodName

    def getParams(self):
        return self.payload.params

class MethodResponse(_Message):
    messageType = 'RESPONSE'

    def set(self, message, returnValue, isFinal=True):
        self.headers.responseTo = message.getMessageId()
        self.headers.targetId = message.getSessionId()
        if not isFinal:
            isFinal = ''
        self.headers.isFinal = isFinal
        self.payload.returnValue = returnValue

    def isError(self):
        return False

    def isFinal(self):
        return bool(self.headers.isFinal)

    def getReturnValue(self):
        return self.payload.returnValue

    def getResponseTo(self):
        return self.headers.responseTo

class MethodError(MethodResponse):
    messageType = 'ERROR'

    def set(self, message, errorData):
        MethodResponse.set(self, message, errorData, True)

    def isError(self):
        return True

class Message(_Message):
    def direct(self, destination, targetId=None):
        self.headers.destination = destination
        if targetId:
            self.headers.targetId = targetId


class DummyMessage(Message):
    "Container for unrecognized message types."
    def __repr__(self):
        return '<%s>(%s)' % (self.headers.messageType, self.getMessageId())


class NodeStatus(Message):
    messageType = 'NODE_STATUS'
    def set(self, sessionId, status):
        self.headers.statusId = sessionId
        self.headers.status = status

    def getStatusId(self):
        return self.headers.statusId

    def getStatus(self):
        return self.headers.status

    def isDisconnected(self):
        return self.headers.status == 'DISCONNECTED'


def thawMessage(headers, payloadStream, payloadSize):
    messageType = headers['messageType']
    if messageType in _messageTypes:
        class_ = _messageTypes[messageType]
    else:
        class_ = DummyMessage
    m = class_()
    m.setHeaders(headers)
    m.setPayloadStream(payloadStream, payloadSize)
    #m.thawPayloadStream()
    return m
