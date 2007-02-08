#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.  All rights reserved.
#
"""
rMake server daemon
"""
import os
import shutil
import signal
import sys

from conary.lib import misc, options
from conary import command

from rmake import compat
from rmake import constants
from rmake import plugins
from rmake.lib import daemon
from rmake.server import repos
from rmake.server import servercfg
from rmake.server import server

class ResetCommand(daemon.DaemonCommand):
    commands = ['reset']

    help = 'Remove all job data from rmake'

    def runCommand(self, daemon, cfg, argSet, args):
        for dir in (cfg.getReposDir(), cfg.getBuildLogDir(),
                    cfg.getDbContentsPath()):
            if os.path.exists(dir):
                print "Deleting %s" % dir
                shutil.rmtree(dir)
        for path in (cfg.getDbPath(),):
            if os.path.exists(path):
                print "Deleting %s" % path
                os.remove(path)

class rMakeDaemon(daemon.Daemon):
    name = 'rmake-server'
    commandName = 'rmake-server'
    version = constants.version
    configClass = servercfg.rMakeConfiguration
    loggerClass = server.ServerLogger
    user = constants.rmakeuser
    groups = [constants.chrootuser]
    commandList = list(daemon.Daemon.commandList) + [ResetCommand,
                                                     command.HelpCommand]

    def getConfigFile(self, argv):
        p = plugins.getPluginManager(argv, servercfg.rMakeConfiguration)
        p.callServerHook('server_preInit', self, argv)
        self.plugins = p
        cfg = daemon.Daemon.getConfigFile(self, argv)
        cfg.sanityCheck() 
        return cfg

    def doWork(self):
        cfg = self.cfg
        cfg.sanityCheckForStart()
        if not cfg.isExternalRepos():
            reposPid = repos.startRepository(cfg, fork=True, 
                                             logger=self.logger)
        else:
            reposPid = None
        misc.removeIfExists(cfg.socketPath)
        rMakeServer = server.rMakeServer(cfg.getServerUri(), cfg,
                                         repositoryPid=reposPid,
                                         pluginMgr=self.plugins)
        signal.signal(signal.SIGTERM, rMakeServer._signalHandler)
        signal.signal(signal.SIGINT, rMakeServer._signalHandler)
        try:
            rMakeServer.serve_forever()
        finally:
            if rMakeServer.repositoryPid is not None:
                self.killRepos(rMakeServer.repositoryPid)

    def killRepos(self, pid):
        self.logger.info('killing repository at %s' % pid)
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception, e:
            self.logger.warning(
            'Could not kill repository at pid %s: %s' % (pid, e))

    def runCommand(self, *args, **kw):
        return daemon.Daemon.runCommand(self, *args, **kw)

def main(argv):
    d = rMakeDaemon()
    try:
        compat.checkRequiredVersions()
        rc = d.main(argv)
        sys.exit(rc)
    except options.OptionError, err:
        d.usage()
        d.logger.error(err)
        sys.exit(1)
