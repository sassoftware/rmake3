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
Skeleton for dispatcher plugins.

Inherit from this to add functionality to the dispatcher, for example a new job
type. The pre/post hooks can also be used to start auxilliary functionality
needed by your job or task handlers.
"""

from rmake.lib import pluginlib


class DispatcherPlugin(pluginlib.Plugin):

    _plugin_type = 'dispatcher'

    def dispatcher_pre_setup(self, dispatcher):
        """Called before the dispatcher initializes its services.

        Use this to register job types and RPC controllers.
        """

    def dispatcher_post_setup(self, dispatcher):
        """Called after the dispatcher initializes its services."""

    def dispatcher_worker_up(self, dispatcher, worker):
        """Called when a worker connects to the dispatcher."""

    def dispatcher_worker_down(self, dispatcher, worker):
        """Called when a worker disconnects from the dispatcher."""
