#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

import copy
import os
import re
import sys
import time

from conary.deps import deps
from conary_test import recipes
from testrunner import testhelp

from rmake import compat
from rmake.build import builder
from rmake.lib import logfile
from rmake.lib import repocache

from rmake_test import resources
from rmake_test import rmakehelp


workingRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'testcase'
    version = '1.0'

    # cross requirements shouldn't matter since we're not 
    # crosscompiling
    crossReqs = ['nonexistant:runtime']
    clearBuildReqs()
    def setup(r):
        if Use.ssl:
            r.Create('/foo', contents='foo')
        else:
            r.Create('/bar', contents='foo')
"""

macrosRecipe = r"""\
class TestRecipe(PackageRecipe):
    name = 'testcase'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        r.macros.foo = 'ssl'
        # this recipe only passes if r.macros.foo == 'readline'
        # and r.macros.multi == 'line1\nline2'
        if r.macros.foo == 'readline' and r.macros.multi == 'line1\nline2':
            r.Create('/foo', contents='foo')
"""

failingRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'testcase2'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        r.Create('/foo', contents='foo')
        r.Run('exit 1')
"""

failedSetupRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'testcase3'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        a = b
        r.Create('/foo', contents='foo')
"""

failedLoadRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'testcase4'
    version = '1.0'
    a = b # NameError

    clearBuildReqs()
    def setup(r):
        r.Create('/foo', contents='foo')
"""

failedBuildReqRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'testcase5'
    version = '1.0'

    clearBuildReqs()
    buildRequires = ['bbbbbbb:devel']
    def setup(r):
        r.Create('/foo', contents='foo')
"""


groupRecipe = """\
class TestRecipe(GroupRecipe):
    name = 'group-foo'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        # sneak in a test of r.macros.buildlabel
        r.setSearchPath(r.macros.buildlabel)
        r.add('simple:runtime')
        r.add('other:runtime')
"""

redirectRecipe = """\
class TestRecipe(RedirectRecipe):
    name = 'redirect'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        r.addRedirect("target", '/localhost@rpl:linux')
"""

filesetRecipe = """\
class TestRecipe(FilesetRecipe):
    name = 'fileset-foo'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        r.addFile('/bin/foo', "orig", '/localhost@rpl:linux')
"""


infoRecipe = """\
class Info(GroupInfoRecipe):
    name = 'info-sys'
    version = '1'
    clearBuildReqs()

    def setup(r):
        r.Group('sys', 3)
"""

derivedRecipe = """\
class TestRecipe(DerivedPackageRecipe):
    name = 'testcase'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        r.Create('/bam', contents='foo')
"""

buildReqsRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'testcase'
    version = '1.0'

    clearBuildReqs()
    buildRequires = [ 'foo:runtime', 'foo:runtime[cross]']
    def setup(r):
        r.Create('/bar', contents='foo')
"""




