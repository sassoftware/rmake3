#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#


from testutils import mock
from testrunner.trial import skipTest
from twisted.internet import defer
from twisted.trial import unittest
from twisted.words.protocols.jabber import jid

from rmake.core import config
from rmake.core import dispatcher
from rmake.core import support
from rmake.core import types
from rmake.lib import pluginlib
from rmake.lib import uuid


class DispatcherTest(unittest.TestCase):

    def setUp(self):
        self.cfg = config.DispatcherConfig()
        self.plugins = pluginlib.PluginManager()

        mock.mock(dispatcher.Dispatcher, '_start_db')
        mock.mock(dispatcher.Dispatcher, '_start_filestore')
        mock.mock(dispatcher.Dispatcher, '_start_bus')
        mock.mock(dispatcher.Dispatcher, '_start_rpc')

        self.disp = dispatcher.Dispatcher(self.cfg, self.plugins)
        self.disp.bus = mock.MockObject()
        self.disp.db = mock.MockObject()
        self.disp.firehose = mock.MockObject()
        self.disp.jobLogger = mock.MockObject()

        self.job = types.RmakeJob(
                uuid.uuid4(), 'test', 'spam', data='ham').freeze()

    def tearDown(self):
        mock.unmockAll()

    def test_getJobs(self):
        job = self.job
        def db_getJobs(job_uuids):
            self.assertEquals(job_uuids, [job.job_uuid])
            return defer.succeed([job])
        self.disp.db._mock.set(getJobs=db_getJobs)

        d = self.disp.getJobs([job.job_uuid])
        assert isinstance(d, defer.Deferred)

        def callback(result):
            self.assertEquals(result, [job])
        d.addCallback(callback)
        return d

    def test_createJob(self):
        job = self.job

        mock.mock(dispatcher, 'getHandlerClass')
        dispatcher.getHandlerClass._mock.setReturn(MockHandler, 'test')

        saved = []
        def db_createJob(newJob, frozen_handler, callback=None):
            self.assertEqual(job.job_uuid, newJob.job_uuid)
            ret = newJob.freeze()
            saved.append(ret)
            return defer.succeed(ret)
        self.disp.db._mock.set(createJob=db_createJob)

        fh_uuid = uuid.uuid4()
        d = self.disp.createJob(job, firehose=str(fh_uuid))
        assert isinstance(d, defer.Deferred)

        def callback(result):
            handler = self.disp.jobs.values()[0]
            self.assertEqual(handler.job.freeze(), saved[0])
            self.assertEqual(handler.started, True)

            self.disp.firehose.subscribe._mock.assertCalled(
                    ('job', str(job.job_uuid)), fh_uuid)
            self.disp.firehose.publish._mock.assertCalled(
                    ('job', str(job.job_uuid), 'self'), 'created')
        d.addCallback(callback)
        return d

    def test_getWorkerList(self):
        jid1 = u'foo@bar/baz'
        jid2 = u'ham@spam/eggs'
        self.disp.bus.getNeighborList._mock.setReturn(
                [jid.JID(jid1), jid.JID(jid2)])
        result = self.disp.getWorkerList()
        self.assertEquals(result, {jid1: None, jid2: None})

    def test_updateJob_normal(self):
        job = self.job.thaw()
        job.status.code = 100
        def db_updateJob(newJob, frozen_handler):
            self.assertEquals(newJob.job_uuid, job.job_uuid)
            self.assertEquals(frozen_handler, None)
            return defer.succeed(newJob.freeze())
        self.disp.db._mock.set(updateJob=db_updateJob)
        mock.mockMethod(self.disp.jobDone)

        d = self.disp.updateJob(job)
        assert isinstance(d, defer.Deferred)

        def callback(result):
            self.assertEquals(result, job.freeze())
            self.disp.jobDone._mock.assertNotCalled()
        d.addCallback(callback)
        return callback

    def test_updateJob_finished(self):
        job = self.job.thaw()
        job.status.code = 200
        def db_updateJob(newJob, frozen_handler):
            self.assertEquals(newJob.job_uuid, job.job_uuid)
            self.assertEquals(frozen_handler, None)
            return defer.succeed(newJob.freeze())
        self.disp.db._mock.set(updateJob=db_updateJob)
        mock.mockMethod(self.disp.jobDone)

        d = self.disp.updateJob(job)
        assert isinstance(d, defer.Deferred)

        def callback(result):
            self.assertEquals(result, job.freeze())
            self.disp.jobDone._mock.assertCalled(job.job_uuid)
        d.addCallback(callback)
        return callback

    def test_workerHeartbeat(self):
        w = jid.JID('ham@spam/eggs')
        class h_msg(object):
            caps = set()
            tasks = {}
            slots = 0
            addresses = set()
        heartbeat = dict(jid=w, msg=h_msg())

        self.assertEqual(self.disp.workers, {})

        self.disp.workerHeartbeat(**heartbeat)
        self.assertEqual(self.disp.workers.keys(), [w])
        self.assertEqual(self.disp.workers[w].jid, w)

        self.disp.workerHeartbeat(**heartbeat)
        self.assertEqual(self.disp.workers.keys(), [w])

        self.disp.workerDown(w)
        self.assertEqual(self.disp.workers, {})

    @skipTest("Not done yet.")
    def test_workerHeartbeat_assignTasks(self):
        """Tasks are assigned to a new worker, and failed on a dead worker."""

    def test_workerHeartbeat_timeout(self):
        """A worker fails to heartbeat for a given interval."""
        w = jid.JID('ham@spam/eggs')
        class h_msg(object):
            caps = set()
            tasks = {}
            slots = 0
            addresses = set()
        self.disp.workerHeartbeat(w, h_msg())
        self.assertEqual(self.disp.workers[w].jid, w)

        checker = support.WorkerChecker(self.disp)
        for x in range(4):
            checker.checkWorkers()
        self.assertEqual(self.disp.workers[w].jid, w)

        checker.checkWorkers()
        self.assertEqual(self.disp.workers, {})

    def test_workerLogging(self):
        task_uuid = uuid.uuid4()
        records = ['log records go here']
        self.disp.tasks[task_uuid] = None
        self.disp.workerLogging(records, task_uuid)
        self.disp.jobLogger.emitMany._mock.assertCalled(records)


class WorkerTest(unittest.TestCase):

    def test_supports(self):
        worker = dispatcher.WorkerInfo(None)
        worker.caps = set(['a', 'b', 'c'])
        assert worker.supports(['a', 'b'])
        assert not worker.supports(['a', 'd'])



class MockHandler(object):

    def __init__(self, disp, job):
        self.job = job

    def start(self):
        self.started = True
