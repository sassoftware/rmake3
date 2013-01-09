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
Tests for rMake plugins.  These tests are for general plugin functionality.

Loading, etc.  For tests of server-side, client side plugins, look in
servertest and cmdlinetest.
"""

import re
import os
import sys
import time


from rmake_test import rmakehelp

from conary.lib import util

from rmake import plugins
from rmake.cmdline import main

class Main(main.RmakeMain):
    def __init__(self, pluginMgr, buildCfg, conaryCfg):
        self.pluginMgr = pluginMgr
        self.buildCfg = buildCfg
        self.conaryCfg = conaryCfg
        main.RmakeMain.__init__(self)

    def getConfigFile(self, argv):
        return (self.buildCfg, self.conaryCfg, self.pluginMgr)


class PluginTest(rmakehelp.RmakeHelper):
    def testPlugin(self):
        pluginDir = self.workDir + '/plugins'
        util.mkdirChain(pluginDir)
        self.writeFile(pluginDir + '/test.py', pluginTxt)
        mgr = plugins.PluginManager([pluginDir])
        mgr.loadPlugins()
        mainHandler = Main(mgr, self.buildCfg, self.cfg)
        mgr.callClientHook('client_preInit', mainHandler, ['rmake'])
        rc, txt = self.captureOutput(mainHandler.main, ['rmake', '--skip-default-config'])
        assert('test         Test Command' in txt)
        rc, txt = self.captureOutput(mainHandler.main, ['rmake', 'test', '--skip-default-config'])
        assert("TEST!\n" == txt)
        mgr.unloadPlugin('test')
        rc, txt = self.captureOutput(mainHandler.main, ['rmake', '--skip-default-config'])
        assert("test              Test Command" not in txt)

    def testGetPluginMgr(self):
        configClass = self.buildCfg.__class__
        p = plugins.getPluginManager(
                    ['rmake', '--skip-default-config',
                     '--plugin-dirs=%s,%s' % (self.workDir,
                                              self.workDir + '/foo')],
                    configClass)
        assert(p.pluginDirs == [self.workDir, self.workDir + '/foo'])
        p = plugins.getPluginManager(
                    ['rmake', 'skip-default-config',
                        '--plugin-dirs=%s,%s' % (self.workDir,
                                                 self.workDir + '/foo'),
                              '--no-plugins'],
                    configClass)
        assert(p.pluginDirs == [])
        p = plugins.getPluginManager(
                    ['rmake', '--skip-default-config'], configClass)
        assert(p.pluginDirs == configClass(False).pluginDirs)



pluginTxt = """
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
