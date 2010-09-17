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
#

import logging
from twisted.internet import defer
from twisted.python import failure as tw_fail
from twisted.words.protocols.jabber.error import StanzaError
from twisted.words.protocols.jabber.xmlstream import (IQ, XMPPHandler,
        toResponse)
from wokkel import disco
from wokkel import iwokkel
from zope.interface import implements

from rmake.lib.jabberlink import constants
from rmake.lib.jabberlink.message import Frame, Message
from rmake.lib.jabberlink.xutil import toJID
from rmake.lib.logger import logFailure

log = logging.getLogger(__name__)


XPATH_AUTHENTICATE = "/iq/authenticate[@xmlns='%s']" % constants.NS_JABBERLINK
XPATH_FRAME = "/iq[@type='set']/frame[@xmlns='%s']" % constants.NS_JABBERLINK


class LinkHandler(XMPPHandler):

    implements(iwokkel.IDisco)

    permissive = False

    def __init__(self):
        self.jid = None
        self.neighbors = {}
        self._callbacks = {}
        self._messageHandlers = {}
        self._rosterReceived = False

    def _addCallback(self, event):
        d = defer.Deferred()
        self._callbacks.setdefault(event, []).append(d)
        return d

    def _fireCallback(self, event, result=None):
        callbacks = self._callbacks.get(event, [])
        for d in callbacks:
            if isinstance(result, tw_fail.Failure):
                d.errback(result)
            else:
                d.callback(result)
        callbacks[:] = []

    def _findNeighbor(self, jid):
        if not jid.resource:
            # Can't magically create a neighbor with a userhost-only JID
            return None
        neighbor = self.neighbors.get(jid.userhost())
        if neighbor is None and self.permissive:
            neighbor = self._addNeighbor(jid, initiating=False)
        return neighbor

    # Configuration

    def addNeighbor(self, jid, initiating):
        jid = toJID(jid)
        self._addNeighbor(jid, initiating)
        if self._rosterReceived:
            self.presence.subscribe(jid)
        # else this neighbor will be processed once the roster is received

    def _addNeighbor(self, jid, initiating):
        ret = self.neighbors[jid.userhost()] = Neighbor(self, jid, initiating)
        return ret

    def addMessageHandler(self, handler):
        self._messageHandlers[handler.namespace] = handler

    def sendTo(self, jid, message):
        jid = toJID(jid)
        self._findNeighbor(jid).send(message)

    def sendWithDeferred(self, jid, message):
        jid = toJID(jid)
        return self._findNeighbor(jid).sendWithDeferred(message)

    def sendWithCallbacks(self, jid, message, callback, *args, **kwargs):
        jid = toJID(jid)
        self._findNeighbor(jid).sendWithCallbacks(message, callback,
                *args, **kwargs)

    def deferUntilConnected(self):
        if self.jid:
            return defer.succeed(None)
        else:
            return self._addCallback('connected')

    # Disco API

    def getDiscoInfo(self, requestor, target, nodeIdentifier=''):
        ident = []
        if self.parent.clientType:
            desc = self.parent.description or 'Unknown jabberlink component'
            ident.append(disco.DiscoIdentity('automation',
                self.parent.clientType, desc))
        for handler in self._messageHandlers.values():
            ident.append(disco.DiscoFeature(handler.namespace))
        return defer.succeed(ident)

    def getDiscoItems(self, requestor, target, nodeIdentifier=''):
        return defer.succeed([])

    # xmlstream events

    def connectionInitialized(self):
        self.jid = self.xmlstream.authenticator.jid
        self.presence = self.parent._handlers['presence']
        log.debug("Connected as %s", self.jid.full())

        self.xmlstream.addObserver(XPATH_AUTHENTICATE, self.onAuthenticate)
        self.xmlstream.addObserver(XPATH_FRAME, self.onFrame)

        self._getRoster()
        self._fireCallback('connected')

    def onPresence(self, presence):
        neighbor = self._findNeighbor(presence.sender)
        if not neighbor:
            return
        neighbor.inRoster = True
        if presence.available:
            neighbor.neighborUp()
        else:
            neighbor.neighborDown()

    def _getRoster(self):
        """Fetch a roster and subscribe to any missing neighbors."""
        d = self.presence.getRoster()

        @d.addCallback
        def got_roster(roster):
            self._rosterReceived = True
            for neighbor in self.neighbors.values():
                neighbor.inRoster = False
            for item in roster.values():
                neighbor = self.neighbors.get(item.jid.userhost())
                if neighbor and item.subscriptionTo and item.subscriptionFrom:
                    log.debug("Already subscribed to %s", item.jid)
                    neighbor.inRoster = True
            for neighbor in self.neighbors.values():
                if not neighbor.inRoster:
                    log.debug("Attempting to subscribe to %s",
                            neighbor.jid.full())
                    self.presence.subscribe(neighbor.jid)

        d.addErrback(logFailure, "Error processing roster:")

    def onAuthenticate(self, iq):
        jid = toJID(iq['from'])
        neighbor = self._findNeighbor(jid)
        if not neighbor:
            iq.handled = True
            error = StanzaError('not-authorized')
            self.send(error.toResponse(iq))
        elif not neighbor.initiating:
            neighbor.onAuthenticate(iq)

    def onFrame(self, iq):
        jid = toJID(iq['from'])
        neighbor = self._findNeighbor(jid)
        if neighbor:
            neighbor.onFrame(iq)
        else:
            iq.handled = True
            error = StanzaError('not-authorized')
            self.send(error.toResponse(iq))

    # API for Neighbor

    def onMessage(self, neighbor, message):
        handler = self._messageHandlers.get(message.message_type)
        if handler:
            try:
                handler.onMessage(neighbor, message)
            except:
                log.exception("Unhandled exception while handling message "
                        "from %s of type '%s':",
                        neighbor.jid.full(), message.message_type)
        else:
            log.warning("Discarding message from %s with unknown type '%s'",
                    neighbor.jid.full(), message.message_type)

    def onNeighborUp(self, jid):
        self.parent.onNeighborUp(jid)

    def onNeighborDown(self, jid):
        self.parent.onNeighborDown(jid)


