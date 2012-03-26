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


import os
import socket
import traceback

from conary.lib import cfgtypes, log, util

from rmake import errors
from rmake.plugins import plugin

from rmake_plugins.multinode_client.build import buildcfg
from rmake_plugins.multinode_client.cmdline import command
from rmake_plugins.multinode_client.server import client


class MultinodeClientPlugin(plugin.ClientPlugin, plugin.LibraryPlugin):
    types = [plugin.TYPE_CLIENT, plugin.TYPE_LIBRARY]

    def client_preInit(self, main, argv):
        # Add support for remote rmake clients
        buildcfg.updateConfig()
        client.attach()
        command.addCommands(main)

    def library_preInit(self):
        buildcfg.updateConfig()
        client.attach()

    def client_preCommand(self, main, thisCommand,
                          (buildConfig, conaryConfig), argSet, args):
        if buildConfig.copyInConfig and not buildConfig.isDefault('copyInConfig'):
            log.warning('Cannot set copyInConfig in multinode mode')
        if buildConfig.copyInConary and not buildConfig.isDefault('copyInConary'):
            log.warning('Cannot set copyInConary in multinode mode')
        buildConfig.copyInConary = False
        buildConfig.copyInConfig = False

    def client_preCommand2(self, main, rmakeHelper, command):
        client.MultinodeClientExtension().attach(rmakeHelper.client)
