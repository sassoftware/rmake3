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

"""
The dispatcher is responsible for moving a job through the build workflow.

It creates jobs, assigns them to nodes, and monitors the progress of the jobs.
Status updates are routed back to clients and to the database.
"""


import errno
import logging
import os
import random
import stat
from rmake.core import constants as core_const
from rmake.core.database import CoreDB
from rmake.core.support import DispatcherBusService, WorkerChecker
from rmake.core.handler import getHandlerClass
from rmake.core.types import TaskCapability, FrozenObject, JobTimes, JobStatus
from rmake.errors import RmakeError
from rmake.lib import dbpool
from rmake.lib import rpc_pickle
from rmake.lib import uuid
from rmake.lib.apirpc import RPCServer, expose
from rmake.lib.logger import logFailure
from rmake.lib.twisted_extras.firehose import FirehoseResource
from rmake.lib.twisted_extras.ipv6 import TCP6Server
from rmake.messagebus import message
from twisted.application.internet import UNIXServer
from twisted.application.service import MultiService
from twisted.web.resource import Resource
from twisted.web.server import Site


log = logging.getLogger(__name__)


class Dispatcher(MultiService, RPCServer):

    def __init__(self, cfg, plugin_mgr, clock=None):
        MultiService.__init__(self)
        RPCServer.__init__(self)
        self.cfg = cfg

        self.db = None
        self.pool = None
        self.plugins = plugin_mgr
        self.firehose = None

        if clock is None:
            from twisted.internet import reactor
            self.clock = reactor
        else:
            self.clock = clock

        self.jobs = {}
        self.workers = {}
        self.tasks = {}
        self.taskQueue = []

        self.plugins.p.dispatcher.pre_setup(self)
        self._start_db()
        self._start_bus()
        self._start_rpc()
        self.plugins.p.dispatcher.post_setup(self)

    def _start_db(self):
        self.pool = dbpool.ConnectionPool(self.cfg.databaseUrl)
        d = self.pool.start()
        d.addErrback(logFailure, "Error connecting to database:")
        self.db = CoreDB(self.pool)

    def _start_bus(self):
        self.bus = DispatcherBusService(self, self.cfg)
        self.bus.setServiceParent(self)

        WorkerChecker(self).setServiceParent(self)

    def _start_rpc(self):
        root = Resource()
        root.putChild('picklerpc', rpc_pickle.PickleRPCResource(self))
        self.firehose = FirehoseResource()
        root.putChild('firehose', self.firehose)
        site = Site(root, logPath=self.cfg.logPath_http)
        if self.cfg.listenPath:
            try:
                st = os.lstat(self.cfg.listenPath)
            except OSError, err:
                if err.errno != errno.ENOENT:
                    raise
            else:
                if not stat.S_ISSOCK(st.st_mode):
                    raise RuntimeError("Path '%s' exists but is not a socket" %
                            (self.cfg.listenPath,))
                os.unlink(self.cfg.listenPath)

            UNIXServer(self.cfg.listenPath, site).setServiceParent(self)
        if self.cfg.listenPort:
            TCP6Server(self.cfg.listenPort, site,
                    interface=self.cfg.listenAddress).setServiceParent(self)

    ## Client API

    @expose
    def getJobs(self, job_uuids):
        return self.pool.runWithTransaction(self.db.core.getJobs, job_uuids)

    @expose
    def createJob(self, job, callbackInTrans=None, firehose=None):
        """Add the given job the database and start running it.

        @param job: The job to add.
        @type  job: L{rmake.core.types.RmakeJob}
        @param callbackInTrans: A function to call inside the database thread
            to perform additional database operations within the same
            transaction.
        @type  callbackInTrans: C{callable}
        @param firehose: Firehose session ID that will be subscribed to the new
            job.
        @type firehose: C{str}
        @return: C{Deferred} fired with a reconstituted C{RmakeJob} upon
            completion.
        """
        if not isinstance(job.data, FrozenObject):
            job.data = FrozenObject.fromObject(job.data)
        try:
            handlerClass = getHandlerClass(job.job_type)
        except KeyError:
            raise RmakeError("Job type %r is unsupported" % job.job_type)
        handler = handlerClass(self, job)

        if firehose:
            try:
                sid = uuid.UUID(str(firehose))
            except ValueError:
                raise RmakeError("Invalid firehose session ID")
            self.firehose.subscribe(('job', str(job.job_uuid)), sid)

        d = self.db.createJob(job, handler.freeze(), callbackInTrans)
        @d.addCallback
        def post_create(newJob):
            log.info("Job %s of type '%s' started", newJob.job_uuid,
                    newJob.job_type)
            self.jobs[newJob.job_uuid] = handler
            handler.start()

            # Note that the handler will immediately send a new status, so no
            # point in sending it here.
            self._publish(job, 'self', 'created')

            return newJob
        return d

    def _publish(self, job, category, data):
        if not isinstance(job, uuid.UUID):
            job = job.job_uuid
        event = ('job', str(job), category)
        self.firehose.publish(event, data)

    # Job handler API

    def jobDone(self, job_uuid):
        if job_uuid not in self.jobs:
            return

        status = self.jobs[job_uuid].job.status
        if status.completed:
            result = 'done'
        elif status.failed:
            result = 'failed'
        else:
            result = 'finished'
        log.info("Job %s %s: %s", job_uuid, result, status.text)

        self._publish(job_uuid, 'self', 'finalized')

        # Discard tasks that are out for processing
        handler = self.jobs[job_uuid]
        for task_uuid in handler.tasks:
            task_info = self.tasks.pop(task_uuid, None)
            if task_info and task_info.worker:
                log.debug("Discarding task %s from running set", task_uuid)
                task_info.worker.tasks.pop(task_uuid, None)

        # Discard tasks that never got assigned
        for task in self.taskQueue[:]:
            if task.job_uuid == job_uuid:
                log.debug("Discarding task %s from queue", task.task_uuid)
                self.taskQueue.remove(task)

        del self.jobs[job_uuid]

    def updateJob(self, job, frozen_handler=None):
        d = self.db.updateJob(job, frozen_handler=frozen_handler)
        @d.addCallback
        def post_update(newJob):
            if not newJob:
                # Superceded by another update
                return None
            self._publish(newJob, 'status', newJob.status)
            if newJob.status.final:
                self.jobDone(newJob.job_uuid)
            return newJob
        return d

    def createTask(self, task):
        d = self.db.createTask(task)
        def cb_post_create(newTask):
            handler = self.jobs[newTask.job_uuid]
            self.tasks[newTask.task_uuid] = TaskInfo(newTask, handler)
            self.taskQueue.append(newTask)
            self._assignTasks()
            return newTask
        d.addCallback(cb_post_create)

        # Notify handler of initial task status, but not if it already failed
        # because the fail-ing entity will have done so already.
        d.addCallback(self._taskUpdated, onlyIfRunning=True)

        d.addErrback(self._failJob, task.job_uuid)
        return d

    def _failJob(self, failure, job_uuid):
        handler = self.jobs.get(job_uuid)
        if not handler:
            return
        handler.failJob(failure, "Unhandled error in dispatcher:")

    ## Message bus API

    def updateTask(self, task):
        d = self.db.updateTask(task)
        d.addCallback(self._taskUpdated)
        d.addErrback(self._failJob, task.job_uuid)
        d.addErrback(logFailure)

    def _taskUpdated(self, newTask, onlyIfRunning=False):
        if not newTask:
            # Superceded
            return
        # If the task is finished, remove it from the assigned node and try to
        # assign more tasks.
        if newTask.status.final:
            if onlyIfRunning:
                return
            info = self.tasks.pop(newTask.task_uuid, None)
            if info and info.worker:
                info.worker.tasks.pop(newTask.task_uuid, None)
            self.clock.callLater(0, self._assignTasks)
        handler = self.jobs.get(newTask.job_uuid)
        if handler:
            handler.taskUpdated(newTask)

    def workerHeartbeat(self, jid, caps, tasks, slots):
        worker = self.workers.get(jid)
        if worker is None:
            log.info("Worker %s connected", jid.full())
            worker = self.workers[jid] = WorkerInfo(jid)
        worker.setCaps(caps, slots)
        self._assignTasks()

    def workerDown(self, jid):
        worker = self.workers.get(jid)
        if worker is None:
            return
        log.info("Worker %s disconnected", jid.full())

        for info in worker.tasks.itervalues():
            task = info.taskForUpdate()
            task.status = JobStatus(400,
                    "The worker processing this task has gone offline.")
            self.updateTask(task)
        del self.workers[jid]

    def workerLogging(self, records, task_uuid):
        info = self.tasks.get(task_uuid)
        if info is None:
            log.warning("Discarding %d log record(s) from errant task %s",
                    len(records), task_uuid.short)
            return
        log.info("%d record(s) for task %s", len(records), task_uuid.short)

    ## Task assignment

    def _assignTasks(self):
        for task in self.taskQueue[:]:
            result = self._assignTask(task)
            if result != core_const.A_LATER:
                # Task is no longer queued (assigned or failed)
                self.taskQueue.remove(task)
            if result == core_const.A_NOW:
                # Update task now that node_assigned is set.
                self.updateTask(task)

    def _assignTask(self, task):
        """Attempt to assign a task to a node.

        If it is not immediately assignable, it is queued.

        @return: A_NOW if the task was assigned, A_LATER if the task should be
            queued, or A_NEVER if the task cannot be assigned.
        """
        log.debug("Trying to assign task %s of job %s", task.task_uuid,
                task.job_uuid)
        scores = {}
        laters = 0
        for worker in self.workers.values():
            result, score = worker.getScore(task)
            if result == core_const.A_NOW:
                log.debug("Worker %s can run task %s now: score=%s",
                        worker.jid, task.task_uuid, score)
                scores.setdefault(score, []).append(worker.jid)
            elif result == core_const.A_LATER:
                log.debug("Worker %s can run task %s later", worker.jid,
                        task.task_uuid)
                laters += 1
            else:
                log.debug("Worker %s cannot run task %s", worker.jid,
                        task.task_uuid)

        if scores:
            # The task is assignable now.
            best = sorted(scores)[-1]
            jid = random.choice(scores[best])
            self._sendTask(task, jid)
            return core_const.A_NOW
        elif laters:
            # Queue the task for later.
            return core_const.A_LATER
        else:
            # No worker can run this task.
            self._failTask(task, "No workers are capable of running this task.")
            return core_const.A_NEVER

    def _sendTask(self, task, jid):
        log.debug("Assigning task %s to worker %s", task.task_uuid, jid)

        # Internal accounting
        task.node_assigned = jid.full()
        worker = self.workers[jid]
        info = self.tasks[task.task_uuid]
        info.worker = worker
        worker.tasks[task.task_uuid] = info

        # Send the task to the worker node
        msg = message.StartTask(task)
        self.bus.sendTo(jid, msg)

    def _failTask(self, task, message):
        log.error("Task %s failed: %s", task.task_uuid, message)
        text = "Task failed: %s" % (message,)
        task.times.ticks = JobTimes.TICK_OVERRIDE
        task.status.code = core_const.TASK_NOT_ASSIGNABLE
        task.status.text = "Task failed: %s" % (message,)
        self.updateTask(task)


