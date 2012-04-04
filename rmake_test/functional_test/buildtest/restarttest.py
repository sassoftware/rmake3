#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import copy
import os
import re

from conary_test import recipes

from rmake_test import rmakehelp


from conary.deps import deps

from rmake.build import builder
from rmake.build import buildjob
from rmake.lib import logfile
from rmake.lib import repocache

from rmake_test import fixtures

class RestartTest(rmakehelp.RmakeHelper):

    def testRestart(self):
        self.openRepository()
        self.openRmakeRepository()
        jobId = fixtures.addBuiltJob1(self)
        db = self.openRmakeDatabase()
        job = db.getJob(jobId)
        logPath = job.troves.values()[0].logPath
        jobContext = [jobId]
        restartJob = self.getRestartJob(job)
        b = builder.Builder(self.rmakeCfg, restartJob, jobContext, db)
        b.initializeBuild()
        trove = restartJob.iterTroves().next()
        assert(trove.isPrebuilt())
        b.build()
        assert(restartJob.isBuilt())
        assert(trove.isBuilt())
        assert(logPath == restartJob.troves.values()[0].logPath)

        # update the source and make sure it needs a rebuild
        fixtures.updateBuiltJob1(self)
        restartJob = self.getRestartJob(job)
        b = builder.Builder(self.rmakeCfg, restartJob, jobContext, db)
        b.initializeBuild()
        trove = restartJob.iterTroves().next()
        assert(not trove.isPrebuilt())
        b.build()
        assert(restartJob.isBuilt())
        assert(trove.isBuilt())
        assert(logPath != restartJob.troves.values()[0].logPath)

        buildReqRun = self.addComponent('buildreq:runtime', '2', ['/buildreq'])
        buildReq = self.addCollection('buildreq', '2', [':runtime'])

        # now update build req - that should start out as prebuilt
        # but in the end it should create new binaries not existing before.
        jobContext = [restartJob.jobId]
        restartJob2 = self.getRestartJob(restartJob)
        b = builder.Builder(self.rmakeCfg, restartJob2, jobContext, db)
        b.initializeBuild()
        trove2 = restartJob2.iterTroves().next()
        assert(trove2.isPrebuilt())
        b.dh.updateBuildableTroves()
        assert(trove2.isBuildable())

    def testRestartWithLoadInstalled(self):
        simpleRecipe = 'loadInstalled("foo")\n' + recipes.simpleRecipe
        simpleSource = self.addComponent('simple:source=1-1', 
                          [('simple.recipe', simpleRecipe)])
        fooSource = self.addComponent('foo:source=1-1',
                               [('foo.recipe', fooRecipe)])
        simpleRun = self.addComponent('simple:runtime=1-1-1')
        simpleColl = self.addCollection('simple=1-1-1', [':runtime'],
                                        loadedReqs=[(fooSource, 'ssl')])
        job = self.newJob(simpleSource)
        db = self.openRmakeDatabase()
        b = builder.Builder(self.rmakeCfg, job, [], db)
        b.initializeBuild()
        simpleBt = job.iterTroves().next()
        simpleBt.troveBuilt([simpleColl.getNameVersionFlavor(),
                             simpleRun.getNameVersionFlavor()])
        restartJob = self.getRestartJob(job)
        jobContext = [job.jobId]
        b = builder.Builder(self.rmakeCfg, restartJob, jobContext, db)
        b.initializeBuild()
        trove = restartJob.iterTroves().next()
        assert(trove.isPrebuilt())
        assert(trove.superClassesMatch)
        fooSource = self.addComponent('foo:source=1-2',
                               [('foo.recipe', fooRecipe)])
        restartJob = self.getRestartJob(job)
        jobContext = [job.jobId]
        b = builder.Builder(self.rmakeCfg, restartJob, jobContext, db)
        b.initializeBuild()
        trove = restartJob.iterTroves().next()
        assert(trove.isPrebuilt())
        assert(not trove.superClassesMatch)



fooRecipe = """class FooRecipe(PackageRecipe):
    name = 'foo'
    version = '1'
    clearBuildReqs()
    if Use.ssl:
        pass
    def setup(r):
        r.Create('/foo')
"""

