#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.  All rights reserved.
#
import errno
import os
import select
import signal
import socket
import sys
import time
import traceback

from conary.lib import options, util
from conary.lib import coveragehook
from conary import conarycfg
from conary import conaryclient

from rmake.worker.chroot import cook

from rmake import constants
from rmake.build import buildcfg
from rmake.lib.apiutils import *
from rmake.lib import apirpc, daemon, logger, repocache, telnetserver

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

        if not buildCfg.copyInConary:
            buildCfg.resetToDefault('policyDirs')
        if not buildCfg.copyInConfig:
            for option in buildCfg._dirsToCopy + buildCfg._pathsToCopy:
                buildCfg.resetToDefault(option)
            conaryCfg = conarycfg.ConaryConfiguration(True)
            buildCfg.strictMode = False
            buildCfg.useConaryConfig(conaryCfg)
            buildCfg.strictMode = True
        if self.cfg.root:
            # test path - we don't have a way to have managed policy
            # in this case.
            buildCfg.enforceManagedPolicy = False
        path = '%s/tmp/conaryrc' % self.cfg.root
        util.mkdirChain(os.path.dirname(path))
        conaryrc = open(path, 'w')
        conaryrc.write('# This is the actual conary configuration used when\n'
                       '# building.\n')
        buildCfg.storeConaryCfg(conaryrc)
        conaryrc.close()

        repos = conaryclient.ConaryClient(buildCfg).getRepos()
        if not name.startswith('group-'):
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
        if not (name, version, flavor) in self._buildInfo:
            return 0
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

    @api(version=1)
    @api_parameters(1, 'str')
    @api_return(1, 'int')
    def startSession(self, callData, command=['/bin/bash', '-l']):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('', 0))
        port = s.getsockname()[1]
        pid = self._fork('Telnet session')
        if pid:
            # Note that when this session dies, the server will die.
            # This is in recognition of the fact that this chroot server,
            # while made to handle multiple commands, in fact only ever
            # receives one command and then dies when it finishes.
            # Perhaps we should get rid of this daemon and instead
            # make it a simple program?
            self._sessionPid = pid
            return port
        try:
            if os.path.exists('/tmp/rmake/builds'):
                workDir = '/tmp/rmake/builds'
            else:
                workDir = '/'
            t = telnetserver.TelnetServerForCommand(('', port), command,
                                                    workDir=workDir)
            self._try('Telnet session', t.handle_request)
        finally:
            os._exit(1)


    def _serveLoopHook(self):
        try:
            ready = select.select(self._unconnectedSubscribers, [], [], 0.1)[0]
        except select.error, err:
            ready = []
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
        self._collectChildren()

    def _pidDied(self, pid, status, name=None):
        if pid == self._sessionPid:
            self._halt = True
        apirpc.XMLApiServer._pidDied(self, pid, status, name=name)

    def _signalHandler(self, sigNum, frame):
        # if they rekill, we just exit
        signal.signal(sigNum, signal.SIG_DFL)
        self._halt = True
        self._haltSignal = sigNum
        return

    def __init__(self, uri, cfg, quiet=False):
        self.cfg = cfg
        self._halt = False
        self._haltSignal = None
        self._buildInfo = {}
        self._unconnectedSubscribers = {}
        self._subscribers = {}
        self._results = {}
        self._sessionPid = None
        serverLogger = logger.ServerLogger('chroot')
        apirpc.XMLApiServer.__init__(self, uri, logger=serverLogger)
        if quiet:
            self.getLogger().setQuietMode()

    def _shutDown(self):
        # we've gotten a request to halt, kill all jobs
        # and then kill ourselves
        self._stopBuilds()
        self._killAllPids()
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
        self.proxy = apirpc.XMLApiProxy(ChrootServer, uri)
        self.resultsReadySocket = None

    def startSession(self, command=['/bin/sh']):
        return self.proxy.startSession(command)

    def subscribeToBuild(self, name, version, flavor):
        port = self.proxy.subscribeToBuild(name, version, flavor)
        if not port:
            return False
        s = socket.socket()
        s.connect(('localhost', port))
        self.resultsReadySocket = s
        return True

    def checkSubscription(self, timeout=0.1):
        if not self.resultsReadySocket:
            return True
        try:
            ready = select.select([self.resultsReadySocket], [], [], timeout)[0]
        except select.error, err:
            return False
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
        if not self.pid:
            return
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except OSError, err:
            if err == errno.ECHILD:
                self.pid = None
                return 0
            raise
        if pid:
            # HM, we lose signal info this way, is that ok?
            self.pid = None
            return status
        rc = self.proxy.stop()
        pid, status = os.waitpid(self.pid, 0)
        self.pid = None
        return status

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
    logDir     = '/tmp/log'
    lockDir    = '/tmp/run'

    def __init__(self, readConfigFiles=False):
        daemon.DaemonConfig.__init__(self)
        self.lockDir = self.lockDir + '.%s' % os.getpid()
        self.logDir = self.logDir + '.%s' % os.getpid()

class StartCommand(daemon.StartCommand):

    def addConfigOptions(self, cfgMap, argDef):
        cfgMap['socket'] = 'socketPath', daemon.ONE_PARAM
        daemon.StartCommand.addConfigOptions(self, cfgMap, argDef)

class ChrootDaemon(daemon.Daemon):
    name = 'rmake-chroot'
    version = constants.version
    configClass = ChrootConfig

    def __init__(self, *args, **kw):
        daemon.Daemon.__init__(self, *args, **kw)
        self._registerCommand(StartCommand)

    def runCommand(self, thisCommand, cfg, *args, **kw):
        cfg.socketPath = cfg.root + cfg.socketPath
        cfg.logDir = cfg.root + cfg.logDir
        cfg.lockDir = cfg.root + cfg.lockDir
        util.removeIfExists(cfg.socketPath)
        util.mkdirChain(os.path.dirname(cfg.socketPath))
        util.mkdirChain(cfg.lockDir)
        util.mkdirChain(cfg.logDir)
        return daemon.Daemon.runCommand(self, thisCommand, cfg, *args, **kw)

    def doWork(self):
        cfg = self.cfg
        server = ChrootServer('unix://%s' % (cfg.socketPath), cfg)
        server._installSignalHandlers()
        server.serve_forever()


def main(argv):
    d = ChrootDaemon()
    rc = d.main(sys.argv)
    sys.exit(rc)

if __name__ == '__main__':
    coveragehook.install()
    sys.path.insert(0, '/usr/share/rmake')
    sys.exit(main(sys.argv))
