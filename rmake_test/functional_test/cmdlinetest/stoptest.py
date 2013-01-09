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
Tests for the rmake stop command

Test to make sure when we try to stop:
    running jobs all processes are stopped, and reasonable messages are sent
    stopped jobs rmake gives a reasonable error

Also should check to make sure that when we ctrl-C this (test) process,
all of the server processes get killed.  Also, when we ctrl-C the server.
"""

import re
import os
import shutil
import sys
import time


from conary_test import recipes
from rmake_test import rmakehelp

from rmake import errors

class StopTest(rmakehelp.RmakeHelper):
    def testStopJobs(self):
        raise testsuite.SkipTestException
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', """\
class TestRecipe(PackageRecipe):
    name = 'testcase'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        r.Run('sleep 180')
""")])
        trv2 = self.addComponent('testcase2:source', '1.0-1', '',
                                [('testcase2.recipe', """\
class TestRecipe(PackageRecipe):
    name = 'testcase2'
    version = '1.0'

    clearBuildReqs()
    buildRequires = ['testcase:runtime']
    def setup(r):
        r.Run('sleep 180')
""")])

        self.openRmakeRepository()
        client = self.startRmakeServer()

        jobId = client.buildTroves([trv.getNameVersionFlavor(),
                                    trv2.getNameVersionFlavor()], self.buildCfg)
        job = client.getJob(jobId, withTroves=False)
        timeSlept = 0
        while timeSlept < 9000:
            job = client.getJob(jobId, withTroves=True)
            troves = list(job.iterTroves())
            if [ x for x in troves if x.isBuilding() ]:
                break
            time.sleep(1)
            timeSlept += 1
        assert(timeSlept < 20)

        timeSlept = 0
        while timeSlept < 6000:
            # get all the chroot server processes
            pipeFD = os.popen("/sbin/pidof -x rootserver.py")
            pids = pipeFD.read().split()
            pipeFD.close()
            pipeFD = os.popen("/sbin/pidof -x %s" % sys.argv[0])
            pids += pipeFD.read().split()
            pipeFD.close()
            chrootPids = []
            serverPids = []
            parentPids = {}
            pids = [int(x) for x in pids]
            toRemove = []

            for pid in pids:
                if not os.path.exists('/proc/%s/status' % pid):
                    toRemove.append(pid)
                    continue
                for ln in open('/proc/%s/status' % pid, 'r'):
                    if ln.startswith('PPid'):
                        parentPid = int(ln.split()[1].strip())
                        parentPids[pid] = [parentPid]
                        break
            pids = [ x for x in pids if x not in toRemove]
            for pid in pids:
                parentPid = parentPids[pid][-1]
                if parentPid in parentPids:
                    parentPids[pid].extend(parentPids[parentPid])

            knownPids = self._getPids()
            for pid in pids:
                if (pid not in knownPids and 
                    not [ x for x in parentPids[pid] if x in knownPids]):
                    continue
                try:
                    argv = open('/proc/%s/cmdline' %pid).read().split('\x00')
                except IOError:
                    continue
                if os.path.realpath(argv[0]) != sys.executable:
                    continue
                if argv[1] == \
                    (self.rmakeCfg.buildDir + '/chroots/testcase/usr/share/rmake/rmake/worker/chroot/rootserver.py'):
                    chrootPids.append(pid)
                elif argv[1] == sys.argv[0]:
                    serverPids.append(pid)

            #assert(len(chrootPids) <= 3)
            if (len(chrootPids) >= 3): # chroot server + cook job + logger
                                       # if there are any extra ones they're
                                       # probably from an earlier build
                break
            else:
                timeSlept += 1
                time.sleep(1)

        m = self.getMonitor(client, showTroveLogs=False,
                                    showBuildLogs=False, jobId=jobId)

        client.stopJob(jobId)
        print "Waiting for all processes to die...."
        timeSlept = 0
        while timeSlept < 6000:
            for pid in list(chrootPids) + list(serverPids):
                try:
                    open('/proc/%s' % pid)
                except IOError:
                    # either the directory doesn't exist, or we don't have permission to 
                    # access it
                    if pid in chrootPids:
                        chrootPids.remove(pid)
                    else:
                        serverPids.remove(pid)
            if not chrootPids and len(serverPids) <= 4:
                break
            else:
                time.sleep(.5)
                timeSlept += .5

        self.checkMonitor(m, ['[TIME] [1] - State: Failed\n'
                          #'[TIME] [1] - Stopped: User requested stop\n'
                          ],
                          ignoreExtras=True)
        try:
            client.stopJob(jobId)
        except errors.RmakeError, err:
            assert(str(err) == 'Cannot stop job %s - it is already stopped' % jobId)

        test1 = [ x for x in client.getJob(jobId).iterTroves() if x.getName() == 'testcase:source'][0]
        assert(test1.isFailed())

    def testStopQueuedJob(self):
        trv = self.addComponent('a:source', '1.0')
        helper = self.getRmakeHelper()
        job = self.newJob(trv)
        job.jobQueued()
        helper.stopJob(job.jobId)
        assert(helper.client.getJob(job.jobId).isFailed())
