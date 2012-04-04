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
Tests dispatcher
"""

import asyncore
import os
import socket
import sys
import time

from testutils import mock
from rmake_test import rmakehelp
from conary_test import recipes

from conary.deps import deps
from conary.deps.deps import parseFlavor

from rmake.build import buildjob
from rmake.build import dephandler
from rmake.lib import procutil
from rmake.messagebus import messages as mbmessages
from rmake.multinode import messages as mnmessages
from rmake.multinode import nodetypes
from rmake.multinode.server import dispatcher
from rmake.worker import recorder

sleepRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'sleep'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        r.Run('sleep 180')
"""

class DispatcherTest(rmakehelp.RmakeHelper):
    def makeCommandMessage(self, num, jobId, troveTup, buildReqs=[]):
        buildTrove = self.newBuildTrove(jobId, *troveTup)
        commandId = 'CMD-%s' % num
        messageId = 'MSG-%s' % commandId
        m = mnmessages.BuildCommand(commandId, self.buildCfg, jobId,
                                  buildTrove, buildReqs, [], 
                                  self.cfg.buildLabel)
        m.stamp(messageId, 'SND-' + messageId, time.time())
        return m

    def makeResolveMessage(self, num, jobId, troveTup):
        buildTrove = self.newBuildTrove(jobId, *troveTup)
        commandId = 'CMD-%s' % num
        messageId = 'MSG-%s' % commandId
        resolveJob = dephandler.ResolveJob(buildTrove, self.buildCfg)
        m = mnmessages.ResolveCommand(commandId, jobId, resolveJob,
                                    buildTrove)
        m.stamp(messageId, 'SND-' + messageId, time.time())
        return m



    def makeStopMessage(self, num, cmd):
        commandId = 'CMD-%s' % num
        messageId = 'MSG-%s' % commandId
        targetId = cmd.getCommandId()
        m = mnmessages.StopCommand(commandId, jobId=cmd.getJobId(),
                                 targetCommandId=targetId)
        m.stamp(messageId, 'SND-' + messageId, time.time())
        return m

    def makeMachineInfo(self, loadavg=1):
        info = procutil.MachineInformation()
        info.loadavg = (loadavg, loadavg, loadavg)
        return info

    def makeRegisterNodeMessage(self, slots=1, jobTypes=None,
                                buildFlavors=None, loadThreshold=10,
                                loadavg=0.5, chrootLimit=4):
        if jobTypes is None:
            jobTypes = self.getNodeCfg().jobTypes
        if buildFlavors is None:
            buildFlavors = [deps.parseFlavor('is:x86')]
        else:
            buildFlavors = [ parseFlavor(x, raiseError=True)
                             for x in buildFlavors]
        nodeInfo = procutil.MachineInformation()
        nodeInfo.loadavg = (loadavg, loadavg, loadavg)
        node = nodetypes.WorkerNode('name', 'localhost', slots, jobTypes, 
                                    buildFlavors, loadThreshold, nodeInfo, [],
                                    chrootLimit)
        return mnmessages.RegisterNodeMessage(node)

    def _check(self, sessionClient, messageType, **headerValues):
        m = sessionClient.messageProcessor.sendMessage._mock.popCall()[0][0]
        assert(isinstance(m, messageType))
        for key, value in headerValues.items():
            self.assertEquals(getattr(m.headers,key), value)

    def _setupMockDispatcher(self):
        db = mock.MockObject()
        self.rmakeCfg.messageBusPort = None
        server = dispatcher.DispatcherServer(self.rmakeCfg, db)
        sessionClient = server.client.getBusClient().getSession()
        mock.mockMethod(sessionClient.poll)
        mock.mockMethod(sessionClient.connect)
        mock.mockMethod(sessionClient.disconnect)
        mock.mockMethod(sessionClient.messageProcessor.sendMessage)
        mock.mock(sessionClient, 'logger')
        mock.mock(server.client.getBusClient(), 'logger')
        sessionClient.handle_connect()
        self._check(sessionClient, mbmessages.ConnectionRequest,
                    sessionClass='DSP')
        m = mbmessages.ConnectedResponse()
        m.set(sessionId='DSP-foo')
        sessionClient.handle_message(m)
        return server, sessionClient

    def testDispatcherServer(self):
        # Test only the server class, not the entire dispatcher
        # hierarchy
        db = mock.MockObject()
        self.rmakeCfg.messageBusPort = None
        server = dispatcher.DispatcherServer(self.rmakeCfg, db)
        mock.mock(server, 'client')
        cmd1 = self.makeCommandMessage(1, 1, self.getNVF('foo:source'))
        trv = cmd1.getTrove()
        cmd2 = self.makeCommandMessage(2, 2, self.getNVF('bar:source',
                                                        flavor='is:x86_64'),
                                [('foo:runtime', (None, None), (trv.getVersion(), parseFlavor('is:x86_64')))])
        cmd3 = self.makeCommandMessage(3, 3, self.getNVF('foo:source',
                                                        flavor='bar is:x86'),
                [('foo:runtime', (None, None), (trv.getVersion(), parseFlavor('bar is:x86')))])
        # command 4 is also from job 2.
        cmd4 = self.makeCommandMessage(4, 2, self.getNVF('bam:source'))
        server.requestCommandAssignment(cmd1, cmd2, cmd3, cmd4)
        server._assignQueuedCommands()
        assert(server.listQueuedCommands() == [ cmd1.getMessageId(),
                                                cmd2.getMessageId(),
                                                cmd3.getMessageId(),
                                                cmd4.getMessageId()])
        node =  self.makeRegisterNodeMessage().getNode()
        # this assigns a command to this node as well.
        server.nodeRegistered('session1', node)
        server.client.assignCommand._mock.assertCalled(cmd1, node)
        server._assignQueuedCommands()
        assert(server.listQueuedCommands() == [ cmd2.getMessageId(),
                                                cmd3.getMessageId(),
                                                cmd4.getMessageId()])
        assert(server.listAssignedCommands()
                == [(cmd1.getCommandId(), node.sessionId)])
        server.commandCompleted(cmd1.getCommandId())
        assert(server.listAssignedCommands() 
                == [(cmd3.getCommandId(), node.sessionId)])
        assert(server.listQueuedCommands() == [ cmd2.getMessageId(),
                                                cmd4.getMessageId()])
        server.commandErrored(cmd3.getCommandId())
        assert(server.listQueuedCommands() == [ cmd2.getMessageId()])
        assert(server.listAssignedCommands()
                == [(cmd4.getCommandId(), node.sessionId)])

        cmd5 = self.makeStopMessage(6, cmd2)
        server.requestCommandAssignment(cmd5)
        assert(not server.listQueuedCommands())

    def testThreshold(self):
        db = mock.MockObject()
        self.rmakeCfg.messageBusPort = None
        server = dispatcher.DispatcherServer(self.rmakeCfg, db)
        mock.mock(server, 'client')
        cmd1 = self.makeCommandMessage(1, 1, self.getNVF('foo:source'))
        cmd2 = self.makeCommandMessage(2, 2, self.getNVF('bar:source'))
        server.requestCommandAssignment(cmd1, cmd2)
        node =  self.makeRegisterNodeMessage(loadThreshold=1).getNode()
        server.nodeRegistered('session1', node)
        nodeInfo = self.makeMachineInfo(loadavg=10)
        server.nodeUpdated('session1', nodeInfo, ['CMD-1'])
        # the command completed, but the load average for this node is 
        # too high, so we wait.
        server.commandCompleted(cmd1.getCommandId())

        assert(not server.listAssignedCommands())
        nodeInfo = self.makeMachineInfo(loadavg=0.5)
        # the load average is low again, so now the second job is assigned.
        server.nodeUpdated('session1', nodeInfo, [])
        assert(server.listAssignedCommands())

    def testDispatcherRPC(self):
        server, sessionClient = self._setupMockDispatcher()
        mock.mockMethod(server.client._logger.logRPCCall)
        rpcClient = dispatcher.DispatcherRPCClient(
                                    server.getClient().getBusClient(),
                                    sessionClient.sessionId)
        cmd1 = self.makeCommandMessage(1, 1, self.getNVF('foo:source'))
        server.requestCommandAssignment(cmd1)
        assert(rpcClient.listQueuedCommands() == [cmd1.getMessageId()])
        node =  self.makeRegisterNodeMessage().getNode()
        # this assigns a command to this node as well.
        server.nodeRegistered('session1', node)
        assert(rpcClient.listQueuedCommands() == [])
        assert(rpcClient.listAssignedCommands() == [(cmd1.getCommandId(),
                                                     node.sessionId)])
        assert(rpcClient.listNodes() == [node.sessionId])
        server.nodeDisconnected('session1')
        assert(rpcClient.listNodes() == [])

    def testLogger(self):
        db = self.openRmakeDatabase()
        troveTup = self.getNVF('foo:source')
        job = buildjob.NewBuildJob(db, [troveTup])
        buildTrove = self.newBuildTrove(job.jobId, *troveTup)
        job.setBuildTroves([buildTrove])
        buildTrove.logPath = self.workDir + '/log'
        buildLog = recorder.BuildLogRecorder()
        buildLog.attach(buildTrove)
        pid = os.fork()
        if pid:
            port = buildLog.getPort()
            logPath = buildLog.logPath
            buildLog.close()
            del buildLog
            s = socket.socket()
            s.connect(('localhost', port))
            s.send('blah blah blah\n')
            s.send('blah blah')
            s.close()
            os.waitpid(pid, 0)
            self.assertEquals(open(logPath).read(),
                              'blah blah blah\nblah blah')
            os.remove(logPath)
        else:
            buildLog._logger.setQuietMode()
            try:
                buildLog.serve_forever()
            finally:
                os._exit(0)

    def testFlavorSelection(self):
        server, sessionClient = self._setupMockDispatcher()
        mock.mockMethod(server.client._logger.logRPCCall)
        rpcClient = dispatcher.DispatcherRPCClient(
                                    server.getClient().getBusClient(),
                                    sessionClient.sessionId)
        node =  self.makeRegisterNodeMessage(
                        buildFlavors=['is:x86 x86_64']).getNode()
        # this assigns a command to this node as well.
        server.nodeRegistered('session1', node)
        assert(server._nodes.getNodeForFlavors([parseFlavor('foo is:x86')]))
        assert(server._nodes.getNodeForFlavors([parseFlavor('bar is:x86_64')]))
        assert(server._nodes.getNodeForFlavors([parseFlavor('bar is:x86 x86_64')]))
        assert(server._nodes.getNodeForFlavors([parseFlavor('')]))
        assert(not server._nodes.getNodeForFlavors([
                                            parseFlavor('foo is:ppc')]))

    def testDispatcherServerFull(self):
        # this should be a functional test where we look at everything
        # from the command being sent in to the events being sent out
        # and the contents of the log.
        # Is it okay still to have a fake Node that performs the build and
        # writes to the port?
        raise testsuite.SkipTestException

    def testDispatcherServerStopFull(self):
        self.startRmakeServer(multinode=True)
        self.startNode()
        trv = self.addComponent('sleep:source', '1.0',
                                [('sleep.recipe', sleepRecipe)])
        name, version, flavor = trv.getNameVersionFlavor()
        flavor = deps.parseFlavor('is:x86')
        buildTrove = self.newBuildTrove(1, name, version, flavor)
        m = mnmessages.BuildCommand('CMD-1', self.buildCfg, 1, buildTrove, [],
                                    [], self.cfg.buildLabel)
        admin = self.getAdminClient(self.rmakeCfg.messageBusPort)
        admin.sendMessage('/command', m)
        count = 0
        while not admin.listNodes() and count < 180:
            time.sleep(.1)
            count += .1
        nodeId = admin.listNodes()[0]
        count = 0
        #print 'Waiting for command to start'
        while not admin.listNodeCommands(nodeId)[1] and count < 180:
            time.sleep(.1)
            count += .1
        m = mnmessages.StopCommand('CMD-2', 1, targetCommandId='CMD-1')
        admin.sendMessage('/command', m)
        #print 'Waiting for command to die'
        while admin.listNodeCommands(nodeId)[1] and count < 180:
            time.sleep(.1)
            count += .1
            # ok, the stop command has finished, now that must be communicated
            # to the dispatcher.
        #print 'Waiting dispatcher to acknowledge'
        while admin.listAssignedCommands() and count < 180:
            time.sleep(.1)
            count += .1


    def testDispatcherServerFullFailure(self):
        # this should be a test where the trove fails - not as full
        # as the build one but should make sure all build messages
        # arrive.
        raise testsuite.SkipTestException

    def testNodeMessagesOutOfSync(self):
        db = mock.MockObject()
        self.rmakeCfg.messageBusPort = None
        server = dispatcher.DispatcherServer(self.rmakeCfg, db)
        mock.mock(server, 'client')
        cmd1 = self.makeCommandMessage(1, 1, self.getNVF('foo:source'))
        cmd2 = self.makeCommandMessage(2, 2, self.getNVF('bar:source'))
        server.requestCommandAssignment(cmd1, cmd2)
        node =  self.makeRegisterNodeMessage(loadThreshold=1,
                                             loadavg=0.5).getNode()
        server.nodeRegistered('session1', node)
        self.assertEquals(server.listAssignedCommands(),
                          [ ('CMD-1', 'session1') ])
        nodeInfo = self.makeMachineInfo(loadavg=1)
        server.nodeUpdated('session1', nodeInfo, ['CMD-1'])
        self.assertEquals(server.listAssignedCommands(),
                          [ ('CMD-1', 'session1') ])
        server._logger.setQuietMode()
        server.nodeUpdated('session1', nodeInfo, [])
        assert(server.listAssignedCommands() == [])
        server.nodeUpdated('session1', nodeInfo, ['CMD-3'])
        assert(server.listAssignedCommands() == [])

    def testDispatcherRespectsChrootLimit(self):
        db = mock.MockObject()
        self.rmakeCfg.messageBusPort = None
        server = dispatcher.DispatcherServer(self.rmakeCfg, db)
        mock.mock(server, 'client')
        node =  self.makeRegisterNodeMessage(chrootLimit=1, slots=4).getNode()
        server.nodeRegistered('session1', node)

        cmd1 = self.makeResolveMessage(1, 1, self.getNVF('foo:source'))
        cmd2 = self.makeResolveMessage(2, 2, self.getNVF('bar:source'))
        cmd3 = self.makeCommandMessage(3, 2, self.getNVF('foo1:source'))
        cmd4 = self.makeCommandMessage(4, 2, self.getNVF('bar2:source'))
        server.requestCommandAssignment(cmd1, cmd2, cmd3, cmd4)
        self.assertEquals(sorted(server.listAssignedCommands()),
                          [ ('CMD-1', 'session1'), ('CMD-2', 'session1'),
                             ('CMD-3', 'session1')])
        server.commandCompleted(cmd1.getCommandId())
        self.assertEquals(sorted(server.listAssignedCommands()),
                          [ ('CMD-2', 'session1'), ('CMD-3', 'session1')])
        server.commandCompleted(cmd3.getCommandId())
        self.assertEquals(sorted(server.listAssignedCommands()),
                          [ ('CMD-2', 'session1'), ('CMD-4', 'session1')])
