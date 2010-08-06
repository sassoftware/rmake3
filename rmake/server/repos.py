#!/usr/bin/python
#
# Copyright (c) 2006-2007 rPath, Inc.  All rights reserved.
#
"""
Wrapper for starting the repository browser
"""
import os
import random
import signal
import socket
import sys

if __name__ == '__main__':
    if 'CONARY_PATH' in os.environ:
        sys.path.insert(0, os.environ['CONARY_PATH'])
    if 'RMAKE_PATH' in os.environ:
        sys.path.insert(0, os.environ['RMAKE_PATH'])

import tempfile

from BaseHTTPServer import HTTPServer
from SimpleHTTPServer import SimpleHTTPRequestHandler
import urllib
import time
import os

from conary import conarycfg
from conary import conaryclient
from conary import dbstore
from conary.lib import cfg, cfgtypes, log, util
from conary.repository import netclient
from conary.repository.netrepos.netserver import NetworkRepositoryServer
from conary.repository.netrepos import netauth, netserver
from conary.repository.errors import UserNotFound
oldExcepthook = sys.excepthook
try:
    from conary.server import server
except:
    # some versions of conary.server.server set the sys.excepthook 
    # at the import level.  But it has important classes that I must
    # use as a library.  So I make sure to reset the excepthook after importing
    # it.
    sys.excepthook = oldExcepthook
    raise

sys.excepthook = oldExcepthook

from conary.server import schema

from rmake import compat
from rmake import errors
from rmake.lib import daemon
from rmake.lib import logfile
from rmake.server import servercfg

conaryDir = sys.modules['conary'].__path__[0]

def startRepository(cfg, fork = True, logger=None):
    global conaryDir
    baseDir = cfg.serverDir
    if logger is None:
        logger = log

    reposDir = '%s/repos' % baseDir
    util.mkdirChain(reposDir)
    if not cfg.reposUser:
        passwordFile = reposDir + '/password'
        if os.path.exists(passwordFile):
            password = open(passwordFile).readline()[:-1]
        else:
            password = ''.join([ chr(random.randrange(ord('a'), ord('z'))) 
                               for x in range(10)])
            open(passwordFile, 'w').write(password + '\n')
            os.chmod(reposDir + '/password', 0700)
        cfg.reposUser.addServerGlob(cfg.reposName, 'rmake', password)

    serverConfig = os.path.join(cfg.getReposDir(), 'serverrc')
    if os.path.exists(serverConfig):
        os.unlink(serverConfig)
    serverCfg = server.ServerConfig(os.path.join(cfg.getReposDir(), 'serverrc'))
    serverCfg.repositoryDB = ('sqlite', cfg.getReposDbPath())
    serverCfg.contentsDir = cfg.getContentsPath()
    serverCfg.port = cfg.getReposInfo()[1]
    serverCfg.configKey('serverName', cfg.reposName) # this works with either
                                                     # 1.0.16 or 1.0.17+
    serverCfg.logFile = cfg.getReposDir() + '/repos.log'
    serverCfg.logFile = None

    # Transfer SSL settings from rMake config object
    if hasattr(server, 'SSL') and server.SSL:
        # The server supports starting in SSL mode
        serverCfg.useSSL = cfg.reposRequiresSsl()
        serverCfg.sslCert = cfg.sslCertPath
        serverCfg.sslKey = cfg.sslCertPath
    elif cfg.reposRequiresSsl():
        raise errors.RmakeError('Tried to start repository at %s, but missing ssl server library: Please install m2crypto' % (cfg.getRepositoryUrl(),))

    (driver, database) = serverCfg.repositoryDB
    db = dbstore.connect(database, driver)

    # Note - this will automatically migrate this repository! 
    # Since this is a throwaway repos anyway, I think that's
    # acceptable.
    compat.ConaryVersion().loadServerSchema(db)
    db.commit()
    db.close()

    user, password = cfg.reposUser.find(cfg.reposName)
    addUser(serverCfg, user, password, write=True)
    if not serverCfg.useSSL:
        # allow anonymous access if we're not securing this repos
        # by using SSL - no use securing access if it's all going to be
        # viewable via tcpdump.
        addUser(serverCfg, 'anonymous', 'anonymous')

    if fork:
        pid = os.fork()
        if pid:
            try:
                pingServer(cfg)
            except:
                killServer(pid)
                raise
            logger.info('Started repository "%s" on port %s (pid %s)' % (
                                                            cfg.reposName,
                                                            serverCfg.port,
                                                            pid))
            return pid
        elif hasattr(logger, 'close'):
            logger.close()
    try:
        os.chdir(cfg.getReposDir())
        serverrc = open(cfg.getReposConfigPath(), 'w')
        serverCfg.store(serverrc, includeDocs=False)
        util.mkdirChain(os.path.dirname(cfg.getReposLogPath()))
        logFile = logfile.LogFile(cfg.getReposLogPath())
        logFile.redirectOutput(close=True)
        serverrc.close()
        os.execv('%s/server/server.py' % conaryDir,
                 ['%s/server/server.py' % conaryDir,
                  '--config-file', cfg.getReposConfigPath()])
    except Exception, err:
        print >>sys.stderr, 'Could not start repository server: %s' % err
        os._exit(1)

