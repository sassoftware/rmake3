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
