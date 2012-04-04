# -*- mode: python -*-
#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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

from rmake.cmdline import monitor
from rmake.build import subscriber
from rmake import failure

class MonitorTest(rmakehelp.RmakeHelper):
    def _subscribeServer(self, client, job, multinode=False):
        if multinode:
            from rmake_plugins.multinode.build import builder
            from rmake.multinode.server import subscriber
            client = builder.BuilderNodeClient(self.rmakeCfg, job.jobId,
                                                 job)
            publisher = subscriber._RmakeBusPublisher(client)
            publisher.attach(job)
            while not client.bus.isRegistered():
                client.serve_once()
            return publisher
        else:
            from rmake.build import subscriber
            subscriber._RmakeServerPublisherProxy(client.uri).attach(job)

    def testMonitor(self):
        self._testMonitor(multinode=False)

    def testMonitorMultinode(self):
        self._testMonitor(multinode=True)

    def _testMonitor(self, multinode):
        _check = self.checkMonitor

        def _checkLog(m, log):
            rc, txt = self.captureOutput(m._serveLoopHook)
            assert(log == txt)

        self.openRmakeRepository()
        repos = self.openRepository()
        client = self.startRmakeServer(multinode=multinode)
        if multinode:
            self.startNode()

        atrv = self.Component('a:source')[0]
        self.addComponent('a:runtime')
        btrv = self.Component('b:source')[0]
        ctrv = self.Component('c:source')[0]
        dtrv = self.Component('d:source')[0]
        etrv = self.Component('e:source')[0]


        port = testsuite.findPorts()[0]
        monitorUri = 'http://localhost:%s/conary' % port
        self.logFilter.add()

        job = self.newJob(atrv, btrv, ctrv, dtrv, etrv)
        m = monitor.monitorJob(client, job.jobId, serve=False,
                               showBuildLogs=True, showTroveDetails=True)
        db = self.openRmakeDatabase()
        a,b,c,d,e = buildTroves = self.makeBuildTroves(job)
        c.addBuildRequirements(['b:runtime'])
        d.addBuildRequirements(['a:runtime'])
        e.addBuildRequirements(['d:runtime'])

        db.subscribeToJob(job)

        job.setBuildTroves(buildTroves)
        dh = self.getDependencyHandler(job, repos)

        publisher = self._subscribeServer(client, job, multinode)
        if not multinode:
            m.subscribe(job.jobId)
        job.log('foo')
        _check(m, '[TIME] [1] foo\n')
        job.jobQueued()
        _check(m, '[TIME] [1] - State: Queued\n[TIME] [1] - Job Queued\n')
        job.jobStarted('foo')
        _check(m, '[TIME] [1] - State: Started\n[TIME] [1] - foo\n')
        job.jobBuilding('foo')
        _check(m, '[TIME] [1] - State: Building\n[TIME] [1] - foo\n')

        job.jobPassed('foo')
        _check(m, '[TIME] [1] - State: Built\n[TIME] [1] - foo\n')
        #job.jobFailed('foo')
        #_check(m, '[TIME] [1] - State: Failed\n[TIME] [1] - Failed while building: foo\n')

        # test of basic trove handling + dephandler cascading failures
        b.log('bar')
        _check(m, '[TIME] [1] - b:source - bar\n')
        b.troveBuildable()
        _check(m, '[TIME] [1] - b:source - State: Buildable\n')
        b.creatingChroot('_local_', 'path')
        _check(m, ['[TIME] [1] - b:source - State: Creating Chroot\n',
                   '[TIME] [1] - b:source - Chroot at path\n'])
        trv, cs = self.Component('b:runtime', requires='trove: a:runtime')
        repos.commitChangeSet(cs)
        b.troveBuilt([x.getNewNameVersionFlavor() for x in cs.iterNewTroveList()])
        dh.updateBuildableTroves(limit=2)# limit=2 should make sure that
                                         # c's dependence on a is found early
        _check(m, ['[TIME] [1] - b:source - State: Built\n'
                   '[TIME] [1] - c:source - Resolved buildreqs include 1 other troves scheduled to be built - delaying: \n',
                   'a:source=/localhost@rpl:linux/1.0-1[]{}\n',
                   '[TIME] [1] - a:source - State: Buildable\n',
                   '[TIME] [1] - c:source - State: Initialized',])
        logPath = self.workDir + '/abuildlog'
        alog = open(logPath, 'w')
        alog.write('Log1\n')
        alog.flush()
        a.logPath = logPath
        a.troveBuilding()
        _check(m, '[TIME] [1] - a:source - State: Building\n'
                  'Tailing a:source build log:\n\n')

        # check to make sure tailing the log works as expected
        _checkLog(m, 'Log1\n')
        alog.write('Log2\n')
        alog.flush()
        _checkLog(m, 'Log2\n')
        u = unichr(40960) + u'abcd' + unichr(1972) + '\n'
        alog.write(u.encode('utf-8'))
        alog.flush()
        _checkLog(m, '\xea\x80\x80abcd\xde\xb4\n')
        alog.write('\xe9")')
        alog.flush()
        _checkLog(m, '\xe9")')
        a.troveFailed(failure.BuildFailed('foo', 'bar'))
        
        _check(m,[
  '[TIME] [1] - a:source - State: Failed\n'
  '[TIME] [1] - a:source - Failed while building: foo\n'
  '[TIME] [1] - c:source - State: Unbuildable\n'
  '[TIME] [1] - c:source - Could not satisfy dependencies:\n'
  '    c:source=/localhost@rpl:linux/1.0-1[] requires:\n'
  '	trove: a:runtime\n'
  '[TIME] [1] - d:source - State: Unbuildable\n'
  '[TIME] [1] - d:source - Could not satisfy build requirements: a:runtime=[]\n'
  '[TIME] [1] - e:source - State: Unbuildable\n'
  '[TIME] [1] - e:source - Could not satisfy build requirements: d:runtime=[]\n'],
  events=1)
        _check(m, '', .1)

    def testMonitorFromFrontEnd(self):
        self._testMonitorFromFrontEnd(multinode=False)

    def testMonitorFromFrontEndMultinode(self):
        self._testMonitorFromFrontEnd(multinode=True)

    def _testMonitorFromFrontEnd(self, multinode):
        #raise testsuite.SkipTestException
        # full test of monitor, from job start to job finished
        # we just gather the transcript
        self.openRmakeRepository()
        repos = self.openRepository()
        client = self.startRmakeServer(multinode=multinode)
        if multinode:
            self.startNode()
        helper = self.getRmakeHelper(uri=client.uri)
        trv = self.addComponent('testcase:source', '1.0-1', '',
                                [('testcase.recipe', """\
class TestRecipe(PackageRecipe):
    name = 'testcase'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        r.Create('/foo', contents='foo')
""")])
        jobId, txt = self.captureOutput(helper.buildTroves,
                           ['%s=%s[%s]' % trv.getNameVersionFlavor()])
        rc, txt = self.captureOutput(helper.poll, jobId, showTroveLogs=True, 
                           showBuildLogs=True)
        txt = re.sub('\[[0-9][0-9]:[0-9][0-9]:[0-9][0-9] ?(AM|PM)?\]', '[TIME]', txt)
        txt = re.sub('\[[0-9- ]*[0-9][0-9]:[0-9][0-9]:[0-9][0-9] ?(AM|PM)?\]', '[TIME]', txt)
        txt = re.sub('pid [0-9]+', 'pid PID', txt)
