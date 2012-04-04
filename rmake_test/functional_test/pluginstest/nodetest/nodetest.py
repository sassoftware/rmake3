# -*- mode: python -*-
#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Tests rmake.multinode
"""

import os
import sys
import time

from testutils import mock
from rmake_test import rmakehelp
from conary_test import recipes

from rmake import failure
from rmake.worker import command

class NodeTest(rmakehelp.PluginTest):

    def testNodePidDied(self):
        from rmake.multinode import workernode
        m = mock.mockClass(workernode.rMakeWorkerNodeServer)()
        m._mock.enableMethod('_pidDied')
        cmd = mock.mockClass(command.Command, mock_runInit=True)
        cmd = cmd(None, 'foo', 1)
        cmd.pid = 377
        cmd._mock.disable('readPipe')
        m._mock.set(commands=[cmd])
        m._pidDied(377, 255)
        # check to make sure self.client.commandErrored was called w/ the
        # right parameters
        f = failure.CommandFailed('foo', 'unexpectedly killed with signal 127')
        m.commandErrored._mock.assertCalled('foo', f)
        m._mock.enableMethod('commandErrored')
        m.commandErrored(cmd,
                         'Command foo unexpectedly died with exit code 4')
        assert(m.commands == [])
        m._mock.set(commands=[cmd])
        mock.mockMethod(m.commandErrored)
        m._pidDied(377, 1024)
        f = failure.CommandFailed('foo', 'unexpectedly died with exit code 4')
        m.commandErrored._mock.assertCalled( 'foo', f)
        assert(m.commands == [])
        m._pidDied(365, 1024)
        m.commandErrored._mock.assertNotCalled()

class NodeTest2(rmakehelp.RmakeHelper):

    def _check(self, sessionClient, messageType, **headerValues):
        m = sessionClient.messageProcessor.sendMessage._mock.popCall()[0][0]
        assert(isinstance(m, messageType))
        for key, value in headerValues.items():
            self.assertEquals(getattr(m.headers,key), value)

    def _setupMockNode(self):
        from rmake.messagebus import messages
        from rmake.multinode import messages as mnmessages
        from rmake.multinode import workernode
        # test how the node responds to various messages sent in from our
        # fake client.
        cfg = self.getNodeCfg()
        server = workernode.rMakeWorkerNodeServer(cfg,
                              messageBusInfo=('localhost', None))
        sessionClient = server.client.getBusClient().getSession()
        mock.mockMethod(sessionClient.poll)
        mock.mockMethod(sessionClient.connect)
        mock.mockMethod(sessionClient.disconnect)
        mock.mockMethod(sessionClient.messageProcessor.sendMessage)
        mock.mock(sessionClient, 'logger')
        sessionClient.handle_connect()
        self._check(sessionClient, messages.ConnectionRequest,
                           sessionClass='WORKER')
        m = messages.ConnectedResponse()
        m.set(sessionId='WORKER-foo')
        sessionClient.handle_message(m)
        self._check(sessionClient, mnmessages.RegisterNodeMessage,
                           nodeType='WORKER', destination='/register')
        self._check(sessionClient, messages.SubscribeRequest,
                    destination='/command?targetNode=WORKER-foo')
        server._serveLoopHook()
        self._check(sessionClient, mnmessages.NodeInfo,
                    destination='/nodestatus')
        return server, sessionClient

    def testNodeServer(self):
        from rmake.messagebus import messages
        from rmake.multinode import messages as mnmessages
        from rmake.multinode import workernode
        # test how the node responds to various messages sent in from our
        # fake client.
        server, sessionClient = self._setupMockNode()
        trv = self.addComponent('simple:source', '1',
                                [('simple.recipe', recipes.simpleRecipe)])

        # send a build command
        buildTrove = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        m = mnmessages.BuildCommand('CMD-1', self.buildCfg, 1, buildTrove, [],
                                    [], self.cfg.buildLabel,
                                    targetNode='WORKER-foo')

        # this should result in the command being queued...
        mock.mockMethod(server.queueCommand)
        mock.mockMethod(server.chrootManager.getRootFactory)
        sessionClient.handle_message(m)
        commandClass = server.queueCommand._mock.calls[0][0][0]
        self.assertEquals(commandClass, command.BuildCommand)
        commandClass = mock.mockClass(command.BuildCommand,
                                      mock_enable=['pid'],
                                      getCommandId=lambda: 'CMD-1',
                                      isErrored=lambda: False)
        server.queueCommand._mock.method(commandClass, self.cfg, 1, 'CMD-1')
        assert(server.listQueuedCommands())

        # pretend we forked this command...
        mock.mockFunctionOnce(os, 'fork', 342)
        server._serveLoopHook()
        assert(server.listCommands())
        # and now it's died...
        mock.mockFunctionOnce(os, 'waitpid', (342, 0))
        server._serveLoopHook()
        assert(not server.listCommands())
        self._check(sessionClient, mnmessages.CommandStatus,
                    destination='/commandstatus', commandId='CMD-1',
                    status=mnmessages.CommandStatus.COMPLETED)

        # let's create another command, one that fails on initialization
        commandClass = command.Command
        def _raise(*args, **kw):
            raise RuntimeError('foo')
        mock.replaceFunctionOnce(commandClass, '__init__', _raise)
        server.queueCommand._mock.method(commandClass, self.cfg, 'CMD-1')

        server._serveLoopHook()
        self._check(sessionClient, mnmessages.CommandStatus,
                    destination='/commandstatus', commandId='CMD-1',
                    status=mnmessages.CommandStatus.ERROR)


    def testNodeServerSlowToConnect(self):
        from rmake.multinode import workernode
        from rmake.worker import command
        from rmake_plugins.multinode_client.server import client
        fclient = mock.MockObject()
        self.mock(client, 'rMakeClient', fclient)
        mock.mock(time, 'sleep') #Otherwise we wait 5 seconds for no good reason
        cfg = self.getNodeCfg()
        msgBusInfo = mock.MockObject()
        # The first time through, raise RuntimeError, and on the subsequent
        # runs return None and a mock object sequentially
        fclient().getMessageBusInfo._mock.raiseErrorOnAccess(RuntimeError('connect to server error'))
        fclient().getMessageBusInfo._mock.setReturns([None, msgBusInfo])

        server = workernode.rMakeWorkerNodeServer(cfg)
        self.assertEquals(len(time.sleep._mock.calls), 2, 'sleep should have been called twice')
        self.assertEquals(len(fclient().getMessageBusInfo._mock.calls), 3)

    def testNodeServerInitializationFailure(self):
        from rmake.multinode import workernode
        serverClass = mock.mockClass(workernode.rMakeWorkerNodeServer,
                                     mockEnable='__init__')
        s = serverClass()
        err = RuntimeError('foo')
        s._mock.raiseErrorOnAccess(err)
        self.assertRaises(RuntimeError, 
                           workernode.rMakeWorkerNodeServer.__init__, 
                          s, self.getNodeCfg())
        args = s.error._mock.popCall()[0]
        assert(args[0] == 'Error initializing Node Server:\n  %s\n%s')
        assert(args[1] == err)

    def testNodeRPCClient(self):
        from rmake.multinode import workernode
        from rmake.worker import command
        server, sessionClient = self._setupMockNode()
        mock.mockMethod(server.client._logger.logRPCCall)
        rpcClient = workernode.WorkerNodeRPCClient(server.client.getBusClient(),
                                                   sessionClient.sessionId)
        assert(tuple(rpcClient.listCommands()) == ([], []))

        commandClass = mock.mockClass(command.BuildCommand,
                                      getCommandId=lambda: 'CMD-1',
                                      mock_enable=['pid', 'commandInfo'])
        server.queueCommand(commandClass, None, 'CMD-1')
        mock.mockFunctionOnce(os, 'fork', 342)
        server._serveLoopHook()
        self.assertEquals(rpcClient.listCommands(), ([], [('CMD-1', 342)]))

    def testNodeServerFull(self):
        from rmake.messagebus import messages
        from rmake.multinode import messages as mnmessages
        # do one build from start -> finish to check out polling, etc.
        port = self.startMessageBus()
        node = self.startNode(messageBusPort=port)
        admin = self.getAdminClient(port)
        clients = admin.listMessageBusClients()
        nodeId = [ x[0] for x in clients.items() if x[1] == 'WORKER' ][0]


        # send a build command - we'll listen for a commandStatus
        # command.
        trv = self.addComponent('simple:source', '1',
                                [('simple.recipe', recipes.simpleRecipe)])
        buildTrove = self.newBuildTrove(1, *trv.getNameVersionFlavor())

        m = mnmessages.BuildCommand('CMD-1', self.buildCfg, 1, buildTrove, [],
                                    [], self.cfg.buildLabel,
                                    targetNode=nodeId)
        subscriber = self.createEventSubscriber(port)
        admin.sendMessage('/command', m)
        while not admin.listNodeCommands(nodeId)[1]:
            subscriber.poll()
            time.sleep(.1)
        while admin.listNodeCommands(nodeId)[1]:
            subscriber.poll()
            time.sleep(.1)
        print "Command Done"
        subscriber.poll()
        # we should have gotten a troveBuilding message at some point,
        # and then a troveBuilt!
        troveTup = buildTrove.getNameVersionFlavor()
        subscriber.assertTroveBuilding(1, *troveTup)
        subscriber.assertTroveBuilt(1, *troveTup)
        binaries = subscriber.getTrovesBuilt(1, *troveTup)
        repos = self.openRepository()
        repos.getTroves(binaries, withFiles=False)

    def testStopCommandFull(self):
        from rmake.messagebus import messages
        from rmake.multinode import messages as mnmessages
        # do one build from start -> finish to check out polling, etc.
        port = self.startMessageBus()
        node = self.startNode(messageBusPort=port)
        admin = self.getAdminClient(port)
        clients = admin.listMessageBusClients()
        nodeId = [ x[0] for x in clients.items() if x[1] == 'WORKER' ][0]

        # send a build command - we'll listen for a commandStatus
        # command.
        trv = self.addComponent('sleep:source', '1',
                                [('sleep.recipe', rmakehelp.sleepRecipe)])
        buildTrove = self.newBuildTrove(1, *trv.getNameVersionFlavor())

        m = mnmessages.BuildCommand('CMD-1', self.buildCfg, 1, buildTrove, [],
                                    [], self.cfg.buildLabel,
                                    targetNode=nodeId)
        subscriber = self.createEventSubscriber(port)
        admin.sendMessage('/command', m)
        count = 0
        while not admin.listNodeCommands(nodeId) and count < 30:
            subscriber.poll()
            time.sleep(.1)
            count += .1
        assert(count != 30)
        count = 0
        while not subscriber._troveBuilding and count < 30:
            subscriber.poll()
            time.sleep(.1)
            count += .1
        assert(count != 30)
        m = mnmessages.StopCommand('CMD-2', 1,
                                   targetCommandId='CMD-1',
                                   targetNode=nodeId)
        admin.sendMessage('/command', m)
        count = 0
        while count < 30 and admin.listNodeCommands(nodeId)[1]:
            subscriber.poll()
            time.sleep(.1)
            count += .1
        assert(count != 30)
        troveTup = buildTrove.getNameVersionFlavor()
        subscriber.assertTroveBuilding(1, *troveTup)
        subscriber.poll()
        count = 0
        while count < 30 and not subscriber._troveFailed:
            subscriber.poll()
            time.sleep(.1)
            count += .1
        subscriber.assertTroveFailed(1, *troveTup)
        reason = subscriber.getFailureReason(1, *troveTup)
        assert(str(reason) == 'Failed while building: Stop requested')

