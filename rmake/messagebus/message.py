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
from jabberlink import message as jmessage

from rmake.messagebus.common import NS_RMAKE

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

    def to_jmessage(self):
        headers = {}
        if self.payload.__dict__:
            headers['content-type'] = 'application/python-pickle'
            headers['rmake-type'] = self.messageType
            payload = cPickle.dumps(self.payload, 2)
        else:
            payload = ''
        return jmessage.Message(NS_RMAKE, payload, headers)

    @classmethod
    def from_jmessage(cls, jmsg):
        sender = jmsg.sender.full()
        messageType = jmsg.headers['rmake-type']
        messageClass = _MessageTypeRegistrar.messageTypes.get(messageType)
        if not messageClass:
            log.warning("Unknown message type %s from %s", messageType, sender)
            return None
        msg = messageClass()

        payloadType = jmsg.headers.get('content-type')
        if payloadType is None:
            msg.payload = None
        else:
            if payloadType == 'application/python-pickle':
                try:
                    msg.payload = cPickle.loads(jmsg.payload)
                except:
                    log.warning("Failed to unpickle message from %s:", sender,
                            exc_info=1)
                    return None
            else:
                log.warning("Unknown payload type %s from %s", payloadType,
                        sender)
                return None

        msg.info.sender = jmsg.sender
        msg.info.id = jmsg.seq
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
    _payload_slots = ('cfg', 'task')


class StartTask(Message):
    messageType = 'start-task'
    _payload_slots = ('task',)


class TaskStatus(Message):
    messageType = 'task-status'
    _payload_slots = ('task',)


class Heartbeat(Message):
    messageType = 'heartbeat'
    _payload_slots = ('caps', 'tasks', 'slots')


class LogRecords(Message):
    messageType = 'logging'
    _payload_slots = ('records', 'task_uuid')
