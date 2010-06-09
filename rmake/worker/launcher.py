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
import os
import socket
import sys
from conary.lib import cfgtypes
from rmake.core.types import TaskCapability
from rmake.lib.twisted_extras.pickle_proto import PickleProtocol
from rmake.lib.twisted_extras.socketpair import socketpair
from rmake.messagebus import message
from rmake.messagebus.client import BusClientService
from rmake.messagebus.config import BusClientConfig
from rmake.worker import executor
from twisted.application.internet import TimerService
from twisted.application.service import MultiService
from twisted.internet.error import ProcessDone, ProcessTerminated
from twisted.internet.protocol import ProcessProtocol
from twisted.python import failure
from twisted.python import reflect

log = logging.getLogger(__name__)


class LauncherService(MultiService):

    def __init__(self, cfg, plugin_mgr):
        MultiService.__init__(self)
        self.cfg = cfg
        self.bus = None
        self.caps = set()
        self.task_types = {}
        self.tasks = {}
        self.plugins = plugin_mgr
        self.plugins.p.launcher.pre_setup(self)
        self._set_caps()
        self._start_bus()
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

    def launch(self, msg):
        task = msg.task
        if task.task_type not in self.task_types:
            log.error("Got task of unsupported type %r", task.type)
            self.sendTaskStatus(task, 400,
                    "Task type is not supported by this node")
            return

        log.info("Starting task %s", task.task_uuid)
        self.tasks[task.task_uuid] = protocol = LaunchedWorker(self, task)
        try:
            self._spawn(protocol)
        except:
            self.taskFailed(task, failure.Failure())

    def _spawn(self, protocol):
        from twisted.internet import reactor

        transport, sock = socketpair(protocol.net, socket.AF_UNIX, reactor)

        args = [sys.executable, executor.__file__]
        reactor.spawnProcess(protocol, sys.executable, args,
                os.environ, childFDs={0:0, 1:1, 2:2, 3:sock.fileno()})

        sock.close()

    def taskFailed(self, task, reason):
        text = "Fatal error in task runner: %s: %s" % (
                reflect.qual(reason.type),
                reflect.safe_str(reason.value))
        self.sendTaskStatus(task, 400, text, detail=reason.getTraceback())

    def sendTaskStatus(self, task, code, text, detail=None):
        task.times.ticks += 1
        status = task.status
        status.code = code
        status.text = text
        status.detail = detail
        if status.final:
            log.info("Task %s finished", task.task_uuid)
            if task.task_uuid in self.tasks:
                del self.tasks[task.task_uuid]
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
        tasks = set(self.launcher.tasks.keys())
        msg = message.Heartbeat(caps=self.launcher.caps, tasks=tasks)
        self.launcher.bus.sendToTarget(msg)


class LaunchedWorker(ProcessProtocol):

    def __init__(self, launcher, task):
        self.launcher = launcher
        self.task = task
        self.net = LaunchedWorkerSocket(self)
        self.pid = None

    def connectionMade(self):
        self.pid = self.transport.pid
        log.debug("Executor %s started", self.pid)

        msg = message.StartWork(self.launcher.cfg, self.task)
        self.net.sendMessage(msg)

    def processEnded(self, reason):
        if reason.check(ProcessDone):
            log.debug("Executor %s terminated normally", self.pid)
            return
        elif reason.check(ProcessTerminated):
            if reason.value.signal:
                log.warning("Executor %s terminated with signal %s",
                        self.pid, reason.value.signal)
            else:
                log.warning("Executor %s terminated with status %s",
                        self.pid, reason.value.status)
        else:
            log.error("Executor %s terminated due to an unknown error:\%s",
                    self.pid, reason.getTraceback())

        self.launcher.taskFailed(self.task, reason)


class LaunchedWorkerSocket(PickleProtocol):

    def __init__(self, worker):
        self.worker = worker

    def messageReceived(self, msg):
        # FIXME: make sure to stash relayed status messages so we send the
        # correct tick count in case of failure.
        print 'msg: %r' % msg


class WorkerConfig(BusClientConfig):
    buildDir            = (cfgtypes.CfgPath, '/var/rmake')
    helperDir           = (cfgtypes.CfgPath, '/usr/libexec/rmake')
    lockDir             = (cfgtypes.CfgPath, '/var/lock')
    logDir              = (cfgtypes.CfgPath, '/var/log/rmake')
    pluginDirs          = (cfgtypes.CfgPathList, [])
    usePlugin           = (cfgtypes.CfgDict(cfgtypes.CfgBool), {})
