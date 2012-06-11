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
Skeleton for dispatcher plugins.

Inherit from this to add functionality to the dispatcher, for example a new job
type. The pre/post hooks can also be used to start auxilliary functionality
needed by your job or task handlers.
"""

from rmake.core import handler as handler_mod
from rmake.lib import pluginlib


class DispatcherPlugin(pluginlib.Plugin):

    _plugin_type = 'dispatcher'

    handlerClasses = ()

    def dispatcher_pre_setup(self, dispatcher):
        """Called before the dispatcher initializes its services.

        Use this to register job types and RPC controllers.
        """
        for cls in self.handlerClasses:
            handler_mod.registerHandler(cls)

    def dispatcher_post_setup(self, dispatcher):
        """Called after the dispatcher initializes its services."""

    def dispatcher_worker_up(self, dispatcher, worker):
        """Called when a worker connects to the dispatcher."""

    def dispatcher_worker_down(self, dispatcher, worker):
        """Called when a worker disconnects from the dispatcher."""
