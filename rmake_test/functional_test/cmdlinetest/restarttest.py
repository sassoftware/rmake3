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


"""
Unit tests for front-end build functionality
"""

import os
import shutil
import sys

from testutils import mock
from conary_test import recipes
from rmake_test import rmakehelp
from rmake_test import fixtures

from conary.deps import deps
from conary import versions

from rmake import errors
from rmake.cmdline import buildcmd

class RestartCmdLineTest(rmakehelp.RmakeHelper):
    def testRestart(self):
        self.openRmakeRepository()
        jobId = fixtures.addBuiltJob1(self)

        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)

        restartJobId = self.discardOutput(helper.restartJob, jobId)
        assert(restartJobId != jobId)
        helper.waitForJob(restartJobId)
        job = helper.getJob(jobId)
        restartJob = helper.getJob(restartJobId)
        assert(restartJob.isBuilt())
        assert(set(job.iterTroves().next().getBinaryTroves()) 
                == set(restartJob.iterTroves().next().getBinaryTroves()))
        fixtures.updateBuiltJob1(self)
        self.addComponent('simple:source', '1', [('simple.recipe',
                                                  recipes.simpleRecipe)])
        restartJobId2 = self.discardOutput(helper.restartJob, restartJobId, 
                                           ['simple'])
        helper.waitForJob(restartJobId2)
        restartJob2 = helper.getJob(restartJobId2)
        trovesByName = dict((x.getName(), x) for x in restartJob2.iterTroves())
        assert(set(trovesByName) == set(['testcase:source', 'simple:source']))
        assert(set(trovesByName['testcase:source'].getBinaryTroves())
                != set(restartJob.iterTroves().next().getBinaryTroves()))

    def testRestartRecipe(self):
        raise testsuite.SkipTestException()
        # Restart a recipe in a context (RMK-692)
        curDir = os.getcwd()
        repos = self.openRmakeRepository()
        client = self.startRmakeServer()
        self.addComponent('simple:source', '1', [('simple.recipe',
                                                  recipes.simpleRecipe)])
        try:
            os.chdir(self.workDir)
            self.checkout('simple')
            os.chdir('simple')
            self.buildCfg.configLine('[1]')
            helper = self.getRmakeHelper(client.uri)
            jobId = self.discardOutput(helper.buildTroves, 'simple.recipe{1}')
            helper.stopJob(jobId)
            helper = self.getRmakeHelper(client.uri)
            jobId = self.discardOutput(helper.restartJob, jobId)
            helper.stopJob(jobId)
        finally:
            os.chdir(curDir)

    def testRestartUpdatesResolveTroves(self):
        self.openRmakeRepository()
        jobId = fixtures.addBuiltJob1(self)
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        # update the resolveTrove item: buildReq.
        # make sure that restart finds the new version.
        buildReq = fixtures.updateBuiltJob1BuildReq(self)
        mock.mockMethod(helper.client.buildJob)
        self.discardOutput(helper.restartJob, jobId)
        (job,), kw = helper.client.buildJob._mock.popCall()
        assert(job.getMainConfig().resolveTroveTups
                == [[buildReq.getNameVersionFlavor()]])

    def testRestartRecursesGroupsAndMatchesRules(self):
        self.openRmakeRepository()
        self.addComponent('foo:source=:branch')
        self.addComponent('foo:runtime=:branch')
        self.addComponent('bar:source=:linux', [('bar.recipe', barRecipe)])
        self.addComponent('group-foo:source', [('group-foo.recipe', groupRecipe)])
        self.buildCfg.configLine('[linuxOnly]')
        self.buildCfg.configLine('matchTroveRule =localhost@rpl:linux')
        helper = self.getRmakeHelper()
        jobId = self.discardOutput(helper.buildTroves, ['group-foo{linuxOnly}'],
                            recurseGroups=buildcmd.BUILD_RECURSE_GROUPS_SOURCE)
        job = helper.getJob(jobId)
        assert(len(list(job.iterTroves())) == 2)
        del self.buildCfg.reposName
        restartId = self.discardOutput(helper.restartJob, jobId)
        job = helper.getJob(restartId)
        assert(len(list(job.iterTroves())) == 2)

    def testRestart2(self):
        self.openRepository()
        self.openRmakeRepository()
        jobId = fixtures.addMultiContextJob1(self)
        helper = self.getRmakeHelper()
        mock.mockMethod(helper.buildJob)
        mock.mockMethod(helper._createBuildJob)
        rc, txt = self.captureOutput(helper.restartJob, jobId)
        assert(txt == 'warning: Context nossl used in job 1 does not exist\n')
        args, kw = helper._createBuildJob._mock.popCall()
        kw = dict(kw)
        assert(kw['configDict']['nossl'])
        assert(len(args) == 1 and len(args[0]) == 2) # building both troves
        assert(set([x[3] for x in args[0]]) == set(['', 'nossl']))
        self.buildCfg.setSection('nossl')
        helper = self.getRmakeHelper()
        mock.mockMethod(helper.buildJob)
        mock.mockMethod(helper._createBuildJob)
        rc, txt = self.captureOutput(helper.restartJob, jobId)
        assert(txt == '')

    def testRestartNoUpdate(self):
        a = self.addComponent('a:source=1')
        b = self.addComponent('b:source=1')
        d = self.addComponent('d:source=1')
        ia = self.addComponent('info-a:source=1')
        ib = self.addComponent('info-b:source=1')
        ibbb = self.addComponent('info-bob:source=1')

        troveList1 = [ a, b, ia, ib, ibbb ]
        a = self.addComponent('a:source=2')
        #b = self.addComponent('b:source=2')
        c = self.addComponent('c:source=2')
        ia = self.addComponent('info-a:source=2')
        ib = self.addComponent('info-b:source=2')
        ibbb = self.addComponent('info-bob:source=2')
        troveList2 = [ a, b, ia, ib, ibbb ]

        self.buildCfg.buildTroveSpecs = [(x, None, None) for x in
                                          ('a', 'b', 'd', 'info-a', 'info-b',
                                          'info-bob')]
        job = self.newJob(*troveList1)
        jobId = job.jobId
        helper = self.getRmakeHelper()
        mock.mockMethod(helper.client.buildJob)

        def _rebuild(updateSpecs=[], troveSpecs=[], excludeSpecs=[]):
            self.discardOutput(helper.restartJob, jobId,
                               troveSpecs=troveSpecs,
                               updateSpecs=updateSpecs,
                               excludeSpecs=excludeSpecs)
            restartJob, = helper.client.buildJob._mock.popCall()[0]
            nameVersion = sorted([ (x[0].split(':')[0],
                                    x[1].trailingRevision().getVersion())
                                    for x in restartJob.iterTroveList() ])
            return nameVersion
        nameVersion = _rebuild(updateSpecs=['info-*', '-info-b*',
                                            'info-bob'],
                               troveSpecs=[('c', None, None)],
                               excludeSpecs=['d'])

        self.assertEquals(nameVersion, [('a', '1'), ('b', '1'), ('c', '2'),
                                        ('info-a', '2'), ('info-b', '1'),
                                        ('info-bob', '2')])
        nameVersion = _rebuild(updateSpecs=['-*'], excludeSpecs=['d'],
                               troveSpecs=[('c', None, None)])
        self.assertEquals(nameVersion, [('a', '1'), ('b', '1'), ('c', '2'),
                                        ('info-a', '1'), ('info-b', '1'),
                                        ('info-bob', '1')])

    def testRestartUpdateConfig(self):
        self.openRepository()
        self.openRmakeRepository()
        jobId = fixtures.addMultiContextJob1(self)
        oldILP = self.buildCfg.installLabelPath
        self.buildCfg.installLabelPath = [ self.cfg.buildLabel,
                                      versions.Label('localhost@rpl:branch') ]
        helper = self.getRmakeHelper()
        mock.mockMethod(helper.buildJob)
        mock.mockMethod(helper._createBuildJob)
        rc, txt = self.captureOutput(helper.restartJob, jobId)
        args, kw = helper._createBuildJob._mock.popCall()
        kw = dict(kw)
        assert(kw['configDict']['nossl'].installLabelPath == oldILP)
        rc, txt = self.captureOutput(helper.restartJob, jobId,
                                    updateConfigKeys=['installLabelPath'])
        args, kw = helper._createBuildJob._mock.popCall()
        kw = dict(kw)
        assert(kw['configDict']['nossl'])
        assert(kw['configDict']['nossl'].installLabelPath
                                == self.buildCfg.installLabelPath)

    def testRestartDeleteThenRestart(self):
        self.openRmakeRepository()
        jobId = fixtures.addBuiltJob1(self)

        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        restartJobId = self.discardOutput(helper.restartJob, jobId)
        assert(restartJobId != jobId)
        restartJobId2 = self.discardOutput(helper.restartJob, restartJobId)
        assert(helper.client.getJob(restartJobId2, withConfigs=True).getMainConfig().jobContext == [jobId, restartJobId])
        helper.deleteJobs([jobId])
        assert(helper.client.getJob(restartJobId2, withConfigs=True).getMainConfig().jobContext == [restartJobId])
        restartJobId3 = self.discardOutput(helper.restartJob, restartJobId2)
        helper.waitForJob(restartJobId3)

    def testRemoveThenRestart(self):
        self.openRmakeRepository()
        jobId = fixtures.addBuiltJob1(self)
        self.markRemoved('testcase:source')
        self.addComponent('simple:source')
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)

        mock.mockMethod(helper.client.buildJob)
        restartJobId = self.discardOutput(helper.restartJob, jobId,
                                          ['simple:source'], 
                                          clearBuildList=True)
        args, kw = helper.client.buildJob._mock.popCall()
        troveTup, = list(args[0].iterTroveList())
        assert(troveTup[0] == 'simple:source')

groupRecipe = """
class FooGroup(GroupRecipe):
    name = 'group-foo'
    version = '1'

    def setup(r):
        r.add('foo')
        r.add('bar')
"""
barRecipe = """
class Bar(PackageRecipe):
    name = 'bar'
    version = '1'
    clearBuildReqs()

    def setup(r):
        r.Create('/bar')
"""
