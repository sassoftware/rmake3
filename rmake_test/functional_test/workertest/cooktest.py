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


import sys
import time

from rmake_test import rmakehelp

from conary.deps import deps
from conary.repository import changeset
from conary import versions

from rmake.lib import logger
from rmake.worker.chroot import cook

class CookTest(rmakehelp.RmakeHelper):

    def _wait(self, buildInfo):
        for i in range(10000):
            result = cook.getResults(*buildInfo)
            if result:
                return result
            time.sleep(.1)

    def testCook(self):
        repos = self.openRepository()
        self.makeSourceTrove('test1', test1Recipe)

        cookFlavor = deps.parseFlavor('readline,ssl,X')

        troveTup = repos.findTrove(self.cfg.buildLabel,
                                    ('test1:source', None, None), None)[0]
        troveTup = (troveTup[0], troveTup[1], cookFlavor)
        targetLabel = versions.Label('localhost@LOCAL:linux')
        newTargetLabel = versions.Label('localhost@LOCAL:linux')
        # adding an unknown flavor shouldn't matter with latest conary.
        self.cfg.buildFlavor = deps.overrideFlavor(self.cfg.buildFlavor, 
                                                   deps.parseFlavor('foobar'))
        logger_ = logger.Logger()

        logPath, pid, buildInfo = self.discardOutput(cook.cookTrove,
                                           self.cfg, repos, logger_,
                                          targetLabel=targetLabel, *troveTup)
        result = self._wait(buildInfo)
        assert(result.isBuildSuccess())
        repos.commitChangeSetFile(result.getChangeSetFile())

        troveTup = repos.findTrove(newTargetLabel,
                               ('test1', None, deps.parseFlavor('readline,ssl')),
                               None)[0]
        assert(troveTup[1].branch().label() == newTargetLabel)
        assert(str(troveTup[2]) == 'readline,ssl')
        self.updatePkg('test1=%s[readline,ssl]' % newTargetLabel, 
                        raiseError=True)
        self.verifyFile(self.rootDir + '/foo/bar', str(self.cfg.buildLabel) + '\n')

    def testChangedRecipeCook(self):
        repos = self.openRepository()
        self.openRmakeRepository()
        trv = self.addComponent(
            'test1:source=/localhost@rpl:linux//rmakehost@LOCAL:linux/1.2-0.1',
            [('test1.recipe', test1Recipe)])

        cookFlavor = deps.parseFlavor('readline,ssl,X')

        troveTup = trv.getNameVersionFlavor()
        troveTup = (troveTup[0], troveTup[1], cookFlavor)
        targetLabel = versions.Label('rmakehost@LOCAL:linux')
        newTargetLabel = versions.Label('rmakehost@LOCAL:linux')
        # adding an unknown flavor shouldn't matter with latest conary.
        self.cfg.buildFlavor = deps.overrideFlavor(self.cfg.buildFlavor, 
                                                   deps.parseFlavor('foobar'))
        logger_ = logger.Logger()

        logPath, pid, buildInfo = self.discardOutput(cook.cookTrove,
                                           self.cfg, repos, logger_,
                                          targetLabel=targetLabel, *troveTup)
        result = self._wait(buildInfo)
        assert(result.isBuildSuccess())

    def testDefaultBuildReqs(self):
        # add a defautl build req on foo:run and make sure that it shows
        # up in the build requirements for the finishehd trove.
        repos = self.openRepository()
        self.cfg.defaultBuildReqs = ['foo:run']
        foo = self.addComponent('foo:run', '1')
        self.updatePkg('foo:run')

        test1 = self.addComponent('test1:source', '1',
                                 [('test1.recipe', test1Recipe)])
        troveTup = test1.getNameVersionFlavor()
        targetLabel = versions.Label('localhost@LOCAL:linux')
        logger_ = logger.Logger()
        logPath, pid, buildInfo = self.discardOutput(cook.cookTrove,
                                          self.cfg, repos, logger_,
                                          targetLabel=self.cfg.buildLabel,
                                          *troveTup)
        result = self._wait(buildInfo)
        assert(result.isBuildSuccess())
        repos = self.openRepository()
        repos.commitChangeSetFile(result.getChangeSetFile())
        troveTup = repos.findTrove(self.cfg.buildLabel, ('test1', None, None), 
                                   None)[0]
        test1 = repos.getTrove(*troveTup)
        assert(test1.getBuildRequirements() == [foo.getNameVersionFlavor()])

    def test_cookTrove(self):
        raise testsuite.SkipTestException('This messes with the environment of the testsuite, resetting CONARY_PATH')
        repos = self.openRepository()
        self.makeSourceTrove('test1', test1Recipe)
        troveTup = repos.findTrove(self.cfg.buildLabel, ('test1:source', None, None), None)[0]
        targetLabel = versions.Label('localhost@rpl:branch')

        csFile = self.workDir + '/test1.ccs'
        self.discardOutput(cook._cookTrove, self.cfg, repos,
                           targetLabel=targetLabel, 
                           csFile=csFile, failureFd=None, *troveTup)

        repos.commitChangeSetFile(csFile)

        troveTup = repos.findTrove(targetLabel, 
                                   ('test1', None, None), None)[0]
        assert(troveTup[1].branch().label() == targetLabel)

    def testCookResults(self):
        trv = self.addComponent('test:source', '1.0-1')
        results = cook.CookResults(*trv.getNameVersionFlavor())
        csFile = 'foobar'
        results.setChangeSetFile(csFile)
        assert(results.getChangeSetFile() == csFile)
        results.setExitStatus(0)
        assert(results.isBuildSuccess())
        results.setExitStatus(1)
        assert(not results.isBuildSuccess())
        results.setExitStatus(0)
        results.setExitSignal(13)
        assert(not results.isBuildSuccess())

        frozenResults = results.__freeze__()
        results = cook.CookResults.__thaw__(frozenResults)
        assert(not results.isBuildSuccess())
        assert(results.getChangeSetFile() == csFile)
        assert(results.getExitSignal() == 13)

    def testFailedTrove(self):
        repos = self.openRepository()
        self.makeSourceTrove('failed', failedRecipe)

        troveTup = repos.findTrove(self.cfg.buildLabel, ('failed:source', None, 
                                   None), None)[0]
        self.logFilter.add()

        logger_ = logger.Logger()
        logPath, pid, buildInfo = self.discardOutput(cook.cookTrove,
                                                    self.cfg, repos, logger_,
                                                    targetLabel=None, *troveTup)
        result = self._wait(buildInfo)
        assert(not result.isBuildSuccess())
        assert(not result.getChangeSetFile())
        assert(not result.getExitSignal())
        assert(result.getExitStatus() == 1)

        # test again, with signal
        self.updateSourceTrove('failed', failedSignalRecipe)
        troveTup = repos.findTrove(self.cfg.buildLabel, ('failed:source', None, 
                                   None), None)[0]

        logPath, pid, buildInfo = self.discardOutput(cook.cookTrove, 
                                                    self.cfg, repos, logger_,
                                                   targetLabel=None, *troveTup)
        result = self._wait(buildInfo)
        assert(result.getExitSignal() == 11)
        assert(not result.isBuildSuccess())
        assert(not result.getChangeSetFile())

    def testCookGroupDoesntPickBuilt(self):
        built = self._setupGroupTroves()

        self.makeSourceTrove('group-foo', groupRecipe)
        builtTroves = [x.getNameVersionFlavor() for x in built]
        self._testCookGroupDoesntPickBuilt(builtTroves)
        self.updateSourceTrove('group-foo',
                groupRecipe.replace('setLabelPath', 'setSearchPath'))

        self._testCookGroupDoesntPickBuilt(builtTroves)


    def testCookGroupDepResolutionWithBuiltTroves(self):
        built = self._setupGroupTroves()
        self.addComponent('test:run',  'localhost@rpl:devel',
                          requires='trove: foo:run trove:bar:run trove:bam:run')
        self.makeSourceTrove('group-foo', groupDepRecipe)

        builtTroves = [x.getNameVersionFlavor() for x in built]
        self._testCookGroupDoesntPickBuilt(builtTroves)
        self.updateSourceTrove('group-foo',
                groupDepRecipe.replace('setLabelPath', 'setSearchPath'))

        self._testCookGroupDoesntPickBuilt(builtTroves)

    def _setupGroupTroves(self):
        repos = self.openRepository()
        repos = self.openRepository(1)
        built = []
        exists = []
        targetFirst = '/localhost@rpl:first//localhost1@rpl:TARGET/1.0-1-1'
        targetDevel = '/localhost@rpl:devel//localhost1@rpl:TARGET/1.0-1-1'

        # we've got these better candidates that are not being built in the
        # same job but would be picked in the case of a showdown.

        # for new builds to rmake new labels we'll have to find some other
        # way to deal with these.
        # we should pick the localhost@rpl:first one bc the labelPath has 
        # first before devel
        built.append(self.addComponent('foo:run',  targetDevel))
        exists.append(self.addComponent('foo:run', 'localhost@rpl:first'))

        # we should pick localhost@rpl:devel one before the the built trove
        # has an incompatible flavor
        built.append(self.addComponent('bar:run', targetFirst, '!ssl'))
        exists.append(self.addComponent('bar:run', 'localhost@rpl:devel'))

        # FIXME: which of the two bams would actually get picked first?
        # It depends on whether the one on TARGET gets committed as a new
        # version or not, when it is eventually cloned back to :first.
        # That's too complicated to even try to guess,
        # so instead we just always assume a version bump when cooking a new
        # version (so ~!readline gets picked).
        built.append(self.addComponent('bam:run', targetFirst, '~!readline'))
        exists.append(self.addComponent('bam:run',
                                        'localhost@rpl:first', '~readline'))
        return built


    def _testCookGroupDoesntPickBuilt(self, builtTroves):
        repos = self.openRepository()
        repos = self.openRepository(1)

        logger_ = logger.Logger()
        troveTup = repos.findTrove(self.cfg.buildLabel, ('group-foo:source', 
                                   None, None), None)[0]
        targetLabel = versions.Label('localhost1@rpl:TARGET')

        logPath, pid, buildInfo = self.discardOutput(cook.cookTrove,
                                                    self.cfg, repos, logger_,
                                                    troveTup[0], troveTup[1],
                                                    troveTup[2],
                                                    targetLabel=targetLabel,
                                                    builtTroves=builtTroves)
        result = self._wait(buildInfo)
        if not result.csFile:
            print result.failureReason
            raise RuntimeError

        repos.commitChangeSetFile(result.csFile)
        group = self.findAndGetTrove('group-foo=localhost1@rpl:TARGET')
        childTroves = [ x for x in group.iterTroveList(strongRefs=True) if x[0] != 'test:run' ]
        self.assertEquals(len(childTroves), 3)
        def _getHost(name):
            return str([x[1].trailingLabel().getHost() for x in childTroves 
                        if x[0] == name][0])
        assert(_getHost('foo:run') == 'localhost')
        assert(_getHost('bar:run') == 'localhost')
        assert(_getHost('bam:run') == 'localhost1')



    def testCookTwoGroups(self):
        self.addComponent('test:run', '1', '!ssl,~test.foo')
        self.addComponent('test:run', '1', 'ssl,~test.foo')
        trv = self.addComponent('group-foo:source', '1', '',
                                [('group-foo.recipe', groupRecipeWithFlags)])
        flavorList = [deps.parseFlavor('!ssl'), deps.parseFlavor('ssl')]

        repos = self.openRepository()
        logger_ = logger.Logger()
        targetLabel = versions.Label('localhost@rpl:TARGET')
        self.cfg.shortenGroupFlavors = True

        logPath, pid, buildInfo = self.discardOutput(cook.cookTrove,
                                                    self.cfg, repos, logger_,
                                                    trv.getName(),
                                                    trv.getVersion(),
                                                    flavorList,
                                                    targetLabel=targetLabel)
        result = self._wait(buildInfo)
        assert(result.isBuildSuccess())
        cs = changeset.ChangeSetFromFile(result.getChangeSetFile())
        newTroves = [ x.getNewNameVersionFlavor()
                      for x in cs.iterNewTroveList() ]
        assert(len(set([x[1] for x in newTroves])))
        flavorList = set([ x[2] for x in newTroves ])
        self.assertEquals(sorted(str(x) for x in flavorList),
                          ['readline,!ssl', 'ssl'])

