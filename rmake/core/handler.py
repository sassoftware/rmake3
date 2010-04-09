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

import cPickle
import logging
from rmake.core.types import RmakeTask
from twisted.python import reflect
from twisted.python.failure import Failure

log = logging.getLogger(__name__)

JOB_STATE_VERSION = 1


class _HandlerRegistrar(type):

    handlers = {}

    def __new__(metacls, name, bases, clsdict):
        cls = type.__new__(metacls, name, bases, clsdict)

        if cls.jobType:
            metacls.handlers[cls.jobType] = cls

        return cls


def getHandlerClass(jobType):
    return _HandlerRegistrar.handlers[jobType]


class JobHandler(object):
    __metaclass__ = _HandlerRegistrar
    __slots__ = ('dispatcher', 'job', 'eventsPending', 'statusPending',
            'state', 'tasks')
    _save = ('state',)

    jobType = None
    jobVersion = 1

    def __init__(self, dispatcher, job):
        self.dispatcher = dispatcher
        self.job = job
        self.eventsPending = []
        self.statusPending = (None, None)
        self.state = None
        self.tasks = {}
        self.setup()

    ## State machine methods

    def setup(self):
        pass

    def start(self):
        assert not self.state
        return self.setStatus(100, 'Starting', state='starting')

    def _begin(self):
        self._try_call('begin_', False)

    def _continue(self, event):
        tickPending, critPending = self.statusPending
        if critPending:
            self.eventsPending.append(event)
            return
        self._try_call('continue_', True, event)

    def _recover(self):
        if not self._try_call('recover_', True):
            self._try_call('begin_', False)

    def _try_call(self, prefix, missingOK, *args):
        name = prefix + self.state
        func = getattr(self, name, None)
        if not func:
            if missingOK:
                return False
            else:
                raise AttributeError("Job handler must define a %s method" %
                        name)

        try:
            func(*args)
        except:
            self.failJob(Failure())

    ## Special end states

    def begin_done(self):
        pass

    ## Changing status and state

    def setStatus(self, code, text, detail=None, state=None):
        if state not in (None, self.state):
            critical = True
            self.state = state
        else:
            critical = False
        self.job.status.code = code
        self.job.status.text = text
        self.job.status.detail = detail
        self.job.times.ticks += 1
        log.debug("Job %s status is: %s %s", self.job.job_uuid, code, text)
        return self._sendStatus(critical)

    def _sendStatus(self, critical):
        tick = self.job.times.ticks
        tickPending, critPending = self.statusPending
        if tickPending is not None:
            assert tickPending < tick
            if critPending:
                # Events are spooled while a critical update is pending, so
                # this should never happen.
                raise RuntimeError("Status update while critical update "
                        "was pending")
            elif not critical:
                # Defer status update until the in-flight one finishes.
                return

        # Start a status update and hook the end to check if someone else
        # changed it again.
        if critical:
            frozen = self.freeze()
        else:
            frozen = None
        self.statusPending = tick, critical
        d = self.dispatcher.updateJob(self.job, frozen=frozen)
        def update_ok(dummy):
            from twisted.internet import reactor
            if critical:
                # Start the next state and re-send any pending events.
                reactor.callLater(0, self._begin)
                for event in self.eventsPending:
                    reactor.callLater(0, self._continue, event)
                self.eventsPending = []

            newPending = self.statusPending[0]
            if newPending is None or newPending > tick:
                # Pre-empted by a critical update.
                return

            if self.job.times.ticks > tick:
                # Schedule another status send immediately.
                log.debug("Scheduling another status update")
                reactor.callLater(0, self._sendStatus, False)
            self.statusPending = None, None
        def update_failed(failure):
            # Clear pending field so the attempt to change state to failed can
            # succeed.
            self.statusPending = None, None
            return failure
        d.addCallbacks(update_ok, update_failed)

        d.addErrback(self.failJob, message="Error setting job status:")
        return d

    def failJob(self, failure, message="Unhandled error in job handler:"):
        log.error("%s\n%sJob: %s\n", message, failure.getTraceback(),
                self.job.job_uuid)

        text = "Job failed: %s: %s" % (
                reflect.qual(failure.type),
                reflect.safe_str(failure.value))
        d = self.setStatus(400, text=text, detail=failure.getTraceback(),
                state='done')
        # If setting status fails we'll have to forget about the job and hope
        # for the best. Perhaps in the future we can handle short-term database
        # faults more gracefully.
        @d.addErrback
        def set_status_failed(failure):
            log.error("Failed to set job status to failed:\n%s",
                    failure.getTraceback())
            self.dispatcher.jobDone(self.job.job_uuid)

    ## Creating/monitoring tasks

    def newTask(self, taskName, taskType, data):
        if data is not None:
            data = cPickle.dumps(2, data)
        task = RmakeTask(None, self.job.job_uuid, taskName, taskType, data)
        return self.dispatcher.createTask(task)

    def countRunningTasks(self, taskType):
        count = 0
        for task in self.tasks.values():
            if task.task_type == taskType and not task.status.final:
                count += 1
        return count

    def taskUpdated(self, task):
        self.tasks[task.task_uuid] = task
        self._continue(('task updated', task))

    ## Freezer machinery

    @classmethod
    def _getVersion(cls):
        return (JOB_STATE_VERSION, cls.jobVersion)

    def freeze(self):
        state_dict = {}
        NOT_SET = object()
        for cls in type(self).mro():
            slots = cls.__dict__.get('_save', ())
            for slot in sorted(slots):
                value = getattr(self, slot, NOT_SET)
                if value is not NOT_SET:
                    state_dict[slot] = value
        data = (self._getVersion(), state_dict)
        return cPickle.dumps(data, 2)

    @classmethod
    def recover(cls, data):
        data = cPickle.loads(data)
        if data[0] != cls._getVersion():
            raise RuntimeError("Version mismatch when recovering job state")

        state_dict = data[1]
        self = cls.__new__()
        for key, value in state_dict.items():
            setattr(self, key, value)
        return self


class TestHandler(JobHandler):
    __slots__ = ('finished', 'started')
    handler_version = 1

    jobType = 'test'
    spam = 15

    # State: begin
    def begin_starting(self):
        return self.setStatus(100, "Collecting spam", state='collect_spam')

    # State: collect_spam
    def begin_collect_spam(self):
        self.started = self.finished = 0
        self.launchStuff(self.spam)
        return self._spamStatus()

    def continue_collect_spam(self, event):
        log.debug("Job %s event: %r", self.job.job_uuid, event)
        if event[0] != 'task updated':
            return
        task = event[1]
        if task.status.final:
            self.finished += 1
        return self._spamStatus()

    def _spamStatus(self):
        if self.finished < self.spam:
            return self.setStatus(100, "Collecting spam {%d/%d}" %
                    (self.finished, self.spam))
        else:
            return self.callChain('1')

    def launchStuff(self, howmany):
        for x in range(min(howmany, self.spam - self.started)):
            self.started += 1
            name = 'foo %d' % self.started
            self.newTask(name, 'test', None)

    # States 1 - 5
    def begin_1(self):
        return self.callChain('2')
    def begin_2(self):
        return self.callChain('3')
    def begin_3(self):
        return self.callChain('4')
    def begin_4(self):
        return self.callChain('5')
    def begin_5(self):
        return self.setStatus(200, "Test job complete", state='done')

    def callChain(self, num):
        from twisted.internet import reactor
        reactor.callLater(0, self._continue, '#%s done' % num)
        return self.setStatus(100, "Chaining (%s)" % num, state=str(num))
