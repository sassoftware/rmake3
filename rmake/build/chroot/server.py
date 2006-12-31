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
import os
import select
import signal
import socket
import sys
import time
import traceback

from conary.lib import log, misc, options, util
from conary import conaryclient

from rmake.build.chroot import cook

from rmake import constants
from rmake.build import buildcfg
from rmake.lib.apiutils import *
from rmake.lib import apirpc, daemon, repocache

class ChrootServer(apirpc.XMLApiServer):

    _CLASS_API_VERSION = 1

    @api(version=1)
    @api_parameters(1, 'BuildConfiguration', 'label',
                       'str', 'version', 'flavor', 'str', 'int')
    @api_return(1, None)
    def buildTrove(self, callData, buildCfg, targetLabel,
                   name, version, flavor, logHost, logPort):

        buildCfg.root = self.cfg.root
        buildCfg.buildPath = self.cfg.root + '/tmp/rmake/builds'
        buildCfg.lookaside = self.cfg.root + '/tmp/rmake/cache'
        buildCfg.dbPath = '/var/lib/conarydb'

        if buildCfg.strictMode:
            conaryCfg = conarycfg.ConaryConfiguration(True)
            buildCfg.strictMode = False
            buildCfg.useConaryConfig(conaryCfg)
            buildCfg.strictMode = True
        path = '%s/tmp/conaryrc' % self.cfg.root
        util.mkdirChain(os.path.dirname(path))
        conaryrc = open(path, 'w')
        conaryrc.write('# This is the actual conary configuration used when\n'
                       '# building.')
        buildCfg.storeConaryCfg(conaryrc)
        conaryrc.close()

        repos = conaryclient.ConaryClient(buildCfg).getRepos()
        repos = repocache.CachingTroveSource(repos,
                                        self.cfg.root + '/var/rmake/cscache',
                                        readOnly=True)
        logPath, pid, buildInfo = cook.cookTrove(buildCfg, repos, self._logger,
                                                 name, version, flavor,
                                                 targetLabel, logHost, logPort)
        pid = buildInfo[1]
        self._buildInfo[name, version, flavor] = buildInfo
        return logPath, pid

    @api(version=1)
    @api_parameters(1, 'str', 'version', 'flavor', 'float')
    @api_return(1, None)
    def checkResults(self, callData, name, version, flavor, wait):
        if (name, version, flavor) in self._results:
            results = self._results[name, version, flavor]
        else:
            timeSpent = 0
            buildInfo = self._buildInfo[name, version, flavor]
            while True:
                results = cook.getResults(*buildInfo)
                if results:
                    break
                elif wait and timeSpent < wait:
                    time.sleep(.1)
                    timeSpent += .1
                else:
                    return ''
            del self._buildInfo[name, version, flavor]
        return freeze(cook.CookResults, results)

    @api(version=1)
    @api_parameters(1, 'str', 'version', 'flavor')
    @api_return(1, 'int')
    def subscribeToBuild(self, callData, name, version, flavor):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('', 0))
        port = s.getsockname()[1]
        s.listen(1)
        self._unconnectedSubscribers[s] = name, version, flavor
        return port

    @api(version=1)
    @api_parameters(1)
    @api_return(1, None)
    def stop(self, callData):
        self._results = []
        self._halt = True
        return

    def _serveLoopHook(self):
        ready = select.select(self._unconnectedSubscribers, [], [], 0.1)[0]
        for socket in ready:
            troveTup = self._unconnectedSubscribers.pop(socket)
            socket, caddr = socket.accept()
            self._subscribers.setdefault(troveTup, []).append(socket)
        for troveInfo, buildInfo in self._buildInfo.items():
            results = cook.getResults(*buildInfo)
            if not results:
                continue
            self._results[troveInfo] = results
            for socket in self._subscribers.get(troveInfo, []):
                socket.close()
            del self._buildInfo[troveInfo]

    def _signalHandler(self, sigNum, frame):
        # if they rekill, we just exit
        signal.signal(sigNum, signal.SIG_DFL)
        self._halt = True
        self._haltSignal = sigNum
        return

    def __init__(self, uri, cfg):
        self.cfg = cfg
        self._halt = False
        self._haltSignal = None
        self._buildInfo = {}
        self._unconnectedSubscribers = {}
        self._subscribers = {}
        self._results = {}
        apirpc.XMLApiServer.__init__(self, uri)

    def _shutDown(self):
        # we've gotten a request to halt, kill all jobs
        # and then kill ourselves
        self._stopBuilds()
        if self._haltSignal:
            os.kill(os.getpid(), self._haltSignal)
        sys.exit(0)

    def _stopBuilds(self):
        for troveNVF, buildInfo in self._buildInfo.items():
            cook.stopBuild(*buildInfo)
            del self._buildInfo[troveNVF]

