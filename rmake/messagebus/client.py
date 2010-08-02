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


from jabberlink import cred as jcred
from jabberlink import client as jclient
from jabberlink import message as jmessage
from jabberlink.handlers import link as jlink
from twisted.internet import defer

from rmake.messagebus.common import NS_RMAKE
from rmake.messagebus import message as rmessage


class RmakeHandler(jlink.LinkHandler):

    permissive = True


class MessageHandler(jmessage.MessageHandler):

    namespace = NS_RMAKE

    def __init__(self, service):
        self.service = service

    def onMessage(self, neighbor, jmsg):
        message = rmessage.Message.from_jmessage(jmsg)
        self.service.messageReceived(message)


class _BaseService(jclient.LinkClient):

    clientType = 'rmake'
    description = 'Unknown rMake component'
    resource = 'rmake'

    handlerClass = RmakeHandler

    def sendTo(self, jid, message, wait=False):
        jmsg = message.to_jmessage()
        d = self.link.sendWithDeferred(jid, jmsg)
        if wait:
            return d
        # If you don't wait for delivery, errors are always discarded.
        d.addErrback(lambda _: None)
        return defer.succeed(None)

    def postStartService(self):
        return self.deferUntilConnected()

    def messageReceived(self, message):
        pass


class BusService(_BaseService):

    def __init__(self, cfg, other_handlers=None):
        self.cfg = cfg
        creds = jcred.XmppServerCredentials(cfg.xmppIdentFile)
        name = self.cfg.xmppJID.user, self.cfg.xmppJID.host
        _BaseService.__init__(self, name, creds, handlers=other_handlers)

        self.link.addMessageHandler(MessageHandler(self))


class BusClientService(_BaseService):

    """Base class for services that maintain a messagebus client."""

    def __init__(self, cfg, other_handlers=None):
        self.cfg = cfg
        creds = jcred.XmppClientCredentials(cfg.xmppIdentFile)
        self.targetJID = self.cfg.dispatcherJID
        _BaseService.__init__(self, self.targetJID.host, creds,
                handlers=other_handlers)

        self.link.addMessageHandler(MessageHandler(self))
        self.connectNeighbor(self.cfg.dispatcherJID)

    def sendToTarget(self, message, wait=False):
        return self.sendTo(self.targetJID, message, wait)

    def isConnected(self):
        neighbor = self.link._findNeighbor(self.targetJID)
        return neighbor and neighbor.isAuthenticated
