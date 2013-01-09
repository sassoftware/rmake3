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