class ChrootClient(object):
    def __init__(self, root, uri, pid=None):
        self.root = root
        self.pid = pid
        self.proxy = apirpc.ApiProxy(ChrootServer, uri)

    def subscribeToBuild(self, name, version, flavor):
        port = self.proxy.subscribeToBuild(name, version, flavor)
        s = socket.socket()
        s.connect(('localhost', port))
        self.resultsReadySocket = s

    def checkSubscription(self):
        ready = select.select([self.resultsReadySocket], [], [], 0.1)[0]
        if ready:
            done = self.resultsReadySocket.recv(1024)
            assert(done == '')
            self.resultsReadySocket.close()
            del self.resultsReadySocket
            return True
        else:
            return False

    def getPid(self):
        return self.pid

    def buildTrove(self, buildCfg, targetLabel, name, version, flavor,
                   logHost='', logPort=0):
        logPath, pid = self.proxy.buildTrove(buildCfg, targetLabel,
                                             name, version, flavor,
                                             logHost, logPort)
        logPath = self.root + logPath
        self.subscribeToBuild(name, version, flavor)
        return logPath, pid

    def checkResults(self, name, version, flavor, wait=False):
        results = self.proxy.checkResults(name, version, flavor, wait)
        if results == '':
            return None

        results = thaw(cook.CookResults, results)
        if results.csFile:
            results.csFile = self.root + results.csFile
        return results

    def stop(self):
        return self.proxy.stop()

    def ping(self, seconds=5, hook=None, sleep=0.1):
        timeSlept = 0
        while timeSlept < seconds:
            try:
                return self.proxy.ping()
            except:
                if timeSlept < seconds:
                    if hook:
                        hook()
                    time.sleep(sleep)
                    timeSlept += sleep
                else:
                    raise

# ----- daemon

class ChrootConfig(daemon.DaemonConfig):
    socketPath = '/tmp/rmake/lib/chrootsocket'
    root       = '/'
    logDir     = '/tmp/rmake/log'
    lockDir    = '/tmp/rmake/run'

    def __init__(self, readConfigFiles=False):
        daemon.DaemonConfig.__init__(self)

class ChrootDaemon(daemon.Daemon):
    name = 'chroot'
    version = constants.version
    configClass = ChrootConfig

    def __init__(self, *args, **kw):
        daemon.Daemon.__init__(self, *args, **kw)

    def runCommand(self, thisCommand, cfg, *args, **kw):
        cfg.socketPath = cfg.root + cfg.socketPath
        cfg.lockDir = cfg.root + cfg.lockDir
        cfg.logDir = cfg.root + cfg.logDir
        misc.removeIfExists(cfg.socketPath)
        util.mkdirChain(os.path.dirname(cfg.socketPath))
        util.mkdirChain(cfg.lockDir)
        util.mkdirChain(cfg.logDir)
        return daemon.Daemon.runCommand(self, thisCommand, cfg, *args, **kw)

    def doWork(self):
        cfg = self.cfg
        server = ChrootServer('unix://%s' % (cfg.socketPath), cfg)
        signal.signal(signal.SIGTERM, server._signalHandler)
        server.serve_forever()


def main(argv):
    try:
        rc = ChrootDaemon().main(sys.argv)
        sys.exit(rc)
    except options.OptionError, err:
        ChrootDaemon().usage()
        log.error(err)
        sys.exit(1)

if __name__ == '__main__':
    sys.path.insert(0, '/usr/share/rmake')
    sys.exit(main(sys.argv))
