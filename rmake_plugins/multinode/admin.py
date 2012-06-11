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


import time

from rmake import errors
from rmake.lib.apiutils import freeze, thaw

from rmake.messagebus import busclient
from rmake.multinode.server import dispatcher
from rmake.multinode.server import messagebus
from rmake.multinode import workernode


class MessageBusAdminClient(object):
    def __init__(self, client):
        self.messagebus = messagebus.MessageBusRPCClient(client)
        self.dispatcher = None
        self._client = client
        self.nodes = {}

    def listMessageBusClients(self):
        """ Lists details about all the message bus clients """
        return self.messagebus.listSessions()

    def listMessageBusQueueLengths(self):
        """ Returns the number of messages in the queue for the 
            connected clients """
        return self.messagebus.listQueueLengths()

    def sendMessage(self, direction, m):
        self._client.sendMessage(direction, m)

    def getDispatcher(self):
        if self.dispatcher is None:
            dispatcherId = self._getDispatcherId()
            assert(dispatcherId)
            self.dispatcher = dispatcher.DispatcherRPCClient(self._client,
                                                             dispatcherId)
        return self.dispatcher

    def _getDispatcherId(self):
        sessionDict = self.messagebus.listSessions()
        for sessionId, class_ in sessionDict.items():
            if class_ == dispatcher.DispatcherNodeClient.sessionClass:
                return sessionId

    def listMessageBusSubscriptions(self):
        """ Asks the message bus for sessionId -> subscriptions mapping """
        pass

    def listNodes(self):
        """ asks the dispatcher for the set of nodes it knows about."""
        return self.getDispatcher().listNodes()

    def listChroots(self, nodeId):
        client = self.getNode(nodeId)
        return client.listChroots()

    def listQueuedCommands(self):
        """
            Asks the dispatcher for the set of commands which are currently
            queued.
        """
        return self.getDispatcher().listQueuedCommands()

    def listAssignedCommands(self):
        """
            Asks the dispatcher for the set of commands which are currently
            being run.
        """
        return self.getDispatcher().listAssignedCommands()

    def getNode(self, nodeId):
        nodeClient =  self.nodes.get(nodeId, None)
        if not nodeClient:
            nodeClient = workernode.WorkerNodeRPCClient(self._client, nodeId)
            self.nodes[nodeId] = nodeClient
        return nodeClient

    def listNodeCommands(self, nodeId):
        """ Asks a node for the set of commands it is working on """
        return self.getNode(nodeId).listCommands()

    def startChrootSession(self, nodeName, chrootPath, command, superUser, 
                           buildTrove=None):
        nodeId = self.getDispatcher().getNodeByName(nodeName)
        passed, results = self.getNode(nodeId).startChrootSession(chrootPath,
                                                     command, superUser,
                                                     buildTrove=buildTrove)
        if passed:
            return results
        else:
            results = thaw('FailureReason', results)
            raise errors.ServerError("Could not start session at %s: %s" % (nodeId, results))

    def deleteChroot(self, nodeName, chrootPath):
        nodeId = self.getDispatcher().getNodeByName(nodeName)
        self.getNode(nodeId).deleteChroot(chrootPath)

    def archiveChroot(self, nodeName, chrootPath, newPath):
        nodeId = self.getDispatcher().getNodeByName(nodeName)
        return self.getNode(nodeId).archiveChroot(chrootPath, newPath)

    def suspendNodes(self, nodeList, suspend):
        return self.getDispatcher().suspendNodes(nodeList, suspend)

    def ping(self, seconds=5, hook=None, sleep=0.1):
        """
            Check for availability of server.
            @param seconds: seconds to wait for ping to succeed
            @type seconds: float (default 5)
            @param hook: if not None, a function that is called after every
            ping failure.
            @type hook: function that takes no arguments
            @param sleep: seconds to sleep between each ping attempt.
            @type sleep: float (default 5)
            @return: True if ping succeeds (otherwise raises exception).
            @raise: errors.OpenError if ping fails
        """
        timeSlept = 0
        while timeSlept < seconds:
            try:
                if not self._client.isConnected():
                    self._client.connect()

                if not self._client.getSessionId():
                    self._client.poll()
                    # Raise something in case we don't get a sessionID
                    # by the deadline -- otherwise the re-raise fails.
                    raise errors.OpenError("Couldn't get a session ID")
                else:
                    return True
            except:
                if hook:
                    hook()
                time.sleep(sleep)
                timeSlept += sleep
        raise

def getAdminClient(host, port):
    bus = busclient.MessageBusClient(host, port, None)
    bus.logger.setQuietMode()
    return MessageBusAdminClient(bus)
