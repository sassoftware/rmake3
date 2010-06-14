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

"""
The executor is responsible for handling a particular unit of subwork, either
in-process or by forking off additional tasks.
"""

import cPickle
import logging
from twisted.internet import defer
from twisted.internet import error as ierror
from twisted.protocols.basic import Int32StringReceiver

from rmake.lib import osutil

log = logging.getLogger(__name__)


class WorkerProtocol(Int32StringReceiver):
    """Simple protocol used to link the launcher and executors."""

    # Packets should be no more than 10MB including overhead.
    MAX_LENGTH = 10000000

    def sendCommand(self, ctr, command, **kwargs):
        self.sendString(cPickle.dumps((ctr, command, kwargs), 2))

    def stringReceived(self, data):
        ctr, command, kwargs = cPickle.loads(data)
        try:
            m = getattr(self, 'cmd_' + command)
        except AttributeError:
            log.error("Ignoring unknown worker command %r", command)
        else:
            m(ctr, **kwargs)


class WorkerParent(WorkerProtocol):
    """Communicate messages from the launcher to the executor."""

    def __init__(self):
        self.ctr = 0
        self.pending = {}
        self.task = None

    def callRemote(self, command, **kwargs):
        ctr = self.ctr
        self.ctr += 1
        d = self.pending[ctr] = defer.Deferred()
        if command == 'launch':
            self._hook_launch(kwargs, d)
        self.sendCommand(ctr, command, **kwargs)
        return d

    def connectionLost(self, reason):
        """Child process went away, fail all pending calls."""
        for d in self.pending.values():
            d.errback(reason)

    def cmd_ack(self, ctr, **result):
        if not result:
            result = None
        d = self.pending.pop(ctr)
        d.callback(result)

    def _hook_launch(self, kwargs, d):
        """Snoop launch commands to keep track of the current task."""
        self.task = kwargs['task']
        self.launcher = kwargs.pop('launcher')

        # Fail tasks that exited cleanly but didn't report success.
        @d.addCallback
        def cb_checkResult(result):
            if not self.task.status.final:
                raise InternalWorkerError("Task failed to send a finalized "
                        "status before terminating.")
            return result

        # Clear saved task and launcher fields after the task is done.
        @d.addBoth
        def bb_clearTask(result):
            self.task = self.launcher = None
            return result

        # Turn process termination events into relevant exceptions.
        @d.addErrback
        def eb_filterErrors(reason):
            if reason.check(ierror.ProcessTerminated, ierror.ProcessDone):
                log.error("Worker exited prematurely with status %s",
                        reason.value.status)
                raise InternalWorkerError("The worker executing the task "
                        "has exited abnormally.")
            return reason

        # Report errors back to the dispatcher.
        d.addErrback(self.launcher.taskFailed, self.task)

    def cmd_status_update(self, ctr, task):
        """Propagate status updates back to the dispatcher."""
        if task.task_uuid != self.task.task_uuid:
            log.warning("Dropping worker status report for wrong task.")
            return
        self.task = task
        self.launcher.forwardTaskStatus(task)


class WorkerChild(WorkerProtocol):

    shutdown = False
    task = None

    def _setproctitle(self):
        title = 'rmake-worker: '
        if self.task:
            title += '<task %s>' % self.task.task_uuid.short
        else:
            title += '<idle>'
        osutil.setproctitle(title)

    def connectionMade(self):
        self._setproctitle()

    def connectionLost(self, reason):
        from twisted.internet import reactor
        try:
            reactor.stop()
        except ierror.ReactorNotRunning:
            pass
        if not self.shutdown:
            import os
            os._exit(-1)

    def cmd_launch(self, ctr, task):
        self.task = task
        self._setproctitle()
        print 'FIRE ZE MISSILES!'
        print 'task uuid:', task.task_uuid
        from twisted.internet import reactor
        def later():
            self.sendStatus(200, 'done')
            self.sendCommand(ctr, 'ack')
            self.task = None
            self._setproctitle()
        reactor.callLater(10, later)

    def cmd_shutdown(self, ctr):
        self.shutdown = True
        self.sendCommand(ctr, 'ack')
        self.transport.loseConnection()

    def sendStatus(self, code, text, detail=None):
        self.task.times.ticks += 1
        status = self.task.status
        status.code = code
        status.text = text
        status.detail = detail
        self.sendCommand(None, 'status_update', task=self.task)


class InternalWorkerError(RuntimeError):
    pass
