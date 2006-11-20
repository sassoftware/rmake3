#!/usr/bin/python2.4
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
rMake server daemon
"""
import os
import shutil
import signal
import sys

from conary.lib import misc, options, log

from rmake import constants
from rmake.lib import daemon
from rmake.server import servercfg
from rmake.server import repos
from rmake.server import server

class ResetCommand(daemon.DaemonCommand):
    commands = ['reset']

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
    name = 'rmake'
    version = constants.version
    configClass = servercfg.rMakeConfiguration
    user = constants.rmakeuser
    commandList = list(daemon.Daemon.commandList) + [ResetCommand]

    def __init__(self, *args, **kw):
        daemon.Daemon.__init__(self, *args, **kw)

    def getConfigFile(self, argv):
        cfg = daemon.Daemon.getConfigFile(self, argv)
        cfg.sanityCheck() 
        return cfg

    def doWork(self):
        cfg = self.cfg
        cfg.sanityCheck()
        if not cfg.isExternalRepos():
            reposPid = repos.startRepository(cfg, fork=True)
        else:
            reposPid = None
        misc.removeIfExists(cfg.socketPath)
        rMakeServer = server.rMakeServer(cfg.getServerUri(), cfg,
                                    repositoryPid=reposPid)
        signal.signal(signal.SIGTERM, rMakeServer._signalHandler)
        signal.signal(signal.SIGINT, rMakeServer._signalHandler)
        try:
            rMakeServer.serve_forever()
        finally:
            if rMakeServer.repositoryPid is not None:
                self.killRepos(rMakeServer.repositoryPid)

    def killRepos(self, pid):
        log.info('killing repository at %s' % pid)
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception, e:
            log.warning(
            'Could not kill repository at pid %s: %s' % (pid, e))

def main(argv):
    try:
        rc = rMakeDaemon().main(argv)
        sys.exit(rc)
    except options.OptionError, err:
        rMakeDaemon().usage()
        log.error(err)
        sys.exit(1)