#        assert('''\
#[TIME] [1] - State: Started''' in txt)
        assert('''\
[TIME] [1] - Starting Build 1 (pid PID)''' in txt)
        assert('''\
[TIME] [1] - testcase:source - State: Buildable
[TIME] [1] - Building testcase:source
        ''')
        assert('''\
[TIME] [1] - testcase:source - State: Building
'''  in txt)
        assert('''\
[TIME] [1] - testcase:source - State: Built
''' in txt)
        assert('+ pathId lookup complete\n' in txt)
        assert('''\
[TIME] [1] - State: Built
[TIME] [1] - build job finished successfully
''' in txt)


    def testPrimingMonitorOutput(self):
        self._testPrimingMonitorOutput(multinode=False)

    def testPrimingMonitorOutputMultinode(self):
        self._testPrimingMonitorOutput(multinode=True)

    def _testPrimingMonitorOutput(self, multinode):
        db = self.openRmakeDatabase()
        self.openRmakeRepository()
        repos = self.openRepository()
        client = self.startRmakeServer(multinode=multinode)
        if multinode:
            self.startNode()

        atrv = self.Component('a:source')[0]

        port = testsuite.findPorts()[0]
        monitorUri = 'http://localhost:%s/conary' % port
        job = self.newJob(atrv)
        m = monitor.monitorJob(client, job.jobId, serve=False,
                               showBuildLogs=True, showTroveDetails=True,
                               uri=monitorUri)
        a, = buildTroves = self.makeBuildTroves(job)

        self._subscribeServer(client, job, multinode)

        job.setBuildTroves(buildTroves)
        dh = self.getDependencyHandler(job, repos)
        job.log('foo1')
        job.log('foo2')


        logPath = self.workDir + '/logPath'
        log = open(logPath, 'w')

        a.logPath = logPath
        a.troveBuilding()

        if multinode:
            rc, txt = self.captureOutput(m.listener._primeOutput, job.jobId)
        else:
            rc, txt = self.captureOutput(m.subscribe, job.jobId)
        assert('foo1' in txt)
        assert('foo2' in txt)
        rc, txt = self.captureOutput(m._serveLoopHook)
        assert(txt == '')
        rc, txt = self.captureOutput(m._serveLoopHook)
        assert(txt == '')
        log.write('bar\nbam\n')
        log.close()
        rc, txt = self.captureOutput(m._serveLoopHook)
        assert(txt == 'bar\nbam\n')



