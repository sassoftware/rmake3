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
from twisted.internet import defer

log = logging.getLogger(__name__)

JOB_STATE_VERSION = 1

STATUS_IDLE, STATUS_SENT, STATUS_AGAIN, STATUS_CRITICAL = range(4)


class _HandlerRegistrar(type):

    handlers = {}

    def __new__(metacls, name, bases, clsdict):
        cls = type.__new__(metacls, name, bases, clsdict)

        if cls.jobType:
            metacls.handlers[cls.jobType] = cls

        return cls


def getHandler(jobType, dispatcher, job):
    return _HandlerRegistrar.handlers[jobType](dispatcher, job)


class JobHandler(object):
    __metaclass__ = _HandlerRegistrar
    __slots__ = ('dispatcher', 'job', 'eventsPending', 'statusPending', 'state')
    _save = ('state',)

    jobType = None
    jobVersion = 1

    def __init__(self, dispatcher, job):
        self.dispatcher = dispatcher
        self.job = job
        self.eventsPending = []
        self.statusPending = STATUS_IDLE
        self.state = None
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
        if self.statusPending == STATUS_CRITICAL:
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
            log.exception("Error in job handler method %s:", name)
            # FIXME: fail the job

    def begin_done(self):
        pass

    def setStatus(self, code, text, detail=None, state=None):
        status = self.job.status
        if (code == status.code and text == status.text and detail ==
                status.detail and state is None):
            return defer.succeed(None)
        if state not in (None, self.state):
            critical = True
            self.state = state
        else:
            critical = False
        status.code = code
        status.text = text
        status.detail = detail
        log.debug("Job %s status is: %s %s", self.job.job_uuid, code, text)
        self._sendStatus(critical)

    def _sendStatus(self, critical):
        if self.statusPending >= STATUS_SENT and not critical:
            if self.statusPending == STATUS_CRITICAL:
                # Shouldn't happen because events get spooled if there's a
                # critical update pending.
                log.warning("Discarding non-critical status update")
                return
            # Send status once the current update finishes.
            self.statusPending = STATUS_AGAIN
            return

        # Start a status update and hook the end to check if someone else
        # changed it again.
        isDone = self.state == 'done'
        if critical:
            self.statusPending = STATUS_CRITICAL
            d = self.dispatcher.updateJob(self.job, isDone=isDone,
                    frozen=self.freeze())
        else:
            self.statusPending = STATUS_SENT
            d = self.dispatcher.updateJob(self.job, isDone=isDone)

        def send_deferred_status(dummy):
            from twisted.internet import reactor
            if critical:
                reactor.callLater(0, self._begin)
                for event in self.eventsPending:
                    reactor.callLater(0, self._continue, event)
                self.eventsPending = []
            elif self.statusPending == STATUS_AGAIN:
                # Schedule another status send immediately.
                log.debug("Scheduling another status update")
                reactor.callLater(0, self._sendStatus, False)
            self.statusPending = STATUS_IDLE
        d.addCallback(send_deferred_status)
        d.addErrback(self.onError)

    def onError(self, failure):
        log.error("Unhandled error in job handler:\n%s" %
                failure.getTraceback())
        # FIXME: fail the job

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
        if self.finished >= self.spam:
            return self.callChain('1')
        else:
            return self._spamStatus()

    def _spamStatus(self):
        return self.setStatus(100, "Collecting spam {%d/%d}" %
                (self.finished, self.spam))

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

    def launchStuff(self, howmany):
        #import random
        from twisted.internet import reactor
        for x in range(min(howmany, self.spam - self.started)):
            self.started += 1
            num = self.started
            reactor.callLater(0, self.did_something, num)
            #reactor.callLater(random.uniform(1, 3), self.did_something, num)

    def did_something(self, num):
        self.finished += 1
        self._continue('spam')

    def callChain(self, num):
        from twisted.internet import reactor
        reactor.callLater(0, self._continue, '#%s done' % num)
        return self.setStatus(100, "Chaining (%s)" % num, state=str(num))
