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

from conary import conaryclient
from rmake.build import buildjob, buildtrove
from rmake.lib import recipeutil
from rmake.worker import command


class CommandTest(rmakehelp.RmakeHelper):
    def testLoadCommand(self):
        job = buildjob.BuildJob(1)
        trv1 = buildtrove.BuildTrove(1, *self.getNVF('foo:source'))
        trv2 = buildtrove.BuildTrove(1, *self.getNVF('bar:source'))
        job.addBuildTrove(trv1)
        job.addBuildTrove(trv2)

        result1 = buildtrove.LoadTroveResult()
        result1.packages = set(['foo', 'baz'])
        result2 = buildtrove.LoadTroveResult()
        result2.buildRequirements = set(['initscripts:runtime'])

        troves = [trv1, trv2]
        tups = [x.getNameVersionFlavor(True) for x in troves]
        results = [result1, result2]
        resultSet = dict(zip(tups, results))

        def getSourceTrovesFromJob(job_, troves_, repos, reposName):
            self.assertEqual(job_, job)
            self.assertEqual(troves_, troves)
            self.assertEqual(reposName, self.rmakeCfg.reposName)
            return resultSet
        self.mock(recipeutil, 'getSourceTrovesFromJob', getSourceTrovesFromJob)
        mock.mock(conaryclient, 'ConaryClient')

        # call
        cmd = command.LoadCommand(self.rmakeCfg, 'cmd', job.jobId, None,
            job, tups, self.rmakeCfg.reposName)
        cmd.publisher = mock.MockObject()
        cmd.runAttachedCommand()

        cmd.publisher.attach._mock.assertCalled(trv1)
        cmd.publisher.attach._mock.assertCalled(trv2)
        self.assertEqual(trv1.packages, set(['foo', 'baz']))
        self.assertEqual(trv2.buildRequirements, set(['initscripts:runtime']))
