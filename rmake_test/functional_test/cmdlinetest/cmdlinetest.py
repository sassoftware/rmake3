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
Unit tests for the rmake command line.  Tests that flags are being passed
appropriate from the command line messages, ensure usage is being popped
up when it is needed, etc, etc. 

This file shouldn't be used to test actual functionality.  Other files
in this directory can be used to do basic tests of command -> functionality
tests, esp. for error cases in the command line, but full functionality
tests should be done at the client level.
"""

import os
import socket
import sys

from testutils import mock

from rmake_test import rmakehelp

from conary.deps import deps

from rmake.build import buildjob
from rmake.cmdline import command, main, helper
from rmake.server import client
from rmake.server import daemon
from rmake import errors

class CmdLineTest(rmakehelp.RmakeHelper):
    def checkRmake(self, cmd, fn, expectedArgs, cfgValues={},
                  returnVal=None, ignoreKeywords=False, **expectedKw):
        cmd += ' --skip-default-config --no-plugins'
        configPath = '%s/etc/rmakerc' % self.rootDir
        if os.path.exists(configPath):
            cmd += ' --build-config-file=%s' % configPath

        oldFn = client.rMakeClient.addRepositoryInfo
        try:
            def addRepositoryInfo(self, buildConfig):
                buildConfig.reposName = 'localhost'
            client.rMakeClient.addRepositoryInfo = addRepositoryInfo
            return self.checkCommand(main.main, 'rmake ' + cmd, fn,
                                     expectedArgs, cfgValues, returnVal,
                                     ignoreKeywords, **expectedKw)
        finally:
            client.rMakeClient.addRepositoryInfo = oldFn

    def checkRmakeServer(self, cmd, fn, expectedArgs, cfgValues={},
                        returnVal=None, ignoreKeywords=False, **expectedKw):
        cmd += ' --skip-default-config --no-plugins'
        configPath = '%s/etc/serverrc' % self.rootDir
        if os.path.exists(configPath):
            cmd += ' --server-config-file=%s' % configPath
        return self.checkCommand(daemon.main, 'rmake-server ' + cmd, fn,
                                 expectedArgs, cfgValues, returnVal,
                                 ignoreKeywords, **expectedKw)


    def testBuild(self):
        self.logCheck2(
            "error: 'build' missing 1 command parameter(s): troveSpec",
                       self.checkRmake, 'build',
                       'rmake.cmdline.command.BuildCommand.usage', [None])

        mock.mock(helper.rMakeHelper, 'createBuildJob')
        mock.mock(helper.rMakeHelper, 'buildJob')
        mock.mock(helper.rMakeHelper, 'displayJob')
        self.checkRmake('build foobar bam=1.0 --no-watch'
                        ' --label=localhost@rpl:1 --host=localhost'
                        ' --match==localhost@rpl:1',
                         'rmake.cmdline.helper.rMakeHelper.createBuildJob',
                          [None, ['foobar',
                                  'bam=1.0']], limitToHosts=['localhost'], 
                                  limitToLabels=['localhost@rpl:1'],
                                  recurseGroups=False,
                                  matchSpecs=['=localhost@rpl:1'],
                                  rebuild=False)

        self.checkRmake('build --recurse foobar bam=1.0 --no-watch --binary-search --quiet --info',
                        'rmake.cmdline.helper.rMakeHelper.createBuildJob',
                        [None, ['foobar',
                                'bam=1.0']], limitToHosts=[], limitToLabels=[],
                                             recurseGroups=1,
                                             matchSpecs=[],
                                             rebuild=False)


        callback = checkBuildConfig(cleanAfterCook=False,
                                    macros={'foo': 'bar',
                                            'bam': 'baz'})

        self.checkRmake('build --recurse foobar --no-clean --prep --macro="foo bar"'
                        ' --macro="bam baz" --no-watch',
                        'rmake.cmdline.helper.rMakeHelper.buildJob',
                        [None, None],
                         checkCallback=callback, quiet=False)

        callback = checkBuildConfig(cleanAfterCook=True, macros={})
        self.checkRmake('build --recurse foobar --prep'
                        ' --no-watch',
                        'rmake.cmdline.helper.rMakeHelper.buildJob',
                        [None, None],
                        checkCallback=callback, quiet=False)


        callback = checkBuildConfig(cleanAfterCook=True, macros={})
        self.checkRmake('build --recurse foobar --no-watch --match foo@bar'
                        ' --match bar@foo',
                        'rmake.cmdline.helper.rMakeHelper.createBuildJob',
                        [None, ['foobar']], limitToHosts=[],
                                            limitToLabels=[],
                                            recurseGroups=2,
                                            matchSpecs=['foo@bar', 'bar@foo'],
                                            checkCallback=callback,
                                            rebuild=False)

        ppcFlavor = deps.parseFlavor('is:ppc')
        def _checkFlavor(client, *args, **kw):
            assert(client.buildConfig.buildFlavor.satisfies(ppcFlavor))

        self.checkRmake('build foobar bam=1.0 --flavor=is:ppc --no-watch',
                        'rmake.cmdline.helper.rMakeHelper.createBuildJob',
                        [None, None], limitToHosts=[], limitToLabels=[],
                        recurseGroups=False, matchSpecs=[],
                        checkCallback=_checkFlavor,
                        rebuild=False)

        self.checkRmake('build foobar --poll',
                        'rmake.cmdline.command.BuildCommand.runCommand',
                        [None, None, None, {'poll' : True},
                         ['rmake', 'build', 'foobar']])

        self.checkRmake('build foobar --commit --message="Foobar"',
                        'rmake.cmdline.command.BuildCommand.runCommand',
                        [None, None, None, {'commit' : True, 
                        'message' : 'Foobar'}, 
                         ['rmake', 'build', 'foobar']])

        def _checkFlavor2(client, *args, **kw):
            flavors = client.buildConfig.flavor
            foo = deps.parseFlavor('foo')
            x86_64 = deps.parseFlavor('is:x86_64')
            x86_and_x86_64 = deps.parseFlavor('is:x86 x86_64')
            assert(len(flavors) == 2)
            assert(flavors[0].satisfies(foo))
            assert(flavors[0].satisfies(x86_64))
            assert(not flavors[0].satisfies(x86_and_x86_64))
            assert(flavors[1].satisfies(foo))
            assert(flavors[1].satisfies(x86_and_x86_64))

        os.mkdir('%s/etc' % self.rootDir)
        f = open('%s/etc/rmakerc' % self.rootDir, 'w')
        f.write('flavor use: is:x86_64\n')
        f.write('flavor use: is:x86 x86_64\n')
        f.close()

        self.checkRmake('build foobar bam=1.0 --flavor foo --no-watch',
                         'rmake.cmdline.helper.rMakeHelper.createBuildJob',
                          [None, ['foobar',
                                  'bam=1.0']], limitToHosts=[], 
                                  limitToLabels=[],
                                  recurseGroups=False,
                                  matchSpecs=[],
                                  checkCallback=_checkFlavor2,
                                  rebuild=False)

    def testRebuild(self):
        self.logCheck2(
            "error: 'rebuild' missing 1 command parameter(s): troveSpec",
                       self.checkRmake, 'rebuild',
                   'rmake.cmdline.command.RebuildCommand.usage', [None])

        mock.mock(helper.rMakeHelper, 'createBuildJob')
        mock.mock(helper.rMakeHelper, 'buildJob')
        mock.mock(helper.rMakeHelper, 'displayJob')

        callback = checkBuildConfig(ignoreAllRebuildDeps=True)
        self.checkRmake('rebuild foo --ignore-rebuild-deps --no-watch',
                        'rmake.cmdline.helper.rMakeHelper.buildJob',
                        [None, None],
                         checkCallback=callback, quiet=False)
        callback = checkBuildConfig(ignoreExternalRebuildDeps=True)
        self.checkRmake('rebuild foo --ignore-external-rebuild-deps --no-watch',
                        'rmake.cmdline.helper.rMakeHelper.buildJob',
                        [None, None],
                         checkCallback=callback, quiet=False)




    def testRestart(self):
        mock.mock(helper.rMakeHelper, 'createRestartJob')
        helper.rMakeHelper.createRestartJob._mock.setReturn(
                                                        buildjob.BuildJob(), 
                                                        _mockAll=True)
        mock.mock(helper.rMakeHelper, 'buildJob')
        mock.mock(helper.rMakeHelper, 'displayJob')
        self.checkRmake('restart 1 --no-watch --info --clear-build-list --clear-prebuilt-list',
                        'rmake.cmdline.helper.rMakeHelper.createRestartJob',
                         [None, 1, []], updateSpecs=[], excludeSpecs=[],
                         updateConfigKeys=None,
                         clearBuildList=True, clearPrebuiltList=True)
        self.checkRmake('restart 1 tmpwatch --no-watch',
                        'rmake.cmdline.helper.rMakeHelper.createRestartJob',
                         [None, 1, ['tmpwatch']],
                         updateSpecs=[], excludeSpecs=[], updateConfigKeys=None,
                         clearBuildList=False, clearPrebuiltList=False)
        self.checkRmake('restart 1 --no-watch --update foo-* --update -foo-bar',
                        'rmake.cmdline.helper.rMakeHelper.createRestartJob',
                         [None, 1, []], updateSpecs=['foo-*', '-foo-bar'],
                         excludeSpecs=[], updateConfigKeys=None,
                         clearBuildList=False, clearPrebuiltList=False)
        self.checkRmake('restart 1 --no-watch --no-update',
                        'rmake.cmdline.helper.rMakeHelper.createRestartJob',
                         [None, 1, []], updateSpecs=['-*'],
                         excludeSpecs=[], updateConfigKeys=None,
                         clearBuildList=False, clearPrebuiltList=False)
        self.checkRmake('restart 1 --no-watch --exclude=foo --update-config=installLabelPath',
                        'rmake.cmdline.helper.rMakeHelper.createRestartJob',
                         [None, 1, []], updateSpecs=[],
                         excludeSpecs=['foo'], 
                         updateConfigKeys=['installLabelPath'],
                         clearBuildList=False, clearPrebuiltList=False)
        self.checkRmake('restart 1 --no-watch --exclude=foo'
                        ' --update-config=all',
                        'rmake.cmdline.helper.rMakeHelper.createRestartJob',
                         [None, 1, []], updateSpecs=[],
                         excludeSpecs=['foo'], updateConfigKeys=['all'], 
                         clearBuildList=False, clearPrebuiltList=False)
        self.checkRmake('restart 1 --no-watch --to-file=foo'
                        ' --update-config=all',
                        'rmake.build.buildjob.BuildJob.writeToFile',
                         [None, 'foo'], sanitize=True)
        callback = checkBuildConfig(ignoreExternalRebuildDeps=True)
        self.checkRmake('restart 1 --no-watch --ignore-external-rebuild-deps'
                        ' --update-config=all',
                        'rmake.cmdline.helper.rMakeHelper.buildJob',
                         [None, None], quiet=False, checkCallback=callback)
        callback = checkBuildConfig(ignoreAllRebuildDeps=True)
        self.checkRmake('restart 1 --no-watch --ignore-rebuild-deps'
                        ' --update-config=all',
                        'rmake.cmdline.helper.rMakeHelper.buildJob',
                         [None, None], quiet=False, checkCallback=callback)

    def testConfigFiles(self):
        def checkBuildConfig(**cfgDict):
            def _checkBuildConfig(self, client, *args, **kw):
                for key, value in cfgDict.items():
                    if key == 'installLabelPath':
                        assert([ str(x) for x in client.buildConfig[key]] == value)
                    elif key == 'user':
                        checkValue = set([' '.join(y for y in x if y is not None) 
                                          for x in client.buildConfig[key]])
                        assert(checkValue == set(value))
                    else:
                        assert(str(client.buildConfig[key]) == value)
            return _checkBuildConfig

        buildConfigPath = self.workDir + '/foo'
        open(buildConfigPath, 'w').write('buildLabel foo.rpath.org@rpl:devel\nstrictMode True\n')

        conaryConfigPath = self.workDir + '/conary'
        open(conaryConfigPath, 'w').write('buildLabel foo.rpath.org@rpl:devel\n')

        callBackFn = checkBuildConfig(buildLabel='foo.rpath.org@rpl:devel',
                                      strictMode='True')
        self.checkRmake('build foobar --build-config-file %s' % buildConfigPath,
                        'rmake.cmdline.command.BuildCommand.runCommand',
                        [None, None, None, None, ['rmake', 'build', 'foobar']],
                        checkCallback=callBackFn)

        callBackFn = checkBuildConfig(buildLabel='foo.rpath.org@rpl:devel')
        self.checkRmake(
                     'build foobar --conary-config-file %s' % conaryConfigPath,
                     'rmake.cmdline.command.BuildCommand.runCommand',
                     [None, None, None, None, ['rmake', 'build', 'foobar']],
                     checkCallback=callBackFn)


        # test: write something in conaryrc, something in context,
        # something in rmakerc, something in rmakerc context, and something
        # on command line with --config.  Items should win in that order.
        open(conaryConfigPath, 'w').write(
                'installLabelPath conaryconfig@rpl:devel\n'
                'buildLabel conaryconfig@rpl:devel\n'
                'user foo.rpath.org conaryConfig\n'
                'showLabels True\n'
                '[foo]\n'
                'installLabelPath conarycontext@rpl:devel\n'
                'buildLabel conarycontext@rpl:devel\n'
                'user foo.rpath.org conarycontext\n')
        open(buildConfigPath, 'w').write(
                'buildLabel rmakerc@rpl:devel\n'
                'user foo.rpath.org rmakerc\n'
                'strictMode False\n'
                '[foo]\n'
                'user foo.rpath.org rmakecontext\n')
        callBackFn = checkBuildConfig(buildLabel='conarycontext@rpl:devel',
                                   user=set(['foo.rpath.org rmakecontext']),
                                   installLabelPath=['conarycontext@rpl:devel'],
                                   showLabels='True')
        self.checkRmake(
                  'build foobar --conary-config-file %s'
                  ' --build-config-file %s --context foo' % (conaryConfigPath,
                                                  buildConfigPath),
                     'rmake.cmdline.command.BuildCommand.runCommand',
                     [None, None, None, None, ['rmake', 'build', 'foobar']],
                     checkCallback=callBackFn)


    def testChangeSet(self):
        self.checkRmake('changeset 111 foo.ccs',
                         'rmake.cmdline.helper.rMakeHelper.createChangeSetFile',
                          [None, 111, 'foo.ccs', []] )
        self.logCheck2(
            "error: 'changeset' missing 2 command parameter(s): jobId, path",
                       self.checkRmake, 'changeset',
                       'rmake.cmdline.command.ChangeSetCommand.usage', [None])
        self.logCheck2(
            "error: 'changeset' missing 1 command parameter(s): path",
                       self.checkRmake, 'changeset 11',
                       'rmake.cmdline.command.ChangeSetCommand.usage', [None])
        self.checkRmake('changeset 111 tmpwatch foo.ccs', 
                         'rmake.cmdline.helper.rMakeHelper.createChangeSetFile',
                          [None, 111, 'foo.ccs', ['tmpwatch']] )

    def testCommit(self):
        self.checkRmake('commit 7 8 --message "Foo"', 
                         'rmake.cmdline.helper.rMakeHelper.commitJobs',
                          [None, [7, 8], ], commitOutdatedSources=False,
                          waitForJob=True, commitWithFailures=True,
                          sourceOnly=False, message="Foo", excludeSpecs=None,
                          writeToFile=None)
        self.checkRmake('ci 7 8 -m "Foo" --to-file /foo',
                         'rmake.cmdline.helper.rMakeHelper.commitJobs',
                          [None, [7, 8], ], commitOutdatedSources=False,
                          waitForJob=True, commitWithFailures=True,
                          sourceOnly=False, message="Foo",
                          excludeSpecs=None, writeToFile='/foo')

        self.checkRmake('commit 7 --commit-outdated-sources --source-only --exclude tmpwatch', 
                         'rmake.cmdline.helper.rMakeHelper.commitJobs',
                          [None, [7], ], commitOutdatedSources=True,
                          waitForJob=True, commitWithFailures=True,
                          sourceOnly=True, message=None,
                          excludeSpecs=['tmpwatch'], writeToFile=None)
        self.logCheck2("error: 'commit' missing 1 command parameter(s): jobId",
                       self.checkRmake, 'commit',
                       'rmake.cmdline.command.CommitCommand.usage', [None])
        self.logCheck2('error: Not a valid jobId or UUID: foo.ccs',
                       self.checkRmake, 'commit 11 foo.ccs extra',
                       None, [None], returnVal=1)

    def testConfig(self):
        self.checkRmake('config --show-passwords',
                        'rmake.cmdline.helper.rMakeHelper.displayConfig',
                        [None], hidePasswords=False, prettyPrint=None)

    def testLoad(self):
        mock.mock(helper.rMakeHelper, 'buildJob')
        self.checkRmake('load foo.ccs --no-watch',
                        'rmake.cmdline.helper.rMakeHelper.loadJobFromFile',
                        [None, 'foo.ccs'])
        args, kw = helper.rMakeHelper.buildJob._mock.popCall()

    def testDelete(self):
        self.checkRmake('delete 7-9,100 101',
                         'rmake.cmdline.helper.rMakeHelper.deleteJobs',
                          [None, [7,8,9,100,101]] )
        self.logCheck2("error: 'delete' missing 1 command parameter(s): jobId",
                       self.checkRmake, 'delete',
                       'rmake.cmdline.command.DeleteCommand.usage', [None])

    def testDelete(self):
        self.checkRmake('delete 7-9,100 101',
                         'rmake.cmdline.helper.rMakeHelper.deleteJobs',
                          [None, [7,8,9,100,101]] )
        self.logCheck2("error: 'delete' missing 1 command parameter(s): jobId",
                       self.checkRmake, 'delete',
                       'rmake.cmdline.command.DeleteCommand.usage', [None])

    def testHelp(self):
        self.checkRmake('help build',
                        'rmake.cmdline.command.BuildCommand.usage',
                        [None])
        self.checkRmake('help',
                        'rmake.cmdline.main.RmakeMain.usage',
                        [None], ignoreKeywords=True)



    def testQuery(self):
        self.checkRmake('q', 'rmake.cmdline.query.displayJobInfo',
                        [None, None, []],
                        displayDetails=False, displayTroves=False,
                        ignoreKeywords=True,
                        showLabels=False, showFullVersions=False, 
                        showFullFlavors=False, showLogs=False, 
                        showBuildLogs=False, jobLimit=None, activeOnly=False)
        self.checkRmake('q 111', 'rmake.cmdline.query.displayJobInfo',
                        [None, 111, []],
                        displayDetails=False, displayTroves=False,
                        ignoreKeywords=True,
                        showLabels=False, showFullVersions=False, 
                        showFullFlavors=False, showLogs=False, showBuildLogs=False, jobLimit=None, activeOnly=False)
        self.checkRmake('q 111 --troves --full-versions --flavors --all', 
                        'rmake.cmdline.query.displayJobInfo',
                        [None, 111, []],
                        displayDetails=False, displayTroves=True,
                        ignoreKeywords=True,
                        showFullFlavors=True, showFullVersions=True,
                        jobLimit=None, activeOnly=False)
        self.checkRmake('q 111 --info --labels --active',
                        'rmake.cmdline.query.displayJobInfo',
                        [None, 111, []],
                        displayDetails=True, displayTroves=False,
                        ignoreKeywords=True,
                        showLabels=True, activeOnly=True)

    def testWatch(self):
        self.checkRmake('watch 6111 --quiet', 
                         'rmake.cmdline.helper.rMakeHelper.watch', 
                          [None, 6111], showBuildLogs=False, 
                          showTroveLogs=False, commit=False)
        self.checkRmake('poll 6111',
                         'rmake.cmdline.helper.rMakeHelper.watch', 
                          [None, 6111], showBuildLogs=True,
                          showTroveLogs=True, commit=False)
        self.logCheck2("error: 'poll' missing 1 command parameter(s): jobId",
                       self.checkRmake, 'poll',
                       'rmake.cmdline.command.PollCommand.usage', [None])
        self.logCheck2("error: 'watch' takes 1 arguments, received 2",
                       self.checkRmake, 'watch 32 extra',
                       'rmake.cmdline.command.PollCommand.usage', [None])
        self.checkRmake('poll 6111 --commit',
                         'rmake.cmdline.helper.rMakeHelper.watch',
                          [None, 6111], showBuildLogs=True,
                          showTroveLogs=True, commit=True)

    def testStop(self):
        self.checkRmake('stop 32',
                        'rmake.cmdline.helper.rMakeHelper.stopJob', [None, 32])
        self.logFilter.add()
        self.logCheck2("error: 'stop' takes 1 arguments, received 2",
                       self.checkRmake, 'stop 32 extra',
                       'rmake.cmdline.command.StopCommand.usage', [None])
        self.logCheck2("error: 'stop' missing 1 command parameter(s): jobId",
                       self.checkRmake, 'stop',
                       'rmake.cmdline.command.StopCommand.usage', [None])

    def testListCommand(self):
        self.checkRmake('list chroots',
                        'rmake.cmdline.query.listChroots', [None, None],
                        allChroots=True)
        self.checkRmake('list chroots --active',
                        'rmake.cmdline.query.listChroots', [None, None],
                        allChroots=False)
        self.logFilter.add()
        self.logCheck2('error: No such list command foo', 
                       self.checkRmake, 'list foo',
                        'rmake.cmdline.command.ListCommand.usage', [None]) 

    def testChrootCommand(self):
        self.checkRmake('chroot 1 foo',
                        'rmake.cmdline.helper.rMakeHelper.startChrootSession', 
                         [None, '1', 'foo', ['/bin/bash', '-l']],
                         superUser = False, chrootHost=None, chrootPath=None)
        self.checkRmake('chroot 1 foo --super',
                        'rmake.cmdline.helper.rMakeHelper.startChrootSession', 
                         [None, '1', 'foo', ['/bin/bash', '-l']],
                         superUser = True, chrootHost=None, chrootPath=None)
        self.checkRmake('chroot 1 foo --super --path foo',
                        'rmake.cmdline.helper.rMakeHelper.startChrootSession', 
                         [None, '1', 'foo', ['/bin/bash', '-l']],
                         superUser = True, chrootHost='_local_', 
                         chrootPath='foo')

        self.logCheck2(
                "error: 'chroot' missing 1 command parameter(s): jobId",
                self.checkRmake, 'chroot',
                'rmake.cmdline.command.ChrootCommand.usage', [None])
        self.logCheck2("error: 'chroot' takes 1-2 arguments, received 3",
                       self.checkRmake, 'chroot foo bar extra',
                       'rmake.cmdline.command.ChrootCommand.usage', [None])

    def testArchiveCommand(self):
        self.checkRmake('archive foo',
                        'rmake.cmdline.helper.rMakeHelper.archiveChroot', 
                         [None, '_local_', 'foo', 'foo'])
        self.checkRmake('archive foo bar',
                        'rmake.cmdline.helper.rMakeHelper.archiveChroot', 
                         [None, '_local_', 'foo', 'bar'])

    def testCleanCommand(self):
        self.checkRmake('clean foo',
                        'rmake.cmdline.helper.rMakeHelper.deleteChroot',
                         [None, '_local_', 'foo'])
        self.logCheck2("error: 'clean' takes 1 arguments, received 2",
                       self.checkRmake, 'clean foo extra',
                       'rmake.cmdline.command.CleanCommand.usage', [None])
        self.logCheck2(
                "error: 'clean' missing 1 command parameter(s): chrootPath",
                self.checkRmake, 'clean',
                'rmake.cmdline.command.CleanCommand.usage', [None])

    def testNewPkgCommand(self):
        self.checkRmake('newpkg foo',
                        'conary.checkin.newTrove',
                        [ None, None, 'foo'], ignoreKeywords=True)

    def testContextCommand(self):
        self.checkRmake('context',
                        'conary.checkin.setContext', 
                        [ None, None ],
                        ask = False, repos = None)

    def testCheckoutCommand(self):
        self.checkRmake('checkout foo',
                        'conary.checkin.checkout',
                        [ None, None, None, ['foo'], None], ignoreKeywords=True)

    def testUsage(self):
        self.checkRmake('', 'rmake.cmdline.main.RmakeMain.usage', [None])

    def testErrors(self):
        params = ['--skip-default-config', '--no-plugins']
        oldFn = client.rMakeClient.addRepositoryInfo
        try:
            client.rMakeClient.addRepositoryInfo = lambda *a, **kw: None
            try:
                main.RmakeMain().main(['rmake', 'query', 'foo'] + params)
            except errors.ParseError, err:
                assert(str(err) == 'Not a valid jobId or UUID: foo')
            else:
                assert(0)
            try:
                main.RmakeMain().main(['rmake', 'build', 'foo', 
                                       '--flavor', '!flav*'] + params)
            except errors.ParseError, err:
                assert(str(err) == "Invalid flavor: '!flav*'")
            else:
                assert(0)
        finally:
            client.rMakeClient.addRepositoryInfo = oldFn

    def testContextConfigFiles(self):
        def checkBuildConfig(**cfgDict):
            def _checkBuildConfig(self, client, *args, **kw):
                for key, value in cfgDict.items():
                    assert(str(client.buildConfig[key]) == value)
            return _checkBuildConfig

        buildConfigPath = self.workDir + '/foo'
        open(buildConfigPath, 'w').write('''\
[foo]
buildLabel foo.rpath.org@rpl:devel
strictMode True
''')

        conaryConfigPath = self.workDir + '/conary'
        open(conaryConfigPath, 'w').write('''
[foo]
buildLabel conaryconfig@rpl:devel
installLabelPath foo.rpath.org@rpl:devel
''')

        callBackFn = checkBuildConfig(buildLabel='foo.rpath.org@rpl:devel',
          installLabelPath="CfgLabelList([Label('foo.rpath.org@rpl:devel')])",
          strictMode='True')
        self.checkRmake('build foobar --context foo'
                        ' --build-config-file %s'
                        ' --conary-config-file %s' % (buildConfigPath,
                                                      conaryConfigPath),
                        'rmake.cmdline.command.BuildCommand.runCommand',
                        [None, None, None, None, ['rmake', 'build', 'foobar']],
                        checkCallback=callBackFn)

    def testContextOverride(self):
        def checkBuildConfig(**cfgDict):
            def _checkBuildConfig(self, client, *args, **kw):
                for key, value in cfgDict.items():
                    value = eval(value)
                    assert(client.buildConfig[key] == value)
            return _checkBuildConfig
        buildConfigPath = self.workDir + '/foo'
        open(buildConfigPath, 'w').write('''\
resolveTroves group-dist
[foo]
resolveTroves []
''')
        callBackFn = checkBuildConfig(
                            resolveTroves="[[('group-foo', None, None)]]")
        self.checkRmake('build foobar --context foo'
                        ' --build-config-file %s'
                        ' --config "resolveTroves group-foo"' \
                                % (buildConfigPath),
                        'rmake.cmdline.command.BuildCommand.runCommand',
                        [None, None, None, None, ['rmake', 'build', 'foobar']],
                        checkCallback=callBackFn)








    def testRmakeServerHelp(self):
        self.checkRmakeServer('help start',
                              'conary.command.HelpCommand.runCommand',
                              [None, None, {},
                               ['rmake-server', 'help', 'start']])

def checkBuildConfig(**cfgDict):
    def _checkBuildConfig(client, *args, **kw):
        for key, value in cfgDict.items():
            assert(client.buildConfig[key] == value)
    return _checkBuildConfig
