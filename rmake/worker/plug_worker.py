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

    taskClasses = ()

    def worker_get_task_types(self):
        """Return a mapping of task types to task handler.

        Handlers should be a subclass of L{TaskHandler}.
        """
        return dict((cls.taskType, cls) for cls in self.taskClasses)

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

    taskType = None

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
