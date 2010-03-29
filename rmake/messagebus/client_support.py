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
from twisted.words.protocols.jabber import sasl
from twisted.words.protocols.jabber import xmlstream
from twisted.words.protocols.jabber import client as jclient
from wokkel import client as wclient
from wokkel import xmppim
from wokkel import subprotocols

log = logging.getLogger(__name__)


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

    # Subscriptions / roster

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

    # Presence

    def availableReceived(self, presence):
        self.parent.onPresence(presence)

    def unavailableReceived(self, presence):
        self.parent.onPresence(presence)


class RegisteringInitializer(object):

    def __init__(self, xmlstream, callback):
        self.xmlstream = xmlstream
        self.callback = callback
        self._inProgress = None

    def initialize(self):
        si = sasl.SASLInitiatingInitializer(self.xmlstream)
        d = si.initialize()
        d.addErrback(self.saslFailed)
        return d

    def saslFailed(self, failure):
        return self.registerAccount()

    def registerAccount(self):
        assert not self._inProgress
        auth = self.xmlstream.authenticator

        iq = jclient.IQ(self.xmlstream, 'set')
        iq.addElement(('jabber:iq:register', 'query'))
        iq.query.addElement('username', content=auth.jid.user)
        iq.query.addElement('password', content=auth.password)

        iq.addCallback(self._registerResultEvent)
        iq.send()

        d = defer.Deferred()
        self._inProgress = (d, auth.jid, auth.password)
        return d

    def _registerResultEvent(self, iq):
        init_d, jid, password = self._inProgress
        self._inProgress = None
        if iq['type'] == 'result':
            # Now that we're reigstered, insert another SASL attempt
            self.xmlstream.initializers.insert(0,
                    sasl.SASLInitiatingInitializer(self.xmlstream))
            if self.callback:
                d = defer.maybeDeferred(self.callback, jid, password)
                d.chainDeferred(init_d)
            else:
                init_d.callback(None)
        elif iq['type'] == 'error':
            jid = self.xmlstream.authenticator.jid.userhost()
            error = iq.error.firstChildElement().name
            if error == 'conflict':
                log.error("Registration of JID %s failed because it is "
                        "already registered. This means the stored password "
                        "is incorrect.", jid)
            else:
                log.error("Registration of JID %s failed (%s).", jid, error)
            init_d.errback(RuntimeError("Registration failed: %s" % error))


class RegisteringAuthenticator(xmlstream.ConnectAuthenticator):

    namespace = 'jabber:client'

    def __init__(self, jid, password, registerCB):
        xmlstream.ConnectAuthenticator.__init__(self, jid.host)
        self.jid = jid
        self.password = password
        self.registerCB = registerCB

    def associateWithStream(self, xs):
        xmlstream.ConnectAuthenticator.associateWithStream(self, xs)

        xs.initializers = [
                #xmlstream.TLSInitiatingInitializer(xs),
                RegisteringInitializer(xs, self.registerCB),
                ]

        for initClass, required in [
                (jclient.BindInitializer, True),
                (jclient.SessionInitializer, False),
                ]:
            init = initClass(xs)
            init.required = required
            xs.initializers.append(init)


class XMPPClient(wclient.XMPPClient):

    authClass = RegisteringAuthenticator

    def __init__(self, jid, password, registerCB=None, host=None, port=5222):
        # NB: This mostly duplicates XMPPClient.__init__ (hence not calling it)
        # but adds the pluggable authenticator.
        self.jid = jid
        self.domain = jid.host
        self.host = host
        self.port = port

        a = self.authClass(jid, password, registerCB)
        f = xmlstream.XmlStreamFactory(a)
        subprotocols.StreamManager.__init__(self, f)
