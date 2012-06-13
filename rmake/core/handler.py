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
The job handler is a state machine unique to each build type that governs the
flow of tasks and status on the dispatcher. It sets build status, creates
tasks for workers to run, and monitors those tasks for completion and failure.

Each handler defines a set of attributes that it wishes to persist each time
the handler's state is updated. These will be recovered in case of a dispatcher
crash, and can be used to determine which tasks need to be run. An ideal
handler arranges its efforts so that the external effects of all previous
states are on permanent storage before it changes state, and that all effects
within the current state can be retried without harm. A recovering handler will
attempt to recreate all tasks within that state, and note the pre-existing
outcomes of any tasks that are still known by the system. It may choose to
restart tasks that were already failed at recovery time.
"""

import logging
from rmake.core import constants as core_const
from rmake.core import types as rmk_types
from rmake.lib import logger
from rmake.lib.ninamori.types import namedtuple
from twisted.internet import defer
from twisted.python import failure as tw_failure
from twisted.python import reflect

log = logging.getLogger(__name__)

JOB_STATE_VERSION = 1

_jobHandlers = {}


def registerHandler(handlerClass):
    assert handlerClass.jobType
    _jobHandlers[handlerClass.jobType] = handlerClass


def getHandlerClass(jobType):
    return _jobHandlers[jobType]


class JobHandler(object):
    __slots__ = ('dispatcher', 'job', 'state', 'tasks', 'clock')

    jobType = None
    jobVersion = 1
    slotType = None
    firstState = 'starting'

    def __init__(self, dispatcher, job):
        self.dispatcher = dispatcher
        self.clock = dispatcher.clock
        self.job = job
        self.state = None
        self.tasks = {}
        self.setup()

    ## State machine methods

    def setup(self):
        pass

    def close(self):
        pass

    def start(self):
        """Start running a job."""
        assert not self.state
        self.setStatus(100, 'Initializing')
        self._changeState(self.firstState)

    def _changeState(self, state):
        """Move to a new state, persist it, and invoke the state function."""
        if self.state == state:
            return
        if state == 'done' and not self.job.status.final:
            self.setStatus(400, "Internal error: Dispatcher plugin failed to "
                    "set status before terminating (from state %r)" %
                    (self.state,))
        self.state = state
        # Wait for the job status to be updated successfully before moving to
        # the next state.
        log.debug("Job %s changing state to %s", self.job.job_uuid, state)
        d = self.dispatcher.updateJob(self.job)
        d.addCallback(self._runState)
        def eb_failure(reason):
            # Try to fail a job; if it suceeds then change state to 'done'
            d2 = self.failJob(reason)
            d2.addCallback(self._changeState)
            return d2
        d.addErrback(eb_failure)

    def _runState(self, dummy):
        """Run the function for handling a particular state."""
        log.debug("Job %s running state %s", self.job.job_uuid, self.state)
        if self.state == 'done':
            self.close()
            return
        func = getattr(self, self.state, None)
        if func is None:
            raise AttributeError("Handler %s doesn't define a state %r!" %
                    (reflect.qual(type(self)), self.state))
        d = defer.maybeDeferred(func)
        def cb_done(newState):
            # State functions return (or callback) their new state, so pass
            # that state into _changeState after one loop through the reactor
            # (to avoid recursion).
            if newState is None:
                newState = 'done'
            elif not isinstance(newState, str):
                raise TypeError("Handler must return its next state, not %r" %
                        (newState,))
            self.clock.callLater(0, self._changeState, newState)
        d.addCallback(cb_done)
        # Pass func's deferred up so the caller can catch exceptions.
        return d

    ## Changing status and state

    def setStatus(self, codeOrStatus, text=None, detail=None):
        """Change the job's status.

        Either pass a code, text, and optional details, or pass a L{JobStatus}
        object as the first argument.
        """
        if isinstance(codeOrStatus, rmk_types.FrozenJobStatus):
            self.job.status = codeOrStatus.thaw()
        elif isinstance(codeOrStatus, rmk_types.JobStatus):
            self.job.status = codeOrStatus
        else:
            assert text is not None
            self.job.status.code = codeOrStatus
            self.job.status.text = text
            self.job.status.detail = detail
        self.job.times.ticks += 1
        log.debug("Job %s status is: %s %s", self.job.job_uuid,
                self.job.status.code, self.job.status.text)

        d = self.dispatcher.updateJob(self.job)
        d.addErrback(self.failJob, message="Error setting job status:",
                failHard=self.job.status.failed)
        return d

    def failJob(self, failure, message="Unhandled error in job handler:",
            failHard=False):
        """Log an exception and set the job status to 'failed'.

        @param failure: Failure object to log
        @type  failure: L{twisted.python.failure.Failure}
        @param message: Message to display as the first line in the logfile
        @type  message: C{str}
        @param failHard: If C{True}, log the error but don't set the status.
        @type  failHard: C{bool}
        """
        log.error("%s\n%sJob: %s\n", message, failure.getTraceback(),
                self.job.job_uuid)
        if failHard:
            self.dispatcher.jobDone(self.job.job_uuid)
            # Transition directly to 'done' state, but short-circuit _setState
            # so it doesn't try to persist the handler -- it'll probably fail
            # if we've already failed twice to set status.
            self.state = 'done'
            return defer.succeed('done')

        status = rmk_types.JobStatus.from_failure(failure, "Job failed")
        d = self.setStatus(status)
        # If setting status fails we'll have to forget about the job and hope
        # for the best. Perhaps in the future we can handle short-term database
        # faults more gracefully.
        @d.addErrback
        def set_status_failed(failure):
            log.error("Failed to set job status to failed:\n%s",
                    failure.getTraceback())
            self.dispatcher.jobDone(self.job.job_uuid)
        # Transition directly to 'done' state
        d.addBoth(lambda _: 'done')
        return d

    ## Creating/monitoring tasks

    def newTask(self, taskName, taskType, data, zone=None, priority=0):
        if not isinstance(data, rmk_types.FrozenObject):
            data = rmk_types.FrozenObject.fromObject(data)
        priority = self.job.job_priority + priority
        task = rmk_types.RmakeTask(None, self.job.job_uuid, taskName, taskType,
                data, task_zone=zone, task_priority=priority)

        d = defer.Deferred()
        self.tasks[task.task_uuid] = TaskCallbacks(d, [])

        d2 = self.dispatcher.createTask(task)
        def eb_create_failed(reason):
            del self.tasks[task.task_uuid]
            d.errback(reason)
        d2.addErrback(eb_create_failed)

        return task

    def taskUpdated(self, task):
        try:
            d, callbacks = self.tasks[task.task_uuid]
        except KeyError:
            log.warning("Discarding task status update for unknown task %s",
                    task.task_uuid)
            return
        for func, args, kwargs in callbacks:
            try:
                func(task, *args, **kwargs)
            except:
                log.exception("Unhandled error in taskUpdated callback:")
        if task.status.final:
            d.callback(task)
            del self.tasks[task.task_uuid]

    def waitForTask(self, task):
        """Defer until the given task has completed."""
        d = defer.Deferred()
        def call_passthrough(result):
            if isinstance(result, tw_failure.Failure):
                d.errback(result)
            else:
                d.callback(result)
            d.addErrback(logger.logFailure,
                    "Unhandled error in waitForTask callback:")
            return result
        self.tasks[task.task_uuid].deferred.addBoth(call_passthrough)
        return d

    def watchTask(self, task, func, *args, **kwargs):
        """Register C{func} to be called each time C{task} is updated."""
        self.tasks[task.task_uuid].callbacks.append((func, args, kwargs))

    def gatherTasks(self, tasks, callback):
        """Wait for tasks to complete then invoke a callback."""
        # Wait for all tasks. Fail job if any tasks fail.
        d = defer.gatherResults([self.waitForTask(x) for x in tasks])
        def cb_gather(results):
            failed = [x for x in results if x.status.failed]
            if not failed:
                return results

            if len(failed) > 1:
                detail = '\n'.join('%s: %s: %s\n%s\n' % (
                    x.task_name, x.status.code, x.status.text, x.status.detail)
                    for x in failed)
                self.setStatus(400, "%s subtasks failed" % len(failed), detail)
            else:
                task = failed[0]
                self.setStatus(400, "%s failed: %s" % (task.task_name,
                    task.status.text), task.status.detail)
            raise TasksFailed(failed)
        d.addCallback(cb_gather)

        # Invoke callback if all tasks suceed; otherwise skip callback and
        # proceed directly to 'done' state.
        d.addCallbacks(callback,
                lambda reason: reason.trap(TasksFailed) and 'done')

        # Catch-all errback to clean up if any part of this handler crashes.
        d.addErrback(self.failJob)

        return d

    def scoreTask(self, task, worker):
        """Score how able a given worker is to run the given task.

        Returns a tuple of an A_* constant and a number. Higher is better.
        """
        # Are there slots available to run this task in?
        assigned = len(worker.tasks)
        available = worker.slots.get(self.slotType, 2)
        free = max(available - assigned, 0)
        if free:
            return core_const.A_NOW, free
        else:
            return core_const.A_LATER, None

    ## Freezer machinery

    def getData(self):
        return self.job.data.getObject()

    def setData(self, obj):
        if not isinstance(obj, rmk_types.FrozenObject):
            obj = rmk_types.FrozenObject.fromObject(obj)
        self.job.data = obj


TaskCallbacks = namedtuple('TaskCallbacks', 'deferred callbacks')


try:
    BaseException
except NameError:
    BaseException = Exception


class TasksFailed(BaseException):
    pass
