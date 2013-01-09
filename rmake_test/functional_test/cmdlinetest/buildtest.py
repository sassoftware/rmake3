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
import re
import shutil

from conary import state
from conary.build import cook
from conary.deps import deps
from conary.lib import util
from conary.state import ConaryStateFromFile
from conary_test import recipes

from rmake import errors
from rmake.cmdline import buildcmd

from rmake_test import fixtures
from rmake_test import resources
from rmake_test import rmakehelp


class BuildCmdLineTest(rmakehelp.RmakeHelper):
    def testChangeFactory(self):
        repos = self.openRmakeRepository()
        helper = self.getRmakeHelper()

        # Commit factory to use
        # Warning: can't use this factory unless set it's factory to "factory"
        self.addComponent('factory-test:source', '0', '',
                          [('factory-test.recipe', localFactory)],
                          factory='factory')

        # Commit recipe which won't cook successfully
        self.addComponent('simple:source', '1', '',
                          [ ('simple.recipe', recipes.simpleRecipe)])

        os.chdir(self.workDir)
        self.checkout('simple')
        os.chdir('simple')

        # Hack around conary's bug not notice only factory change during checkin
        self.writeFile('simple.recipe',
                        recipes.simpleRecipe + '\tr.Create("bar")\n')

        # Load CONARY state file
        stateFile = "CONARY"
        conaryState = ConaryStateFromFile(stateFile)
        sourceState = conaryState.getSourceState()

        # Verify no factory
        assert(sourceState.getFactory() == '')

        # Set factory
        sourceState.setFactory('test')
        conaryState.write(stateFile)

        # Verify build is successful
        (name,version,flavor) = buildcmd.getTrovesToBuild(self.buildCfg,
                                    helper.getConaryClient(),
                                   ['simple.recipe'], message='foo')[0]

        # checkout newly shadowed package
        self.checkout(name,versionStr=version.asString())

        # get state file object of newly shadowed package
        os.chdir('simple')
        conaryState = ConaryStateFromFile(stateFile)
        sourceState = conaryState.getSourceState()

        # check factory matches
        assert(sourceState.getFactory() == 'test')

        # TODO test for adding and removing files while changing factory

    def testGetTrovesToBuild(self):
        repos = self.openRmakeRepository()
        helper = self.getRmakeHelper()

        self.addComponent('simple:source', '1', '',
                            [ ('simple.recipe', recipes.simpleRecipe),
                              ('foo',           'content\n')])

        os.chdir(self.workDir)
        self.checkout('simple')
        os.chdir('simple')
        self.writeFile('simple.recipe', 
                        recipes.simpleRecipe + '\tr.AddSource("bar")\n')
        self.remove('foo')
        self.writeFile('bar', 'content\n')
        self.addfile('bar', text=True)
        os.mkdir('baz') # just make a random dir - rmake should
                        # ignore this.
        (n,v,f) = buildcmd.getTrovesToBuild(self.buildCfg,
                                    helper.getConaryClient(),
                                   ['simple.recipe[bam]'], message='foo')[0]
        assert(f == deps.parseFlavor('bam'))
        f = deps.parseFlavor('')
        assert(v.trailingLabel().getHost() == self.rmakeCfg.reposName)
        # make sure we can commit this uphill
        assert(len(list(v.iterLabels())) == 2)
        trove = repos.getTrove(n,v,f, withFiles=True)
        assert(set(x[1] for x in list(trove.iterFileList())) == set(['simple.recipe', 'bar']))
        # okay now let's do it again, no change this time
        v2 = buildcmd.getTrovesToBuild(self.buildCfg, helper.getConaryClient(),
                                    ['simple.recipe'], message='foo')[0][1]
        assert(v == v2)
        # this time, change the config setting for foo
        self.setSourceFlag('bar', binary=True)
        v3 = buildcmd.getTrovesToBuild(self.buildCfg, helper.getConaryClient(),
                                    ['simple.recipe'], message='foo')[0][1]
        assert(v3 != v2)


        # one more time, revert back to original.
        self.writeFile('simple.recipe', recipes.simpleRecipe)
        v4 = buildcmd.getTrovesToBuild(self.buildCfg, helper.getConaryClient(),
                                    ['simple.recipe'], message='foo')[0][1]
        assert(v4.trailingLabel().getHost() == self.rmakeCfg.reposName)
        assert(v4 != v3)
        assert(helper.buildConfig.buildTroveSpecs == 
                                        [(self.workDir + '/simple/simple.recipe', None, deps.parseFlavor(''))])

    def testGetInfoRecipe(self):
        recipePath = self.workDir + '/info-foo.recipe'
        self.writeFile(recipePath, infoRecipe)
        self.openRepository()
        self.openRmakeRepository()
        helper = self.getRmakeHelper()

        self.logFilter.add()
        v = buildcmd.getTrovesToBuild(self.buildCfg, helper.getConaryClient(), 
                                      [recipePath])[0][1]
        assert(v.trailingLabel().getHost() == self.rmakeCfg.reposName)

    def testGetTrovesWithFileWithPackageNameInSameDirectory(self):
        simpleRecipe = recipes.simpleRecipe
        self.addComponent('simple:source', '1-1', 
                            [('simple.recipe', simpleRecipe)])
        os.chdir(self.workDir)
        self.checkout('simple')
        os.chdir('simple')
        self.addComponent('simple:source', '1-2',
                            [('simple.recipe', simpleRecipe)])
        # file with the name of the package we're trying to build.
        # If this working correctly, "rmake build simple" should build the 
        # file in the repository (1-2), not the local .recipe (which is 1-1)
        self.writeFile('simple', 'foo\n')
        self.writeFile('simple.recipe', simpleRecipe + '#change\n')

        self.openRepository()
        self.openRmakeRepository()
        helper = self.getRmakeHelper()
        v = buildcmd.getTrovesToBuild(self.buildCfg, helper.getConaryClient(), 
                                      ['simple'])[0][1]
        self.assertEquals(v.getHost(), 'localhost')

    def testGetTrovesWithOtherDirectory(self):
        simpleRecipe = recipes.simpleRecipe
        self.addComponent('simple:source', '1-1', 
                            [('simple.recipe', simpleRecipe)])
        os.chdir(self.workDir)
        self.checkout('simple')
        self.addComponent('simple:source', '1-2',
                            [('simple.recipe', simpleRecipe)])
        # file with the name of the package we're trying to build.
        # If this working correctly, "rmake build simple" should build the 
        # file in the repository (1-2), not the local .recipe (which is 1-1)
        self.writeFile('simple/simple', 'foo\n')
        self.writeFile('simple/simple.recipe', simpleRecipe + '#change\n')

        self.openRepository()
        self.openRmakeRepository()
        helper = self.getRmakeHelper()
        _gifp = cook.getRecipeInfoFromPath
        try:
            def checkCWD(*args, **kwargs):
                self.failUnlessEqual(os.getcwd(),
                    os.path.join(self.workDir, 'simple'))
                return _gifp(*args, **kwargs)
            cook.getRecipeInfoFromPath = checkCWD

            v = buildcmd.getTrovesToBuild(self.buildCfg,
                helper.getConaryClient(), ['simple/simple.recipe'])[0][1]
        finally:
            cook.getRecipeInfoFromPath = _gifp
        self.assertEquals(v.getHost(), 'rmakehost')

    def testGetTrovesToBuildWithRecipeAndRPM(self):
        recipePath = self.workDir + '/local.recipe'
        self.writeFile(recipePath, localSourceRecipe)
        self.writeFile(self.workDir + '/foo', 'Contents\n')
        shutil.copyfile(resources.get_archive('/tmpwatch-2.9.0-2.src.rpm'),
                        self.workDir + '/tmpwatch-2.9.0-2.src.rpm')

        self.openRepository()
        self.openRmakeRepository()
        helper = self.getRmakeHelper()

        self.logFilter.add()
        v = buildcmd.getTrovesToBuild(self.buildCfg, helper.getConaryClient(), 
                                      [recipePath])[0][1]
        assert(v.trailingLabel().getHost() == self.rmakeCfg.reposName)

        self.writeFile(recipePath, localSourceRecipe + '\n')

        v2 = buildcmd.getTrovesToBuild(self.buildCfg, helper.getConaryClient(),
                                       [recipePath])[0][1]
        assert(v2.trailingLabel().getHost() == self.rmakeCfg.reposName)
        assert(v2 != v)

        self.writeFile(recipePath, localSourceRecipe + '\n')
        v3 = buildcmd.getTrovesToBuild(self.buildCfg, helper.getConaryClient(),
                                       [recipePath])[0][1]
        assert(v3.trailingLabel().getHost() == self.rmakeCfg.reposName)
        assert(v3 == v2)

    def testGetTrovesToBuildNewPackage(self):
        self.openRmakeRepository()
        # create another version in that repository on another label.
        # this triggers RMK-685
        self.addComponent( 
            'simple:source=/localhost@foo:branch//rmakehost@local:branch/1:1-1')
        helper = self.getRmakeHelper()

        os.chdir(self.workDir)
        self.newpkg('simple=localhost@rpl:branch')
        os.chdir('simple')
        self.writeFile('simple.recipe', 
                        recipes.simpleRecipe + '\tr.Create("/bar")\n\tr.addAction("echo 1")\n')
        v = buildcmd.getTrovesToBuild(self.buildCfg, helper.getConaryClient(),
                                   ['simple.recipe'], message='foo')[0][1]
        assert(v.trailingLabel().getHost() == self.rmakeCfg.reposName)
        assert(str(v.branch().parentBranch()) == '/localhost@rpl:branch')

    def testGetTrovesToBuildNoPackageWithTemplate(self):
        repos = self.openRepository()
        self.openRmakeRepository()
        helper = self.getRmakeHelper()
        templateDir = resources.get_archive('recipeTemplates')
        oldRTD = self.cfg.recipeTemplateDirs
        oldTemplate = self.cfg.recipeTemplate
        self.buildCfg.recipeTemplateDirs = [templateDir]
        self.buildCfg.recipeTemplate = 'test'
        os.chdir(self.workDir)
        self.writeFile('simple.recipe', 
                        recipes.simpleRecipe + '\tr.Create("/bar")\n')
        v = buildcmd.getTrovesToBuild(self.buildCfg,
                                    helper.getConaryClient(),
                                   ['simple.recipe'], message='foo')[0][1]
        assert(v.trailingLabel().getHost() == self.rmakeCfg.reposName)
        assert(len(list(v.iterLabels())) == 2)
        assert(str(v.branch().parentBranch()) == '/localhost@rpl:linux')
        fileList = repos.iterFilesInTrove('simple:source', v, 
                             deps.parseFlavor(''), withFiles=True)
        for item  in fileList:
            assert(item[4].flags.isConfig())

    def testGetTrovesToBuildNoPackage(self):
        repos = self.openRepository()
        self.openRmakeRepository()
        helper = self.getRmakeHelper()
        templateDir = resources.get_archive('recipeTemplates')
        os.chdir(self.workDir)
        self.writeFile('simple.recipe', 
                        recipes.simpleRecipe + '\tr.Create("/bar")\n')
        v = buildcmd.getTrovesToBuild(self.buildCfg,
                                    helper.getConaryClient(),
                                   ['simple.recipe'], message='foo')[0][1]
        assert(v.trailingLabel().getHost() == self.rmakeCfg.reposName)
        assert(len(list(v.iterLabels())) == 2)
        assert(str(v.branch().parentBranch()) == '/localhost@rpl:linux')
        fileList = repos.iterFilesInTrove('simple:source', v, 
                             deps.parseFlavor(''), withFiles=True)
        for item  in fileList:
            assert(item[4].flags.isConfig())

    def testGetTrovesFromBinaryGroup(self):
        helper = self.getRmakeHelper()
        self.addComponent('group-foo:source', '1')
        binTrv = self.addCollection('simple', '1', [':runtime'],
                                    createComps=True,
                                    defaultFlavor='readline')
        branchBinTrv = self.addCollection('simple', ':branch/1', [':runtime'],
                                          createComps=True,
                                          defaultFlavor='!readline')
        self.addCollection('group-foo', '1', ['simple', 
                                  ('simple', ':branch', '!readline')],
                           defaultFlavor='readline')
        sourceTrv = self.addComponent('simple:source', '2',
                                      [('simple.recipe', recipes.simpleRecipe)])
        branchTrv = self.addComponent('simple:source', ':branch/2', 
                                      [('simple.recipe', recipes.simpleRecipe)])
        def _getTroves(*matchSpecs):
            return buildcmd.getTrovesToBuild(self.buildCfg, 
                                             helper.getConaryClient(),
                                             ['group-foo'], recurseGroups=True,
                                             matchSpecs=matchSpecs)

        trvs = _getTroves('simple=:linux', '-group-foo')
        assert(trvs == [('simple:source', sourceTrv.getVersion(),
                         binTrv.getFlavor())])
        trvs = _getTroves('simple=:branch', '-group-foo')
        assert(trvs == [('simple:source', branchTrv.getVersion(),
                         branchBinTrv.getFlavor())])
        trvs = _getTroves('=[readline]', '-group-foo')
        assert(trvs == [('simple:source', sourceTrv.getVersion(),
                         binTrv.getFlavor())])
        trvs = _getTroves('si*[readline]', '-group-*')
        assert(trvs == [('simple:source', sourceTrv.getVersion(),
                         binTrv.getFlavor())])

    def testRestartCookSourceGroup(self):
        self.addComponent('foo:source=1')
        self.addComponent('bar:source=1')
        self.addComponent('group-foo:source=1', 
                          [('group-foo.recipe', groupFooRecipe)])
        helper = self.getRmakeHelper()
        job = helper.createBuildJob('group-foo',
                           recurseGroups=helper.BUILD_RECURSE_GROUPS_SOURCE)
        db = self.openRmakeDatabase()
        db.addJob(job)
        jobId = job.jobId
        self.addComponent('group-foo:source=2', 
                          [('group-foo.recipe', groupFooRecipe2)])
        job = helper.createRestartJob(jobId)
        assert(sorted([x[0] for x in job.iterTroveList()]) == ['bar:source', 
                                                        'group-foo:source'])

        job = helper.createRestartJob(jobId, updateSpecs=['-*'])
        assert(sorted([x[0] for x in job.iterTroveList()]) 
                == ['foo:source', 'group-foo:source'])
        assert(job.getMainConfig().jobContext == [jobId])
        job = helper.createRestartJob(jobId, clearPrebuiltList=True)
        assert(job.getMainConfig().jobContext == [])

    def testCookSourceGroup(self):
        self.openRepository()
        repos = self.openRepository(1)
        trv0 = self.addComponent('test0:source', '1').getNameVersionFlavor()
        trv1 = self.addComponent('test:source', '1').getNameVersionFlavor()
        trv2 = self.addComponent('test2:source', '1').getNameVersionFlavor()
        trv5 = self.addComponent('test5:source', '1').getNameVersionFlavor()
        self.addComponent('test4:source', 
                           '/localhost1@rpl:linux/1-1').getNameVersionFlavor()
        self.addComponent('group-foo:source', '1',
                          [('group-foo.recipe', groupRecipe),
                            ('preupdate.sh', '#!/bin/sh\necho "hello"\n')])
        self.openRmakeRepository()
        helper = self.getRmakeHelper()
        self.buildCfg.limitToHosts('localhost')
        self.buildCfg.addMatchRule('-group-foo')
        job = buildcmd.getBuildJob(self.buildCfg,
                          helper.getConaryClient(),
                          ['group-foo[ssl]',
                           'group-foo[!ssl]'],
                          recurseGroups=buildcmd.BUILD_RECURSE_GROUPS_SOURCE)
        trvs = set(job.iterTroveList())
        assert(trvs == set([(trv0[0], trv0[1], deps.parseFlavor('')),
                            (trv1[0], trv1[1], deps.parseFlavor('ssl')),
                            (trv2[0], trv2[1], deps.parseFlavor('readline')),
                            (trv5[0], trv5[1], deps.parseFlavor(''))]))
        helper = self.getRmakeHelper()
        db = self.openRmakeDatabase()
        db.addJob(job)
        jobId = job.jobId
        job = helper.createRestartJob(jobId)
        os.chdir(self.workDir)
        self.checkout('group-foo')
        os.chdir('group-foo')
        self.writeFile('group-foo.recipe', groupRecipe + '#\n') # change
        self.buildCfg.matchTroveRule = []
        self.buildCfg.limitToLabels('localhost@rpl:linux')
        self.buildCfg.addMatchRule('-group-foo')
        self.buildCfg.addMatchRule('-[readline]')
        trvs = buildcmd.getTrovesToBuild(
                          self.buildCfg, helper.getConaryClient(),
                          ['group-foo.recipe[ssl]',
                           'group-foo.recipe[!ssl]'],
                          recurseGroups=buildcmd.BUILD_RECURSE_GROUPS_SOURCE,
                          matchSpecs=self.buildCfg.matchTroveRule)
        trvs = set(trvs)
        assert(trvs == set([(trv0[0], trv0[1], deps.parseFlavor('')),
                            (trv1[0], trv1[1], deps.parseFlavor('ssl')),
                            (trv5[0], trv5[1], deps.parseFlavor(''))]))
        # Build the actual group, and this time let's do a fresh commit
        # instead of a shadow + commit.
        os.remove('CONARY')
        self.buildCfg.matchTroveRule = []
        trvs = buildcmd.getTrovesToBuild(
                          self.buildCfg, helper.getConaryClient(),
                          ['group-foo.recipe[ssl]',
                           'group-foo.recipe[!ssl]'],
                          recurseGroups=buildcmd.BUILD_RECURSE_GROUPS_NONE,
                          matchSpecs=self.buildCfg.matchTroveRule)
        trvs = set(trvs)
        assert(len(trvs) == 2)
        assert([x[0] for x in trvs] == ['group-foo:source', 'group-foo:source'])


    def testGetTrovesToBuildFailedPackage(self):
        self.openRmakeRepository()
        helper = self.getRmakeHelper()

        os.chdir(self.workDir)
        self.newpkg('simple')
        os.chdir('simple')
        self.writeFile('simple.recipe', 
                        recipes.simpleRecipe + '\ta = b # NameError\n')
        try:
            v = buildcmd.getTrovesToBuild(self.buildCfg, 
                                       helper.getConaryClient(),
                                       ['simple.recipe'], message='foo')[0][1]
        except errors.RmakeError, msg:
            assert(str(msg) == "could not initialize recipe: %s/simple/simple.recipe:8:\n NameError: global name 'b' is not defined" % self.workDir)
        else:
            assert 0, "expected RmakeError"

        self.writeFile('simple.recipe', 
                        recipes.simpleRecipe + '\tr.addArchive("blammo")\n')
        try:
            v = buildcmd.getTrovesToBuild(self.buildCfg, 
                                          helper.getConaryClient(),
                                       ['simple.recipe'], message='foo')[0][1]
        except errors.RmakeError, msg:
            assert(str(msg) == 'Could not commit changes to build recipe %s/simple/simple.recipe: Source file blammo does not exist' % self.workDir)
        else:
            assert 0, "expected RmakeError"


    def testCookBinaryGroup(self):
        repos = self.openRmakeRepository()
        self.startRmakeServer()
        helper = self.getRmakeHelper()
        bamTrv = self.addComponent('group-bam:source', '1')
        self.addComponent('group-bam:source', '2')
        binTrv = self.addCollection('simple', '1', [':runtime'], 
                                    createComps=True,
                                    defaultFlavor='readline')
        self.addCollection('group-foo', '1', ['simple'], 
                           defaultFlavor='readline', 
                           sourceName='group-bam:source')
        sourceTrv = self.addComponent('simple:source', '2', 
                                      [('simple.recipe', recipes.simpleRecipe)])

        trvs = buildcmd.getTrovesToBuild(self.buildCfg, 
                                         helper.getConaryClient(),
                                         ['group-foo[ssl]'],
                                         matchSpecs=['-group-foo'],
                                         recurseGroups=True)
        assert(len(trvs) == 2)
        assert(set(trvs) == set([('simple:source', sourceTrv.getVersion(),
                                 binTrv.getFlavor()),
                                 ('group-bam:source', bamTrv.getVersion(), 
                                  deps.parseFlavor('ssl'))]))
        jobId, txt = self.captureOutput(helper.buildTroves,
                                       ['group-foo'], 
                                       matchSpecs=['-group-bam'],
                                       recurseGroups=True)
        helper.waitForJob(jobId)
        assert(helper.client.getJob(jobId).isBuilt())
        self.addComponent('foo:source=2')
        binTrv = self.addCollection('foo', '2', [':runtime'], 
                                    createComps=True,
                                    defaultFlavor='~readline,~ssl')
        self.addCollection('group-foo', '2', ['foo=2'],
                           defaultFlavor='~readline,~ssl',
                           sourceName='group-bam:source')
        job = helper.createRestartJob(jobId, updateSpecs=['-group-*'])
        assert(sorted(x.getName() for x in job.iterTroves()) == ['simple:source'])
        job = helper.createRestartJob(jobId)
        assert(sorted(x.getName() for x in job.iterTroves()) == ['foo:source'])

    def testResolveTroveList(self):
        repos = self.openRepository()
        self.addComponent('foo:run', '1')
        grp = self.addCollection('group-dist', '1', ['foo:run'])
        oldResolveTroves = self.buildCfg.resolveTroves
        self.buildCfg.resolveTroves = [[('group-dist', None, None)]]
        try:
            resolveTroveTups = buildcmd._getResolveTroveTups(self.buildCfg, repos)
        finally:
            self.buildCfg.resolveTroves = oldResolveTroves
        assert(resolveTroveTups == [[grp.getNameVersionFlavor()]])

    def testResolveTroveListError(self):
        repos = self.openRepository()
        oldResolveTroves = self.buildCfg.resolveTroves
        self.buildCfg.resolveTroves = [[('group-dist', None, None)]]
        try:
            try:
                buildcmd._getResolveTroveTups(self.buildCfg, repos)
            except errors.RmakeError, msg:
                assert(str(msg) == 'Could not find resolve troves for [default] context: group-dist'
                               ' was not found on path localhost@rpl:linux\n')
            else:
                assert 0, "didn't raise expected exception"
        finally:
            self.buildCfg.resolveTroves = oldResolveTroves

    def testRemovefile(self):
        
        repos = self.openRmakeRepository()
        helper = self.getRmakeHelper()

        self.buildCfg.configLine('[foo]')
        self.buildCfg.configLine('flavor ssl')

        self.addComponent('local:source', '1', '',
                          [ ('local.recipe', localSourceRecipe2),
                            ('foo',           'content\n')])
        os.chdir(self.workDir)
        self.checkout('local')
        os.chdir('local')
        self.writeFile('local.recipe', 
                       '\n'.join(localSourceRecipe2.split('\n')[:-1]))
        self.remove('foo')
        job = self.captureOutput(buildcmd.getBuildJob,
                                 self.buildCfg,
                                 helper.getConaryClient(),
                                 ['local.recipe{foo}'], message='foo')
        # make sure that making no changes works as well
        job = self.captureOutput(buildcmd.getBuildJob,
                                     self.buildCfg,
                                     helper.getConaryClient(),
                                     ['local.recipe{foo}'], message='foo')

    def testLoadJob(self):
        self.addComponent('simple:source', '1', '',
                          [ ('simple.recipe', recipes.simpleRecipe)])
        helper = self.getRmakeHelper()
        job = helper.createBuildJob('simple')
        job.writeToFile(self.workDir + '/foo.job')
        helper.buildConfig.user.append(('localhost', 'bam', 'newpass'))
        job2 = helper.loadJobFromFile(self.workDir + '/foo.job')
        assert(list(job2.iterTroveList()) == list(job.iterTroveList()))
        assert(job2.iterConfigList().next().user 
               != job.iterConfigList().next().user)

    def testSubDirectories(self):

        repos = self.openRmakeRepository()
        helper = self.getRmakeHelper()

        self.addComponent('local:source', '1', '',
                          [ ('local.recipe', localSourceRecipe3),
                            ('subdir/foo',           'content\n')])
        os.chdir(self.workDir)
        self.checkout('local')
        os.chdir('local')
        self.writeFile('local.recipe', 
                        (localSourceRecipe3 + '\tr.addSource("bar/bam")\n'))
        os.mkdir('bar')
        self.writeFile('bar/bam', 'content2\n')
        self.addfile('bar')
        self.addfile('bar/bam', text=True)
        (n,v,f) = self.captureOutput(buildcmd.getTrovesToBuild,
                                     self.buildCfg,
                                     helper.getConaryClient(),
                                     ['local.recipe'], message='foo')[0][0]
        # make sure that making no changes works as well
        (n,v,f) = self.captureOutput(buildcmd.getTrovesToBuild,
                                     self.buildCfg,
                                     helper.getConaryClient(),
                                     ['local.recipe'], message='foo')[0][0]

    def testBuildRecipeWithMissingFile(self):
        self.openRmakeRepository()
        self.addComponent('simple:source', 
                          [('simple.recipe', recipes.simpleRecipe)])
        os.chdir(self.workDir)
        self.checkout('simple')
        os.chdir('simple')
        self.writeFile('simple.recipe',
                       recipes.simpleRecipe + '\tr.addSource("foo")\n')
        self.writeFile('foo', 'foo\n')
        helper = self.getRmakeHelper()
        self.buildCfg.configLine('sourceSearchDir .')
        (n,v,f) = self.captureOutput(buildcmd.getTrovesToBuild,
                                     self.buildCfg,
                                     helper.getConaryClient(),
                                     ['simple.recipe'], message='foo')[0][0]
        os.chdir('..')
        self.checkout('simple=%s' % v)
        os.chdir('simple')
        stateFile = state.ConaryStateFromFile('CONARY').getSourceState()
        pathId, = [x[0] for x in stateFile.iterFileList() if x[1] == 'foo']
        assert(not stateFile.fileIsAutoSource(pathId))

    def testRefreshRecipe(self):
        self.cfg.sourceSearchDir = self.workDir + '/source'
        self.buildCfg.sourceSearchDir = self.workDir + '/source'
        util.mkdirChain(self.cfg.sourceSearchDir)
        autoSourceFile = self.cfg.sourceSearchDir + '/autosource'
        self.writeFile(autoSourceFile, 'contents\n')
        self.makeSourceTrove('auto', autoSourceRecipe)
        os.chdir(self.workDir)
        self.checkout('auto')
        os.chdir('auto')

        self.writeFile(autoSourceFile, 'contents2\n')
        self.refresh()

        repos = self.openRmakeRepository()
        helper = self.getRmakeHelper()
        (n,v,f) = self.captureOutput(buildcmd.getTrovesToBuild,
                                     self.buildCfg,
                                     helper.getConaryClient(),
                                     ['auto.recipe'], message='foo')[0][0]
        trv = repos.getTrove(n,v,f)
        filesToGet = []
        for pathId, path, fileId, fileVersion in trv.iterFileList():
            if path == 'autosource':
                filesToGet.append((fileId, fileVersion))
        contents = repos.getFileContents(filesToGet)[0]
        assert(contents.get().read() == 'contents2\n')

    def testRebuild(self):
        self.addComponent('foo:source')
        self.addComponent('bar:source')
        self.buildCfg.configLine('[x86]')
        helper = self.getRmakeHelper()
        job = buildcmd.getBuildJob(self.buildCfg,
                          helper.getConaryClient(),
                          ['foo'],
                          rebuild=True)
        assert(not job.getMainConfig().prebuiltBinaries)
        self.addComponent('foo:runtime')
        self.addCollection('foo', [':runtime'])
        self.addComponent('bar:runtime')
        self.addCollection('bar', [':runtime'])
        self.addComponent('bar:runtime[is:x86_64]')
        self.addCollection('bar[is:x86_64]', [':runtime'])
        job = helper.createBuildJob(['foo', 'bar{x86}'],
                          rebuild=True)
        assert(sorted([x[0] for x in job.getMainConfig().prebuiltBinaries]) == ['bar', 'bar', 'foo'])



    def testBuildInfo(self):
        self.addComponent('bar:runtime')
        self.addComponent('foo:source')
        self.openRepository()
        self.openRmakeRepository()
        self.buildCfg.flavor = [deps.parseFlavor('is:x86')]
        self.buildCfg.configLine('resolveTroves bar:runtime')
        self.buildCfg.configLine('[nossl]')
        self.buildCfg.configLine('flavor !ssl is: x86')
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        rc, txt = self.captureOutput(helper.buildTroves,['foo{nossl}', 'foo[ssl]'], infoOnly=True, limitToLabels='localhost@rpl:linux')
        txt = re.sub('flavor.*', 'flavor <flavor>', txt)
        txt = re.sub('buildFlavor .*', 'buildFlavor <flavor>', txt)
        assert('repositoryMap' in txt)
        txt = re.sub('repositoryMap .*?\n', '', txt)
        self.assertEquals(txt, '''
{Default Context}

ResolveTroves:

bar:runtime=/localhost@rpl:linux/1.0-1-1[]

Configuration:
copyInConfig              False
copyInConary              False
buildFlavor <flavor>
flavor <flavor>
installLabelPath          localhost@rpl:linux
resolveTrovesOnly         False
user                      rmakehost rmake <password>
user                      * test <password>

Building:
foo:source=localhost@rpl:linux/1.0-1[ssl]

{nossl}

ResolveTroves:

bar:runtime=/localhost@rpl:linux/1.0-1-1[]

Configuration:
buildFlavor <flavor>
flavor <flavor>
installLabelPath          localhost@rpl:linux
resolveTrovesOnly         False
user                      rmakehost rmake <password>
user                      * test <password>

Building:
foo:source=localhost@rpl:linux/1.0-1{nossl}
''')

        rc, txt = self.captureOutput(helper.buildTroves,['foo{nossl}', 'foo[ssl]'], quiet=True, infoOnly=True)
        self.assertEquals(txt, '''\
foo:source=localhost@rpl:linux/1.0-1[ssl]
foo:source=localhost@rpl:linux/1.0-1{nossl}
''')
        job = fixtures.addBuiltJob1(self)
        rc, txt = self.captureOutput(helper.restartJob, 1, infoOnly=True,
                                     quiet=True)
        self.assertEquals(txt, '''\
testcase:source=localhost@rpl:linux/1-1[ssl]
''')

