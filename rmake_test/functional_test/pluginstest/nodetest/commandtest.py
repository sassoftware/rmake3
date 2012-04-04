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
Tests multinode commands
"""
from testutils import mock

import new
import time

from rmake_test import rmakehelp
from conary_test import recipes

import os


class CommandTest(rmakehelp.RmakeHelper):

    def _check(self, sessionClient, messageType, **headerValues):
        m = sessionClient.messageProcessor.sendMessage._mock.popCall()[0][0]
        assert(isinstance(m, messageType))
        for key, value in headerValues.items():
            self.assertEquals(getattr(m.headers,key), value)
        return m

    def _setupMockCommand(self, jobId, troveTup):
        from rmake.worker import command
        from rmake.messagebus import messages
        from rmake.multinode import messages as mnmessages
        from rmake.multinode import workernode
        # test how the node responds to various messages sent in from our
        # fake client.
        buildTrove = self.newBuildTrove(jobId, *troveTup)

        commandClass = mock.mockClass(command.BuildCommand, mock_runInit=True)
        buildCommand = commandClass(self.getNodeCfg(), 'CMD-1', jobId, 
                                 mock.MockObject(), self.buildCfg, 
                                 mock.MockObject(), buildTrove,
                                 targetLabel=self.cfg.buildLabel, 
                                 builtTroves=[])
        buildCommand._mock.disable('chrootFactory')
        buildCommand._mock.disable('chroot')
        buildCommand.chroot._mock.set(pid=50)
        buildCommand.chroot._mock.set(
                            buildTrove=lambda *args, **kw: ('/tmp/foo', 50))
        buildCommand._mock.disable('readPipe')
        buildCommand._mock.disable('writePipe')
        return buildCommand

    def testFailedBuildCommand(self):
        # test how the node responds to various messages sent in from our
        # fake client.
        from rmake.messagebus import messages
        from rmake.multinode import messages as mnmessages

        trv = self.addComponent('simple:source', '1',
                                [('simple.recipe', recipes.simpleRecipe)])
        cmd = self._setupMockCommand(1, trv.getNameVersionFlavor())
        cmd.chroot.checkSubscription._mock.raiseErrorOnAccess(
                                                    RuntimeError('foo'))
        trv = cmd.getTrove()
        mock.mockMethod(trv.troveFailed)
        cmd.chroot._mock.set(buildTrove=lambda *args, **kw: ('/tmp/foo', 50))
        self.assertRaises(SystemExit, cmd._runCommand)
        failureReason = trv.troveFailed._mock.popCall()[0][0]
        assert(failureReason.getErrorMessage() == 'foo')

    def testPassedBuildCommand(self):
        # test how the node responds to various messages sent in from our
        # fake client.
        from rmake.messagebus import messages
        from rmake.multinode import messages as mnmessages
        trv = self.addComponent('simple:source', '1',
                                [('simple.recipe', recipes.simpleRecipe)])
        cmd = self._setupMockCommand(1, trv.getNameVersionFlavor())
        self.assertRaises(SystemExit, cmd._runCommand)

    def testStopCommand(self):
        from rmake.multinode import messages as mnmessages
        from rmake.multinode import workernode
        from rmake.worker import command
        pid = os.fork()
        if not pid:
            try:
                time.sleep(10000)
            finally:
                os._exit(0)
        targetId = 'oldCmdId'
        targetCommand = mock.MockObject(pid=pid, getCommandId=lambda: targetId,
                                        jobId=1)
        port = self.startMessageBus()
        nodeCfg = self.getNodeCfg(port)
        node = workernode.rMakeWorkerNodeServer(nodeCfg,
                                        messageBusInfo=('localhost', port))
        cmd = command.StopCommand(nodeCfg, 'cmdId', targetCommand, node._killPid)
        cmd.commandDied(0)
        assert(cmd.isErrored())
        assert(str(cmd.getFailureReason()) 
               == 'Failed while executing command cmdId: oldCmdId did not die!')

        cmd = command.StopCommand(nodeCfg, 'cmdId', targetCommand, 
                                  node._killPid)
        cmd._runCommand()
        cmd.commandDied(0)
        try:
            os.waitpid(pid, os.WNOHANG)
            assert 0, 'sould not have gotten error here!'
        except OSError:
            pass
        assert(not cmd.isErrored())
