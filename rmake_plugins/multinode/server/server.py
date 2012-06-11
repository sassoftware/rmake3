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


import random
import socket

from rmake import errors
from rmake.lib import apirpc
from rmake.lib import procutil
from rmake.lib.apiutils import api, api_parameters, api_return, freeze, thaw
from rmake.multinode.server import subscriber
from rmake.worker.chroot import rootmanager

from rmake_plugins.multinode import admin

def allow_anonymous(fn):
    fn.allowAnonymousAccess = True
    return fn

class ServerExtension(apirpc.ApiServer):

    @api(version=1)
    @api_parameters(1)
    @api_return(1, None)
    def listNodes(self, callData):
        return [freeze('Node', x) for x in self.server.db.listNodes()]

    def _initializeNodes(self):
        self.server.db.deactivateAllNodes()

    @api(version=1)
    @api_parameters(1)
    @api_return(1, None)
    @allow_anonymous
    def getMessageBusInfo(self, callData):
        host = self.server.cfg.getMessageBusHost(qualified=True)
        return dict(host=host, port=self.server.cfg.messageBusPort)

    def __init__(self, server):
        self.server = server

    # replace the canBuild method.  Yuck.  There should be a better
    # way to outsource the determination of whether the server can 
    # support another build.
    def _canBuild(self):
        if self.server.db.getEmptySlots():
            return True

    def _authCheck(self, callData, fn, *args, **kw):
        if hasattr(fn, 'allowAnonymousAccess'):
            return True
        if (callData.auth.getSocketUser()
          or callData.auth.getCertificateUser()):
            return True
        user, password = (callData.auth.getUser(), callData.auth.getPassword())
        if (user, password) == self.server.internalAuth:
            return True
        self.server.auth.authCheck(user, password, callData.auth.getIP())
        return True

    def attach(self):
        server = self.server
        server._nodeClient = subscriber.rMakeServerNodeClient(server.cfg, self)
        server._nodeClient.connect()
        server._subscribers = [subscriber._JobDbLogger(server.db),
                                # it's important that the job logger comes 
                                # first, since that means the state will be 
                                # recorded in the database before it is 
                                # published
                               subscriber._RmakeBusPublisher(
                                                        server._nodeClient)]
        server._internalSubscribers = list(server._subscribers)
        server._addMethods(self)
        server._canBuild = self._canBuild
        server._authCheck = self._authCheck
        server._initializeNodes = self._initializeNodes
        server.worker = Worker(server.cfg, server._nodeClient, server._logger)


class Worker(object):
    """
        Used by build manager to speak w/ dispatcher + receive updates on 
        troves.
    """
    def __init__(self, cfg, client, logger):
        self.cfg = cfg
        self.client = client
        self.logger = logger
        self.chrootManager = rootmanager.ChrootManager(self.cfg, self.logger)

    def getAdminClient(self):
        return admin.getAdminClient(self.cfg.getMessageBusHost(),
                self.cfg.messageBusPort)

    def deleteChroot(self, host, chrootPath):
        self.getAdminClient().deleteChroot(host, chrootPath)

    def archiveChroot(self, host, chrootPath, newPath):
        return self.getAdminClient().archiveChroot(host, chrootPath, newPath)

    def listChrootsWithHost(self):
        client = self.getAdminClient()
        nodeIds = client.listNodes()
        localRoots = [('_local_', x) for x in self.chrootManager.listChroots()]
        chroots = []
        nodeNames = client.getDispatcher().getNamesByIds(nodeIds)
        for nodeId in nodeIds:
            nodeClient = client.getNode(nodeId)
            if nodeId not in nodeNames:
                continue
            nodeName = nodeNames[nodeId]
            chroots.extend((nodeName, x) for x in nodeClient.listChroots())
        return chroots + localRoots

    def startSession(self, host, chrootPath, command, superUser=False,
                     buildTrove=None):
        hostname, port = self.getAdminClient().startChrootSession(
                                                host, chrootPath, command,
                                                superUser, buildTrove)
        return True, (hostname, port)


    def buildTrove(self, buildCfg, jobId, buildTrove, eventHandler, 
                   buildReqs, targetLabel):
        buildTrove.disown()
        self.client.buildTrove(buildCfg, jobId, buildTrove,
                               buildReqs, targetLabel)

    def commandErrored(self, commandInfo, failureReason):
        buildTrove = commandInfo.getTrove()
        buildTrove.own()
        buildTrove.troveFailed(failureReason)

    def commandCompleted(self, commandInfo):
        # we'll wait for the "Trove built" message.
        pass

    def stopAllCommands(self):
        self.client.stopAllCommands()

    def hasActiveTroves(self):
        return bool(self.client._commands)

    def _checkForResults(self):
        if self.eventHandler.hadEvent():
            self.eventHandler.reset()
            return True
        return False

    def handleRequestIfReady(self):
        self.client.poll()
