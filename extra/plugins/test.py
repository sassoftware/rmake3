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
Example plugin that adds a command to the client front end.
"""
from rmake.plugins import plugin
from rmake.cmdline import command

class TestPlugin(plugin.ClientPlugin):
    def client_preInit(self, mainObj, argv):
        self.mainObj = mainObj
        mainObj._registerCommand(TestCommand)

    def unload(self):
        self.mainObj._unregisterCommand(TestCommand)

class TestCommand(command.rMakeCommand):
    commands = ['test']
    commandGroup = command.CG_INFO
    help = 'Test Command'

    def runCommand(self, client, cfg, argSet, args):
        print 'TEST!'
