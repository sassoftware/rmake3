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


import copy
import errno
import logging
import os
import random
import stat
from rmake.core import constants as core_const
from rmake.core.config import DispatcherConfig
from rmake.core.dispatcher_support import DispatcherBusService, WorkerChecker
from rmake.core.handler import getHandlerClass
from rmake.core.types import TaskCapability
from rmake.db import database
from rmake.errors import RmakeError
from rmake.lib import dbpool
from rmake.lib import rpc_pickle
from rmake.lib.apirpc import RPCServer, expose
from rmake.lib.daemon import setDebugHook
from rmake.lib.logger import logFailure
from rmake.lib.twisted_extras.ipv6 import TCP6Server
from rmake.messagebus import message
from twisted.application.internet import UNIXServer
from twisted.application.service import MultiService
from twisted.internet import defer
from twisted.web.resource import Resource
from twisted.web.server import Site


log = logging.getLogger(__name__)


class Dispatcher(MultiService, RPCServer):

    def __init__(self, cfg, plugins=()):
        MultiService.__init__(self)

        # Get additional RPC namespaces from plugins
        rpc_children = {}
        for plugin in plugins:
            rpc_children.update(plugin.getRPCNamespaces())
        RPCServer.__init__(self, rpc_children)

        self.pool = dbpool.ConnectionPool(cfg.databaseUrl)
        self.db = database.Database(cfg.databaseUrl,
                dbpool.PooledDatabaseProxy(self.pool))

        self.bus = DispatcherBusService(self, cfg)
        self.bus.setServiceParent(self)

        self.jobs = {}
        self.workers = {}
        self.taskQueue = []

        WorkerChecker(self).setServiceParent(self)

        root = Resource()
        root.putChild('picklerpc', rpc_pickle.PickleRPCResource(self))
        site = Site(root, logPath=cfg.logPath_http)
        if cfg.listenPath:
            try:
                st = os.lstat(cfg.listenPath)
            except OSError, err:
                if err.errno != errno.ENOENT:
                    raise
            else:
                if not stat.S_ISSOCK(st.st_mode):
                    raise RuntimeError("Path '%s' exists but is not a socket" %
                            (cfg.listenPath,))
                os.unlink(cfg.listenPath)

            UNIXServer(cfg.listenPath, site).setServiceParent(self)
        if cfg.listenPort:
            TCP6Server(cfg.listenPort, site, interface=cfg.listenAddress
                    ).setServiceParent(self)

    ## Client API

    @expose
    def getJobs(self, callData, job_uuids):
        return self.pool.runWithTransaction(self.db.core.getJobs, job_uuids)

    @expose
    def createJob(self, callData, job):
        try:
            handlerClass = getHandlerClass(job.job_type)
        except KeyError:
            raise RmakeError("Job type %r is unsupported" % job.job_type)

        d = self.pool.runWithTransaction(self.db.core.createJob, job)
        @d.addCallback
        def post_create(newJob):
            log.info("Job %s of type '%s' started", newJob.job_uuid,
                    newJob.job_type)
            handler = handlerClass(self, newJob)
            self.jobs[newJob.job_uuid] = handler
            handler.start()
            return newJob
        return d

    # Job handler API

    def jobDone(self, job_uuid):
        if job_uuid in self.jobs:
            status = self.jobs[job_uuid].job.status
            if status.completed:
                result = 'done'
            elif status.failed:
                result = 'failed'
            else:
                result = 'finished'
            log.info("Job %s %s: %s", job_uuid, result, status.text)

            handler = self.jobs[job_uuid]
            tasks = set(handler.tasks)
            for worker in self.workers.values():
                worker.tasks -= tasks

            for task in self.taskQueue[:]:
                if task.job_uuid == job_uuid:
                    log.debug("Discarding task %s from queue", task.task_uuid)
                    self.taskQueue.remove(task)

            del self.jobs[job_uuid]
        else:
            log.warning("Tried to remove job %s but it is already gone.",
                    job_uuid)

    def updateJob(self, job, frozen=None):
        # Use a copy of the job object because the request gets put into a
        # queue until there is a DB worker available.
        job = copy.deepcopy(job)
        return self.pool.runWithTransaction(self._updateJob, job,
                frozen=frozen)

    def _updateJob(self, job, frozen=None):
        job = self.db.core.updateJob(job, frozen=frozen)
        if not job:
            # Superceded by another update
            return
        if job.status.final:
            self.jobDone(job.job_uuid)

    def createTask(self, task):
        job = self.jobs[task.job_uuid]
        if task.task_uuid in job.tasks:
            return defer.succeed(job.tasks[task.task_uuid])
        job.tasks[task.task_uuid] = task

        # Try to assign before saving so we can avoid a second trip to the DB
        result = self._assignTask(task)
        if result == core_const.A_LATER:
            log.debug("Queueing task %s", task.task_uuid)
            self.taskQueue.append(task)

        # Use a copy of the task because the request gets put into a queue
        # until there is a DB worker available.
        task = copy.deepcopy(task)
        d = self.pool.runWithTransaction(self.db.core.createTaskMaybe, task)
        @d.addCallback
        def post_create(newTask):
            # Note that the task might already have failed, if it could not be
            # assigned. We store it anyway for the convenience of the job
            # handler.
            job.tasks[newTask.task_uuid] = newTask
            return newTask
        d.addCallback(self._taskUpdated)
        d.addErrback(self._failJob, task.job_uuid)
        return d

    def _failJob(self, failure, job_uuid):
        handler = self.jobs.get(job_uuid)
        if not handler:
            return
        handler.failJob(failure, "Unhandled error in dispatcher:")

    ## Message bus API

    def updateTask(self, task):
        d = self.pool.runWithTransaction(self.db.core.updateTask, task)
        d.addCallback(self._taskUpdated)
        d.addErrback(self._failJob, task.job_uuid)
        d.addErrback(logFailure)

    def _taskUpdated(self, newTask):
        if not newTask:
            # Superceded
            return
        # If the task is finished, remove it from the assigned node and try to
        # assign more tasks.
        if newTask.status.final:
            # Note that node_assigned is not used here because the update to
            # set it might not have completed. It is easier and just as safe to
            # scan from the worker side.
            for worker in self.workers.values():
                if newTask.task_uuid in worker.tasks:
                    worker.tasks.discard(newTask.task_uuid)
            from twisted.internet import reactor
            reactor.callLater(0, self._assignTasks)
        handler = self.jobs.get(newTask.job_uuid)
        if not handler:
            return
        handler.taskUpdated(newTask)

    def workerHeartbeat(self, jid, caps, tasks):
        worker = self.workers.get(jid)
        if worker is None:
            log.info("Worker %s connected: caps=%r", jid.full(), caps)
            worker = self.workers[jid] = WorkerInfo(jid)
        worker.setCaps(caps)
        self._assignTasks()

    def workerDown(self, jid):
        if jid in self.workers:
            log.info("Worker %s disconnected", jid.full())
            del self.workers[jid]

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
        worker.tasks.add(task.task_uuid)

        # Send the task to the worker node
        msg = message.StartTask(task)
        msg.send(self.bus, jid)

    def _failTask(self, task, message):
        log.error("Task %s failed: %s", task.task_uuid, message)
        text = "Task failed: %s" % (message,)
        task.status.code = core_const.TASK_NOT_ASSIGNABLE
        task.status.text = "Task failed: %s" % (message,)
        self.updateTask(task)


