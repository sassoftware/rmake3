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


from testutils import mock
from testrunner.trial import skipTest
from twisted.internet import defer
from twisted.trial import unittest
from twisted.words.protocols.jabber import jid

from rmake.core import config
from rmake.core import constants as core_const
from rmake.core import dispatcher
from rmake.core import handler
from rmake.core import support
from rmake.core import types
from rmake.lib import pluginlib
from rmake.lib import uuid
from rmake.messagebus import message


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
        self.caps = set([
            types.VersionCapability(tuple(dispatcher.PROTOCOL_VERSIONS)),
            ])

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
            caps = self.caps
            tasks = {}
            slots = {None: 0}
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
            caps = self.caps
            tasks = {}
            slots = {None: 0}
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

    def test_taskScore(self):
        job = self.job
        w = dispatcher.WorkerInfo(jid.JID('ham@spam/eggs'))
        self.disp.workers[w.jid] = w
        self.disp.jobs[job.job_uuid] = handler.JobHandler(self.disp, job)
        msg = message.Heartbeat(caps=[
            types.TaskCapability('task.1'),
            types.ZoneCapability('zone.1'),
            ] + list(self.caps),
            tasks=[], addresses=[], slots={None: 1})
        # Assignable
        w.setCaps(msg)
        result, score = self.disp._scoreTask(types.RmakeTask('task',
            job.job_uuid, 'name', 'task.1', task_zone='zone.1'), w)
        assert result == core_const.A_NOW
        assert score == 1
        # Busy
        w.tasks['bogus'] = 1
        result, score = self.disp._scoreTask(types.RmakeTask('task',
            job.job_uuid,  'name', 'task.1', task_zone='zone.1'), w)
        assert result == core_const.A_LATER
        del w.tasks['bogus']
        # No task
        result, score = self.disp._scoreTask(types.RmakeTask('task',
            job.job_uuid, 'name', 'task.2', task_zone='zone.1'), w)
        assert result == core_const.A_NEVER
        # No zone
        result, score = self.disp._scoreTask(types.RmakeTask('task',
            job.job_uuid, 'name', 'task.1', task_zone='zone.2'), w)
        assert result == core_const.A_WRONG_ZONE
        assert score == None

    def test_workerSupports(self):
        w = dispatcher.WorkerInfo(jid.JID('ham@spam/eggs'))
        msg = message.Heartbeat(caps=[
            types.TaskCapability('task.1'),
            types.ZoneCapability('zone.1'),
            ] + list(self.caps),
            tasks=[], addresses=[], slots={None: 1})
        w.setCaps(msg)
        assert w.supports([types.TaskCapability('task.1')])
        assert w.supports([types.ZoneCapability('zone.1')])
        assert w.supports([types.TaskCapability('task.1'),
            types.ZoneCapability('zone.1')])
        assert not w.supports([types.ZoneCapability('task.1')])
        assert not w.supports([types.TaskCapability('zone.1')])
        assert not w.supports([types.TaskCapability('task.2')])

    def test_zoneNames(self):
        w = dispatcher.WorkerInfo(jid.JID('ham@spam/eggs'))
        msg = message.Heartbeat(caps=[
            types.TaskCapability('task.1'),
            types.ZoneCapability('zone.1'),
            types.ZoneCapability('zone.2'),
            ] + list(self.caps),
            tasks=[], addresses=[], slots={None: 1})
        w.setCaps(msg)
        assert sorted(w.zoneNames) == [
                'zone.1', 'zone.2']


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
