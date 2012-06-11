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
