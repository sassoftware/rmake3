#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.  All rights reserved.
#
"""
Wrapper for starting the repository browser
"""
import os
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
from conary import dbstore
from conary.lib import cfg, cfgtypes, log, util
from conary.repository import errors
from conary.repository import netclient
from conary.repository.netrepos.netserver import NetworkRepositoryServer
from conary.repository.netrepos import netauth, netserver
from conary.server import schema, server

from rmake.lib import daemon
from rmake.lib import logfile
from rmake.server import servercfg

conaryDir = sys.modules['conary'].__path__[0]

def startRepository(cfg, fork = True, logger=None):
    global conaryDir
    baseDir = cfg.serverDir
    if logger is None:
        logger = log

    util.mkdirChain('%s/repos' % baseDir)


    serverConfig = os.path.join(cfg.getReposDir(), 'serverrc')
    if os.path.exists(serverConfig):
        os.unlink(serverConfig)
    serverCfg = server.ServerConfig(os.path.join(cfg.getReposDir(), 'serverrc'))
    serverCfg.repositoryDB = ('sqlite', cfg.getReposPath())
    serverCfg.contentsDir = cfg.getContentsPath()
    serverCfg.port = cfg.serverPort
    serverCfg.configKey('serverName', cfg.serverName) # this works with either
                                                      # 1.0.16 or 1.0.17+
    serverCfg.logFile = cfg.getReposDir() + '/repos.log'
    serverCfg.logFile = None

    (driver, database) = serverCfg.repositoryDB
    db = dbstore.connect(database, driver)

    # Note - this will automatically migrate this repository! 
    # Since this is a throwaway repos anyway, I think that's
    # acceptible.
    schema.loadSchema(db)
    db.commit()

    user, password = cfg.user.find(cfg.serverName)
    addUser(serverCfg, user, password, write=True)
    addUser(serverCfg, 'anonymous', 'anonymous')

    if fork:
        pid = os.fork()
        if pid:
            pingServer(cfg)
            logger.info('Started repository "%s" on port %s (pid %s)' % (
                                                            cfg.serverName,
                                                            cfg.serverPort,
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
    baseDir = cfg.proxyDir
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

    if fork:
        pid = os.fork()
        if pid:
            pingServer(cfg, cfg.getProxyUrl())
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
    if cfg.serverUrl:
        repositoryMap = {cfg.serverName : cfg.serverUrl }
    else:
        repositoryMap = {cfg.serverName :
                    'http://%s:%s/conary/' % (os.uname()[1], cfg.serverPort) }
    userList = conarycfg.UserInformation()
    if proxyUrl:
        proxy = {'http'  : proxyUrl,
                 'https' : proxyUrl}
    else:
        proxy = None

    repos = netclient.NetworkRepositoryClient(repositoryMap, userList,
                                              proxy=proxy)
    for i in range(0,20000):
        try:
            checked = repos.c[cfg.serverName].checkVersion()
        except Exception, err:
            if i == 20000:
                raise
            time.sleep(.1)
        else:
            return True

def addUser(cfg, name, password=None, write=False):
    baseUrl="http://%s:%s/" % (os.uname()[1], cfg.port)
    netRepos = NetworkRepositoryServer(cfg, baseUrl)
    try:
        netRepos.auth.userAuth.getUserIdByName(name)
    except errors.UserNotFound: # yuck, we need a hasUser interface
        pass
    else:
        netRepos.auth.deleteUserByName(name)

    netRepos.auth.addUser(name, password)
    netRepos.auth.addAcl(name, None, None, write, False, False)

if __name__ == '__main__':
    sys.excepthook = util.genExcepthook()
    rmakeConfig = servercfg.rMakeConfiguration(True)
    startRepository(rmakeConfig, fork=False)
