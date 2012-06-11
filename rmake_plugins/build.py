#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


"""
This plugin serves as the entry point to the basic build functionality of rMake.
"""

import logging
from rmake.build import constants as buildconst
from rmake.build import disp_handler
from rmake.build import nodecfg
from rmake.build import repos
from rmake.build import server
from rmake.build import servercfg
from rmake.build import worker
from rmake.core import plug_dispatcher
from rmake.worker import plug_worker

log = logging.getLogger(__name__)


class BuildPlugin(plug_dispatcher.DispatcherPlugin, plug_worker.WorkerPlugin):

    cfg = None

    # Dispatcher

    def dispatcher_pre_setup(self, dispatcher):
        disp_handler.register()

        self.cfg = self.configFromOptions(servercfg.rMakeConfiguration)
        self.server = server.BuildServer(dispatcher, self.cfg)
        dispatcher._addChild('build', self.server)

    def dispatcher_post_setup(self, dispatcher):
        from twisted.internet import reactor
        reactor.callWhenRunning(self._start_servers)
        self.server._post_setup()

    def _start_servers(self):
        from twisted.internet import reactor
        try:
            if not self.cfg.isExternalRepos():
                repos.startRepository(self.cfg)
            if not self.cfg.isExternalProxy():
                repos.startProxy(self.cfg)
        except:
            log.exception("Error starting server:")
            reactor.stop()

    # Worker

    def worker_get_task_types(self):
        return {
                buildconst.LOAD_TASK: worker.LoadTask,
                buildconst.RESOLVE_TASK: worker.ResolveTask,
                buildconst.BUILD_TASK: worker.BuildTask,
                }

    def worker_pre_build(self, handler):
        handler.cfg = self.configFromOptions(nodecfg.NodeConfiguration)
