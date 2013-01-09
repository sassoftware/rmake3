#!/usr/bin/python
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
rMake multi-node worker daemon
"""
import os
import shutil
import sys

from conary.lib import options
from conary import command

from rmake import constants
from rmake import plugins
from rmake.lib import daemon
from rmake.worker.chroot import rootmanager
from rmake.multinode import workernode

from rmake.node import nodecfg

class ResetCommand(daemon.DaemonCommand):
    commands = ['reset']

    help = 'Remove all job data from rmake'

    def runCommand(self, daemon, cfg, argSet, args):
        for dir in (cfg.getBuildLogDir(),):
            if os.path.exists(dir):
                print "Deleting %s" % dir
                shutil.rmtree(dir)

        for dir in (cfg.getCacheDir(),):
            if os.path.exists(dir):
                print "Deleting subdirectories of %s" % dir
                for subDir in os.listdir(dir):
                    shutil.rmtree(dir + '/' + subDir)
        rootManager = rootmanager.ChrootManager(cfg)
        chroots = rootManager.listChroots()
        print "Deleting %s chroots" % len(chroots)
        for chroot in chroots:
            rootManager.deleteChroot(chroot)

class HelpCommand(command.HelpCommand):
    def addParameters(self, argDef):
        argDef["config"] = options.MULT_PARAM
        return command.HelpCommand.addParameters(self, argDef)

    def runCommand(self, daemon, cfg, argSet, args):
        return command.HelpCommand.runCommand(self, cfg, argSet, args)

class HelpCommand(command.HelpCommand):
    def addParameters(self, argDef):
        argDef["config"] = options.MULT_PARAM
        return command.HelpCommand.addParameters(self, argDef)

    def runCommand(self, daemon, cfg, argSet, args):
        return command.HelpCommand.runCommand(self, cfg, argSet, args)

class rMakeNodeDaemon(daemon.Daemon):
    name = 'rmake-node'
    commandName = 'rmake-node'
    version = constants.version
    configClass = nodecfg.NodeConfiguration
    user = constants.rmakeUser
    groups = [constants.chrootUser]
    capabilities = 'cap_sys_chroot+ep'
    commandList = list(daemon.Daemon.commandList) + \
                  [ResetCommand, HelpCommand]

    def getConfigFile(self, argv):
        self.plugins = plugins.getPluginManager(argv, nodecfg.NodeConfiguration)
        cfg = daemon.Daemon.getConfigFile(self, argv)
        cfg.sanityCheck()
        return cfg

    def doWork(self):
        cfg = self.cfg
        from rmake import compat
        compat.checkRequiredVersions()
        nodeServer = workernode.rMakeWorkerNodeServer(cfg)
        nodeServer._installSignalHandlers()
        nodeServer.serve_forever()

def main(argv):
    d = rMakeNodeDaemon()
    sys.exit(d.mainWithExceptionHandling(argv))