infoRecipe = """\
class InfoRecipe(UserInfoRecipe):
    name = 'info-foo'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        r.User('foo', 500)
"""

groupRecipe = """
class FooGroup(GroupRecipe):
    name = 'group-foo'
    version = '1'

    def setup(r):
        r.add('test0')
        r.addAll('test5')
        if Use.ssl:
            r.add('test-derived', '1', 'ssl', source='test')
        else:
            r.add('test2', '1', 'readline')
            r.add('test3', '1', 'readline')
            r.add('test4', 'localhost1@rpl:linux/1', 'readline')
        r.addPostUpdateScript(contents = '''#!/bin/bash
/sbin/service foundation-config start

''')
        r.addPreUpdateScript('preupdate.sh')

"""

groupRecipe2 = """
class FooGroup(GroupRecipe):
    name = 'group-foo'
    version = '2'

    def setup(r):
        r.add('test0')
        r.add('test6')
"""

groupFooRecipe = """
class FooGroup(GroupRecipe):
    name = 'group-foo'
    version = '1'

    def setup(r):
        r.add('foo')
"""

groupFooRecipe2 = """
class FooGroup(GroupRecipe):
    name = 'group-foo'
    version = '2'

    def setup(r):
        r.add('bar')
"""


autoSourceRecipe = """\
class AutoSource(PackageRecipe):
    name = 'auto'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        r.addSource('autosource', dest='/foo/autosource')
"""

localSourceRecipe = """\
class LocalSource(PackageRecipe):
    name = 'local'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        r.addSource('dc_client.init', rpm='distcache-1.4.5-2.src.rpm')
        r.addSource('foo', dest='/')
        r.addArchive('tmpwatch-2.9.0.tar.gz', rpm='tmpwatch-2.9.0-2.src.rpm')
        del r.NormalizeManPages
"""

localSourceRecipe2 = """\
class LocalSource(PackageRecipe):
    name = 'local'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        r.addSource('dc_client.init', rpm='distcache-1.4.5-2.src.rpm')
        r.addArchive('tmpwatch-2.9.0.tar.gz', rpm='tmpwatch-2.9.0-2.src.rpm')
        r.addSource('foo', dest='/')
"""

localSourceRecipe3 = """\
class LocalSource(PackageRecipe):
    name = 'local'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        r.addSource('subdir/foo', dest='/')
        r.addAction('echo "hello"')
"""

localFactory = """\
class FactoryTest(Factory):
    name = 'factory-test'
    version = '0'
    def getRecipeClass(self):
        class TestRecipe(PackageRecipe):
            name = self.packageName
            version = 'setbysuperclass'
            def setup(r):
                r.Create('/etc/foo')
        return TestRecipe
"""
