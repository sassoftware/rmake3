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
Skeletons for worker and launcher plugins.

Worker plugins are used to implement handlers for new task types. They are
invoked both by the launcher (to determine which tasks can be run) and by the
worker (to perform the task).

Launcher plugins are used to add special functionality to the launcher and are
not typically required in order to add a new task type.
"""

import logging
from twisted.internet import threads

from rmake.core.types import FrozenObject, JobStatus
from rmake.lib import pluginlib


class LauncherPlugin(pluginlib.Plugin):

    _plugin_type = 'launcher'

    def launcher_pre_setup(self, launcher):
        pass

    def launcher_post_setup(self, launcher):
        pass


class WorkerPlugin(pluginlib.Plugin):

    _plugin_type = 'worker'

    def worker_get_task_types(self):
        """Return a mapping of task types to task handler.

        Handlers should be a subclass of L{TaskHandler}.
        """
        return {}

    def worker_pre_build(self, handler):
        pass


class TaskHandler(object):
    """
    Subclass for task handlers.

    Handlers should override the run() method and report progress, completion,
    and failure using the setStatus() method. Work is done in a secondary
    thread, so do not call any twisted methods without callFromThread!

    Handlers that are purely non-blocking may choose to override start()
    instead and integrate with the reactor directly.
    """

    def __init__(self, wchild, task):
        self._wchild = wchild
        self.wcfg = wchild.cfg
        self.task = task.thaw()
        # TODO: Replace or configure this with something that will send logs
        # upstream.
        self.log = logging.getLogger('rmake.task.' + task.task_uuid.short)

    # Reactor methods -- don't call from run()!

    def start(self):
        return threads.deferToThread(self.run)

    # Worker thread methods

    def sendStatus(self, code, text, detail=None):
        self.task.status = JobStatus(code, text, detail)
        return self._sendStatus()

    def _sendStatus(self):
        from twisted.internet import reactor
        reactor.callFromThread(self._wchild.sendTask, self.task.freeze())

    def failTask(self, reason):
        from twisted.internet import reactor
        reactor.callFromThread(self._wchild.failTask, reason)

    def run(self):
        raise NotImplementedError

    # Helper methods
    def getData(self):
        return self.task.task_data.getObject()

    def setData(self, obj):
        self.task.task_data = FrozenObject.fromObject(obj)
