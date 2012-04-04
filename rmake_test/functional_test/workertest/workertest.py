#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

import os
import sys
import time

from conary_test import recipes

from conary import versions
from conary.lib import log
from conary.repository import netclient

from rmake.build import builder
from rmake.build import buildtrove
from rmake.lib import logger
from rmake.worker import worker

from rmake_test import rmakehelp
from testutils import mock

class WorkerTest(rmakehelp.RmakeHelper):

    def testWorker(self):
        # RMK-367 - test that we handle alrdeady stopped commands
        repos = self.openRepository()
        w = worker.Worker(self.rmakeCfg, logger.Logger())
        rc, txt = self.captureOutput(w.stopCommand, 'foo')
        assert(txt.endswith('warning: Asked to stop unknown command foo\n'))

    def testBuildEmptyRecipe(self):
        trv = self.addComponent('empty:source=1',
                                [('empty.recipe', emptyRecipe)])
        job = self.newJob(trv)
        trv = job.iterTroves().next()
        w = worker.Worker(self.rmakeCfg, log)

        b = mock.MockObject()
        eventHandler = builder.EventHandler(job, b)
        w.buildTrove(self.buildCfg, 1, trv, eventHandler, [], [],
                     versions.Label('localhost@rpl:linux'))
        while not trv.isFailed():
            w.serve_once()
        reason = trv.getFailureReason()
        self.assertEquals(str(reason), 'Failed while building: Error building recipe empty:source=/localhost@rpl:linux/1-1[]: Check logs')
        time.sleep(.2)

    def testBuildPrep(self):
        trv = self.addComponent('simple:source=1', 
                        [('simple.recipe', recipes.simpleRecipe)])
        w = worker.Worker(self.rmakeCfg, log)
        job = self.newJob(trv)
        dh = self.getDependencyHandler(job, self.openRepository())
        trv1, = list(job.iterTroves())
        trv1.buildType = buildtrove.TROVE_BUILD_TYPE_PREP

        b = mock.MockObject()
        eventHandler = builder.EventHandler(job, b)
        w.buildTrove(self.buildCfg, 1, trv1, eventHandler, [], [],
                     versions.Label('localhost@rpl:linux'))
        while not trv1.isFinished():
            w.serve_once()
        assert(trv1.isPrepared())
        assert(os.path.exists(self.cfg.root + '/var/rmake/chroots/simple/tmp/rmake/simple-checkout/CONARY'))

emptyRecipe = """
class EmptyRecipe(PackageRecipe):
    name = 'empty'
    version = '1'
    clearBuildReqs()

    def setup(r):
        pass
"""

