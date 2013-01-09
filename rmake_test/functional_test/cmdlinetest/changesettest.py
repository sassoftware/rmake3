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
Tests for the rmake poll command

The goal here is to test subscriptions rMake Server -> monitor

We control the build job here, and we control the monitor loops so that
we can see the output as it happens.

"""

import re
import os
import sys
import time


from rmake_test import rmakehelp

from rmake import failure
from rmake.cmdline import monitor

class ChangesetTest(rmakehelp.RmakeHelper):
    def testChangeset(self):
        self.openRmakeRepository()
        repos = self.openRepository()
        client = self.startRmakeServer()
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', """\
class TestRecipe(PackageRecipe):
    name = 'testcase'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        r.Create('/foo', contents='foo')
""")])
        jobId = client.buildTroves([trv.getNameVersionFlavor()], self.buildCfg)
        timeSlept = 0
        while timeSlept < 60:
            if client.getJob(jobId, withTroves=False).isFinished():
                break
            else:
                time.sleep(.3)
                timeSlept += .3
        assert(timeSlept < 60)
        helper = self.getRmakeHelper(client.uri)
        path = self.workDir + '/changeset.ccs'
        cs = helper.createChangeSet(jobId)
        assert(len(cs.getPrimaryTroveList()) == 1)
        assert(cs.getPrimaryTroveList()[0][0] == 'testcase')
