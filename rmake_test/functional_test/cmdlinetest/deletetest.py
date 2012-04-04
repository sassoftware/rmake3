# -*- mode: python -*-
#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

"""
Tests for the rmake delete command
"""

import re
import os
import shutil
import sys
import time


from conary_test import recipes
from rmake_test import rmakehelp

from rmake import errors
from rmake.cmdline import monitor
from rmake.build import subscriber

class DeleteTest(rmakehelp.RmakeHelper):
    def _subscribeServer(self, client, job):
        subscriber._RmakeServerPublisherProxy(client.uri).attach(job)

    def testDelete(self):
        db = self.openRmakeDatabase()
        self.openRmakeRepository()
        repos = self.openRepository()
        client = self.startRmakeServer()

        atrv = self.Component('a:source')[0]
        trv, cs = self.Component('a:runtime')
        job = self.newJob(atrv)

        db.subscribeToJob(job)
        self._subscribeServer(client, job)
        a, = buildTroves = self.makeBuildTroves(job)
        job.jobStarted('')
        job.setBuildTroves(buildTroves)

        logPath = self.workDir + '/abuildlog'
        alog = open(logPath, 'w')
        alog.write('Log1\n')
        alog.flush()
        a.logPath = logPath
        a.troveBuilding()
        alog.flush()
        a.troveBuilt([x.getNewNameVersionFlavor() 
                      for x in cs.iterNewTroveList()])
        self.assertRaises(errors.RmakeError, client.deleteJobs, [job.jobId])
        job.jobPassed('')
        client.deleteJobs([job.jobId])
        self.assertRaises(errors.JobNotFound, client.getJob, job.jobId)

