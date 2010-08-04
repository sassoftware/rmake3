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


class XmlStreamFactory(xmlstream.XmlStreamFactory):

    def buildProtocol(self, addr):
        # Override to prevent resetDelay() from being called until we actually
        # authenticate.
        return xish_stream.XmlStreamFactoryMixin.buildProtocol(self, addr)

    def clientConnectionLost(self, connector, reason):
        log.error("XMPP connection lost: %s", reason.getErrorMessage())
        xmlstream.XmlStreamFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        log.error("XMPP connection failed: %s", reason.getErrorMessage())
        xmlstream.XmlStreamFactory.clientConnectionFailed(self, connector,
                reason)
