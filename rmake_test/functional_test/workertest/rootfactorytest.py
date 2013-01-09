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

import copy
import os
import signal
import stat
import sys

from conary import conarycfg
from conary.deps import deps
from conary import trove
from conary import versions
from conary.repository import changeset, netclient
from conary import conaryclient

from rmake import errors
from rmake.build import buildcfg
from rmake.build import buildjob
from rmake.build import buildtrove
from rmake.worker.chroot import rootserver
from rmake.worker.chroot import rootfactory
from rmake.worker.chroot import rootmanager
from rmake.lib import logfile

from conary_test import rephelp
from rmake_test import rmakehelp

class ChrootTest(rmakehelp.RmakeHelper):

    def _createRoot(self, jobList, buildTrove, start=True, reuseRoots=False,
                    copyInConary=True):
        cfg = buildcfg.BuildConfiguration(False, conaryConfig=self.cfg,
                                          root=self.cfg.root, 
                                          serverConfig=self.rmakeCfg,
                                          strictMode=False)
        cfg.copyInConary = copyInConary
        cfg.defaultBuildReqs = []
        cfg.reuseRoots = reuseRoots
        if jobList and isinstance(jobList[0], trove.Trove):
            jobList = [ (x.getName(), (None, None),
                        (x.getVersion(), x.getFlavor()), False)
                        for x in jobList ]

        mgr = rootmanager.ChrootManager(self.rmakeCfg)
        factory = mgr.getRootFactory(cfg, jobList, [], [], buildTrove)
        self.captureOutput(factory.create)
        if start:
            client = factory.start()
        else:
            client = None
        return mgr, factory, cfg, client


    def testReuse(self):
        def _checkTroves(root, troveList):
            db = self.openDatabase(root)
            exists = set(db.iterAllTroves())
            assert(set(x.getNameVersionFlavor() for x in troveList) == exists)

        src = self.addComponent('foo:source', '1')
        buildTrove = self.newBuildTrove(1, *src.getNameVersionFlavor())
        self.rmakeCfg.chrootLimit = 1

        trv1 = self.addComponent('test1:runtime', '1', filePrimer=1)
        trv2 = self.addComponent('test2:runtime', '1', filePrimer=2)
        trv3 = self.addComponent('test3:runtime', '1', filePrimer=3)
        n,v,f = trv1.getNameVersionFlavor()
        factory = self._createRoot([trv1, trv2, trv3], buildTrove, start=False)[1]
        root = factory.getRoot()
        _checkTroves(root, [trv1, trv2, trv3])

        self._createRoot([trv1,trv2,trv3], buildTrove, start=False, reuseRoots=True)
        _checkTroves(root + '-1', [trv1, trv2, trv3])

        # update 2, erase 3
        trv2 = self.addComponent('test2:runtime', '2', filePrimer=2)
        self._createRoot([trv1,trv2], buildTrove, start=False, reuseRoots=True)
        _checkTroves(root, [trv1, trv2])

    def testChrootCache(self):
        if not hasattr(netclient.NetworkRepositoryClient, 'getChangeSetFingerprints'):
            raise testsuite.SkipTestException('conary too old for chroot cache functionality')
        chrootCache = self.workDir + '/chrootcache'
        self.rmakeCfg.configLine('chrootcache local %s/chrootcache' %self.workDir)
        src = self.addComponent('foo:source', '1')
        buildTrove = self.newBuildTrove(1, *src.getNameVersionFlavor())
        self.rmakeCfg.chrootLimit = 1

        trv1 = self.addComponent('test1:runtime', '1', filePrimer=1)
        trv2 = self.addComponent('test2:runtime', '1', filePrimer=2)
        trv3 = self.addComponent('test3:runtime', '1', filePrimer=3)
        self._createRoot([trv1, trv2, trv3], buildTrove, start=False)[1]
        # pre-test to make errors with the new hash in them
        expectedHash = 'db8d1e90e0de24619ee548fb54f2d64f36e5e0c9'
        expectedPath = '%s/%s.tar.gz' % (chrootCache, expectedHash)
        actualHash = os.listdir(chrootCache)[0].split('.')[0]
        self.failUnlessEqual(actualHash, expectedHash)
        # make sure the chroot was cached
        self.failUnless(os.path.exists(expectedPath))
        # make sure the chroot gets used
        def updateChangeSet(*args, **kw):
            self.fail('updateChangeSet should not have been called at all')
        # self.mock will automatically unmock when this test case finishes
        self.mock(conaryclient.ConaryClient, 'updateChangeSet', updateChangeSet)
        # uncomment to test the test
        # os.unlink(expectedPath)
        self._createRoot([trv1,trv2,trv3], buildTrove, start=False)

    def testHelperCommandline(self):
        src = self.addComponent('foo:source', '1')
        buildTrove = self.newBuildTrove(1, *src.getNameVersionFlavor())
        trv1 = self.addComponent('test1:runtime', '1', filePrimer=1)

        self.mock(os, '_exit', lambda code: None)
        self.mock(os, 'execv', lambda bin, cmdargs: args.extend(cmdargs))

        # Normal
        factory = self._createRoot([trv1], buildTrove, start=False)[1]
        factory.chroot.canChroot = lambda: True

        args = []
        factory.start(forkCommand=lambda: 0)
        socketPath = factory.socketPath[len(factory.getRoot()):]
        self.assertEquals(args[1:], [factory.getRoot(), socketPath])

        # With chroot caps
        self.rmakeCfg.configLine('chrootCaps True')
        factory = self._createRoot([trv1], buildTrove, start=False)[1]
        factory.chroot.canChroot = lambda: True

        args = []
        factory.start(forkCommand=lambda: 0)
        socketPath = factory.socketPath[len(factory.getRoot()):]
        self.assertEquals(args[1:], [factory.getRoot(), socketPath,
            '--chroot-caps'])

    def testChrootFactory(self):
        self.openRmakeRepository()
        repos = self.openRepository()

        self.addComponent('test1:source', '1.0', '',
                          [('test1.recipe', test1Recipe )])
        self.addComponent('test1:source', '2.0', '',
                          [('test1.recipe', test1Recipe.replace('1.0', '2.0'))])

        rootDir = self.rmakeCfg.getChrootDir() + '/testBuildReqs'
        self.makeSourceTrove('testBuildReqs',
             testBuildReqsRecipe % dict(rootDir=rootDir))

        troveTup = repos.findTrove(self.cfg.buildLabel, 
                                   ('testBuildReqs:source', None, None),
                                   None)[0]
        cookFlavor = deps.parseFlavor('readline,ssl,X')
        troveTup = (troveTup[0], troveTup[1], cookFlavor)

        db = self.openRmakeDatabase()
        job = self.newJob(troveTup)
        buildTrove = buildtrove.BuildTrove(job.jobId, *troveTup)
        buildTrove.setPublisher(job.getPublisher())

        cfg = buildcfg.BuildConfiguration(False, conaryConfig=self.cfg,
                                          root=self.cfg.root, 
                                          serverConfig=self.rmakeCfg)
        cfg.defaultBuildReqs = []

        trv1 = self.addComponent('test1:runtime', '1.0', '',
                                 [('/usr/bin/test1',
                                  rephelp.RegularFile(contents='#!/bin/sh', perms=0755))])
        trv2 = self.addCollection('test1', '1.0', [':runtime'])
        trv3 = self.addComponent('test2:runtime', '1.0', '',
                                 [('/usr/bin/test2',
                                   rephelp.RegularFile(contents='#!/bin/sh', perms=0755))])
        trv4 = self.addComponent('testunreadable:runtime', '1.0', '',
            [('/usr/untraverseable',
              rephelp.Directory(perms=0700)),
             ('/usr/symlink',
              rephelp.Symlink(target='/usr/untraverseable')),
             ('/usr/untraverseable/unreadable',
              rephelp.RegularFile(perms=0600))])

        mgr = rootmanager.ChrootManager(self.rmakeCfg)
        jobList = [ (x[0], (None, None), (x[1], x[2]), False) for x in 
                    (trv1.getNameVersionFlavor(), trv2.getNameVersionFlavor(),
                     trv3.getNameVersionFlavor(), trv4.getNameVersionFlavor())]

        logFile = logfile.LogFile(self.workDir + '/chrootlog')
        logFile.redirectOutput()
        factory = mgr.getRootFactory(cfg, jobList, [], [], buildTrove)
        factory.create()
        chrootClient = factory.start()
        try:
            logPath = chrootClient.buildTrove(cfg,
                                              cfg.getTargetLabel(troveTup[1]),
                                              *troveTup)
            result = chrootClient.checkResults(wait=20, *troveTup)
            logFile.restoreOutput()
            assert(result)
            assert result.isBuildSuccess(), repr(result.getFailureReason())
            untraverseable = mgr.baseDir + '/testBuildReqs/usr/untraverseable'
            self.assertEquals(stat.S_IMODE(os.stat(untraverseable).st_mode), 0705)
            unreadable = untraverseable + '/unreadable'
            self.assertEquals(stat.S_IMODE(os.stat(unreadable).st_mode), 0604)
            cs = changeset.ChangeSetFromFile(result.getChangeSetFile())
            trvCs = [ x for x in cs.iterNewTroveList()
                     if x.getName() == 'testBuildReqs:runtime'][0]
            trv = trove.Trove(trvCs)
            files = [ x[1] for x in trv.iterFileList()]
            # make sure the loadInstalled picked the recipe that 
            # matches the installed package.
            assert('/foo/1.0' in files)
        finally:
            chrootClient.stop()

    def testPerlReqs(self):
        self.openRmakeRepository()
        repos = self.openRepository()

        trvname = "perl-dummy"

        perl = self.addComponent('perl:lib', provides='perl: CGI perl: strict')
        trv = self.makeSourceTrove(trvname, testPerlRecipe)

        troveTup = repos.findTrove(self.cfg.buildLabel, 
                                   (trvname + ':source', None, None),
                                   None)[0]

        cookFlavor = deps.parseFlavor('readline,ssl,X')
        troveTup = (troveTup[0], troveTup[1], cookFlavor)

        db = self.openRmakeDatabase()
        job = self.newJob(troveTup)
        buildTrove = buildtrove.BuildTrove(job.jobId, *troveTup)
        buildTrove.setPublisher(job.getPublisher())

        logFile = logfile.LogFile(self.workDir + '/chrootlog')
        logFile.redirectOutput()
        mgr, factory, cfg, client = self._createRoot([perl], buildTrove, 
                                                     start=True)
        logPath = client.buildTrove(cfg, cfg.getTargetLabel(troveTup[1]),
                                          *troveTup)
        result = client.checkResults(wait=20, *troveTup)
        client.stop()
        logFile.restoreOutput()

        assert(result)
        assert(result.isBuildSuccess())
        cs = changeset.ChangeSetFromFile(result.getChangeSetFile())

        trvHash = {}
        for trv in cs.iterNewTroveList():
            trvHash[trv.getName()] = trv

        # this also checks to make sure build logging is turned on
        if len(trvHash) < 3:
            raise RuntimeError('logging turned off!')
        self.failUnless(trvname in trvHash)
        self.failUnless(trvname + ':data' in trvHash)
        self.failUnless(trvname + ':debuginfo' in trvHash)

        trv = trvHash[trvname + ':data']

        dps = [ (d[0].tagName, d[1].getName()) for d in
            trv.getRequires().iterDeps() ]

        dps.sort()
        self.failUnlessEqual(dps,
                             [('perl', ('CGI', )), ('perl', ('strict',))])


    def testPerlReqsScriptCopy(self):
        self.openRmakeRepository()
        repos = self.openRepository()

        trvname = "perl-dummy"

        perl = self.addComponent('perl:lib', provides='perl: CGI perl: strict')
        trv = self.makeSourceTrove(trvname, testPerlRecipe)

        troveTup = repos.findTrove(self.cfg.buildLabel, 
                                   (trvname + ':source', None, None),
                                   None)[0]

        cookFlavor = deps.parseFlavor('readline,ssl,X')
        troveTup = (troveTup[0], troveTup[1], cookFlavor)

        db = self.openRmakeDatabase()
        job = self.newJob(troveTup)
        buildTrove = buildtrove.BuildTrove(job.jobId, *troveTup)
        buildTrove.setPublisher(job.getPublisher())

        logFile = logfile.LogFile(self.workDir + '/chrootlog')
        logFile.redirectOutput()
        mgr, factory, cfg, _ = self._createRoot([perl], buildTrove, 
                                                start=False)
        logFile.restoreOutput()

        # Is the scripts directory copied?
        conaryDir = os.path.dirname(sys.modules['conary'].__file__)
        scriptsDir = os.path.realpath(os.path.join(conaryDir, '../scripts'))
        if not os.path.exists(scriptsDir):
            raise testsuite.SkipTestException('Cant test copy in conary when scripts dir doesnt exist')

        rootfact = factory.chroot
        self.failUnless(scriptsDir in [ x[0] for x in rootfact.dirsToCopy ])

        perlreqs = os.path.join(scriptsDir, 'perlreqs.pl')
        self.failUnless(perlreqs in [ x[0] for x in rootfact.filesToCopy ])

    def testInstallX86OnX86_64(self):
        trv = self.addComponent('foo:runtime', '1', 'is:x86 x86_64')
        self.addComponent('foo:runtime', '1', 'ssl,readline is:x86_64')
        self.cfg.flavor = [deps.parseFlavor('ssl, readline is:x86 x86_64')]
        src = self.addComponent('foo:source', '1')
        buildTrove = self.newBuildTrove(1, *src.getNameVersionFlavor())
        mgr, factory, cfg, client = self._createRoot([trv], buildTrove,
                                                     start=False)
        db = self.openDatabase(factory.root)
        assert(db.iterAllTroves().next() == trv.getNameVersionFlavor())

    def testBadConaryInRoot(self):
        trv = self.addComponent('conary:python', '1.0.40-1-1')
        src = self.addComponent('foo:source', '1')
        buildTrove = self.newBuildTrove(1, *src.getNameVersionFlavor())
        try:
            mgr, factory, cfg, client = self._createRoot([trv], buildTrove,
                                                         start=False,
                                                         copyInConary=False)
            assert 0, 'should have asserted'
        except errors.RmakeError, e:
            self.assertEquals(str(e),
                        'rMake requires conary version 1.1.19 or greater - tried to install version 1.0.40 in chroot')

        trv = self.addComponent('conary:python', '2.2-1-1')
        mgr, factory, cfg, client = self._createRoot([trv], buildTrove,
                                                     start=False,
                                                     copyInConary=False)


    def testConaryVersionLimits(self):
        # Don't allow chroots to be created w/ a conary version that is too old.
        def _checkTroves(root, troveList):
            db = self.openDatabase(root)
            exists = set(db.iterAllTroves())
            assert(set(x.getNameVersionFlavor() for x in troveList) == exists)

        src = self.addComponent('foo:source', '1')
        buildTrove = self.newBuildTrove(1, *src.getNameVersionFlavor())
        self.rmakeCfg.chrootLimit = 1

        trv1 = self.addComponent('conary:python', '1.1.14', filePrimer=1)
        try:
            self._createRoot([trv1], buildTrove, start=False,
                             copyInConary=False)
            assert(0)
        except errors.RmakeError, e:
            self.assertEquals(str(e),
                              'rMake requires conary version 1.1.19 or greater - tried to install version 1.1.14 in chroot')


test1Recipe = '''
class TestRecipe1(PackageRecipe):
    name = 'test1'
    version = '1.0'
    clearBuildReqs()

    if Use.ssl:
        pass

    def setup(r):
        r.Create('/foo/bar', contents='1')
        if Use.readline:
            pass
'''

testBuildReqsRecipe = '''
loadInstalled('test1')
class TestBuildReqs(PackageRecipe):
    name = 'testBuildReqs'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        r.Create('/foo/bar', contents='1')
        r.Create('/foo/%%s' %% TestRecipe1.version, contents='1')
        r.Run('sh %(rootDir)s/usr/bin/test1')
        r.Run('sh %(rootDir)s/usr/bin/test2')
'''

testPerlRecipe = '''
class PerlDummy(PackageRecipe):
    name = 'perl-dummy'
    version = '0.1'

    clearBuildReqs()
    buildRequires = [ 'perl:lib', ]

    def setup(r):
        contents =("#!/usr/bin/perl -w\\n"
                   "use strict;\\n"
                   "use CGI;\\n")
        r.Create("%(datadir)s/perl-dummy/foo.pl", contents=contents)
'''
