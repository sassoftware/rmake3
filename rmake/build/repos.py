#
# Copyright (c) 2006-2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
"""
Wrapper for starting the repository browser
"""

import errno
import logging
import os
import random
import sys
import time

if __name__ == '__main__':
    if 'CONARY_PATH' in os.environ:
        sys.path.insert(0, os.environ['CONARY_PATH'])
    if 'RMAKE_PATH' in os.environ:
        sys.path.insert(0, os.environ['RMAKE_PATH'])

from conary import conarycfg
from conary import conaryclient
from conary import dbstore
from conary.lib import util
from conary.repository.netrepos.netserver import NetworkRepositoryServer
from conary.repository.errors import UserNotFound
from conary.server import server as cny_server
from conary.server import schema as cny_schema
from rmake import errors
from twisted.internet import error as tw_err
from twisted.internet import protocol

log = logging.getLogger(__name__)

conaryDir = sys.modules['conary'].__path__[0]


def startRepository(cfg, logger=None):
    reposDir = cfg.getReposDir()
    util.mkdirChain(reposDir)

    # Generate and store a random password for the rmake user if not configured
    # with one.
    if not cfg.reposUser:
        passwordFile = reposDir + '/password'
        if os.path.exists(passwordFile):
            password = open(passwordFile).readline().strip()
        else:
            password = ''.join([ chr(random.randrange(ord('a'), ord('z'))) 
                               for x in range(10)])
            open(passwordFile, 'w').write(password + '\n')
            os.chmod(reposDir + '/password', 0700)
        cfg.reposUser.addServerGlob(cfg.reposName, 'rmake', password)

    serverCfg = cny_server.ServerConfig()
    serverCfg.repositoryDB = ('sqlite', cfg.getReposDbPath())
    serverCfg.contentsDir = cfg.getContentsPath()
    serverCfg.port = cfg.getReposInfo()[1]
    serverCfg.configKey('serverName', cfg.reposName)

    # Transfer SSL settings from rMake config object
    if getattr(cny_server, 'SSL', None):
        # The server supports starting in SSL mode
        serverCfg.useSSL = cfg.reposRequiresSsl()
        serverCfg.sslCert = cfg.sslCertPath
        serverCfg.sslKey = cfg.sslCertPath
    elif cfg.reposRequiresSsl():
        raise errors.RmakeError("Tried to start repository at %s, but missing "
                "ssl server library: Please install m2crypto." %
                (cfg.getRepositoryUrl(),))

    (driver, database) = serverCfg.repositoryDB
    db = dbstore.connect(database, driver)

    # Note - this will automatically migrate this repository! 
    # Since this is a throwaway repos anyway, I think that's
    # acceptable.
    cny_schema.loadSchema(db, doMigrate=True)
    db.commit()
    db.close()

    user, password = cfg.reposUser.find(cfg.reposName)
    addUser(serverCfg, user, password, write=True)
    if not serverCfg.useSSL:
        # allow anonymous access if we're not securing this repos
        # by using SSL - no use securing access if it's all going to be
        # viewable via tcpdump.
        addUser(serverCfg, 'anonymous', 'anonymous')

    return _startServer(serverCfg, cfg.getReposLogPath(),
            cfg.getReposConfigPath(), 'repository')


def startProxy(cfg, logger=None):
    proxyDir = cfg.getProxyDir()
    proxyPort = cfg.getProxyInfo()[1]

    util.mkdirChain(proxyDir)
    os.chdir(proxyDir)

    serverCfg = cny_server.ServerConfig()
    serverCfg.serverName = []
    serverCfg.proxyDB = ('sqlite', cfg.getProxyPath())
    serverCfg.changesetCacheDir = cfg.getProxyChangesetPath()
    serverCfg.proxyContentsDir = cfg.getProxyContentsPath()
    serverCfg.port = proxyPort

    # Transfer SSL settings from rMake config object
    if getattr(cny_server, 'SSL', None):
        # The server supports starting in SSL mode
        serverCfg.useSSL = cfg.proxyRequiresSsl()
        serverCfg.sslCert = cfg.sslCertPath
        serverCfg.sslKey = cfg.sslCertPath

    util.mkdirChain(cfg.getProxyContentsPath())
    return _startServer(serverCfg, cfg.getProxyLogPath(),
            cfg.getProxyConfigPath(), 'proxy')


def _startServer(serverCfg, logPath, cfgPath, name):

    util.mkdirChain(os.path.dirname(logPath))

    serverrc = open(cfgPath, 'w')
    serverCfg.store(serverrc, includeDocs=False)
    serverrc.close()

    repos = os.path.join(conaryDir, 'server', 'server.py')
    proto = MonitorProtocol(logPath, name)
    from twisted.internet import reactor
    return reactor.spawnProcess(proto, repos,
            [repos, '--config-file', cfgPath])


class MonitorProtocol(protocol.ProcessProtocol):

    def __init__(self, logPath, name):
        self.logPath = logPath
        self.logFile = None
        self.logInode = None
        self.name = name

    def writeLog(self, data):
        if self.logFile:
            # Close the logfile if it has been rotated away.
            try:
                st = os.stat(self.logPath)
            except OSError, err:
                if err.errno != errno.ENOENT:
                    raise
                inode = None
            else:
                inode = st.st_dev, st.st_ino
            if inode != self.logInode:
                self.logFile.close()
                self.logFile = None

        if not self.logFile:
            self.logFile = open(self.logPath, 'a')
            st = os.fstat(self.logFile.fileno())
            self.logInode = st.st_dev, st.st_ino

        self.logFile.write(data)
        self.logFile.flush()

    def processEnded(self, reason):
        if reason.check(tw_err.ProcessDone):
            return
        elif reason.check(tw_err.ProcessTerminated):
            msg = "Process exited with status %s" % reason.value.status
        else:
            msg = "Process ended with unknown error"
        log.error("%s terminated unexpectedly: %s\n"
                "Check the logfile for details: %s", self.name, msg,
                self.logPath)
        from twisted.internet import reactor
        reactor.stop()

    outReceived = errReceived = writeLog


def pingServer(cfg, proxyUrl=None):
    conaryCfg = conarycfg.ConaryConfiguration(False)
    conaryCfg.repositoryMap = cfg.getRepositoryMap()
    conaryCfg.user = cfg.reposUser
    if proxyUrl:
        conaryCfg.conaryProxy = {'http'  : proxyUrl,
                                 'https' : proxyUrl}
    else:
        proxy = None
    repos = conaryclient.ConaryClient(conaryCfg).getRepos()
    for i in range(0,20000):
        try:
            repos.c[cfg.reposName].checkVersion()
        except Exception, err:
            time.sleep(.1)
        else:
            return True
    raise


def addUser(cfg, name, password=None, write=False):
    baseUrl="http://127.0.0.1:%s/" % (cfg.port,)
    netRepos = NetworkRepositoryServer(cfg, baseUrl)
    try:
        netRepos.auth.userAuth.getUserIdByName(name)
    except UserNotFound: # yuck, we need a hasUser interface
        netRepos.auth.addUser(name, password)
        if hasattr(netRepos.auth, 'addRole'):
            netRepos.auth.addRole(name)
            netRepos.auth.addRoleMember(name, name)
        netRepos.auth.addAcl(name, None, None, write, False)
    else:
        netRepos.auth.changePassword(name, password)
