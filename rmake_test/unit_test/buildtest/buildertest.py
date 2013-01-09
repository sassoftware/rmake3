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


from rmake_test import rmakehelp
from testutils import mock

from conary.lib import util

from rmake.build import builder
from rmake.build import dephandler
from rmake.build import imagetrove
from rmake.db import database
from rmake.lib import recipeutil

class BuilderTest(rmakehelp.RmakeHelper):

    # FIXME: as unit tests, these are not good.  
    # potential solution: break or reorganize the involved 
    # functions to make fewer calls to external code.
    
    def testInitializeBuild(self):
        builderObj = mock.MockInstance(builder.Builder)
        regTrv = mock.MockObject()
        regTrv2 = mock.MockObject()
        specTrv = mock.MockObject()
        regTrv.isSpecial._mock.setReturn(False)
        regTrvTup = self.makeTroveTuple('reg:source')
        regTrv.getNameVersionFlavor._mock.setReturn(regTrvTup)
        regTrv2.isSpecial._mock.setReturn(False)
        regTrv2Tup = self.makeTroveTuple('reg:source')
        regTrv2.getNameVersionFlavor._mock.setReturn(regTrv2Tup)
        specTrv.isSpecial._mock.setReturn(True)

        job = mock.MockObject(jobId=1)
        job.iterConfigList._mock.setDefaultReturn([])
        job.getMainConfig()._mock.set(primaryTroves=[])
        job.iterTroves._mock.setDefaultReturn([regTrv, regTrv2, specTrv])
        job.iterLoadableTroveList._mock.setDefaultReturn([
            regTrvTup, regTrv2Tup])

        job.isLoading._mock.setDefaultReturn(False)
        job.isFailed._mock.setDefaultReturn(False)
        job.isLoaded._mock.setDefaultReturn(True)

        mock.mock(dephandler, 'DependencyHandler')
        builderObj._mock.set(job=job)
        builderObj._mock.enableMethod('initializeBuild')
        builderObj._mock.set(serverCfg=self.rmakeCfg)
        builderObj.buildCfg._mock.set(isolateTroves=False)

        # Call
        self.failUnless(builderObj.initializeBuild())

        builderObj.worker.loadTroves._mock.assertCalled(job,
            [regTrvTup, regTrv2Tup], builderObj.eventHandler,
            self.rmakeCfg.reposName)

        expectReg = sorted([regTrv, regTrv2])
        expected = sorted(expectReg + [specTrv])
        job.setBuildTroves._mock.assertCalled(expected)

        logDir = builderObj.serverCfg.getBuildLogDir(1)
        rscache = self.rmakeCfg.getResolverCachePath()
        dephandler.DependencyHandler._mock.assertCalled(
                                         builderObj.job.getPublisher(),
                                         builderObj.logger,
                                         expectReg, [specTrv], logDir,
                                         dumbMode=False,
                                         resolverCachePath=rscache)

    def testBuild(self):
        trv = imagetrove.ImageTrove(1, *self.makeTroveTuple('group-foo'))
        builderObj = mock.MockInstance(builder.Builder)
        dh = mock.MockObject()
        worker = mock.MockObject()

        dh.hasBuildableTroves._mock.setReturn(False)
        dh.hasSpecialTroves._mock.setReturns([True, False])
        dh.moreToDo._mock.setReturns([True, True, False])
        dh.popSpecialTrove._mock.setReturn(trv)
        dh.jobPassed._mock.setReturn(True)

        worker._checkForResults._mock.setReturn(False)

        builderObj._mock.set(dh=dh, worker=worker)
        builderObj._mock.enableMethod('build')
        builderObj._mock.enableMethod('actOnTrove')
        builderObj.build()
        worker.actOnTrove._mock.assertCalled(trv.getCommand(), trv.cfg, trv.jobId, trv, 
                                             builderObj.eventHandler, 
                                             builderObj.startTroveLogger(trv))
