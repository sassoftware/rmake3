#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
