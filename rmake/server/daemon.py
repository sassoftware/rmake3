#!/usr/bin/python
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
rMake server daemon
"""
import os
import shutil
import signal
import sys

from conary.lib import options, util
from conary import command

from rmake import compat
from rmake import constants
from rmake import plugins
from rmake.lib import daemon
from rmake.server import repos
from rmake.server import servercfg
from rmake.server import server
# needed for deleting chroots upon "reset"
from rmake.worker.chroot import rootmanager

class ResetCommand(daemon.DaemonCommand):
    commands = ['reset']

    help = 'Remove all job data from rmake'

    def runCommand(self, daemon, cfg, argSet, args):
        for dir in (cfg.getReposDir(), cfg.getBuildLogDir(),
                    cfg.getDbContentsPath(), cfg.getProxyDir(),
                    cfg.getResolverCachePath()):
            if os.path.exists(dir):
                print "Deleting %s" % dir
                shutil.rmtree(dir)

        for dir in (cfg.getCacheDir(),):
            if os.path.exists(dir):
                print "Deleting subdirectories of %s" % dir
                for subDir in os.listdir(dir):
                    shutil.rmtree(dir + '/' + subDir)
        for path in (cfg.getDbPath()[1],):
            if os.path.exists(path):
                print "Deleting %s" % path
                os.remove(path)
        rootManager = rootmanager.ChrootManager(cfg)
        chroots = rootManager.listChroots()
        print "Deleting %s chroots" % len(chroots)
        for chroot in chroots:
            rootManager.deleteChroot(chroot)

class HelpCommand(daemon.DaemonCommand, command.HelpCommand):
    commands = ['help']

    def runCommand(self, daemon, cfg, argSet, args):
        command.HelpCommand.runCommand(self, cfg, argSet, args)

class rMakeDaemon(daemon.Daemon):
    name = 'rmake-server'
    commandName = 'rmake-server'
    version = constants.version
    configClass = servercfg.rMakeConfiguration
    loggerClass = server.ServerLogger
    user = constants.rmakeUser
    groups = [constants.chrootUser]
    capabilities = 'cap_sys_chroot+ep'
    commandList = list(daemon.Daemon.commandList) + [ResetCommand, HelpCommand]

    def getConfigFile(self, argv):
        p = plugins.getPluginManager(argv, servercfg.rMakeConfiguration)
        p.callServerHook('server_preInit', self, argv)
        self.plugins = p
        cfg = daemon.Daemon.getConfigFile(self, argv)
        cfg.sanityCheck() 
        return cfg

    def doWork(self):
        cfg = self.cfg
        try:
            cfg.sanityCheckForStart()
        except Exception, e:
            self.logger.error(e)
            sys.exit(1)
        reposPid = None
        proxyPid = None

        rMakeServer = None
        try:
            if not cfg.isExternalRepos():
                reposPid = repos.startRepository(cfg, fork=True, 
                                                 logger=self.logger)
            if cfg.proxyUrl and not cfg.isExternalProxy():
                proxyPid = repos.startProxy(cfg, fork=True,
                                            logger=self.logger)
            if cfg.getSocketPath():
                util.removeIfExists(cfg.getSocketPath())
            rMakeServer = server.rMakeServer(cfg.getServerUri(), cfg,
                                             repositoryPid=reposPid,
                                             proxyPid=proxyPid,
                                             pluginMgr=self.plugins)
            rMakeServer._installSignalHandlers()
            rMakeServer.serve_forever()
        finally:
            if rMakeServer:
                if rMakeServer.repositoryPid:
                    self.killRepos(reposPid)
                if rMakeServer.proxyPid:
                    self.killRepos(proxyPid, 'proxy')
            else:
                # rmake server failed to start
                if reposPid:
                    self.killRepos(reposPid)
                if proxyPid:
                    self.killRepos(proxyPid, 'proxy')


    def killRepos(self, pid, name='repository'):
        self.logger.info('killing %s at %s' % (name, pid))
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception, e:
            self.logger.warning(
            'Could not kill %s at pid %s: %s' % (name, pid, e))

    def runCommand(self, *args, **kw):
        return daemon.Daemon.runCommand(self, *args, **kw)

def main(argv):
    d = rMakeDaemon()
    if '--debug-all' or '-d' in argv:
        sys.excepthook = util.genExcepthook(debug=True, debugCtrlC=True)
    try:
        compat.checkRequiredVersions()
        rc = d.mainWithExceptionHandling(argv)
        return rc
    except options.OptionError, err:
        d.usage()
        d.logger.error(err)
        return 1