class WorkerInfo(object):

    def __init__(self, jid):
        self.jid = jid
        self.caps = set()
        self.tasks = {}
        self.slots = 0
        # expiring is incremented each time WorkerChecker runs and zeroed each
        # time the worker heartbeats. When it gets high enough, the worker is
        # assumed dead.
        self.expiring = 0

    def setCaps(self, caps, slots):
        self.caps = caps
        self.slots = slots
        self.expiring = 0

    def getScore(self, task):
        """Score how able this worker is to run the given task.

        Returns a tuple of an A_* constant and a number. Higher is better.
        """
        # Does the worker support the given task type?
        for cap in self.caps:
            if not isinstance(cap, TaskCapability):
                continue
            if cap.taskType == task.task_type:
                break
        else:
            return core_const.A_NEVER, None

        # Are there slots available to run this task in?
        assigned = len(self.tasks)
        free = max(self.slots - assigned, 0)
        if free:
            return core_const.A_NOW, free
        else:
            return core_const.A_LATER, None


class TaskInfo(object):

    def __init__(self, task, handler):
        self.task_uuid = task.task_uuid
        self._task = task.freeze()
        self.handler = handler
        self.worker = None

    def taskForUpdate(self):
        task = self._task.thaw()
        task.task_data = None
        task.times.ticks = JobTimes.TICK_OVERRIDE
        return task
