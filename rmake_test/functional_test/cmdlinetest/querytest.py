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
Tests for the rmake info command
"""

import re
import os
import sys
import time
import StringIO


from rmake_test import rmakehelp

from conary.deps import deps

from rmake import failure
from rmake.build import buildcfg
from rmake.cmdline import query

class QueryTest(rmakehelp.RmakeHelper):
    def testQuery(self):
        self.buildCfg.configLine('[x86]')
        client = self.getRmakeHelper()
        db = self.openRmakeDatabase()
        src = self.addComponent('foo:source', '1')
        trv = (src.getNameVersionFlavor() + ('x86',))
        job = self.newJob(trv)
        bt = self.newBuildTrove(job.jobId, *trv)
        job.setBuildTroves([bt])
        rv, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     displayTroves=True, displayDetails=True)
        assert(txt.split() == '''\
1      State:    Initialized         
       Status:   JobID entry created 
       To Build: 1                    Building: 0
       Built:    0                    Failed:   0

       foo:source=:linux/1-1{x86}
         State: Initialized         

'''.split())
        job.jobStarted('Started')
        bt.troveBuildable()
        rv, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     displayTroves=True, displayDetails=True)
        txt = re.sub('Started: .*Build Time:.*', 'Started:  TIME', txt)
        assert(txt.split() == '''\
1      State:    Started             
       Status:   Started             
       Started:  TIME
       To Build: 1                    Building: 0
       Built:    0                    Failed:   0

       foo:source=:linux/1-1{x86}
         State: Buildable           

'''.split())
        job.jobBuilding(bt.getName())
        bt.troveBuilding()
        rv, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     displayTroves=True, displayDetails=True)
        txt = re.sub('Start: .*Build time:.*', 'Start: TIME', txt)
        txt = re.sub('Started: .*Build Time:.*', 'Started:  TIME', txt)

        assert(txt.split() == '''\
1      State:    Building            
       Status:   foo:source          
       Started:  TIME
       To Build: 0                    Building: 1
       Built:    0                    Failed:   0

       foo:source=:linux/1-1{x86}
         State: Building            
         Start: TIME

'''.split())
        job.jobFailed('troves failed')
        bt.troveMissingBuildReqs([('foo:run', None, deps.parseFlavor(''))])
        rv, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     displayTroves=True, displayDetails=True)
        txt = re.sub('Start: .*Build time:.*', 'Start: TIME', txt)
        txt = re.sub('Started: .*Build Time:.*', 'Started:  TIME', txt)
        assert(txt.split() == '''\
1      State:    Failed
       Status:   Failed while building: troves failed
       Started:  TIME
       To Build: 0                    Building: 0
       Built:    0                    Failed:   1

       foo:source=:linux/1-1{x86}
         State: Failed
         Start: TIME
         Status: Could not satisfy build requirements: foo:run=[]

'''.split())
        rv, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     displayTroves=True)
        assert(txt.split() == '''\
1     Failed                    just now
      (1 troves) foo

     Failed Troves [1]:
     foo[]


'''.split())
        bt.trovePrebuilt([], [])
        rv, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     displayTroves=True)
        assert(txt.split() == '''\
1     Failed                    just now
      (1 troves) foo

     Prebuilt Troves [1]:
     foo[]


'''.split())


        bt.troveMissingBuildReqs([('foo:run', None, deps.parseFlavor(''))],
                                 False)
        rv, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     displayTroves=True)
        assert(txt.split() == '''\
1     Failed                    just now
      (1 troves) foo

     Unbuildable Troves [1]:
     foo[]


'''.split())

        rv, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     showConfig=True)
        sio = StringIO.StringIO(txt)
        txtarr = [ x.strip() for x in sio.readlines() ]
        self.failUnlessIn('[x86]', txtarr)
        # Make sure we can read the config
        ncfg = buildcfg.BuildConfiguration(readConfigFiles=False)
        sio.seek(0)
        ncfg.readObject('/some/path', sio)
        self.failUnless(ncfg.hasSection('x86'))

        # Now display config for just one trove
        rv, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     troveSpecs=['foo'], showConfig=True)
        sio = StringIO.StringIO(txt)
        txtarr = [ x.strip() for x in sio.readlines() ]
        self.failUnlessEqual(txtarr[2], '[x86]')

    def testQueryTracebacks(self):
        client = self.getRmakeHelper()
        db = self.openRmakeDatabase()
        src = self.addComponent('foo:source', '1')
        job = self.newJob(src)
        bt = self.newBuildTrove(job.jobId, *src.getNameVersionFlavor())
        job.setBuildTroves([bt])
        bt.troveFailed(failure.BuildFailed('failed text', 
                                           'exception\noutput\n'))
        rv, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     showTracebacks=True)
        assert(txt.split() == '''\
1     Initialized
      (1 troves) foo
       foo:source=:linux/1-1
         State: Failed
         Status: Failed while building: failed text

exception
output
'''.split())

    def testList(self):
        client = self.getRmakeHelper()
        db = self.openRmakeDatabase()
        src = self.addComponent('foo:source', '1')
        job = self.newJob(src)
        rv, txt = self.captureOutput(query.displayJobInfo, client)
        assert(txt == '1     Initialized               \n'
                      '      (1 troves) foo\n')

    def testLimit(self):
        client = self.getRmakeHelper()
        db = self.openRmakeDatabase()
        src = self.addComponent('foo:source', '1')
        job = self.newJob(src)
        job.jobBuilding('Building')
        job2 = self.newJob(src)
        job3 = self.newJob(src)
        rv, txt = self.captureOutput(query.displayJobInfo, client, jobLimit=2)
        assert(txt == '2     Initialized               \n'
                      '      (1 troves) foo\n'
                      '3     Initialized               \n'
                      '      (1 troves) foo\n')
        rv, txt = self.captureOutput(query.displayJobInfo, client, jobLimit=1, 
                                     activeOnly=True)
        assert(txt == '1     Building                  \n'
                      '      (1 troves) foo\n')


    def testQueryTimes(self):
        assert(query.getTimeDifference(3) == '3 secs')
        assert(query.getTimeDifference(0) == '0 secs')
        assert(query.getTimeDifference(61) == '1 min, 1 sec')
        assert(query.getTimeDifference(125) == '2 mins, 5 secs')
        assert(query.getTimeDifference(3600) == '1 hour')
        assert(query.getTimeDifference(3620) == '1 hour')
        assert(query.getTimeDifference(3664) == '1 hour, 1 min')

        def _test(diff, expected):
            self.assertEquals(query.getOldTime(time.time() - diff), expected)
        _test(60 * 60 * 24 * 15, '2 weeks ago')
        _test(60 * 60 * 24 * 10, '1 week ago')
        _test(60 * 60 * 24 * 4, '4 days ago')
        _test(60 * 60 * 24, '1 day, 0 hours ago')
        _test(60 * 60 * 10, '10 hours ago')
        _test(60 * 50, '50 minutes ago')
        _test(50, 'just now')

    def testMultiContext(self):
        client = self.getRmakeHelper()
        db = self.openRmakeDatabase()
        tuple = self.makeTroveTuple('foo:source')
        job = self.newJob()
        bt = self.newBuildTrove(job.jobId, *(tuple + ('foo',)))
        bt2 = self.newBuildTrove(job.jobId, *tuple)
        job.setBuildTroves([bt, bt2])
        theJob, troveList = query.getJobsToDisplay(query.DisplayConfig(client),
                                            client,
                                            job.jobId, ['foo{foo}'])[0]
        troves = [ theJob.getTrove(*x) for x in troveList]
        assert(len(troves) == 1)
        assert(troves[0].getContext() == 'foo')
        theJob, troveList = query.getJobsToDisplay(query.DisplayConfig(client),
                                            client,
                                            job.jobId, ['foo{}'])[0]
        troves = [ theJob.getTrove(*x) for x in troveList]
        assert(len(troves) == 1)
        assert(troves[0].getContext() == '')
        theJob, troveList = query.getJobsToDisplay(query.DisplayConfig(client),
                                            client,
                                            job.jobId, ['foo'])[0]
        troves = [ theJob.getTrove(*x) for x in troveList]
        assert(len(troves) == 2)
        rv, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     displayTroves=True)
 
    def testShowBuildLogs(self):
        client = self.getRmakeHelper()
        db = self.openRmakeDatabase()
        tuple = self.makeTroveTuple('foo:source')
        job = self.newJob((tuple + ('foo',)), tuple)
        job = self.newJob((tuple + ('foo',)), tuple)
        bt = job.getTrove(*(tuple + ('foo',)))
        bt2 = job.getTrove(*tuple)
        bt.logPath = self.workDir + '/foo1'
        bt.troveBuilding()
        btFromDb = db.getTrove(job.jobId, *bt.getNameVersionFlavor(True))
        assert(bt.logPath == btFromDb.logPath)
        self.writeFile(bt.logPath, 'foo\nbar\n')
        bt.troveFailed('Failure reason')
        bt2.troveFailed('Failure reason', isPrimaryFailure=False)
        rc, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     ['foo{foo}'], showBuildLogs=True)
        txt = re.sub('Start: .*Build time:.*', 'Start: TIME', txt)
        self.assertEquals(txt.split(), '''2     Initialized               
       foo:source=:linux/1-1{foo}
         State: Failed           
         Start: TIME
         Status: Failed while building: Failure reason

foo
bar

'''.split())
        rc, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     [], showBuildLogs=True)
        txt = re.sub('Start: .*Build time:.*', 'Start: TIME', txt)
        self.assertEquals(txt.split(), '''2     Initialized               
      (1 troves) foo
       foo:source=:linux/1-1
         State: Unbuildable         
         Status: Failed while building: Failure reason
No build log.
       foo:source=:linux/1-1{foo}
         State: Failed              
         Start: TIME
         Status: Failed while building: Failure reason

foo
bar

'''.split())

    def testShowLogs(self):
        tuple = self.makeTroveTuple('foo:source')
        job = self.newJob()
        bt = self.newBuildTrove(job.jobId, *(tuple + ('foo',)))
        bt2 = self.newBuildTrove(job.jobId, *tuple)
        client = self.getRmakeHelper()
        db = self.openRmakeDatabase()
        tuple = self.makeTroveTuple('foo:source')
        job = self.newJob()
        bt = self.newBuildTrove(job.jobId, *(tuple + ('foo',)))
        bt2 = self.newBuildTrove(job.jobId, *tuple)
        job.setBuildTroves([bt, bt2])
        bt.troveBuilding()
        bt2.troveBuilding()
        bt.log('foo')
        bt.log('bar')
        job.log('bam')
        rc, txt = self.captureOutput(query.displayJobInfo, client, job.jobId,
                                     ['foo{foo}'], showLogs=True, displayDetails=True)
        txt = re.sub('Start: .*Build time:.*', 'Start: TIME', txt)
        txt = re.sub('\[[^]]*\]', '[TIME]', txt)
        assert(txt.split() == '''\
2      State:    Initialized
       Status:
       To Build: 0                    Building: 2
       Built:    0                    Failed:   0

[TIME] bam
       foo:source=:linux/1-1{foo}
         State: Building
         Start: TIME
[TIME] foo
[TIME] bar
'''.split())
