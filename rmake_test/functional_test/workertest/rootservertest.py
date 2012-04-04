#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

from conary.deps import deps
from conary import versions

from rmake.build import buildcfg
from rmake.build import buildtrove
from rmake.worker.chroot import rootserver
from rmake.lib.rpcproxy import ShimAddress

from rmake_test import rmakehelp


class ChrootTest(rmakehelp.RmakeHelper):

    def testChrootServer(self):
        raise testsuite.SkipTestException("Test is unreliable")
        repos = self.openRepository()

        targetLabel = versions.Label('localhost@rpl:branch')
        cfg = buildcfg.BuildConfiguration(False, conaryConfig=self.cfg,
                                          root=self.cfg.root,
                                          serverConfig=self.rmakeCfg,
                                          strictMode=False)
        cfg.defaultBuildReqs = []

        cfg.targetLabel = targetLabel


        trv = self.makeSourceTrove('test1', test1Recipe)



        troveTup = repos.findTrove(self.cfg.buildLabel, ('test1:source', None, 
                                   None), None)[0]
        cookFlavor = deps.parseFlavor('readline,ssl,X')
        troveTup = (troveTup[0], troveTup[1], cookFlavor)

        db = self.openRmakeDatabase()
        job = self.newJob(troveTup)
        buildTrove = buildtrove.BuildTrove(job.jobId, *troveTup)
        buildTrove.setPublisher(job.getPublisher())

        cfg.root = self.cfg.root
        client = rootserver.ChrootClient('/', ShimAddress(
            rootserver.ChrootServer(None, cfg, quiet=True)))
        logPath = self.discardOutput(client.buildTrove,cfg,
                                    cfg.getTargetLabel(troveTup[1]),
                                    *troveTup)
        result = client.checkResults(wait=10, *troveTup)
        assert(result.isBuildSuccess())

        repos.commitChangeSetFile(result.getChangeSetFile())

        troveTup = repos.findTrove(targetLabel,
                           ('test1', None, deps.parseFlavor('readline,ssl')),
                               None)[0]
        assert(troveTup[1].branch().label() == targetLabel)
        assert(str(troveTup[2]) == 'readline,ssl')


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

