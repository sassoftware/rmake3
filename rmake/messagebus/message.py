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


import logging

from rmake.lib import chutney
from rmake.lib.jabberlink import message as jmessage
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
            payload = chutney.dumps(self.payload)
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
                    msg.payload = chutney.loads(jmsg.payload)
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
chutney.register(MessagePayload)


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
    _payload_slots = ('caps', 'tasks', 'slots', 'addresses')


class LogRecords(Message):
    messageType = 'logging'
    _payload_slots = ('records', 'job_uuid', 'task_uuid')
