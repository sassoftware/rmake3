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
import os
from twisted.internet import defer
from twisted.internet import error as ierror
from twisted.protocols.basic import Int32StringReceiver

from rmake.core.types import JobStatus
from rmake.lib import logger
from rmake.lib import osutil
from rmake.lib import pluginlib

log = logging.getLogger(__name__)


class WorkerProtocol(Int32StringReceiver):
    """Simple protocol used to link the launcher and executors."""

    # Packets should be no more than 10MB including overhead.
    MAX_LENGTH = 10000000

    def sendCommand(self, ctr, command, **kwargs):
        self.sendString(cPickle.dumps((ctr, command, kwargs), 2))

    def stringReceived(self, data):
        try:
            ctr, command, kwargs = cPickle.loads(data)
            try:
                m = getattr(self, 'cmd_' + command)
            except AttributeError:
                log.error("Ignoring unknown worker command %r", command)
            else:
                m(ctr, **kwargs)
        except:
            log.exception("Unhandled error processing incoming command:")
            os._exit(1)


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
        def cb_checkResult(result):
            if not self.task.status.final:
                raise InternalWorkerError("Task failed to send a finalized "
                        "status before terminating.")
            return result
        d.addCallback(cb_checkResult)

        # Turn process termination events into relevant exceptions.
        def eb_filterErrors(reason):
            if reason.check(ierror.ProcessTerminated, ierror.ProcessDone):
                log.error("Worker exited prematurely with status %s",
                        reason.value.status)
                raise InternalWorkerError("The worker executing the task "
                        "has exited abnormally.")
            return reason
        d.addErrback(eb_filterErrors)

        # Report errors back to the dispatcher. Using a function here because
        # self.task will get replaced.
        def eb_failTask(reason):
            self.launcher.failTask(reason, self.task)
        d.addErrback(eb_failTask)

        # Clear saved task and launcher fields after the task is done.
        def bb_clearTask(result):
            self.task = self.launcher = None
        d.addBoth(bb_clearTask)

        d.addErrback(logger.logFailure)


    def cmd_status_update(self, ctr, task):
        """Propagate status updates back to the dispatcher."""
        if task.task_uuid != self.task.task_uuid:
            log.warning("Dropping worker status report for wrong task.")
            return
        self.task = task
        self.launcher.forwardTaskStatus(task)


class WorkerChild(WorkerProtocol):

    # Static
    pluginTypes = ('worker',)

    # Configuration
    cfg = None
    plugins = None
    task_types = None

    # Runtime (per task)
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
            os._exit(-1)

    def cmd_launch(self, ctr, task):
        self.task = task.freeze()
        pluginName, handlerClass = self.task_types.get(task.task_type)
        if not handlerClass:
            # The dispatcher isn't supposed to send us tasks we can't handle,
            # so this is probably a bug.
            self.sendStatus(JobStatus(
                400, "Worker can't run task of type %r" % (task.task_type,)))
            self.sendCommand(ctr, 'ack')
            return
        self._setproctitle()

        handler = handlerClass(self, task)
        self.plugins.getPlugin(pluginName).worker_pre_build(handler)
        d = handler.start()

        d.addErrback(self.failTask)
        @d.addBoth
        def cb_cleanup(result):
            self.task = None
            self._setproctitle()
            self.sendCommand(ctr, 'ack')
            return result
        return d

    def cmd_startup(self, ctr, pluginDirs, disabledPlugins, pluginOptions,
            cfgBlob):
        self.plugins = pluginlib.PluginManager(pluginDirs, disabledPlugins,
                supportedTypes=self.pluginTypes)
        self.plugins.loadPlugins()
        self.plugins.setOptions(pluginOptions)
        self.cfg = cPickle.loads(cfgBlob)

        self.task_types = {}
        for plugin, tasks in self.plugins.p.worker.get_task_types().items():
            for task_type, task_handler in tasks.items():
                self.task_types[task_type] = (plugin, task_handler)

        self.sendCommand(ctr, 'ack')

    def cmd_shutdown(self, ctr):
        self.shutdown = True
        self.sendCommand(ctr, 'ack')
        self.transport.loseConnection()

    def sendTask(self, task):
        task = task.thaw()
        task.times.ticks = self.task.times.ticks + 1
        self.task = task.freeze()
        self.sendCommand(None, 'status_update', task=self.task)

    def sendStatus(self, status):
        task = self.task.thaw()
        task.status = status
        self.sendTask(task)

    def failTask(self, reason, logIt=True):
        if logIt:
            logger.logFailure(reason, "Fatal error in task runner:")
        self.sendStatus(JobStatus.from_failure(reason,
                "Fatal error in task runner"))


class InternalWorkerError(RuntimeError):
    pass
