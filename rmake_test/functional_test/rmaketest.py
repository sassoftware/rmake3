#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

from conary_test import recipes

import os
from SimpleXMLRPCServer import SimpleXMLRPCServer
import signal
import sys
import time

from rmake_test import rmakehelp

from conary.conaryclient import cmdline

from rmake.build import buildcfg
from rmake.build import buildjob
from rmake.server import client, server, servercfg
from rmake.lib import localrpc,logfile,recipeutil


class RMakeTest(rmakehelp.RmakeHelper):

    def testBasic(self):
        repos = self.openRepository()
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', basicRecipe)])


        self.openRmakeRepository()
        uri = 'unix://%s/socket' % self.rootDir
        srv = server.rMakeServer(#None,
                uri,
                self.rmakeCfg,
                None, quiet=True)
        self.buildCfg.uuid = self.genUUID('foo')
        self.buildCfg.strictMode = True
        #client = server.rMakeClient(srv)
        #client = server.rMakeClient('http://localhost:60005')
        rmakeClient = client.rMakeClient(uri)
        pid = os.fork()
        if pid:
            srv._close()
            try:
                helper = self.getRmakeHelper(rmakeClient.uri)
                troveSpec = '%s=%s[%s]' % trv.getNameVersionFlavor()
                jobId = self.discardOutput(helper.buildTroves, [troveSpec])
                buildCfg = rmakeClient.getJobConfig(jobId)
                self.assertEquals(buildCfg.buildTroveSpecs, 
                                  [cmdline.parseTroveSpec(troveSpec)])
                for i in range(0, 1000):
                    job = rmakeClient.getJob(jobId)
                    if job.isFinished():
                        break
                    time.sleep(1)
                # make sure a trove can actually be found
                if job.isFailed():
                    raise RuntimeError('Job Failed: %s' % job.getFailureReason())
                repos.findTrove(None, ('testcase', 'rmakehost@local:linux', None),
                                self.buildCfg.flavor)
            finally:
                os.kill(pid, signal.SIGTERM)
                self.waitThenKill(pid)
        else:
            try:
                sys.stdin = open('/dev/null')
                lf = logfile.LogFile(self.rootDir + '/srv.log')
                lf.redirectOutput()
                srv.serve_forever()
            finally:
                os._exit(1)

    def testExternalServer(self):
        # test committing and cooking into an external server and then
        # cloning out.
        self.openRepository()
        repos = self.openRepository(1)
        self.startRmakeProxy(reposName='localhost1')
        self.rmakeCfg.proxyUrl = self.rmakeCfg.getProxyUrl()
        rmakeClient, rmakeCfg, buildCfg = self.startRmakeServer(
                                                    reposName = 'localhost1')

        self.addComponent('foo:runtime', requires='trove:bar:runtime')
        self.addComponent('bar:runtime', filePrimer=1)
        buildCfg.resolveTroves.append([('foo:runtime', None, None),
                                       ('bar:runtime', None, None)])
        buildCfg.resolveTrovesOnly = True
        helper = self.getRmakeHelper(rmakeClient.uri, rmakeCfg=rmakeCfg,
                                     buildCfg=buildCfg)

        v = '/localhost@rpl:linux//localhost1@local:linux/1.0-1-1'
        self.addComponent('simple:runtime', v)
        self.addCollection('simple', v, [':runtime'])

        trv = self.addComponent('simple:source', '1.0-1', '',
                                [('simple.recipe', recipes.simpleRecipe)])
        os.chdir(self.workDir)
        self.checkout('simple')
        self.writeFile('simple/simple.recipe',
                       recipes.simpleRecipe.replace('clearBuildReqs()', 'clearBuildReqs(); buildRequires = ["foo:runtime"]'))


        jobId = self.discardOutput(helper.buildTroves,
                                   ['simple/simple.recipe'])
        helper.waitForJob(jobId)
        assert(rmakeClient.getJob(jobId, withTroves=False).isBuilt())
        troves = list(rmakeClient.getJob(jobId).iterTroves())
        assert(troves[0].getBinaryTroves())
        passed, txt = self.commitJob(helper, str(jobId))
        assert(passed)
        flavor = self.getArchFlavor()
        self.assertEquals(txt, """
Committed job 1:
    simple:source=/localhost@rpl:linux//localhost1@local:linux/1-0.1[%s] ->
       simple=/localhost@rpl:linux/1-1-1[]
       simple:source=/localhost@rpl:linux/1-1[]

""" % flavor)
        results = repos.findTrove(self.cfg.installLabelPath,
                                  ('simple', None, None), self.cfg.flavor)
        assert(results)

    def testMultipleContexts(self):
        config = """
[nossl]
buildFlavor !ssl
"""
        repos = self.openRepository()
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', 
                                  basicRecipe + '\tif Use.ssl:pass')])

        self.openRmakeRepository()
        self.writeFile(self.workDir + '/config', config)
        self.buildCfg.read(self.workDir + '/config')

        uri = 'unix://%s/socket' % self.rootDir
        self.buildCfg.strictMode = True
        srv = server.rMakeServer(#None,
                    uri,
                    self.rmakeCfg,
                    None, quiet=True)

        rmakeClient = client.rMakeClient(uri)

        pid = os.fork()
        if pid:
            srv._close()
            try:
                helper = self.getRmakeHelper(rmakeClient.uri)
                troveSpec = '%s=%s[%s]' % trv.getNameVersionFlavor()
                troveSpec2 = '%s=%s[%s]{nossl}' % trv.getNameVersionFlavor()
                jobId = helper.buildTroves([troveSpec, troveSpec2])
                buildCfg = rmakeClient.getJobConfig(jobId)
                self.assertEquals(buildCfg.buildTroveSpecs, [cmdline.parseTroveSpec(troveSpec)])
                helper.waitForJob(jobId)
                job = helper.getJob(jobId)
                # make sure a trove can actually be found
                if job.isFailed():
                    raise RuntimeError('Job Failed: %s' % job.getFailureReason())
                trvs = job.findTrovesWithContext(None, 
                                        [('testcase:source', None, None, None)])
                assert(len(trvs) == 1)
                self.assertEquals(len(trvs.values()[0]), 2)
            finally:
                os.kill(pid, signal.SIGTERM)
                self.waitThenKill(pid)
        else:
            try:
                sys.stdin = open('/dev/null')
                lf = logfile.LogFile(self.rootDir + '/srv.log')
                lf.redirectOutput()
                srv.serve_forever()
            finally:
                os._exit(1)

basicRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'testcase'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        r.Create('/foo', contents='foo')
"""

flavoredRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'testcase'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        if Use.ssl:
            pass
        r.Create('/foo', contents='foo')
"""



