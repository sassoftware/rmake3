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
The launcher is the root process of a worker node. It forks to handle incoming
jobs and accumulates messages to and distributes messages from the dispatcher
to the worker processes via a UNIX socket.

The launcher must re-exec after forking to prevent Twisted state from escaping
into the worker process.
"""

import cPickle
import logging
import time
from conary.lib import cfgtypes
from twisted.application.internet import TimerService
from twisted.application.service import MultiService

from rmake.core.types import JobStatus, TaskCapability
from rmake.lib.proc_pool import pool
from rmake.messagebus import message
from rmake.messagebus.client import BusClientService
from rmake.messagebus.config import BusClientConfig
from rmake.worker import executor

log = logging.getLogger(__name__)


class LauncherService(MultiService):

    def __init__(self, cfg, plugin_mgr):
        MultiService.__init__(self)
        self.cfg = cfg
        self.bus = None
        self.caps = set()
        self.pool = None
        self.plugins = plugin_mgr
        self.plugins.p.launcher.pre_setup(self)
        self._set_caps()
        self._start_bus()
        self._start_pool()
        self.plugins.p.launcher.post_setup(self)

    def _set_caps(self):
        for plugin, tasks in self.plugins.p.worker.get_task_types().items():
            for task in tasks:
                self.caps.add(TaskCapability(task))

    def _start_bus(self):
        self.bus = LauncherBusService(self.cfg)
        self.bus.setServiceParent(self)
        HeartbeatService(self).setServiceParent(self)

    def _start_pool(self):
        # The elusive double pickle: even though parent-child communication
        # is transparently pickled, the config object needs special handling
        # because the worker must load plugins before unpickling.
        self.pool = PoolService(args=dict(
            pluginDirs=self.plugins.pluginDirs,
            disabledPlugins=self.plugins.disabledPlugins,
            pluginOptions=self.cfg.pluginOption,
            cfgBlob=cPickle.dumps(self.cfg, 2),
            ))
        self.pool.setServiceParent(self)

    def launch(self, msg):
        task = msg.task
        log.info("Task %s starting: job %s, task '%s'", task.task_uuid.short,
                task.job_uuid.short, task.task_name)
        d = self.pool.launch(task=task, launcher=self)
        d.addErrback(self.failTask, task)

    def failTask(self, reason, task):
        task.times.ticks += 1
        task.status = JobStatus.from_failure(reason,
                "Fatal error in task runner")
        self.forwardTaskStatus(task)

    def forwardTaskStatus(self, task):
        status = task.status
        if status.final:
            log.info("Task %s %s: %s %s", task.task_uuid.short,
                    status.completed and 'complete' or 'failed', status.code,
                    status.text)
        msg = message.TaskStatus(task)
        self.bus.sendToTarget(msg)


class LauncherBusService(BusClientService):

    description = 'rMake Worker'

    def messageReceived(self, msg):
        if isinstance(msg, message.StartTask):
            self.parent.launch(msg)
        else:
            BusClientService.messageReceived(self, msg)

    def onNeighborUp(self, jid):
        if jid != self.cfg.dispatcherJID:
            return
        log.info("Connected to dispatcher")
        # Call up to the daemon instance so it can set the process title.
        self.parent.parent.targetConnected(self.jid, jid)

    def onNeighborDown(self, jid):
        if jid != self.cfg.dispatcherJID:
            return
        log.error("Lost connection to dispatcher")


class HeartbeatService(TimerService):

    def __init__(self, launcher, interval=5):
        self.launcher = launcher
        TimerService.__init__(self, interval, self.heartbeat)
        self.last_nag = time.time()
        self.sent_hello = False

    def heartbeat(self):
        tasks = self.launcher.pool.getTaskList()
        msg = message.Heartbeat(caps=self.launcher.caps, tasks=tasks)
        bus = self.launcher.bus
        self.launcher.bus.sendToTarget(msg)
        if not bus.isConnected() and time.time() - self.last_nag > 5:
            log.error("Dispatcher is not online")
            self.last_nag = time.time()


class PoolService(pool.ProcessPool):

    childFactory = executor.WorkerChild
    parentFactory = executor.WorkerParent

    def launch(self, task, launcher):
        return self.doWork('launch', task=task, launcher=launcher)

    def getTaskList(self):
        if self.finished:
            return set()
        tasks = set()
        for connector in self.busy:
            child = connector.protocol
            if child.task:
                tasks.add(child.task.task_uuid)
        return tasks


class WorkerConfig(BusClientConfig):
    lockDir             = (cfgtypes.CfgPath, '/var/lock')
    logDir              = (cfgtypes.CfgPath, '/var/log/rmake')

    # Plugins
    pluginDirs          = (cfgtypes.CfgPathList, [])
    pluginOption        = (cfgtypes.CfgDict(
        cfgtypes.CfgList(cfgtypes.CfgString)), {})
    usePlugin           = (cfgtypes.CfgDict(cfgtypes.CfgBool), {})
