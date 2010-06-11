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

import logging
from ampoule import pool
from conary.lib import cfgtypes
from rmake.core.types import TaskCapability
from rmake.messagebus import message
from rmake.messagebus.client import BusClientService
from rmake.messagebus.config import BusClientConfig
from rmake.worker import executor
from twisted.application.internet import TimerService
from twisted.application.service import MultiService, Service
from twisted.python import reflect

log = logging.getLogger(__name__)


class LauncherService(MultiService):

    def __init__(self, cfg, plugin_mgr):
        MultiService.__init__(self)
        self.cfg = cfg
        self.bus = None
        self.caps = set()
        self.pool = None
        self.task_types = {}
        self.plugins = plugin_mgr
        self.plugins.p.launcher.pre_setup(self)
        self._set_caps()
        self._start_bus()
        self._start_pool()
        self.plugins.p.launcher.post_setup(self)

    def _set_caps(self):
        for plugin, tasks in self.plugins.p.worker.get_task_types().items():
            for task, taskClass in tasks.items():
                self.task_types[task] = taskClass
                self.caps.add(TaskCapability(task))

    def _start_bus(self):
        self.bus = LauncherBusService(self.cfg)
        self.bus.setServiceParent(self)
        HeartbeatService(self).setServiceParent(self)

    def _start_pool(self):
        self.pool = PoolService()
        self.pool.setServiceParent(self)

    def launch(self, msg):
        task = msg.task
        if task.task_type not in self.task_types:
            log.error("Got task of unsupported type %r", task.type)
            self.sendTaskStatus(task, 400,
                    "Task type is not supported by this node")
            return

        log.info("Starting task %s", task.task_uuid)
        d = self.pool.launch(task=task, launcher=self)
        d.addErrback(self.taskFailed, task)

    def taskFailed(self, reason, task):
        text = "Fatal error in task runner: %s: %s" % (
                reflect.qual(reason.type),
                reflect.safe_str(reason.value))
        self.sendTaskStatus(task, 400, text, detail=reason.getTraceback())

    def sendTaskStatus(self, task, code=None, text=None, detail=None):
        task.times.ticks += 1
        status = task.status
        if code is not None:
            status.code = code
            status.text = text
            status.detail = detail
        self.forwardTaskStatus(task)

    def forwardTaskStatus(self, task):
        status = task.status
        if status.final:
            log.info("Task %s %s: %s %s", task.task_uuid,
                    status.completed and 'completed' or 'failed', status.code,
                    status.text)
        msg = message.TaskStatus(task)
        self.bus.sendToTarget(msg)


class LauncherBusService(BusClientService):

    role = 'worker'
    description = 'rMake Worker'

    def messageReceived(self, msg):
        if isinstance(msg, message.StartTask):
            self.parent.launch(msg)
        else:
            BusClientService.messageReceived(self, msg)


class HeartbeatService(TimerService):

    def __init__(self, launcher, interval=5):
        self.launcher = launcher
        TimerService.__init__(self, interval, self.heartbeat)

    def heartbeat(self):
        tasks = self.launcher.pool.getTaskList()
        msg = message.Heartbeat(caps=self.launcher.caps, tasks=tasks)
        self.launcher.bus.sendToTarget(msg)


class PoolService(Service):

    childFactory = executor.WorkerChild
    serverFactory = executor.WorkerParent

    pool = None

    def startService(self):
        Service.startService(self)
        from twisted.internet import reactor
        self.pool = pool.ProcessPool(self.childFactory, self.serverFactory,
                min=1, max=1000, recycleAfter=5)
        reactor.callLater(0, self.pool.start)

    def stopService(self):
        print 'shutting down'
        Service.stopService(self)
        return self.pool.stop()

    def launch(self, task, launcher):
        return self.pool.doWork('launch', task=task, launcher=launcher)

    def getTaskList(self):
        if not self.pool:
            return set()
        tasks = set()
        for child in self.pool.busy:
            if child.task:
                tasks.add(child.task.task_uuid)
        return tasks


class WorkerConfig(BusClientConfig):
    buildDir            = (cfgtypes.CfgPath, '/var/rmake')
    helperDir           = (cfgtypes.CfgPath, '/usr/libexec/rmake')
    lockDir             = (cfgtypes.CfgPath, '/var/lock')
    logDir              = (cfgtypes.CfgPath, '/var/log/rmake')
    pluginDirs          = (cfgtypes.CfgPathList, [])
    usePlugin           = (cfgtypes.CfgDict(cfgtypes.CfgBool), {})