class BuilderTest(rmakehelp.RmakeHelper):

    def testBasic(self):
        # FIXME: this is really slow - ~20 seconds.
        # Perhaps we need to make hooks to make this test faster?
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', workingRecipe)])
        trv2 = self.addComponent('testcase2:source', '1.0-1', '',
                                [('testcase2.recipe', failingRecipe)])
        trv3 = self.addComponent('testcase3:source', '1.0-1', '',
                                [('testcase3.recipe', failedSetupRecipe)])
        trv4 = self.addComponent('testcase4:source', '1.0-1', '',
                                [('testcase4.recipe', failedLoadRecipe)])
        trv5 = self.addComponent('testcase5:source', '1.0-1', '',
                                [('testcase5.recipe', failedBuildReqRecipe)])
        self.openRmakeRepository()

        troveList = [
                (trv.getName(), trv.getVersion(), deps.parseFlavor('!ssl')),
                trv2.getNameVersionFlavor(),
                trv3.getNameVersionFlavor(),
                trv4.getNameVersionFlavor(),
                trv5.getNameVersionFlavor(),
                ]
        db = self.openRmakeDatabase()
        job = self.newJob(*troveList)
        db.subscribeToJob(job)
        b = builder.Builder(self.rmakeCfg, job)
        self.logFilter.add()
        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        try:
            b.build()
        except Exception:
            b.worker.stopAllCommands()
            raise
        logFile.restoreOutput()

        assert(set([x.getName() for x in b.dh.depState.getFailedTroves()])
               == set([trv2.getName(), trv3.getName(), trv4.getName(),
                       trv5.getName()]))

        repos = self.openRepository()
        results = repos.findTrove(None, ('testcase', 'rmakehost@local:linux',
                                         deps.parseFlavor('!ssl')), 
                                         self.buildCfg.flavor)
        assert(len(results) == 1)
        assert(results[0][2] == deps.parseFlavor('~!ssl'))
        troveDict = dict((x.getName(), x)
                         for x in db.getJob(1).iterFailedTroves())
        assert(len(troveDict) == 4)
        trv2 = troveDict['testcase2:source']
        failureReason = str(trv2.getFailureReason())
        # remove the arch-specific flavor here, we're not testing that
        failureReason = re.sub(r'\[.*\]', '[FLAVOR]', failureReason)
        assert(str(failureReason) == 'Failed while building: Error building recipe testcase2:source=/localhost@rpl:linux/1.0-1[FLAVOR]: Shell command "exit 1" exited with exit code 1')
        trv3 = troveDict['testcase3:source']
        assert(str(trv3.getFailureReason()) == "Failed while loading recipe: global name 'b' is not defined")
        trv4 = troveDict['testcase4:source']
        failureReason = str(trv4.getFailureReason())
        failureReason = re.sub('/tmp.*\.recipe',
                               'TEMP.recipe',
                               failureReason)
        failureReason = re.sub('temp-testcase4.*\.recipe',
                               'testcase4.recipe',
                               failureReason)

        errStr = '''\
Failed while loading recipe: unable to load recipe file /varTEMP.recipe:
Error in recipe file "testcase4.recipe":
 Traceback (most recent call last):
  File "/varTEMP.recipe", line 1, in ?
    class TestRecipe(PackageRecipe):
  File "/varTEMP.recipe", line 4, in TestRecipe
    a = b # NameError
NameError: name 'b' is not defined
'''
        if sys.version_info > (2, 5):
            errStr = errStr.replace('?', '<module>')
        self.assertEquals(failureReason, errStr)
        trv5 = troveDict['testcase5:source']
        self.assertEquals(str(trv5.getFailureReason()),
                     'Could not satisfy build requirements: bbbbbbb:devel=[]')
        assert(str(b.job.getFailureReason()) == """\
Failed while building: Build job had failures:
   * testcase2:source: Error building recipe testcase2:source=/localhost@rpl:linux/1.0-1[%s]: Shell command "exit 1" exited with exit code 1
   * testcase3:source: Failed while loading recipe
   * testcase4:source: Failed while loading recipe
   * testcase5:source: Could not satisfy build requirements: bbbbbbb:devel=[]
""" % self.getArchFlavor())

    def testBuildReqs(self):
        self.addComponent('foo:runtime[!cross]')
        self.addComponent('foo:runtime=2[cross]', filePrimer=1)
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', buildReqsRecipe)])
        self.openRmakeRepository()
        db = self.openRmakeDatabase()
        job = self.newJob(trv.getNameVersionFlavor())
        db.subscribeToJob(job)
        b = builder.Builder(self.rmakeCfg, job)
        self.logFilter.add()
        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        try:
            b.build()
        except Exception:
            b.worker.stopAllCommands()
            raise
        logFile.restoreOutput()
        assert b.job.isBuilt(), b.job.troves.values()[0].getFailureReason().getTraceback()
        trv = self.findAndGetTrove('testcase=rmakehost@local:linux')
        buildReqs = trv.getBuildRequirements()
        assert len(buildReqs) == 2, "Got cross req twice!"

        

    def testLoadInstalled(self):
        # Test to ensure that when we are building package a
        # and package b is installed in that root, the version of
        # package b installed in that root is loaded and read for
        # class info.
        loadInstalledRecipe = """\
loadInstalled('buildreq')
class TestRecipe(PackageRecipe):
    name = 'loadreq'
    version = '1.0'

    clearBuildReqs()
    buildRequires = ['buildreq:runtime']
    def setup(r):
        r.Create(BuildReq.filePath)
"""

        buildreqRecipe = """\
class BuildReq(PackageRecipe):
    name = 'buildreq'
    version = '1.0'
    filePath = '/foo1.0'

    clearBuildReqs()
    def setup(r):
        r.Create('/foo', contents='foo')
"""
        buildreqRecipe2 = buildreqRecipe.replace('1.0', '2.0')

        br = self.addComponent('buildreq:source', '1.0-1', '',
                                [('buildreq.recipe', buildreqRecipe)])
        br2 = self.addComponent('buildreq:source', '2.0-1', '',
                                [('buildreq.recipe', buildreqRecipe2)])
        li = self.addComponent('loadreq:source', '2.0-1', '',
                               [('loadreq.recipe', loadInstalledRecipe)])
        self.addComponent('buildreq:runtime', '1.0-1-1')
        self.addCollection('buildreq', '1.0-1-1', [':runtime'])
        job = self.buildTroves(li.getNameVersionFlavor())
        assert(job.isBuilt())
        liBuilt = job.getTrove(*(job.getTrovesByName('loadreq')[0]))
        # get built version info
        v, f = liBuilt.iterBuiltTroves().next()[1:]
        repos = repocache.CachingTroveSource(self.openRepository(),
                                             self.rmakeCfg.getCacheDir())
        trv = repos.getTrove('loadreq:runtime', v, f, withFiles=True)
        files = [x[1] for x in trv.iterFileList()]
        # make sure that we loaded version 1.0 when building, even though
        # version 2.0 was available.
        assert('/foo1.0' in files)

    def testCopyInPolicy(self):
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', workingRecipe)])
        self.openRmakeRepository()

        troveList = [ trv.getNameVersionFlavor() ]
        db = self.openRmakeDatabase()
        buildCfg = copy.deepcopy(self.buildCfg)
        buildCfg.strictMode = False
        buildCfg.copyInConary = True
        fakePolicyPath = resources.get_archive('policy')
        buildCfg.policyDirs = buildCfg.policyDirs + [ fakePolicyPath ]

        job = self.newJob(buildConfig=buildCfg, *troveList)
        b = builder.Builder(self.rmakeCfg, job)
        self.logFilter.add()
        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        b.build()
        logFile.restoreOutput()
        trove = b.job.troves.values()[0]
        assert(str(trove.getFailureReason()).endswith(
                                        'This fake policy always breaks.'))

    def testGroupRecipe(self):
        if compat.ConaryVersion().conaryVersion[0:2] == [1,2]:
            raise testhelp.SkipTestException('test fails on 1.2')
        repos = self.openRmakeRepository()
        db = self.openRmakeDatabase()

        self.buildCfg.shortenGroupFlavors = True
        self.buildCfg.setSection('foo') # add context foo
        self.buildCfg.configLine('buildFlavor desktop is:x86')
        self.buildCfg.setSection('bar') 
        self.buildCfg.configLine('buildFlavor !desktop is:x86')

        simple = self.addComponent('simple:runtime', '1.0-1-1', '')
        other1 = self.addComponent('other:runtime', '1.0-1-1', '!desktop',
                filePrimer=1)
        other2 = self.addComponent('other:runtime', '1.0-1-1', 'desktop',
                filePrimer=1)

        # Prevent the desktop flag from being pre-filtered out
        recipe = groupRecipe + '\n        if Use.desktop: pass\n'
        trv = self.addComponent('group-foo:source', 
                     '/localhost@rpl:linux//rmakehost@local:linux/1:1.0-1',
                     [('group-foo.recipe', recipe)])
        troveList = [
                trv.getNameVersionFlavor() + ('foo',),
                trv.getNameVersionFlavor() + ('bar',),
                ]
        job = self.newJob(*troveList)
        b = builder.Builder(self.rmakeCfg, job)

        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        b.build()
        logFile.restoreOutput()
        assert b.job.isBuilt(), str(b.job.getFailureReason())
        assert len(b.job.getBuiltTroveList()) == 2, b.job.getBuiltTroveList()

        for tup in b.job.getBuiltTroveList():
            groupTrove = repos.getTrove(*tup)
            # this is just a very basic test of builder -> group build.
            # tests of the group cook code's ability to include the right 
            # version in particular cases should be in cooktest.py
            if '!desktop' in str(groupTrove.getFlavor()):
                other = other1
            else:
                other = other2
            self.assertEqual(sorted(groupTrove.iterTroveList(strongRefs=True)),
                    [other.getNameVersionFlavor(),
                        simple.getNameVersionFlavor()])

    def testRedirectRecipe(self):
        self.openRmakeRepository()
        db = self.openRmakeDatabase()
        self.addComponent('redirect:run', '1')
        self.addCollection('redirect', '1', [':run'])
        self.addComponent('target:run', '1')
        self.addCollection('target', '1', [':run'])
        # simulate building a checkout
        trv = self.addComponent(
         'redirect:source=/localhost@rpl:linux//rmakehost@local:linux/1.0-1', 
         [('redirect.recipe', redirectRecipe)])
        os.chdir(self.workDir)
        troveList = [ trv.getNameVersionFlavor() ]
        job = self.newJob(*troveList)
        b = builder.Builder(self.rmakeCfg, job)

        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        b.build()
        logFile.restoreOutput()
        assert b.job.isBuilt(), b.job.getFailureReason()

    def testFilesetRecipe(self):
        self.openRmakeRepository()
        self.addComponent('orig:run', '1', ['/bin/foo'])
        self.addCollection('orig', '1', [':run'])
        trv = self.addComponent('fileset-foo:source', '1.0-1', '',
                                [('fileset-foo.recipe', filesetRecipe)])
        troveList = [ trv.getNameVersionFlavor() ]
        job = self.newJob(*troveList)
        b = builder.Builder(self.rmakeCfg, job)
        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        b.build()
        logFile.restoreOutput()
        assert b.job.isBuilt(), b.job.troves.values()[0].getFailureReason()



    def testInfoRecipe(self):
        self.openRmakeRepository()
        db = self.openRmakeDatabase()
        trv = self.addComponent('info-sys:source', '1.0-1', '',
                                [('info-sys.recipe', infoRecipe)])
        troveList = [ trv.getNameVersionFlavor() ]
        job = self.newJob(*troveList)
        b = builder.Builder(self.rmakeCfg, job)

        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        b.build()
        logFile.restoreOutput()
        assert(b.job.isBuilt())

    def testMacrosRecipe(self):
        self.openRmakeRepository()
        db = self.openRmakeDatabase()
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', macrosRecipe)])
        self.buildCfg.configLine('macros foo readline')
        self.buildCfg.macros['multi'] = 'line1\nline2'
        job = self.newJob(trv)
        b = builder.Builder(self.rmakeCfg, job)

        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        b.build()
        logFile.restoreOutput()
        assert(b.job.isBuilt())
        # this recipe will only work if r.macros.foo has been successfully 
        # set to readline

    def testDerivedRecipe(self):
        self.openRmakeRepository()
        db = self.openRmakeDatabase()
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', workingRecipe)])
        self.addComponent('testcase:run', '1.0-1-1', 
                           ['/foo', '/bar'])
        self.addCollection('testcase', '1.0-1-1', [':run'])
        trv = self.addComponent('testcase:source', 
                                '/localhost@rpl:linux//branch/1.0-1',
                                [('testcase.recipe', workingRecipe)])
        trv = self.addComponent('testcase:source', 
                                '/localhost@rpl:linux//branch/1.0-1.1',
                                [('testcase.recipe', derivedRecipe)])
        troveList = [ trv.getNameVersionFlavor() ]
        job = self.newJob(*troveList)
        b = builder.Builder(self.rmakeCfg, job)

        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        b.build()
        logFile.restoreOutput()
        assert(b.job.isBuilt())

    def testDerivedRecipeCheckout(self):
        self.openRmakeRepository()
        db = self.openRmakeDatabase()
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', workingRecipe)])
        self.addComponent('testcase:run', '1.0-1-1', 
                           ['/foo', '/bar'])
        self.addCollection('testcase', '1.0-1-1', [':run'])
        trv = self.addComponent('testcase:source', 
                                '/localhost@rpl:linux//branch/1.0-1',
                                [('testcase.recipe', workingRecipe)])
        trv = self.addComponent('testcase:source', 
                                '/localhost@rpl:linux//branch/1.0-1.1',
                                [('testcase.recipe', derivedRecipe)])
        os.chdir(self.workDir)
        self.checkout('testcase=:branch')
        os.chdir('testcase')
        self.writeFile('testcase.recipe', '#comment\n' + derivedRecipe)
        helper = self.getRmakeHelper()
        server = helper.client.uri.server
        jobId = self.discardOutput(helper.buildTroves, ['testcase.recipe'])
        job = helper.getJob(jobId)
        while not job.isFinished():
            server._serveLoopHook()
            job = helper.getJob(jobId)
            import time
            time.sleep(.5)
        assert(job.isBuilt()), job.getFailureReason()
        server._halt = 1
        server._serveLoopHook()
        time.sleep(2)

    def testMultipleDelayedRecipes(self):
        self.openRmakeRepository()
        db = self.openRmakeDatabase()

        trv = self.addComponent('redirect:source', '1.0-1', '',
                                [('redirect.recipe', redirectRecipe)])
        trv2 = self.addComponent('fileset-foo:source', '1.0-1', '',
                                [('fileset-foo.recipe', filesetRecipe)])
        troveList = [ trv.getNameVersionFlavor(), trv2.getNameVersionFlavor() ]
        job = self.newJob(*troveList)
        db.subscribeToJob(job)
        b = builder.Builder(self.rmakeCfg, job)
        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        b.build()
        logFile.restoreOutput()
        assert(b.job.isFailed())
        failedTroves = list(b.job.iterFailedTroves())
        assert(len(failedTroves) == 2)
        group = [ x for x in failedTroves if x.getName() == trv.getName()][0]
        assert(str(group.getFailureReason()) == 'Trove failed sanity check: redirect and fileset packages must be alone in their own job')
        assert(str(b.job.getFailureReason()) == 'Job failed sanity check: redirect and fileset packages must be alone in their own job: fileset-foo, redirect')

    def testPrebuiltBinaries(self):
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', workingRecipe)])
        trv2 = self.addComponent('simple:source', '1.0-2',
                                   [('simple.recipe', recipes.simpleRecipe)])
        binTrv = self.addCollection('testcase=1.0-1-1[ssl]', [':runtime'], 
                                 createComps=True)
        binTrv2 = self.addCollection('testcase=1.0-1-1[!ssl]', [':runtime'], 
                                     createComps=True)
        binTrv3 = self.addCollection('testcase=1.0-1-1', [':runtime'], 
                                 createComps=True)
        binTrv4 = self.addCollection('simple=1.0-1-1', [':runtime'])
        job = self.newJob(trv, trv2)
        prebuilt = [ x.getNameVersionFlavor() for x in 
                     (binTrv, binTrv2, binTrv3, binTrv4)]
        job.getMainConfig().prebuiltBinaries = prebuilt
        b = builder.Builder(self.rmakeCfg, job)
        b.initializeBuild()
        for trv in job.iterTroves():
            if trv.getName().split(':')[0] in ['testcase']:
                assert(trv.isPrebuilt())
                assert(trv.prebuiltIsSourceMatch())
            else:
                assert(trv.isPrebuilt())
                assert(not trv.prebuiltIsSourceMatch())
        job = self.newJob(trv2)
        job.getMainConfig().prebuiltBinaries = prebuilt
        b = builder.Builder(self.rmakeCfg, job)
        b.initializeBuild()
        for trv in job.iterTroves():
            assert(trv.isPrebuilt())
            assert(not trv.prebuiltIsSourceMatch())
        binTrv5 = self.addCollection('simple=1.0-2-1', [':runtime'],
                             loadedReqs=[binTrv.getNameVersionFlavor()])
        prebuilt.append(binTrv5.getNameVersionFlavor())
        job.getMainConfig().prebuiltBinaries = prebuilt
        b = builder.Builder(self.rmakeCfg, job)
        b.initializeBuild()
        for trv in job.iterTroves():
            assert(trv.isPrebuilt())
            assert(not trv.prebuiltIsSourceMatch())
        job.getMainConfig().ignoreAllRebuildDeps = True
        b = builder.Builder(self.rmakeCfg, job)
        b.initializeBuild()
        for trv in job.iterTroves():
            assert(trv.isPrebuilt())

    def testPrebuiltGroups(self):
        """
        Groups should never be pre-built.

        @tests: RMK-903
        """
        self.addComponent('foo:runtime')
        groupSource = self.addComponent('group-foo:source=1.0-1',
            [('group-foo.recipe', groupRecipe)])
        groupTrove = self.addCollection('group-foo=1.0-1-1',
            ['foo:runtime'])

        job = self.newJob(groupSource)
        job.getMainConfig().prebuiltBinaries = [
            groupTrove.getNameVersionFlavor()]
        build = builder.Builder(self.rmakeCfg, job)
        build.initializeBuild()

        for buildTrove in job.iterTroves():
            self.failIf(buildTrove.isPrebuilt(), "Group trove is pre-built")

    def testBuildImages(self):
        rbuildServer = self.startMockRbuilder()
        oldSleep = time.sleep
        self.mock(time, 'sleep', lambda x: oldSleep(.1))
        self.addComponent('foo:run')
        trv = self.addCollection('group-foo', ['foo:run'])
        db = self.openRmakeDatabase()
        job = self.newJob()
        trv = self.newImageTrove(job.jobId, productName='product', imageType='imageType',
                                 imageOptions={},
                                 *trv.getNameVersionFlavor())
        trv.setConfig(self.buildCfg)
        job.addBuildTrove(trv)
        job.setBuildTroves([trv])
        b = builder.Builder(self.rmakeCfg, job)
        self.logFilter.add()
        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        try:
            b.build()
        except Exception:
            b.worker.stopAllCommands()
            raise
        log = db.getTroveBuildLog(1, job.troves.values()[0].getNameVersionFlavor(), 0)[1]
        expectedLog = '''\
0: Working: 51
0: Working: 101
0: Working: 151
0: Finished.
'''
        assert(expectedLog in log)

    def testBuildImagesMultinode(self):
        raise testhelp.SkipTestException()
        rbuildServer = self.startMockRbuilder()
        oldSleep = time.sleep
        self.mock(time, 'sleep', lambda x: oldSleep(.1))
        self.addComponent('foo:run')
        trv = self.addCollection('group-foo', ['foo:run'])
        rmakeClient = self.startRmakeServer(multinode=True)
        self.startNode()
        helper = self.getRmakeHelper(rmakeClient.uri)
        job = helper.createImageJob('project', [('group-foo', 'imageType', {})])
        jobId = helper.buildJob(job)
        helper.waitForJob(jobId)
        db = self.openRmakeDatabase()
        trove = job.troves.values()[0]
        nvfc = list(trove.getNameVersionFlavor()) + [trove.getContext()]
        log = db.getTroveBuildLog(1, nvfc, 0)[1]
        expectedLog = '''\
0: Working: 51
0: Working: 101
0: Working: 151
0: Finished.
'''
        assert(expectedLog in log)

    def testBuildImagesWithBuildName(self):
        raise testhelp.SkipTestException()
        rbuildServer = self.startMockRbuilder()
        oldSleep = time.sleep
        self.mock(time, 'sleep', lambda x: oldSleep(.1))
        self.addComponent('foo:run')
        trv = self.addCollection('group-foo', ['foo:run'])
        rmakeClient = self.startRmakeServer(multinode=True)
        self.startNode()
        helper = self.getRmakeHelper(rmakeClient.uri)
        job = helper.createImageJob('project', [
            ('group-foo', 'imageType', {}, 'Image Name'),
            ('group-foo', 'imageType', {}, 'Image Name'),
            ('group-foo', 'imageType', {}),
            ('group-foo', 'imageType', {})
        ])
        self.assertEquals(
            [x[3] for x in job.troves.keys()],
            ['Image_3', 'Image_2', 'Image_Name_(1)', 'Image_Name'])

        jobId = helper.buildJob(job)
        helper.waitForJob(jobId)
        db = self.openRmakeDatabase()
        expectedLog = '''\
0: Working: 51
0: Working: 101
0: Working: 151
0: Finished.
'''
        for trove in job.troves.values():
            nvfc = list(trove.getNameVersionFlavor()) + [trove.getContext()]
            log = db.getTroveBuildLog(1, nvfc, 0)[1]
            assert(expectedLog in log)