def startProxy(cfg, fork = True, logger=None):
    global conaryDir
    baseDir = cfg.getProxyDir()
    proxyPort = cfg.getProxyInfo()[1]

    util.mkdirChain('%s/repos' % baseDir)

    if os.path.exists(cfg.getProxyConfigPath()):
        os.unlink(cfg.getProxyConfigPath())
    serverCfg = server.ServerConfig(cfg.getProxyConfigPath())
    serverCfg.serverName = []
    serverCfg.proxyDB = ('sqlite', cfg.getProxyPath())
    serverCfg.changesetCacheDir = cfg.getProxyChangesetPath()
    serverCfg.proxyContentsDir = cfg.getProxyContentsPath()
    serverCfg.port = proxyPort
    serverCfg.logFile = None

    # Transfer SSL settings from rMake config object
    if hasattr(server, 'SSL') and server.SSL:
        # The server supports starting in SSL mode
        serverCfg.useSSL = cfg.proxyRequiresSsl()
        serverCfg.sslCert = cfg.sslCertPath
        serverCfg.sslKey = cfg.sslCertPath

    if fork:
        pid = os.fork()
        if pid:
            try:
                pingServer(cfg, cfg.getProxyUrl())
            except:
                killServer(pid)
                raise
            if logger:
                logger.info('Started proxy on port %s (pid %s)' % (proxyPort,
                                                                   pid))
            return pid
        elif hasattr(logger, 'close'):
            logger.close()
    try:
        util.mkdirChain(cfg.getProxyDir())
        os.chdir(cfg.getProxyDir())
        serverrc = open(cfg.getProxyConfigPath(), 'w')
        serverCfg.store(serverrc, includeDocs=False)
        util.mkdirChain(os.path.dirname(cfg.getProxyLogPath()))
        util.mkdirChain(cfg.getProxyContentsPath())
        logFile = logfile.LogFile(cfg.getProxyLogPath())
        logFile.redirectOutput(close=True)
        serverrc.close()
        os.execv('%s/server/server.py' % conaryDir,
                 ['%s/server/server.py' % conaryDir,
                  '--config-file', cfg.getProxyConfigPath()])
    except Exception, err:
        print >>sys.stderr, 'Could not start proxy server: %s' % err
        os._exit(1)

def pingServer(cfg, proxyUrl=None):
    conaryCfg = conarycfg.ConaryConfiguration(False)
    conaryCfg.repositoryMap = cfg.getRepositoryMap()
    conaryCfg.user = cfg.reposUser
    if proxyUrl:
        if hasattr(conaryCfg,'proxyMap'):
            conaryCfg.proxyMap.update('conary:http*', '*', [proxyUrl])
        else:
            conaryCfg.conaryProxy['http'] = proxyUrl
            conaryCfg.conaryProxy['https'] = proxyUrl

    repos = conaryclient.ConaryClient(conaryCfg).getRepos()
    for i in range(0,20000):
        try:
            repos.c[cfg.reposName].checkVersion()
        except Exception, err:
            time.sleep(.1)
        else:
            return True
    raise

def killServer(*pids):
    for pid in pids:
        os.kill(pid, signal.SIGTERM)

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

if __name__ == '__main__':
    sys.excepthook = util.genExcepthook()
    rmakeConfig = servercfg.rMakeConfiguration(True)
    startRepository(rmakeConfig, fork=False)
