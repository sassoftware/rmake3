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


import errno
import logging
import os
from twisted.internet import defer
from twisted.python import failure
from twisted.words.protocols.jabber.error import StanzaError
from twisted.words.protocols.jabber.jid import JID
from twisted.words.protocols.jabber.xmlstream import XMPPHandler
from rmake.lib import pubsub
from rmake.messagebus import common
from rmake.messagebus import message
from rmake.messagebus.client_support import PresenceProtocol, XMPPClient
from rmake.messagebus.common import toJID
from wokkel import disco
from wokkel import generic
from wokkel import iwokkel
from wokkel.ping import PingHandler
from zope.interface import implements

log = logging.getLogger(__name__)


class RmakeHandler(XMPPHandler):

    implements(iwokkel.IDisco)

    jid = None

    def connectionInitialized(self):
        self.jid = self.xmlstream.authenticator.jid
        self.xmlstream.addObserver(common.XPATH_RMAKE_MESSAGE, self.onMessage)
        self.xmlstream.addObserver(common.XPATH_RMAKE_IQ, self.onCommand)

    def onMessage(self, element):
        msg = message.Message.from_dom(element)
        if msg:
            self.parent.messageReceived(msg)

    def onCommand(self, element):
        pass

    def getDiscoInfo(self, requestor, target, nodeIdentifier=''):
        desc = self.parent.description or 'Unknown rMake component'
        ident = [disco.DiscoIdentity('automation', 'rmake', desc),
                disco.DiscoFeature(common.NS_RMAKE)]
        if self.parent.role:
            ident.append(common.getInfoForm(self.parent.role))
        return defer.succeed(ident)

    def getDiscoItems(self, requestor, target, nodeIdentifier=''):
        return defer.succeed([])


class RmakeClientHandler(RmakeHandler):

    targetRole = 'dispatcher'

    def __init__(self, targetJID):
        self.targetJID = targetJID

    def connectionInitialized(self):
        RmakeHandler.connectionInitialized(self)
        d = self.parent.checkAndSubscribe(self.targetJID, self.targetRole)
        def got_ok(dummy):
            self.parent.targetConnected()
        def got_error(failure):
            failure.trap(StanzaError)
            if failure.value.condition == 'service-unavailable':
                self.parent.targetLost(failure)
            else:
                return failure
        d.addCallbacks(got_ok, got_error)
        d.addErrback(onError)


class BusService(XMPPClient, pubsub.Publisher):

    # Service discovery info
    role = None
    description = None

    def __init__(self, cfg, handler=None, other_handlers=None):
        self.cfg = cfg
        jid, password = self._getIdent()
        XMPPClient.__init__(self, jid, password, registerCB=self._writeIdent)
        pubsub.Publisher.__init__(self)

        if not handler:
            handler = RmakeHandler()
        self._handler = handler
        self._handler.setHandlerParent(self)

        self._handlers = {
                'disco': disco.DiscoClientProtocol(),
                'disco_s': disco.DiscoHandler(),
                'ping': PingHandler(),
                'presence': PresenceProtocol(),
                'fallback': generic.FallbackHandler(),
                }
        if other_handlers:
            self._handlers.update(other_handlers)
        for handler in self._handlers.values():
            handler.setHandlerParent(self)

    def _getIdent(self):
        """Retrieve or generate a JID + password for this component to use."""
        try:
            fObj = open(self.cfg.xmppIdentFile)
        except IOError, err:
            if err.errno == errno.ENOENT:
                return self._makeIdent()
            raise
        return self._getIdent2(fObj)

    def _getIdent2(self, fObj):
        """Locate the JID and password to use in a stored identity map."""
        # This implementation is for components with well-known JIDs
        myJID = self.cfg.xmppJID
        assert myJID

        for line in fObj:
            jid, password = line.split()[:2]
            if toJID(jid).userhost() == myJID.userhost():
                return myJID, password.decode('ascii')
        else:
            return self._makeIdent()

    def _makeIdent(self):
        password = os.urandom(16).encode('hex').decode('utf8')
        return self.cfg.xmppJID, password

    def _writeIdent(self, jid, password):
        try:
            fObj = open(self.cfg.xmppIdentFile, 'a')
        except:
            log.exception("Could not save credentials for JID %s. Continuing "
                    "anyway.", jid)
            return
        fObj.write('%s %s\n' % (jid.userhost(), password))
        fObj.close()

    def checkAndSubscribe(self, jid, role):
        d = self._handlers['disco'].requestInfo(jid)
        @d.addCallback
        def got_info(info):
            if common.NS_RMAKE not in info.features:
                raise RuntimeError("%s is not a rmake component" % jid.full())
            form = info.extensions[common.FORM_RMAKE_INFO]
            actual_role = form.fields['role'].value
            if role != actual_role:
                raise RuntimeError("%s is not a rmake %s" % (jid.full(), role))
            self._handlers['presence'].subscribe(jid.userhostJID())
        return d

    def messageReceived(self, msg):
        if isinstance(msg, message.Event):
            try:
                msg.publish(self)
            except:
                log.exception("Error handling event %s:", msg.event)

    def onPresence(self, presence):
        pass


class BusClientService(BusService):

    """Base class for services that maintain a messagebus client."""

    resource = 'rmake'

    def __init__(self, cfg, handler=None, other_handlers=None):
        self._targetJID = cfg.dispatcherJID
        if not handler:
            handler = RmakeClientHandler(self._targetJID)
        BusService.__init__(self, cfg, handler=handler,
                other_handlers=other_handlers)
        self.addRelay(self._send_events)

    def _send_events(self, event, *args, **kwargs):
        msg = message.Event(event=event, args=args, kwargs=kwargs)
        msg.send(self.xmlstream, self._targetJID)

    def _getIdent2(self, fObj):
        """Locate the JID and password to use in a stored identity map."""
        # This implementation is for client components.
        targetJID = self.cfg.dispatcherJID
        assert targetJID

        for line in fObj:
            jid, password = line.split()[:2]
            jid = toJID(jid)
            if jid.host == targetJID.host:
                jid = JID(tuple=(jid.user, jid.host, self.resource))
                return jid, password.decode('ascii')
        else:
            return self._makeIdent()

    def _makeIdent(self):
        host = self.cfg.dispatcherJID.host
        username = os.urandom(16).encode('hex')
        password = os.urandom(16).encode('hex')
        jid = toJID('%s@%s/%s' % (username, host, self.resource))
        return jid, password

    ## Event handlers

    def onPresence(self, presence):
        if presence.sender == self._targetJID and not presence.available:
            self.targetLost(failure.Failure(
                RuntimeError("Target service became unavailable")))

    def targetConnected(self):
        pass

    def targetLost(self, failure):
        # FIXME: Not a great way to handle this.
        log.error("Server went away (%s), shutting down.", self._targetJID)
        from twisted.internet import reactor
        reactor.stop()

    ## Commands

    def sendToTarget(self, msg):
        msg.send(self, self._targetJID)


def onError(failure):
    log.error("Unhandled error in callback:\n%s", failure.getTraceback())
