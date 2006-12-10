#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
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
"""

