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


from testutils import mock

from rmake_test import rmakehelp

from rmake.build import imagetrove
from rmake.lib import recipeutil
from rmake.lib import repocache

class RecipeUtilTest(rmakehelp.RmakeHelper):
    def testGetSourceTrovesFromJob(self):
        repos = mock.mockClass(repocache.CachingTroveSource)()
        trv1 = self.newBuildTrove(1, *self.makeTroveTuple('bar:source'))
        trv1Tup = trv1.getNameVersionFlavor(True)
        trv1.setConfig(self.buildCfg)
        job = self.newJob()
        job.addBuildTrove(trv1)
        mock.mockFunction(recipeutil.loadSourceTroves, {trv1Tup: 'result'})

        rc = recipeutil.getSourceTrovesFromJob(job, [trv1], repos,
            self.rmakeCfg.reposName)
        self.failUnlessEqual(rc, {trv1Tup: 'result'})
        args, kw = recipeutil.loadSourceTroves._mock.popCall()
        assert(args[3] == [trv1])