class Neighbor(object):

    window_size = 4

    def __init__(self, link, jid, initiating):
        assert jid.resource
        self.link = link
        self.jid = jid
        self.initiating = initiating

        self.inRoster = False
        self.isAvailable = False
        self.isAuthenticated = False

        self.out_seq_ackd = 0  # Seq of first unacknowledged frame
        self.out_seq_sent = 0  # Seq of first unsent frame
        self.out_seq_new = 0  # Seq of first uncreated frame
        self.in_seq_recv = -1  # Seq of last frame received
        self.out_buf = []
        self.in_buf = []

        self.callbacks = {}

    def neighborUp(self):
        if not self.isAvailable:
            self.isAvailable = True
            log.debug("Neighbor %s is up", self.jid.full())
            self.link.onNeighborUp(self.jid)
            if self.initiating:
                self._do_authenticate()

    def neighborDown(self):
        if self.isAvailable:
            self._resetStream()
            log.debug("Neighbor %s is down", self.jid.full())
            self.link.onNeighborDown(self.jid)

    def _resetStream(self):
        self.isAvailable = False
        self.isAuthenticated = False
        self.out_seq_ackd = 0
        self.out_seq_sent = 0
        self.out_seq_new = 0
        self.in_seq_recv = -1
        self.out_buf = []
        self.in_buf = []

    # Authentication

    def _do_authenticate(self):
        iq = IQ(self.link.xmlstream, 'set')
        iq.addElement('authenticate', constants.NS_JABBERLINK)

        d = iq.send(self.jid.full())

        def auth_ok(resp):
            log.debug("Successfully authenticated to %s", self.jid.full())
            self.isAuthenticated = True
            self._do_send()

        def auth_fail(failure):
            failure.trap(StanzaError)
            if failure.value.condition == 'service-unavailable':
                # They either disappeared or don't support jabberlink
                self.neighborDown()
            else:
                return failure

        d.addCallbacks(auth_ok, auth_fail)
        d.addErrback(logFailure, "Error authenticating to neighbor %s" %
                self.jid.full())

    def onAuthenticate(self, iq):
        self.isAuthenticated = True
        iq.handled = True
        reply = toResponse(iq, 'result')
        self.link.send(reply)

    # Sending

    def send(self, message):
        frames = message.split(self.out_seq_new)
        self.out_buf.extend(frames)
        self.out_seq_new += len(frames)
        assert frames[-1].seq == (self.out_seq_new - 1)
        self._do_send()

    def _do_send(self):
        if not (self.isAvailable and self.isAuthenticated):
            # Not connected
            return
        if self.out_seq_new == self.out_seq_sent:
            # Nothing to send
            return
        # Send up to "window_size" frames before waiting for an ack
        max_seq = min(self.out_seq_new, self.out_seq_ackd + self.window_size)
        for send_seq in xrange(self.out_seq_sent, max_seq):
            frame = self.out_buf.pop(0)
            assert frame.seq == send_seq
            iq = frame.to_dom(self.link.xmlstream)
            d = iq.send(self.jid.full())
            d.addCallback(self._ack_received, send_seq)
            d.addErrback(logFailure)
            self.out_seq_sent += 1

    def _ack_received(self, dummy, seq_num):
        if seq_num != self.out_seq_ackd:
            log.warning("Ignoring out-of-sequence ACK from %s",
                    self.jid.full())
            return
        self.out_seq_ackd += 1
        self._do_send()

    def sendWithCallbacks(self, message, callback, *args, **kwargs):
        self.send(message)
        self.callbacks.setdefault(message.seq, []).append((callback, args,
            kwargs))

    def sendWithDeferred(self, message):
        d = defer.Deferred()
        results = []  # accumulator for incoming replies
        self.sendWithCallbacks(message, self._deferred_reply, d, results)
        return d

    def _deferred_reply(self, message, d, results):
        results.append(message)
        if not message.more:
            d.callback(results)

    # Receiving

    def onFrame(self, iq):
        iq.handled = True
        frame = Frame.from_dom(iq)
        if frame.seq != self.in_seq_recv + 1:
            log.warning("Ignoring out-of-sequence frame from %s",
                    self.jid.full())
            error = StanzaError('bad-request')
            self.link.send(error.toResponse(iq))
            return

        # ACK
        self.in_buf.append(frame)
        self.in_seq_recv += 1
        self.link.send(toResponse(iq, 'result'))

        if not frame.more:
            self._do_recv()

    def _do_recv(self):
        while self.in_buf:
            for n, frame in enumerate(self.in_buf):
                if not frame.more:
                    n += 1
                    break
            else:
                # No terminating frame received
                return

            frames, self.in_buf = self.in_buf[:n], self.in_buf[n:]
            message = Message.join(frames)
            if not message:
                continue

            message.sender = self.jid

            usedCallback = False
            if message.in_reply_to in self.callbacks:
                for func, args, kwargs in self.callbacks[message.in_reply_to]:
                    func(message, *args, **kwargs)
                    usedCallback = True
                if not message.more:
                    del self.callbacks[message.in_reply_to]

            if not usedCallback:
                self.link.onMessage(self, message)
