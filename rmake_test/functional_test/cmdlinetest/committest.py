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


"""
Tests for the rmake commit command
"""

import os
import shutil

from conary.deps import deps
from conary import checkin
from conary import state
from conary import versions
from conary.lib import log
from conary.lib import openpgpfile
from conary.lib import openpgpkey
from conary.repository import changeset
from conary_test import recipes
from rmake.build import subscriber
from rmake.cmdline import commit
from rmake import errors
from rmake_test import fixtures
from rmake_test import resources
from rmake_test import rmakehelp


class CommitTest(rmakehelp.RmakeHelper):
    _check = rmakehelp.RmakeHelper.checkMonitor

    def _subscribeServer(self, client, job):
        subscriber._RmakeServerPublisherProxy(client.uri).attach(job)

    def testCommitFromFrontEnd(self):
        self.openRmakeRepository()
        db = self.openRmakeDatabase()
        repos = self.openRepository()
        client = self.startRmakeServer()
        trv1 = self.addComponent('testcase:source', '1.0-1', '')
        trv2 = self.addComponent('testcase:source', ':branch2/1.0-1', '',
                                 filePrimer=1)
        built = {}

        for trv, filePrimer in [(trv1, 2),(trv2, 3)]:
            targetBranch = trv.getVersion().branch()
            targetBranch = targetBranch.createShadow(versions.Label('%s@LOCAL:linux' % self.rmakeCfg.reposName))
            targetVer = '%s/1.0-1-1' % targetBranch
            runTrv = self.addComponent('testcase:runtime', targetVer,
                                        filePrimer=filePrimer,
                                        pathIdSalt=str(filePrimer))
            self.addCollection('testcase', targetVer, 
                               [runTrv.getNameVersionFlavor()])

            cs = repos.createChangeSet([('testcase', (None, None),
                                        (runTrv.getVersion(),
                                         runTrv.getFlavor()),
                                        True),
                                        ('testcase:runtime', (None, None),
                                        (runTrv.getVersion(),
                                         runTrv.getFlavor()),
                                        False)], recurse=False)
            built[trv] = cs

        helper = self.getRmakeHelper(client.uri)

        job = self.newJob(trv1, trv2)
        db.subscribeToJob(job)
        self._subscribeServer(client, job)

        buildTroves = trvBranch1,trvBranch2 = self.makeBuildTroves(job)
        job.setBuildTroves(buildTroves)
        cs = built[trv1]
        trvBranch1.troveBuilt([x.getNewNameVersionFlavor()
                               for x in cs.iterNewTroveList()])
        cs = built[trv2]
        trvBranch2.troveBuilt([x.getNewNameVersionFlavor()
                               for x in cs.iterNewTroveList()])
        job.jobPassed('')
        jobId = job.jobId

        m = self.getMonitor(client, showTroveLogs=False,
                                    showBuildLogs=False, jobId=jobId)
        passed, txt = self.commitJob(helper, str(job.jobId))
        assert(passed)
        assert(txt == """
Committed job 1:
    testcase:source=/localhost@rpl:linux/1.0-1 ->
       testcase=/localhost@rpl:linux/1.0-1-1[]

    testcase:source=/localhost@rpl:branch2/1.0-1 ->
       testcase=/localhost@rpl:branch2/1.0-1-1[]

""")

        self._check(m, ['[TIME] [1] - State: Committing\n',
                        '[TIME] [1] - State: Committed\n'],
                    ignoreExtras=True, events=3)
        results = repos.findTroves(self.cfg.installLabelPath,
                                  [('testcase', None, None),
                                   ('testcase', ':branch2', None)], 
                                   self.cfg.flavor)
        assert(results)
        job = client.getJob(jobId)
        assert(job.isCommitted())
        assert(job.isFinished())
        binaryTroves = job.iterTroves().next().getBinaryTroves()
        assert(set(x[1].trailingLabel().getHost() for x in binaryTroves)
               == set(['localhost']))
        self.logFilter.add()
        passed, txt = self.commitJob(helper, job.jobId, sourceOnly=True,
                                     waitForJob=True)
        assert(not passed)
        self.logFilter.compare('error: Job(s) already committed')

    def _setupSignature(self, repos, fingerprint):
        # supply the pass phrase for our private key
        keyCache = openpgpkey.getKeyCache()
        keyCache.getPrivateKey(fingerprint, '111111')

        # get the public key
        keyRing = open(resources.get_archive('pubring.gpg'))
        if hasattr(openpgpfile, 'readKeyData'):
            keyData = openpgpfile.readKeyData(keyRing, fingerprint)
        else:
            keyData = openpgpfile.exportKey(fingerprint, keyRing)
            keyData.seek(0)
            keyData = keyData.read()

        # upload the public key
        repos = self.openRepository()
        repos.addNewPGPKey(self.cfg.buildLabel, 'test', keyData)
        self.buildCfg.signatureKey = fingerprint

    def testCommitSource(self):
        repos = self.openRepository()

        # test signing the trove as well
        fingerprint = 'F7440D78FE813C882212C2BF8AC2828190B1E477'
        self._setupSignature(repos, fingerprint)

        self.openRmakeRepository()
        client = self.startRmakeServer()

        helper = self.getRmakeHelper(client.uri)

        trv = self.addComponent('simple:source', '1-1', '',
                                [('simple.recipe', recipes.simpleRecipe)])
        os.chdir(self.workDir)
        self.checkout('simple')
        self.writeFile('simple/simple.recipe', 
                       recipes.simpleRecipe + '\t#foo\n')
        jobId = self.discardOutput(helper.buildTroves,
                                   ['simple/simple.recipe'])

        # make a local change here while it's cooking
        os.chdir('simple')
        self.writeFile('simple.recipe', 
                       recipes.simpleRecipe + '\t#foo2\n')
        self.commit()
        helper.waitForJob(jobId)
        assert(client.getJob(jobId, withTroves=False).isBuilt())
        troves = list(client.getJob(jobId).iterTroves())
        assert(troves[0].getBinaryTroves())
        self.logFilter.add()
        passed, txt = self.commitJob(helper, str(jobId))
        assert(not passed)
        self.logFilter.compare(['error: The following source troves are out of date:\nsimple:source=/localhost@rpl:linux/1-1 (replaced by newer 1-2)\n\nUse --commit-outdated-sources to commit anyway'])

        self.logFilter.remove()
        passed, txt = self.commitJob(helper, str(jobId),
                                     commitOutdatedSources=True)
        assert(passed)
        assert(txt == """
Committed job 1:
    simple:source=/localhost@rpl:linux//rmakehost@local:linux/1-1.1[%s] ->
       simple=/localhost@rpl:linux/1-3-1[]
       simple:source=/localhost@rpl:linux/1-3[]

""" % self.getArchFlavor())

        results = repos.findTrove(self.cfg.installLabelPath,
                                  ('simple', None, None), self.cfg.flavor)
        assert(results)

        # check to make sure the trove and its source were both signed
        t = repos.getTrove(*results[0])
        signature = t.getDigitalSignature(fingerprint)
        signature = signature.getSignatures().signatures.iter().next()
        assert(signature[0] == fingerprint)
        # check to make sure the clonedFrom setting is not set.
        #if compat.ConaryVersion().supportsCloneNoTracking():
        #    assert(not t.troveInfo.clonedFrom())
        results = repos.findTrove(self.cfg.installLabelPath,
                          ('simple:source', None, None), self.cfg.flavor)
        assert(results)
        t = repos.getTrove(*results[0])
        signature = t.getDigitalSignature(fingerprint)
        signature = signature.getSignatures().signatures.iter().next()
        assert(signature[0] == fingerprint)
        assert(str(state.ConaryStateFromFile(self.workDir + '/simple/CONARY').getSourceState().getVersion().trailingRevision()) == '1-3')

    def testCommitSourceOnly(self):
        repos = self.openRepository()

        self.openRmakeRepository()
        client = self.startRmakeServer()

        helper = self.getRmakeHelper(client.uri)

        trv = self.addComponent('simple:source', '1-1', '',
                                [('simple.recipe', recipes.simpleRecipe)])
        os.chdir(self.workDir)
        self.checkout('simple')
        self.writeFile('simple/simple.recipe', 
                       recipes.simpleRecipe + '\t#foo\n')

        jobId = self.discardOutput(helper.buildTroves,
                                   ['simple/simple.recipe'])
        self.logFilter.add()
        passed, txt = self.commitJob(helper, str(jobId), sourceOnly=True,
                                     waitForJob=True)
        assert(passed)
        assert(txt == '''Waiting for job 1 to complete before committing

Committed job 1:
    simple:source=/localhost@rpl:linux//rmakehost@local:linux/1-1.1[%s] ->
       simple:source=/localhost@rpl:linux/1-2[]

''' % self.getArchFlavor())

        self.logFilter.remove()

    def testFailToCommitLocalRecipe(self):
        # We've cooked a local recipe that's not on a branch - there's
        #    nowhere to commit it to!
        self.openRmakeRepository()
        repos = self.openRepository()
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)

        localSourceRecipe = """\
class LocalSource(PackageRecipe):
    name = 'local'
    version = '1.0'
    clearBuildReqs()

    def setup(r):
        r.addArchive('tmpwatch-2.9.0.tar.gz', rpm='tmpwatch-2.9.0-2.src.rpm')
        r.addSource('dc_client.init', rpm='distcache-1.4.5-2.src.rpm')
        r.addSource('foo', dest='/')
"""

        recipePath = self.workDir + '/local.recipe'
        self.writeFile(recipePath, localSourceRecipe)
        self.writeFile(self.workDir + '/foo', 'Contents\n')
        shutil.copyfile(resources.get_archive('tmpwatch-2.9.0-2.src.rpm'),
                        self.workDir + '/tmpwatch-2.9.0-2.src.rpm')
        self.logFilter.add() # this message correct, conary can't guess the type
                             # of this file.
        jobId = self.discardOutput(helper.buildTroves,
                                   [self.workDir + '/local.recipe'])
        helper.waitForJob(jobId)
        assert(not client.getJob(jobId, withTroves=False).isFailed())
        helper = self.getRmakeHelper(client.uri)
        self.logFilter.add()
        m = self.getMonitor(client, showTroveLogs=False,
                                    showBuildLogs=False, jobId=jobId)
        passed, txt = self.commitJob(helper, jobId)
        assert(passed)
        assert(txt == """
Committed job 1:
    local:source=/localhost@rpl:linux//rmakehost@local:linux/1.0-0.1[%s] ->
       local=/localhost@rpl:linux/1.0-1-1[]
       local:source=/localhost@rpl:linux/1.0-1[]

""" % self.getArchFlavor())
        self._check(m, ['[TIME] [1] - State: Committing\n',
                        '[TIME] [1] - State: Committed\n'])
        job = client.getJob(jobId)
        assert(job.isCommitted())
        assert(job.isFinished())

    def testCommitTwoJobs(self):
        self.openRmakeRepository()
        db = self.openRmakeDatabase()
        jobId1 = fixtures.addBuiltJob1(self)
        jobId2 = fixtures.addBuiltJob2(self)

        repos = self.openRepository()
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        passed, txt = self.commitJobs(helper, [jobId1, jobId2])
        assert(passed)
        self.assertEquals(txt, """
Committed job 1:
    testcase:source=/localhost@rpl:linux/1-1[ssl %s] ->
       testcase=/localhost@rpl:linux/1-1-1[ssl]


Committed job 2:
    testcase2:source=/localhost@rpl:linux/1-1[%s] ->
       testcase2=/localhost@rpl:linux/1-1-1[]

""" % (self.getArchFlavor(), self.getArchFlavor()))

    def testCommitSameJobTwice(self):
        self.openRepository()
        self.openRmakeRepository()
        jobId = fixtures.addBuiltJob1(self)
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        rc, txt = self.captureOutput(helper.commitJob, jobId)
        rc, txt = self.captureOutput(helper.commitJob, jobId)
        assert(txt == 'error: Job(s) already committed\n')
        job = helper.getJob(jobId)
        assert(job.isCommitted())
        # make sure you don't recommit when the job has already been committed.
        jobId = self.discardOutput(helper.restartJob, job.jobId)
        helper.waitForJob(jobId)
        job = helper.getJob(jobId)
        assert(not job.isFailed())
        self.logFilter.add()
        assert(helper.commitJob(jobId))
        self.logFilter.compare(['warning: All built troves have already been committed'])

    def testCommitToFile(self):
        self.openRepository()
        self.openRmakeRepository()
        jobId = fixtures.addBuiltJob1(self)
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        changesetPath = self.workDir + '/commit.ccs'
        rc, txt = self.captureOutput(helper.commitJob, jobId,
                                     writeToFile=changesetPath)
        cs = changeset.ChangeSetFromFile(changesetPath)
        for trvCs in cs.iterNewTroveList():
            assert(trvCs.getNewVersion().getHost() == 'localhost')



    def testCommitJobWithFailuresOnOneBranch(self):
        # If one branch has failures, make sure we don't get messages 
        # that the job has not troves to commit.
        self.openRepository()
        self.openRmakeRepository()
        jobId = fixtures.addFailedJob1(self)
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        rc, txt = self.captureOutput(helper.commitJob, jobId)
        assert(txt == '\nCommitted job 1:\n'
                      '    testcase:source=/localhost@rpl:linux/1-1[ssl %s] ->\n'
                      '       testcase=/localhost@rpl:linux/1-1-1[ssl]\n\n' % self.getArchFlavor())

    def testCommitMultipleContexts(self):
        self.openRepository()
        self.openRmakeRepository()
        jobId = fixtures.addMultiContextJob1(self)
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        rc, txt = self.captureOutput(helper.commitJob, jobId)
        self.assertEquals(txt, '''
Committed job 1:
    testcase3:source=/localhost@rpl:linux/1-1[%s] ->
       testcase3=/localhost@rpl:linux/1-1-1[]
       testcase3-pkg=/localhost@rpl:linux/1-1-1[]

warning: Not committing testcase3, testcase3-pkg on /localhost@rpl:linux//rmakehost@local:linux/1-2-0.1[]{nossl} - overridden by /localhost@rpl:linux//rmakehost@local:linux/1-1-0.1[]
''' % self.getArchFlavor())
        restartJobId = self.discardOutput(helper.restartJob, jobId)
        helper.waitForJob(restartJobId)
        job = helper.getJob(restartJobId)
        assert(job.isBuilt())
        rc, txt = self.captureOutput(helper.commitJob, restartJobId)
        self.assertEquals(txt,
                    'warning: All built troves have already been committed\n')


    def testCommitMultipleGroupFlavors(self):
        self.openRepository()
        db = self.openRmakeDatabase()
        repos = self.openRmakeRepository()
        client = self.startRmakeServer()

        self.addComponent('foo:run=1[ssl]')
        foossl = self.addCollection('foo=1[ssl]', [':run'])
        self.addComponent('foo:run=1[!ssl]')
        foonossl = self.addCollection('foo=1[!ssl]', [':run'])
        self.addComponent('foo:run=1[readline]')
        foo = self.addCollection('foo=1[readline]', [':run'])

        trv = self.addComponent('group-test:source', '1.0-1', '')
        built = {}

        targetBranch = trv.getVersion().branch()
        targetBranch = targetBranch.createShadow(versions.Label('%s@LOCAL:linux' % self.rmakeCfg.reposName))
        targetVer = '%s/1.0-1-1' % targetBranch
        sslgroup = self.addCollection('group-test', targetVer,
                           [foossl.getNameVersionFlavor()])
        nosslgroup = self.addCollection('group-test', targetVer,
                                  [foonossl.getNameVersionFlavor()])

        sslcs = repos.createChangeSet([('group-test', (None, None),
                                    (sslgroup.getVersion(),
                                     sslgroup.getFlavor()),
                                    True)], recurse=False)
        nosslcs = repos.createChangeSet([('group-test', (None, None),
                                    (nosslgroup.getVersion(), 
                                     nosslgroup.getFlavor()), 
                                    True)], recurse=False)


        helper = self.getRmakeHelper(client.uri)

        job = self.newJob(
                (trv.getName(), trv.getVersion(), deps.parseFlavor('ssl')),
                (trv.getName(), trv.getVersion(), deps.parseFlavor('!ssl')))
        db.subscribeToJob(job)
        self._subscribeServer(client, job)

        buildTroves = btSsl , btNossl  = self.makeBuildTroves(job)
        job.setBuildTroves(buildTroves)
        btSsl.troveBuilt([x.getNewNameVersionFlavor()
                               for x in sslcs.iterNewTroveList()])
        btNossl.troveBuilt([x.getNewNameVersionFlavor()
                               for x in nosslcs.iterNewTroveList()])
        job.jobPassed('')
        jobId = job.jobId

        m = self.getMonitor(client, showTroveLogs=False,
                                    showBuildLogs=False, jobId=jobId)
        self.addCollection('group-test=1.0-1-1[readline]', ['foo:run'])
        passed, txt = self.commitJob(helper, str(job.jobId))
        # this should bump the version #s of the groups because there's
        # already something at 1.0-1-1 even though it's a completely different
        # flavor.
        assert(txt == '''
Committed job 1:
    group-test:source=/localhost@rpl:linux/1.0-1[ssl] ->
       group-test=/localhost@rpl:linux/1.0-1-2[ssl]

    group-test:source=/localhost@rpl:linux/1.0-1[!ssl] ->
       group-test=/localhost@rpl:linux/1.0-1-2[!ssl]

''')

    def testUpdateRecipes(self):
        self.logFilter.add()
        log.setVerbosity(log.INFO)
        simpleRecipe = recipes.simpleRecipe
        os.chdir(self.workDir)
        self.newpkg('simple')
        os.chdir('simple')
        self.writeFile('simple.recipe', simpleRecipe)
        self.addfile('simple.recipe')
        self.writeFile('foo', 'bar\n')
        self.buildCfg.configLine('[foo]')
        self.buildCfg.configLine('[bar]')
        conaryStateFile = state.ConaryStateFromFile(os.getcwd() + '/CONARY')
        conaryStateFile.setContext('foo')
        conaryStateFile.write(os.getcwd() + '/CONARY')

        # here we pretend we've done an rmake commit of the same job.
        repos = self.openRepository()
        trv = self.addComponent('simple:source', '1.0',
                                [('simple.recipe', simpleRecipe)])
        commit.updateRecipes(repos, self.buildCfg,
                             [os.getcwd() + '/simple.recipe'],
                             [trv.getNameVersionFlavor()])
        assert(os.path.exists('foo'))
        conaryStateFile = state.ConaryStateFromFile(os.getcwd() + '/CONARY')
        stateFile = conaryStateFile.getSourceState()
        assert(stateFile.getVersion() == trv.getVersion())
        assert(conaryStateFile.getContext() == 'foo')
        conaryStateFile.setContext('bar')
        conaryStateFile.write(os.getcwd() + '/CONARY')
        assert(checkin.diff(repos) == 0)
        trv = self.addComponent('simple:source', '2.0',
                                [('simple.recipe',
                                 simpleRecipe + '\n\t#change\n')])
        assert(checkin.diff(repos) == 0)
        commit.updateRecipes(repos, self.buildCfg,
                             [os.getcwd() + '/simple.recipe'],
                             [trv.getNameVersionFlavor()])
        assert(checkin.diff(repos) == 0)
        assert(os.path.exists('foo'))
        conaryStateFile = state.ConaryStateFromFile(os.getcwd() + '/CONARY')
        stateFile = conaryStateFile.getSourceState()
        assert(stateFile.getVersion() == trv.getVersion())
        assert(conaryStateFile.getContext() == 'bar')
        self.logFilter.compare([
       '+ Replacing CONARY file %s/simple after initial commit' % self.workDir, 
       '+ Updating %s/simple after commit' % self.workDir,
       '+ patching %s/simple/simple.recipe' % self.workDir, 
       '+ patch: applying hunk 1 of 1'])

    def testUpdateRecipesAddFile(self):
        simpleRecipe = recipes.simpleRecipe
        repos = self.openRepository()
        trv = self.addComponent('simple:source', '1.0',
                                [('simple.recipe', simpleRecipe),
                                 ('bam', 'bam\n')])
        os.chdir(self.workDir)
        self.checkout('simple')
        os.chdir('simple')
        self.writeFile('foo', 'bar\n')
        self.addfile('foo', text=True)
        self.writeFile('bar', 'bar\n')
        self.addfile('bar', binary=True)
        self.remove('bam')

        trv = self.addComponent('simple:source', '2.0',
                                [('simple.recipe', simpleRecipe),
                                 ('foo', 'bar\n'),
                                 ('bar', 'bar\n')])
        commit.updateRecipes(repos, self.buildCfg,
                             [os.getcwd() + '/simple.recipe'],
                             [trv.getNameVersionFlavor()])
        conaryStateFile = state.ConaryStateFromFile(os.getcwd() + '/CONARY')
        stateFile = conaryStateFile.getSourceState()
        assert(stateFile.getVersion() == trv.getVersion())

    def testCommitAlreadyInProgress(self):
        self.openRmakeRepository()
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        trvRun = self.addComponent('foo:run', 
                                   '/localhost@rpl:linux//rmakehost@rpl:linux/1-1-1')
        trv = self.addCollection('foo', '/localhost@rpl:linux//rmakehost@rpl:linux/1-1-1',
                                  [':run'])
        trvSrc = self.addComponent('foo:source', 
                                    '/localhost@rpl:linux/1-1')
        job = self.newJob(trvSrc)
        db = self.openRmakeDatabase()
        db.subscribeToJob(job)
        bt, = buildTroves = self.makeBuildTroves(job)
        job.setBuildTroves(buildTroves)
        bt.troveBuilt([x.getNameVersionFlavor() for x in [trvRun, trv]])
        job.jobCommitting()
        try:
            helper.commitJob(job.jobId)
        except errors.RmakeError, e:
            assert(str(e) == 'Job 1 is already committing')
        stopped = client.stopJob(job.jobId)
        self.captureOutput(helper.commitJob, job.jobId)
        assert(client.getJob(job.jobId).isCommitted())

    def testCommitExclude(self):
        self.openRmakeRepository()
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        trvRun = self.addComponent('foo:run', 
                                   '/localhost@rpl:linux//rmakehost@rpl:linux/1-1-1')
        trv = self.addCollection('foo', '/localhost@rpl:linux//rmakehost@rpl:linux/1-1-1',
                                  [':run'])
        trvSrc = self.addComponent('foo:source', 
                                    '/localhost@rpl:linux/1-1')
        trvRunSsl = self.addComponent('foo:run', 
                                   '/localhost@rpl:linux//rmakehost@rpl:linux/1-1-1', 'ssl')
        trvSsl = self.addCollection('foo', '/localhost@rpl:linux//rmakehost@rpl:linux/1-1-1',
                                  [':run'], defaultFlavor='ssl')

        job = self.newJob((trvSrc, 'foo'), (trvSrc, 'bar'))
        db = self.openRmakeDatabase()
        db.subscribeToJob(job)
        btFoo, btBar = buildTroves = self.makeBuildTroves(job)
        job.setBuildTroves(buildTroves)
        btFoo.troveBuilt([x.getNameVersionFlavor() for x in [trvRun, trv]])
        btBar.troveBuilt([x.getNameVersionFlavor() for x in [trvRunSsl,
                                                             trvSsl]])
        job.jobPassed('')
        rc, txt = self.captureOutput(helper.commitJob, job.jobId,
                                 excludeSpecs=['foo{bar}'])
        assert(txt == '\nCommitted job 1:\n'
                      '    foo:source=/localhost@rpl:linux/1-1{foo} ->\n'
                      '       foo=/localhost@rpl:linux/1-1-1[ssl]\n\n')
