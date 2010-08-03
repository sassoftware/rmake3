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
from wokkel import xmppim

log = logging.getLogger(__name__)


class FriendlyPresenceProtocol(xmppim.PresenceProtocol,
        xmppim.RosterClientProtocol):
    """Accept all subscription requests and reply in kind."""

    def connectionInitialized(self):
        xmppim.PresenceProtocol.connectionInitialized(self)
        xmppim.RosterClientProtocol.connectionInitialized(self)
        # RFC-3921 7.3 says that we should request the roster before sending
        # initial presence or expecting any subscriptions to be in effect.
        d = self.getRoster()

        @d.addCallback
        def process_roster(roster):
            # Purge roster items with no active subscription.
            for item in roster.values():
                if not item.subscriptionTo and not item.subscriptionFrom:
                    self.removeItem(item.jid)
        d.addBoth(lambda result: self.available())

    # Subscriptions / roster

    def subscribeReceived(self, presence):
        """If someone subscribed to us, subscribe to them."""
        log.debug("Auto-subscribing to %s", presence.sender.userhost())
        self.subscribed(presence.sender)
        self.subscribe(presence.sender.userhostJID())

    def unsubscribeReceived(self, presence):
        """If someone unsubscribed us, unsubscribe them."""
        log.debug("Auto-unsubscribing to %s", presence.sender.userhost())
        self.unsubscribed(presence.sender)
        self.unsubscribe(presence.sender.userhostJID())

    def onRosterSet(self, item):
        """If we no longer have visibility on someone, remove them entirely."""
        if not item.subscriptionTo and not item.subscriptionFrom:
            self.removeItem(item.jid)

    # Presence

    def availableReceived(self, presence):
        self.parent.link.onPresence(presence)

    def unavailableReceived(self, presence):
        self.parent.link.onPresence(presence)
