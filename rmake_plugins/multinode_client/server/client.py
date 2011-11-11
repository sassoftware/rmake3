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


from rmake.server import client
from rmake.lib.apiutils import thaw

from rmake.multinode import messages
from rmake.multinode import nodeclient
from rmake.multinode import nodetypes

class MultinodeClientExtension(object):

    def attach(self, client):
        self.proxy = client.proxy
        client.listNodes = self.listNodes
        client.getMessageBusInfo = self.getMessageBusInfo
        self.standaloneListenToEvents = client.listenToEvents
        client.listenToEvents = self.listenToEvents

    def listNodes(self):
        """
            Lists all known nodes

            @return: list of (name, slots) for each node.
        """
        rv =  self.proxy.listNodes()
        return [thaw('Node', x) for x in rv]

    def getMessageBusInfo(self):
        """
            Returns data about the mesage bus for clients to connect
        """
        rv =  self.proxy.getMessageBusInfo()
        if not rv:
            return None
        return MessageBusInfo(**rv)

    def listenToEvents(self, uri, jobId, listener,
                       showTroveDetails=False,
                       serve=True):
        info = self.getMessageBusInfo()
        if not info:
            return self.standaloneListenToEvents(uri, jobId, listener=listener,
                                             showTroveDetails=showTroveDetails)
        else:
            receiver = EventReceiver(jobId, info.host, info.port, listener)
            receiver.connect()
            if serve:
                receiver.serve_forever()
            return receiver

class EventReceiver(nodeclient.NodeClient):
    sessionClass = 'CLI'
    def __init__(self, jobId, messageBusHost, messageBusPort, listener):
        node = nodetypes.Client()
        nodeclient.NodeClient.__init__(self, messageBusHost, messageBusPort,
                                       None, listener, node,
                                       logMessages=False)
        self.bus.logger.setQuietMode()
        self.bus.connect()
        self.bus.subscribe('/event?jobId=%s' % jobId)
        self.listener = listener
        listener._primeOutput(jobId)
        while not self.bus.isRegistered():
            self.serve_once()
            self.bus.flush()

    def messageReceived(self, m):
        nodeclient.NodeClient.messageReceived(self, m)
        if isinstance(m, messages.EventList):
            self.listener._receiveEvents(*m.getEventList())

    def _serveLoopHook(self):
        self.listener._serveLoopHook()

    def serve_forever(self):
        try:
            while True:
                self.handleRequestIfReady(0.01)
                self._serveLoopHook()
                if self.listener._shouldExit():
                    break
        finally:
            self.listener.close()

class MessageBusInfo(object):
    def __init__(self, host=None, port=None):
        self.host = host
        self.port = port

oldRmakeClient = client.rMakeClient
def rMakeClient(*args, **kw):
    rv = oldRmakeClient(*args, **kw)
    MultinodeClientExtension().attach(rv)
    return rv

def attach():
    client.rMakeClient = rMakeClient