class WorkerInfo(object):

    def __init__(self, jid):
        self.jid = jid
        self.caps = set()
        self.tasks = set()
        self.slots = 2
        # expiring is incremented each time WorkerChecker runs and zeroed each
        # time the worker heartbeats. When it gets high enough, the worker is
        # assumed dead.
        self.expiring = 0

    def setCaps(self, caps):
        self.caps = caps
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
        # Note that not all task types will consume a slot.
        assigned = len(self.tasks)
        free = max(self.slots - assigned, 0)
        if free:
            return core_const.A_NOW, free
        else:
            return core_const.A_LATER, None


def main():
    import optparse
    import sys

    cfg = DispatcherConfig()
    parser = optparse.OptionParser()
    parser.add_option('--debug', action='store_true')
    parser.add_option('-c', '--config-file', action='callback', type='str',
            callback=lambda a, b, value, c: cfg.read(value))
    parser.add_option('--config', action='callback', type='str',
            callback=lambda a, b, value, c: cfg.configLine(value))
    options, args = parser.parse_args()
    if args:
        parser.error("No arguments expected")

    for name in ('xmppJID', 'xmppIdentFile'):
        if cfg[name] is None:
            sys.exit("error: Configuration option %r must be set." % name)

    from rmake.lib.logger import setupLogging
    level = options.debug and logging.DEBUG or logging.INFO
    setupLogging(
            logPath=cfg.logPath_server, fileLevel=level,
            consoleFormat='file', consoleLevel=level,
            withTwisted=True)
    setDebugHook()

    from twisted.internet import reactor
    service = Dispatcher(cfg)
    #if options.debug:
    #    service.bus.logTraffic = True
    service.startService()
    reactor.run()


if __name__ == '__main__':
    main()