test1Recipe = '''
class TestRecipe1(PackageRecipe):
    name = 'test1'
    version = '1.0'
    clearBuildReqs()

    if Use.ssl:
        pass

    def setup(r):
        r.Create('/foo/bar', contents=r.macros.buildlabel)
        if Use.readline:
            pass
'''

failedRecipe = '''
class TestRecipe1(PackageRecipe):
    name = 'failed'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        r.Run('exit 1')
'''

failedSignalRecipe = '''
import signal
class TestRecipe1(PackageRecipe):
    name = 'failed'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        # we can't just call r.Run, that's wrapped. 
        r.extraBuild(KillMe(r))

class KillMe(build.BuildAction):
    def do(self, macros):
        os.kill(os.getpid(), signal.SIGSEGV)
'''

groupRecipe = '''
class GroupRecipe1(GroupRecipe):
    name = 'group-foo'
    version = '1.0'
    checkPathConflicts = False
    clearBuildReqs()

    def setup(r):
        r.setLabelPath('localhost@rpl:first', 'localhost@rpl:devel')
        r.add('foo:run')
        r.add('bar:run')
        r.add('bam:run')
'''

groupDepRecipe = '''
class GroupRecipe1(GroupRecipe):
    name = 'group-foo'
    version = '1.0'
    checkPathConflicts = False
    autoResolve = True
    clearBuildReqs()

    def setup(r):
        r.setLabelPath('localhost@rpl:first', 'localhost@rpl:devel')
        r.add('test:run')
'''

groupRecipeWithFlags = '''
class GroupRecipe(GroupRecipe):
    name = 'group-foo'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        if Use.ssl:
            r.add('test:run')
        elif Use.readline:
            r.add('test:run')
'''
