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


"""
rMake messagebus client implementation for Twisted.

This includes a client protocol, factory, and XMLRPC proxy.
"""


from rmake.lib.jabberlink import cred as jcred
from rmake.lib.jabberlink import client as jclient
from rmake.lib.jabberlink import message as jmessage
from rmake.lib.jabberlink.handlers import link as jlink
from rmake.messagebus.common import NS_RMAKE
from rmake.messagebus import message as rmessage


class RmakeHandler(jlink.LinkHandler):

    pass


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

    def __init__(self, *args, **kwargs):
        jclient.LinkClient.__init__(self, *args, **kwargs)
        self.link.permissive = self.cfg.xmppPermissive
        for jid in self.cfg.xmppPermit:
            self.listenNeighbor(jid)
        self.link.addMessageHandler(MessageHandler(self))

    def sendTo(self, jid, message):
        jmsg = message.to_jmessage()
        self.link.sendTo(jid, jmsg)

    def postStartService(self):
        return self.deferUntilConnected()

    def messageReceived(self, message):
        pass


class BusService(_BaseService):

    def __init__(self, cfg, other_handlers=None):
        self.cfg = cfg
        creds = jcred.XmppServerCredentials(cfg.xmppIdentFile)
        name = self.cfg.xmppJID.user, self.cfg.xmppJID.host
        _BaseService.__init__(self, name, creds, handlers=other_handlers,
                host=cfg.xmppHost)


class BusClientService(_BaseService):

    """Base class for services that maintain a messagebus client."""

    def __init__(self, cfg, other_handlers=None):
        self.cfg = cfg
        creds = jcred.XmppClientCredentials(cfg.xmppIdentFile)
        self.targetJID = self.cfg.dispatcherJID
        _BaseService.__init__(self, self.targetJID.host, creds,
                handlers=other_handlers, host=cfg.xmppHost)

        self.connectNeighbor(self.cfg.dispatcherJID)

    def sendToTarget(self, message):
        return self.sendTo(self.targetJID, message)

    def isConnected(self):
        neighbor = self.link._findNeighbor(self.targetJID)
        return neighbor and neighbor.isAuthenticated
