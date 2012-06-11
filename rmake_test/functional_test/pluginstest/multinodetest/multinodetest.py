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
Basic multinode tests.
"""

import time

from rmake_test import rmakehelp
from conary_test import recipes

from conary.lib import util

class MultinodeTest(rmakehelp.RmakeHelper):

    def testMultinode(self):
        trv = self.addComponent('simple:source', '1.0-1', '',
                                [('simple.recipe', recipes.simpleRecipe)])
        self.openRmakeRepository()
        client = self.startRmakeServer(multinode=True)
        client = self.getRmakeHelper(client.uri)

        adminClient = self.getAdminClient()
        nodes = adminClient.listNodes()
        assert(len(nodes) == 0)
        self.startNode(1)
        while True:
            nodes = adminClient.listNodes()
            if len(nodes) == 1:
                break
        self._checkPids()
        jobId = self.discardOutput(client.buildTroves,
                                   [trv.getNameVersionFlavor()], 
                                   buildConfig=self.buildCfg)
        while True:
            assignedCommands = adminClient.listAssignedCommands()
            time.sleep(.5)
            if assignedCommands:
                break
        nodeId = assignedCommands[0][1]
        commands = []
        loopCount = 0
        while not commands and loopCount < 1000:
            queuedCommands, commands = adminClient.listNodeCommands(nodeId)
            time.sleep(.5)
            self._checkPids()
            loopCount += 1
        assert(loopCount != 1000)
        loopCount = 0
        # wait until the command has been finished by this node.
        while commands or queuedCommands and loopCount < 1000:
            queuedCommand, commands = adminClient.listNodeCommands(nodeId)
            time.sleep(.5)
            self._checkPids()
            loopCount += 1
        assert(loopCount != 1000)
        client.waitForJob(jobId)
        job = client.getJob(jobId)
        assert(job.isBuilt())

    def testMultinodeStartNodeLate(self):
        trv = self.addComponent('simple:source', '1.0-1', '',
                                [('simple.recipe', recipes.simpleRecipe)])
        self.openRmakeRepository()
        client = self.startRmakeServer(multinode=True)
        client = self.getRmakeHelper(client.uri)
        jobId = self.discardOutput(client.buildTroves,
                                   [trv.getNameVersionFlavor()], 
                                   buildConfig=self.buildCfg)
        queuedCommands = []
        adminClient = self.getAdminClient()
        #while not queuedCommands:
        #    queuedCommands = adminClient.listQueuedCommands()
        #    time.sleep(.1)
        time.sleep(.5)
        #assert(adminClient.listQueuedCommands())
        self.startNode(1)
        # wait for the command to be assigned to the now-available node.
        while queuedCommands:
            queuedCommands = adminClient.listQueuedCommands()
            time.sleep(.1)
        client.waitForJob(jobId)
        job = client.getJob(jobId)
        assert(job.isBuilt())

    def testMultinodeShutDown(self):
        # for a while, multinode server wasn't doing the right thing on
        # the reception of sigints - instead, it was waiting for the 20 second
        # timeout to kill the dispatcher and the multinode server.  This
        # should ensure they both shut down in half that time (should be faster
        # but allowances made for boxes under heavy load)
        self.startRmakeServer(multinode=True)
        start = time.time()
        self.stopRmakeServer()
        finish = time.time()
        assert(finish - start <= 10)

    def testListChroots(self):
        self.openRmakeRepository()
        client = self.startRmakeServer(multinode=True)
        self.startNode()
        nodeName = self.nodeCfg.name
        trv, cs = self.Component('foo:source')
        job = self.newJob(trv)
        trv = job.iterTroves().next()
        publisher = self.subscribeServer(client, trv, multinode=True)
        db = self.openRmakeDatabase()
        trv.creatingChroot(nodeName, 'foo')
        while not db.listChroots():
            time.sleep(.1)
            trv.creatingChroot(nodeName, 'foo')
        assert([ (x.host, x.path) for x in db.listChroots()] 
                == [(nodeName, 'foo')])
        util.mkdirChain(self.rmakeCfg.buildDir + '/chroots/foo')
        assert([ (x.host, x.path) for x in client.listChroots()] 
                == [(nodeName, 'foo')])
        util.rmtree(self.rmakeCfg.buildDir + '/chroots/foo')
        assert([ (x.host, x.path) for x in client.listChroots()] == [])
