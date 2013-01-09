#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
from conary.lib import cfgtypes
from twisted.application.internet import TimerService
from twisted.application.service import MultiService

from rmake.core import types
from rmake.core.types import JobStatus, TaskCapability
from rmake.lib import netlink
from rmake.lib.proc_pool import pool
from rmake.messagebus import message
from rmake.messagebus.client import BusClientService
from rmake.messagebus.config import BusClientConfig
from rmake.worker import executor

log = logging.getLogger(__name__)

# Protocol versions of the dispatcher that are supported by the launcher
PROTOCOL_VERSIONS = set([3])


class LauncherService(MultiService):

    def __init__(self, cfg, plugin_mgr, debug=False):
        MultiService.__init__(self)
        self.cfg = cfg
        self.debug = debug
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
        versions = tuple(sorted(PROTOCOL_VERSIONS))
        self.caps.add(types.VersionCapability(versions))
        for plugin, tasks in self.plugins.p.worker.get_task_types().items():
            for task in tasks:
                self.caps.add(TaskCapability(task))
        for zone in self.cfg.zone:
            self.caps.add(types.ZoneCapability(zone))

    def _start_bus(self):
        self.bus = LauncherBusService(self.cfg)
        self.bus.setServiceParent(self)
        HeartbeatService(self).setServiceParent(self)

    def _start_pool(self):
        # The elusive double pickle: even though parent-child communication
        # is transparently pickled, the config object needs special handling
        # because the worker must load plugins before unpickling.
        self.pool = PoolService(
                args=dict(
                    pluginDirs=self.plugins.pluginDirs,
                    disabledPlugins=self.plugins.disabledPlugins,
                    pluginOptions=self.cfg.pluginOption,
                    cfgBlob=cPickle.dumps(self.cfg, 2),
                    ),
                debug=self.debug)
        self.pool.setServiceParent(self)

    def launch(self, msg):
        task = msg.task
        log.info("Task %s starting: job %s, task '%s'", task.task_uuid.short,
                task.job_uuid.short, task.task_name)

        d = self.pool.launch(
                task=task,
                launcher=self,
                )
        d.addErrback(self.failTask, task)

    def failTask(self, reason, task):
        task = task.thaw()
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
        msg = message.TaskStatus(task.freeze())
        self.bus.sendToTarget(msg)

    def forwardTaskLogs(self, task, records):
        msg = message.LogRecords(
                records=records,
                job_uuid=task.job_uuid,
                task_uuid=task.task_uuid,
                )
        self.bus.sendToTarget(msg)


class LauncherBusService(BusClientService):

    description = 'rMake Worker'

    def messageReceived(self, msg):
        if isinstance(msg, message.StartTask):
            self.parent.launch(msg)
        else:
            BusClientService.messageReceived(self, msg)

    def onNeighborUp(self, jid):
        if jid.userhost() != self.cfg.dispatcherJID.userhost():
            return
        log.info("Connected to dispatcher")
        # Call up to the daemon instance so it can set the process title.
        self.parent.parent.targetConnected(self.jid, jid)

    def onNeighborDown(self, jid):
        if jid.userhost() != self.cfg.dispatcherJID.userhost():
            return
        log.error("Lost connection to dispatcher")


class HeartbeatService(TimerService):

    def __init__(self, launcher, interval=5):
        self.launcher = launcher
        TimerService.__init__(self, interval, self.heartbeat)
        self.sent_hello = False
        self.netlink = netlink.RoutingNetlink()

    def heartbeat(self):
        tasks = self.launcher.pool.getTaskList()
        slots = self.launcher.cfg.getSlots()
        addresses = set(x[1] for x in self.netlink.getAllAddresses())
        msg = message.Heartbeat(caps=self.launcher.caps, tasks=tasks,
                slots=slots, addresses=addresses)
        self.launcher.bus.sendToTarget(msg)


class PoolService(pool.ProcessPool):

    childFactory = executor.WorkerChild
    parentFactory = executor.WorkerParent

    def launch(self, task, launcher):
        return self.doWork('launch',
                task=task,
                launcher=launcher,
                )

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
    slots               = (cfgtypes.CfgInt, 2)
    slotsByType         = cfgtypes.CfgDict(cfgtypes.CfgInt)
    zone                = (cfgtypes.CfgList(cfgtypes.CfgString), [])

    # Plugins
    pluginDirs          = (cfgtypes.CfgPathList, [])
    pluginOption        = (cfgtypes.CfgDict(
        cfgtypes.CfgList(cfgtypes.CfgString)), {})
    usePlugin           = (cfgtypes.CfgDict(cfgtypes.CfgBool), {})

    def getSlots(self):
        slots = dict(self.slotsByType)
        slots[None] = self.slots
        return slots
