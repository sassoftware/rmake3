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
from twisted.words.protocols.jabber import xmlstream
from twisted.words.protocols.jabber.jid import JID
from twisted.words.xish import xmlstream as xish_stream
from wokkel import disco
from wokkel import generic
from wokkel import subprotocols
from wokkel.client import XMPPClient

from rmake.lib.jabberlink.handlers.link import LinkHandler
from rmake.lib.jabberlink.handlers.presence import FriendlyPresenceProtocol
from rmake.lib.jabberlink.initializers.register import RegisteringAuthenticator

log = logging.getLogger(__name__)


class LinkClient(XMPPClient):

    authClass = RegisteringAuthenticator
    handlerClass = LinkHandler

    clientType = None
    description = None
    resource = 'jabberlink'

    initialDelay = 0.1  # faster restart after registration

    def __init__(self, domain, creds, handlers=None, host=None, port=5222):
        # Note that this partly duplicates XMPPClient.__init__, so that method
        # should not be called.
        user, domain, password = creds.get(domain)
        self.jid = JID(tuple=(user, domain, self.resource))
        self.creds = creds
        self.domain = domain
        self.host = host
        self.port = port

        auth = self.authClass(self.jid, password, self._writeCreds)
        factory = XmlStreamFactory(auth)
        subprotocols.StreamManager.__init__(self, factory)

        self._handlers = {}

        self._configureHandlers(handlers)

        def post_connect(dummy):
            self.factory.resetDelay()
        self.deferUntilConnected().addCallback(post_connect)

    def _configureHandlers(self, other_handlers=None):
        self.link = self.handlerClass()
        self._handlers.update({
            'link': self.link,
            'disco': disco.DiscoClientProtocol(),
            'disco_s': disco.DiscoHandler(),
            'presence': FriendlyPresenceProtocol(),
            'fallback': generic.FallbackHandler(),
            })
        if other_handlers:
            self._handlers.update(other_handlers)
        for handler in self._handlers.values():
            handler.setHandlerParent(self)

    def _writeCreds(self, jid, password):
        """Called after successful registration to write the newly generated
        credentials to permanent storage."""
        self.creds.set(jid.user, jid.host, password)

    def deferUntilConnected(self):
        return self.link.deferUntilConnected()

    def connectNeighbor(self, jid):
        self.link.addNeighbor(jid, initiating=True)

    def listenNeighbor(self, jid):
        self.link.addNeighbor(jid, initiating=False)

    def onNeighborUp(self, jid):
        pass

    def onNeighborDown(self, jid):
        pass

    def getNeighborList(self):
        """Return a list of JIDs of authenticated neighbors."""
        out = []
        for neighbor in self.link.neighbors.itervalues():
            if not neighbor.isAuthenticated:
                continue
            out.append(neighbor.jid)
        return out


class XmlStreamFactory(xmlstream.XmlStreamFactory):

    reconnecting = False

    def buildProtocol(self, addr):
        # Override to prevent resetDelay() from being called until we actually
        # authenticate.
        self.reconnecting = False
        return xish_stream.XmlStreamFactoryMixin.buildProtocol(self, addr)

    def clientConnectionLost(self, connector, reason):
        if self.continueTrying and not self.reconnecting:
            log.error("XMPP connection lost: %s", reason.getErrorMessage())
        xmlstream.XmlStreamFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        if self.continueTrying:
            log.error("XMPP connection failed: %s", reason.getErrorMessage())
        xmlstream.XmlStreamFactory.clientConnectionFailed(self, connector,
                reason)

    def setReconnecting(self):
        self.reconnecting = True
