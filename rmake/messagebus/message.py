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

import cPickle
import logging
import random
from rmake.messagebus.common import toJID, NS_RMAKE
from twisted.internet import defer
from twisted.words.xish import domish
from twisted.words.protocols.jabber.xmlstream import IQ

log = logging.getLogger(__name__)


class _MessageTypeRegistrar(type):

    messageTypes = {}

    def __new__(metacls, name, bases, clsdict):
        clsdict.setdefault('__slots__', ())
        pslots = clsdict.get('_payload_slots')
        if pslots:
            setter = 'def set(self, %s):\n' % (', '.join(pslots))
            for pslot in pslots:
                # Define properties for each payload slot to fetch that
                # attribute.
                ctx = {}
                stmt = ('def %(n)s(self): return self.payload.%(n)s' %
                        dict(n=pslot))
                exec stmt in ctx
                clsdict[pslot] = property(ctx[pslot])

                setter += '    self.payload.%(n)s = %(n)s\n' % dict(n=pslot)

            # Define a set() method
            ctx = {}
            exec setter in ctx
            clsdict['set'] = ctx['set']

        cls = type.__new__(metacls, name, bases, clsdict)
        if cls.messageType:
            metacls.messageTypes[cls.messageType] = cls
        return cls


class Message(object):
    """Base class for all thawed message types."""
    __metaclass__ = _MessageTypeRegistrar
    __slots__ = ('payload', 'info')
    _payload_slots = None

    messageType = None

    def __init__(self, *args, **kwargs):
        self.payload = MessagePayload()
        self.info = MessageInfo()
        if args or kwargs:
            self.set(*args, **kwargs)

    def __repr__(self):
        className = type(self).__name__
        return '<%s>' % (className,)

    def _add_rmake_node(self, xmppNode):
        rmakeNode = xmppNode.addElement('rmake', NS_RMAKE)
        rmakeNode['type'] = self.messageType
        if self.payload.__dict__:
            rmakeNode['content-type'] = 'application/python-pickle'
            payloadBytes = cPickle.dumps(self.payload, 2)
            zippedBytes = payloadBytes.encode('zlib')
            if len(zippedBytes) < len(payloadBytes):
                rmakeNode['transfer-encoding'] = 'gzip+base64'
                rmakeNode.addContent(zippedBytes.encode('base64'))
            else:
                rmakeNode['transfer-encoding'] = 'base64'
                rmakeNode.addContent(payloadBytes.encode('base64'))
        return rmakeNode

    @staticmethod
    def _get_id():
        return '%x' % random.getrandbits(64)

    def send(self, xmlstream, to):
        msg = domish.Element((None, 'message'))
        msg['to'] = toJID(to).full()
        msg['type'] = 'normal'
        msg['id'] = self._get_id()
        self._add_rmake_node(msg)
        xmlstream.send(msg)
        return defer.succeed(None)

    @staticmethod
    def from_dom(xmppNode):
        sender = xmppNode.getAttribute('from')
        rmakeNode = xmppNode.firstChildElement()
        if not rmakeNode or (
                rmakeNode.uri, rmakeNode.name) != (NS_RMAKE, 'rmake'):
            # Not a rMake message.
            return None

        messageType = rmakeNode['type']
        messageClass = _MessageTypeRegistrar.messageTypes.get(messageType)
        if not messageClass:
            log.warning("Unknown message type %s from %s", messageType, sender)
            return None
        msg = messageClass()

        payloadType = rmakeNode.getAttribute('content-type')
        transferCoding = rmakeNode.getAttribute('transfer-encoding')
        if payloadType is None:
            msg.payload = None
        else:
            if transferCoding == 'gzip+base64':
                payloadBytes = str(rmakeNode).decode('base64').decode('zlib')
            elif transferCoding == 'base64':
                payloadBytes = str(rmakeNode).decode('base64')
            else:
                log.warning("Unknown transfer coding %s from %s",
                        transferCoding, sender)
                return None

            if payloadType == 'application/python-pickle':
                try:
                    msg.payload = cPickle.loads(payloadBytes)
                except:
                    log.warning("Failed to unpickle message from %s:", sender,
                            exc_info=1)
                    return None
            else:
                log.warning("Unknown payload type %s from %s", payloadType,
                        sender)
                return None

        msg.info.sender = xmppNode['from']
        msg.info.id = xmppNode.getAttribute('id')
        return msg

    def __getstate__(self):
        return {'payload': self.payload, 'info': self.info}

    def __setstate__(self, state):
        self.payload = state['payload']
        self.info = state['info']


class MessagePayload(object):
    """Dummy object used as an attribute store for messages."""


class MessageInfo(object):
    id = None
    sender = None


class Event(Message):
    """Event published by the sender and subscribed by the receiver."""
    messageType = 'event'
    _payload_slots = ('event', 'args', 'kwargs')

    def publish(self, publisher):
        """Publish this event to the given "publisher"."""
        publisher._send(self.payload.event, self.info, *self.payload.args,
                **self.payload.kwargs)


class StartWork(Message):
    messageType = 'start-work'
    _payload_slots = ('cfg',)


class StartTask(Message):
    messageType = 'start-task'
    _payload_slots = ('task',)


class TaskStatus(Message):
    messageType = 'task-status'
    _payload_slots = ('task',)


class Heartbeat(Message):
    messageType = 'heartbeat'
    _payload_slots = ('caps', 'tasks')
