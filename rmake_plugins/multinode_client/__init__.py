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
