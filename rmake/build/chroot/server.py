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
import signal
import sys
import time
import traceback

from conary.lib import log, misc, options, util

from rmake.build.chroot import cook

from rmake import constants
from rmake.build import buildcfg
from rmake.lib.apiutils import *
from rmake.lib import apirpc, daemon

class ChrootServer(apirpc.XMLApiServer):

    _CLASS_API_VERSION = 1

    @api(version=1)
    @api_parameters(1, 'BuildConfiguration', 'label',
                       'str', 'version', 'flavor')
    @api_return(1, None)
    def buildTrove(self, callData, buildCfg, targetLabel,
                   name, version, flavor):

        buildCfg.root = self.cfg.root
        buildCfg.buildPath = self.cfg.root + '/tmp/rmake/builds'
        buildCfg.lookaside = self.cfg.root + '/tmp/rmake/cache'
        buildCfg.dbPath = '/var/lib/conarydb'

        logPath, pid, buildInfo = cook.cookTrove(buildCfg,
                                                 name, version, flavor,
                                                 targetLabel)
        pid = buildInfo[1]
        self._buildInfo[name, version, flavor] = buildInfo
        return logPath, pid

    @api(version=1)
    @api_parameters(1, 'str', 'version', 'flavor', 'float')
    @api_return(1, None)
    def checkResults(self, callData, name, version, flavor, wait):
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
    @api_parameters(1)
    @api_return(1, None)
    def stop(self, callData):
        self._results = []
        self._halt = True
        return

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
        apirpc.XMLApiServer.__init__(self, uri)

    def _serveLoopHook(self):
        if self._halt:
            try:
                log.info('Stopping chroot server')
                # we've gotten a request to halt, kill all jobs  
                # and then kill ourselves
                self._stopBuilds()
                if self._haltSignal:
                    os.kill(os.getpid(), self._haltSignal)
            except Exception, err:
                try:
                    log.error('Halt failed: %s\n%s', err, 
                              traceback.format_exc())
                finally:
                    os._exit(1)
            else:
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

    def getPid(self):
        return self.pid

    def buildTrove(self, buildCfg, targetLabel, name, version, flavor):
        logPath, pid = self.proxy.buildTrove(buildCfg, targetLabel,
                                             name, version, flavor)
        logPath = self.root + logPath
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
