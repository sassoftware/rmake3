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
rMake messagebus client implementation for Twisted.

This includes a client protocol, factory, and XMLRPC proxy.
"""


import logging
from twisted.words.protocols.jabber.xmlstream import XMPPHandler
from rmake.lib import pubsub
from rmake.messagebus import common
from rmake.messagebus import message
from rmake.messagebus.common import toJID
from rmake.messagebus.pubsub import BusSubscriber
from wokkel import disco
from wokkel import xmppim
from wokkel.client import XMPPClient
from wokkel.ping import PingHandler

log = logging.getLogger(__name__)


class RmakeHandler(XMPPHandler):

    jid = None

    def connectionInitialized(self):
        self.jid = self.xmlstream.authenticator.jid
        self.xmlstream.addObserver(common.XPATH_RMAKE_MESSAGE, self.onMessage)
        self.xmlstream.addObserver(common.XPATH_RMAKE_IQ, self.onCommand)

    def onMessage(self, element):
        msg = message.Message.from_dom(element)
        if msg:
            print 'a message!'
        else:
            print 'not a message :('

    def onCommand(self, element):
        print 'cmd'



class RmakeClientHandler(RmakeHandler):

    targetRole = 'dispatcher'

    def __init__(self, targetJID):
        self.targetJID = targetJID

    def connectionInitialized(self):
        RmakeHandler.connectionInitialized(self)
        d = self.parent.checkAndSubscribe(self.targetJID, self.targetRole)
        def say_hi(dummy):
            msg = message.Event('useless', 'hello', (), {})
            msg.send(self.xmlstream, self.targetJID)
        d.addCallback(say_hi)
        d.addErrback(onError)


class BusService(XMPPClient):

    def __init__(self, reactor, jid, password):
        XMPPClient.__init__(self, toJID(jid), password)
        self._reactor = reactor

        self._handler = self._getHandler()
        self._handler.setHandlerParent(self)

        self._handlers = {
                'disco': disco.DiscoClientProtocol(),
                'disco_s': disco.DiscoHandler(),
                'ping': PingHandler(),
                'presence': PresenceProtocol(),
                }
        for handler in self._handlers.values():
            handler.setHandlerParent(self)

        self._publishers = {}
        self._subscribers = {}

    def _getHandler(self):
        raise NotImplementedError

    def checkAndSubscribe(self, jid, role):
        d = self._handlers['disco'].requestInfo(jid)
        def got_info(info):
            if common.NS_RMAKE not in info.features:
                raise RuntimeError("%s is not a rmake component" % jid.full())
            form = info.extensions[common.FORM_RMAKE_INFO]
            actual_role = form.fields['role'].value
            if role != actual_role:
                raise RuntimeError("%s is not a rmake %s" % (jid.full(), role))
            self._handlers['presence'].subscribe(jid.userhostJID())
        d.addCallback(got_info)
        return d


class BusClientService(BusService):

    """Base class for services that maintain a messagebus client."""

    resource = 'rmake'

    def __init__(self, reactor, jid, password, targetJID):
        # Connect with an anonymous JID (just the host + resource)
        self._targetJID = toJID(targetJID)
        BusService.__init__(self, reactor, jid, password)

    def _getHandler(self):
        return RmakeClientHandler(self._targetJID)

    def messageReceived(self, message):
        if isinstance(message, message_types.Event):
            # Forward event to all interested subscribers.
            publisher = self._publishers.get(message.targetTopic)
            if publisher:
                message.publish(publisher)

    # Pub-sub infrastructure
    def subscribeEvents(self, topic, subscriber):
        """Subscribe "subscriber" to events directed to "topic"."""
        if topic in self._publishers:
            publisher = self._publishers[topic]
        else:
            publisher = self._publishers[topic] = pubsub.Publisher()
        publisher.subscribe(subscriber)

    def publishEvents(self, topic, publisher):
        """Publish events from "publisher" to the given "topic"."""
        if topic in self._subscribers:
            subscriber = self._subscribers[topic]
        else:
            subscriber = self._subscribers[topic] = BusSubscriber(self, topic)
        publisher.subscribe(subscriber)


class PresenceProtocol(xmppim.PresenceProtocol, xmppim.RosterClientProtocol):
    """Accept all subscription requests and reply in kind."""

    def connectionInitialized(self):
        xmppim.PresenceProtocol.connectionInitialized(self)
        xmppim.RosterClientProtocol.connectionInitialized(self)
        # RFC-3921 7.3 says that we should request the roster before sending
        # initial presence or expecting any subscriptions to be in effect.
        def process_roster(roster):
            # Purge roster items with no active subscription.
            for item in roster.values():
                if not item.subscriptionTo and not item.subscriptionFrom:
                    self.removeItem(item.jid)
        d = self.getRoster()
        d.addCallback(process_roster)
        d.addBoth(lambda result: self.available())

    def subscribeReceived(self, presence):
        """If someone subscribed to us, subscribe to them."""
        self.subscribed(presence.sender)
        self.subscribe(presence.sender.userhostJID())

    def unsubscribeReceived(self, presence):
        """If someone unsubscribed us, unsubscribe them."""
        self.unsubscribed(presence.sender)
        self.unsubscribe(presence.sender.userhostJID())

    def onRosterSet(self, item):
        """If we no longer have visibility on someone, remove them entirely."""
        if not item.subscriptionTo and not item.subscriptionFrom:
            self.removeItem(item.jid)


def onError(failure):
    failure.printTraceback()
    # XXX -- don't do this
    from twisted.internet import reactor
    try:
        reactor.stop()
    except:
        pass
