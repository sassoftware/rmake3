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


from rmake_test import rmakehelp
from testutils import mock

from rmake.build import imagetrove
from rmake.worker import command
from rmake.worker import worker
from conary.lib import log

class WorkerTest(rmakehelp.RmakeHelper):
    def testActOnTrove(self):
        w = worker.Worker(self.rmakeCfg, log)
        eventHandler = mock.MockObject()
        mock.mockMethod(w.queueCommand)
        trv = imagetrove.ImageTrove(1, *self.makeTroveTuple('group-foo'))
        trv.logPath = self.workDir + '/log'
        w.actOnTrove(trv.getCommand(), self.cfg, trv.jobId, trv, eventHandler, None) 
        # this is a horrible API
        w.queueCommand._mock.assertCalled
        assertCalled = w.queueCommand._mock.assertCalled
        assertCalled(w.commandClasses['image'], self.rmakeCfg, 
                     'IMAGE-1-group-foo-1', trv.jobId, eventHandler,  self.cfg,
                     trv, None, self.workDir + '/log')

    def testStopCommand(self):
        wlog = mock.MockObject()
        w = worker.Worker(self.rmakeCfg, wlog)
        mock.mockMethod(w.getCommandById)
        mock.mockMethod(w.runCommand)

        # Unknown command
        w.getCommandById._mock.setReturn(None, 'LOAD-1')
        w.stopCommand('LOAD-1')
        wlog.warning._mock.assertCalled('Asked to stop unknown command LOAD-1')

        # Trove command
        troveCommand = w.getCommandById('BUILD-2')
        w.stopCommand('BUILD-2')
        self.assertEquals(w.runCommand._mock.calls[0][0][:4],
                (command.StopCommand, w.cfg, 'STOP-BUILD-2-1', troveCommand))
        del w.runCommand._mock.calls[:]
        troveCommand.trove.troveFailed._mock.assertCalled('Stop requested')

        # Job command
        loadCommand = w.getCommandById('LOAD-3')
        loadCommand._mock.set(trove=None)
        w.stopCommand('LOAD-3')
        self.assertEquals(w.runCommand._mock.calls[0][0][:4],
                (command.StopCommand, w.cfg, 'STOP-LOAD-3-1', loadCommand))
        del w.runCommand._mock.calls[:]
        loadCommand.job.jobFailed._mock.assertCalled('Stop requested')

        # Corner case (no job or trove)
        badCommand = w.getCommandById('PANTS-4')
        badCommand._mock.set(job=None, trove=None)
        w.stopCommand('PANTS-4')
        self.assertEquals(w.runCommand._mock.calls[0][0][:4],
                (command.StopCommand, w.cfg, 'STOP-PANTS-4-1', loadCommand))
        del w.runCommand._mock.calls[:]
        wlog.warning._mock.assertCalled('Command %s has no job or trove '
                'assigned -- cannot fail job.', 'PANTS-4')
