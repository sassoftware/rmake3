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


class Message(object):
    """Base class for all thawed message types."""

    messageType = None

    def __init__(self, *args, **kwargs):
        if args or kwargs:
            self.set(*args, **kwargs)

    def __repr__(self):
        className = type(self).__name__
        return '<%s>' % (className,)

    def _add_rmake_node(self, xmppNode):
        rmakeNode = xmppNode.addElement('rmake', NS_RMAKE)
        rmakeNode['type'] = self.messageType
        rmakeNode['content-type'] = 'application/python-pickle'

        payloadBytes = cPickle.dumps(self, 2)
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

        transferCoding = rmakeNode['transfer-encoding']
        if transferCoding == 'gzip+base64':
            payloadBytes = str(rmakeNode).decode('base64').decode('zlib')
        elif transferCoding == 'base64':
            payloadBytes = str(rmakeNode).decode('base64')
        else:
            log.warning("Unknown transfer coding %s from %s", transferCoding,
                    sender)
            return None

        payloadType = rmakeNode['content-type']
        if payloadType == 'application/python-pickle':
            try:
                message = cPickle.loads(payloadBytes)
            except:
                log.warning("Failed to unpickle message from %s:", sender,
                        exc_info=1)
                return None
        else:
            return None

        if rmakeNode['type'] != message.messageType:
            log.warning("Got message of type %s but it unpickled as a %s "
                    "(from %s)", rmakeNode['type'], message.messageType,
                    sender)
            return None

        if xmppNode.hasAttribute('id'):
            message._id = xmppNode['id']
        return message


class Event(Message):
    """Event published by the sender and subscribed by the receiver."""

    messageType = 'event'

    def set(self, subsystem, event, args, kwargs):
        self.subsystem = subsystem
        self.event = event
        self.args = args
        self.kwargs = kwargs

    def publish(self, publisher):
        """Publish this event to the given "publisher"."""
        publisher._send(self.event, *self.args, **self.kwargs)
