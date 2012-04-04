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

import atexit
import copy
import errno
import itertools
import os
import re
import shutil
import signal
import tempfile
import time
import traceback
import urllib
from conary.conaryclient import cmdline
from conary.deps import deps
from conary import conaryclient
from conary import trove
from conary.lib import log
from conary.lib import sha1helper
from conary.lib import util
from conary_test.acltest import AuthorizationServer, PasswordHttpRequests
from conary_test import rephelp
from testrunner import testhelp
from testutils import mock
from testutils import sqlharness

from rmake.build import buildcfg
from rmake.build import builder
from rmake.build import buildjob
from rmake.build import buildtrove
from rmake.build import dephandler
from rmake.build import imagetrove
from rmake.build import subscriber as buildsubscriber
from rmake.cmdline import buildcmd
from rmake.cmdline import helper
from rmake.cmdline import monitor
from rmake.db import database
from rmake import compat
from rmake import plugins
from rmake.lib import logfile
from rmake.lib import logger
from rmake.lib import subscriber
from rmake.lib.rpcproxy import ShimAddress
from rmake.server import client
from rmake.server import repos
from rmake.server import server
from rmake.server import servercfg
from rmake_test import mockrbuilder
from rmake_test import resources


sleepRecipe = """
class SimpleRecipe(PackageRecipe):
    name = 'sleep'
    version = '1'
    clearBuildReqs()
    def setup(r):
        r.Run('sleep 100000')
"""

class NoIPPasswordHttpRequests(PasswordHttpRequests):
    allowNoIp = True

class _rMakeDatabase(sqlharness.RepositoryDatabase):

    def createUsers(self):
        auth = self._getNetAuth()
        self.createUser(auth, 'rmake', 'rmake', admin = True, write = True)
        self.createUser(auth, 'anonymous', 'anonymous', admin = False, write = False)

def rMakeDatabase(path):
    dir, baseName =  os.path.dirname(path), os.path.basename(path)
    return rMakeSqliteServer(dir).getDB(name=baseName)

class rMakeSqliteServer(sqlharness.SqliteServer):
    def createDB(self, name):
        sqlharness.BaseSQLServer.createDB(self, name)
        repodb = _rMakeDatabase(self, name)
        # make sure to create the file
        db = repodb.connect()
        db.transaction()
        db.commit()
        repodb.stop()
        return repodb

        

_proxy = None

_reposDir = None

class rMakeServer(rephelp.StandaloneServer):
    def __init__(self, rmakeCfg, repMap):
        self.rmakeCfg = rmakeCfg
        rephelp.StandaloneServer.__init__(self,
            nameList = [rmakeCfg.reposName],
            reposDB = rMakeDatabase(self.rmakeCfg.getReposDbPath()),
            contents = rephelp.ContentStore(self.rmakeCfg.getContentsPath()),
            server = None,
            serverDir = None,
            reposDir = self._getReposDir(),
            conaryPath = None,
            repMap = rmakeCfg.getRepositoryMap(),
            requireSigs = False)

        self.name = rmakeCfg.reposName
        if self.serverpid == -1:
            self.rmakeCfg.reposUrl = 'http://localhost:%s' % self.port
        else:
            self.port = rmakeCfg.getReposInfo()[1]
        self.serverFilePath = None
        self.delServerPath = False

    def _getReposDir(self):
        global _reposDir
        _reposDir = rephelp.getReposDir(_reposDir, 'rmaketest')
        return _reposDir

    def getMap(self):
        return self.rmakeCfg.getRepositoryMap()

    def start(self):
        if self.serverpid != -1:
            repos.pingServer(self.rmakeCfg)
            return
        if os.path.exists(self.rmakeCfg.serverDir):
            shutil.rmtree(self.rmakeCfg.serverDir)
        self.serverpid = repos.startRepository(self.rmakeCfg, fork=True)

class rMakeProxy(rephelp.StandaloneProxyServer):
    def __init__(self, rmakeCfg, reposName=None):
        self.rmakeCfg = rmakeCfg
        self.serverpid = -1
        self.needsPGPKey = True
        self.contents = rephelp.ContentStore(rmakeCfg.getProxyContentsPath())
        self.csContents = rephelp.ContentStore(rmakeCfg.getProxyChangesetPath())
        self.reposDB = rMakeDatabase(rmakeCfg.getProxyPath())
        self.serverFilePath = None
        self.delServerPath = False

    def getProxyUrl(self):
        return self.rmakeCfg.getProxyUrl()

    def updateConfig(self, cfg):
        cfg.conaryProxy = {'http'  : self.rmakeCfg.getProxyUrl(),
                           'https' : self.rmakeCfg.getProxyUrl()}

    def reset(self):
        self.contents.reset()
        self.csContents.reset()

    def start(self):
        if self.serverpid != -1:
            repos.pingServer(self.rmakeCfg,
                             proxyUrl=self.rmakeCfg.getProxyUrl())
            return
        else:
            self.port = testhelp.findPorts(1)[0]
        self.rmakeCfg.proxyUrl = 'http://LOCAL:%s' % self.port
        if os.path.exists(self.rmakeCfg.getProxyDir()):
            shutil.rmtree(self.rmakeCfg.getProxyDir())
        self.serverpid = repos.startProxy(self.rmakeCfg, fork=True)

class PluginTest(testhelp.TestCase):
    def setUp(self):
        testhelp.TestCase.setUp(self)
        self.pluginMgr = plugins.PluginManager(resources.get_plugin_dirs())
        self.pluginMgr.loadPlugins()
        self.pluginMgr.installImporter()
        self.importPlugins()
        self.pluginMgr.uninstallImporter()
        self.pluginMgr.disableAllPlugins()

    def importPlugins(self):
        pass

class RmakeHelper(rephelp.RepositoryHelper, PluginTest):
    def setUp(self):
        global _proxy
        self.proxy = _proxy
        rephelp._proxy = _proxy
        PluginTest.setUp(self)
        rephelp.RepositoryHelper.setUp(self)
        _realFork = os.fork
        self._realFork = os.fork
        if self.topDir:
            self.pidfile = self.topDir + '/pids'
        else:
            self.pidfile = self.tmpDir + '/pids'

        def _recordedFork():
            pid = _realFork()
            if pid:
                if self.topDir:
                    open(self.pidfile, 'a').write('%s\n' % pid)
                else:
                    open(self.pidfile, 'a').write('%s\n' % pid)
            return pid
        os.fork = _recordedFork

        compat.testing = False
        cfg = servercfg.rMakeConfiguration(False)
        cfg.buildDir = self.cfg.root + cfg.buildDir
        cfg.serverDir = self.reposDir + '-rmake'
        cfg.logDir = self.cfg.root + cfg.logDir
        cfg.lockDir = self.cfg.root + cfg.lockDir
        cfg.lockDir = self.cfg.root + cfg.lockDir

        cfg.setServerName('rmakehost')

        self.rmakeCfg = cfg
        if self.proxy:
            self.rmakeCfg.proxyUrl = self.proxy.getProxyUrl()
        else:
            self.rmakeCfg.proxyUrl = None
        if os.path.exists(resources.get_path('commands')):
            # otherwise just leave it as the default /usr/libexec/rmake
            self.rmakeCfg.helperDir = resources.get_path('commands')
        self.rmakeCfg.sslCertPath  = self.reposDir + '-certs/cert'
        if not os.path.exists(self.rmakeCfg.sslCertPath):
            self.rmakeCfg.makeCertificate()
        self.nodeCfg = None
        self.nodes = {}

        # we need this user/name to be _before the default '*' test foo
        # user that rephelp inserts
        for info in self.rmakeCfg.reposUser:
            self.cfg.user.addServerGlob(*info)

        buildCfg = buildcfg.BuildConfiguration(False, self.rootDir)
        buildCfg.strictMode = False
        buildCfg.defaultBuildReqs = []
        buildCfg.resolveTroves = []
        buildCfg.useConaryConfig(self.cfg)
        buildCfg.entitlementDirectory = self.rootDir + buildCfg.entitlementDirectory
        self.buildCfg = buildCfg

        util.mkdirChain(self.rmakeCfg.serverDir)
        dbPath = self.rmakeCfg.serverDir + '/jobs.db'
        if os.path.exists(dbPath):
            os.unlink(dbPath)

        self.rmakeServerPid = None
        self.messageBusPid = None
        self.rbaServerPid = None
        self.mockRbuilder = None

        from rmake_plugins.multinode.server import servercfg as pluginservercfg
        pluginservercfg.resetConfig()

    def stopRmakeServer(self):
        self._kill(self.rmakeServerPid, useCoverage=False)
        self.rmakeServerPid = None

    def waitThenKill(self, pid, timeout=20, mySignal=signal.SIGTERM):
        remaining = timeout
        current = time.time()
        while remaining > 0:
            found, status = os.waitpid(pid, os.WNOHANG)
            if found:
                return found, status
            time.sleep(0.1)
            remaining = current + timeout - time.time()
        os.kill(pid, mySignal)
        if signal != signal.SIGKILL:
            self.waitThenKill(pid=pid, mySignal=signal.SIGKILL)
            raise RuntimeError('child pid %s did not die!' % pid)
        else:
            return os.waitpid(pid, 0)

    def _checkPids(self):
        if self.rmakeServerPid:
            # need to have it kill child processes
            foundPid, status = os.waitpid(self.rmakeServerPid, os.WNOHANG)
            if foundPid:
                self.rmakeServerPid = None
                raise RuntimeError('Rmake server died')
        if self.messageBusPid:
            foundPid, status = os.waitpid(self.rmakeServerPid, os.WNOHANG)
            if foundPid:
                self.messageBusPid = None
                raise RuntimeError('MessageBus died')
        for nodeId, pid in self.nodes.items():
            foundPid, status = os.waitpid(pid, os.WNOHANG)
            if foundPid:
                del self.nodes[nodeId]
                raise RuntimeError('Node %s died' % nodeId)

    def _getPids(self):
        if os.path.exists(self.pidfile):
            pids = open(self.pidfile).read().split('\n')[:-1]
            pids = [int(x) for x in pids]
            return pids

    def tearDown(self):
        mock.unmockAll()
        os.fork = self._realFork
        if os.path.exists(self.pidfile):
            pids = open(self.pidfile).read().split('\n')[:-1]
            pids = [int(x) for x in pids]
            os.remove(self.pidfile)
        else:
            pids = []
        rephelp.RepositoryHelper.tearDown(self)
        if self.rmakeServerPid:
            # need to have it kill child processes
            self.stopRmakeServer()
        if self.messageBusPid:
            self._kill(self.messageBusPid)
            self.messageBusPid = None
        if self.rbaServerPid:
            self._kill(self.rbaServerPid)
            self.rbaServerPid = None
        if self.mockRbuilder:
            self._kill(self.mockRbuilder.pid)

        for nodeId in self.nodes.keys():
            self.stopNode(nodeId)
        logger.shutdown()

        undead = []
        okay = [ x.serverpid for x in self.servers.servers if x ]
        if self.proxy:
            okay.append(self.proxy.serverpid)
        for pid in pids:
            if not pid:
                continue
            foundPid = False
            try:
                foundPid, status = os.waitpid(pid, os.WNOHANG)
            except OSError, err:
                pass
            else:
                if not foundPid:
                    if pid not in okay:
                        undead.append(pid)
        slept = 0
        while undead and slept < 1:
            time.sleep(.1)
            slept += .1
            for pid in list(undead):
                try:
                    foundPid, status = os.waitpid(pid, os.WNOHANG)
                except OSError, err:
                    pass
                if foundPid:
                    undead.remove(pid)

        if undead:
            msg = 'After test finished, pids %s were not dead!\n' % ', '.join(str(x) for x in undead)
            for pid in undead:
                try:
                    os.kill(pid, signal.SIGKILL)
                    os.waitpid(pid, 0)
                except OSError, err:
                    if err.errno != errno.ESRCH:
                        raise
                    # No such process
            raise RuntimeError(msg)

    def _kill(self, pid, useCoverage=True):
        if useCoverage and os.environ.get('COVERAGE_DIR', None):
            os.kill(pid, signal.SIGUSR2)
        else:
            os.kill(pid, signal.SIGTERM)
        self.waitThenKill(pid)

    def stopNodes(self):
        for nodeId in self.nodes:
            self.stopNode(nodeId)

    def stopNode(self, nodeId):
        pid = self.nodes[nodeId]
        if os.environ.get('COVERAGE_DIR', None):
            os.kill(pid, signal.SIGUSR2)
        else:
            os.kill(pid, signal.SIGTERM)
        self.waitThenKill(pid)

    def openRmakeDatabase(self):
        return database.Database(
                ('sqlite', self.rmakeCfg.serverDir + '/jobs.db'),
                self.rmakeCfg.serverDir + '/jobcontents')

    def startRmakeProxy(self, reposName=None):
        global _proxy
        if reposName:
            self.rmakeCfg.setServerName(reposName)
            self.rmakeCfg.reposUrl = self.cfg.repositoryMap[reposName]
        if not self.proxy:
            self.proxy = rMakeProxy(self.rmakeCfg)
            self.proxy.start()
            atexit.register(stopProxy)
            _proxy = self.proxy
        self.rmakeCfg.proxyUrl = self.proxy.getProxyUrl()

    def openRmakeRepository(self, serverIdx=4):
        global _proxy
        self.proxy = _proxy
        if self.servers.servers[serverIdx]:
            url = self.servers.servers[serverIdx].getMap().values()[0]
            self.rmakeCfg.reposUrl = url
            self.buildCfg.reposName = self.rmakeCfg.reposName
            self.servers.servers[serverIdx].setNeedsReset()
            return conaryclient.ConaryClient(self.cfg).getRepos()
        self.servers.servers[serverIdx] = rMakeServer(self.rmakeCfg, self.servers.getMap())
        self.servers.servers[serverIdx].start()

        self.startRmakeProxy()

        # make sure repository map is up to date
        self.cfg.repositoryMap.update(self.servers.getMap())
        url = self.servers.servers[serverIdx].getMap().values()[0]
        self.rmakeCfg.reposUrl = url
        self.buildCfg.reposName = self.rmakeCfg.reposName
        return conaryclient.ConaryClient(self.cfg).getRepos()


    def openRepository(self, *args, **kw):
        rc = rephelp.RepositoryHelper.openRepository(self, *args, **kw)
        self.buildCfg.repositoryMap.update(self.cfg.repositoryMap)
        self.buildCfg.user.extend(self.cfg.user)
        return rc

    def checkRmakeServer(self):
        died = False
        pidFound = False
        try:
            pidFound, status = os.waitpid(self.rmakeServerPid, os.WNOHANG)
        except OSError, err:
            if err == errno.ESEARCH:
                died = 'Pid already dead.'
            else:
                raise
        if pidFound:
            if os.WIFEXITED(status):
                exitRc = os.WEXITSTATUS(status)
                died = 'Server died with status %s' % exitRc
            else:
                died = 'Server died with signal %s' % os.WTERMSIG(status)
        if died:
            self.rmakeServerPid = None
            raise RuntimeError(died)

    def startMessageBus(self):
        assert(not self.messageBusPid)
        port,  = testhelp.findPorts()
        pid = os.fork()
        if pid:
            self.messageBusPid = pid
            return port
        else:
            try:
                from rmake.multinode.server import messagebus
                logDir = self.rmakeCfg.logDir
                util.mkdirChain(logDir + '/messages')
                mb = messagebus.MessageBus('::', port,
                            logDir + '/standalone_messagebus',
                            logDir + '/messages/standalone_messagebus')
                mb.serve_forever()
                os._exit(0)
            except Exception, err:
                print "Server died: %s" % traceback.format_exc()
                os._exit(1)

    def getAdminClient(self, messageBusPort=None):
        if not messageBusPort:
            messageBusPort = self.rmakeCfg.messageBusPort
        self.pluginMgr.enablePlugin('multinode')
        self.pluginMgr.installImporter()
        from rmake.messagebus import busclient
        from rmake_plugins.multinode import admin
        self.pluginMgr.uninstallImporter()
        self.pluginMgr.disablePlugin('multinode')
        b = busclient.MessageBusClient('localhost', messageBusPort, None,
                                       connectionTimeout=10)
        b.logger.setQuietMode()
        adminClient =  admin.MessageBusAdminClient(b)
        return adminClient

    def startRmakeServer(self, reposName=None, multinode=False, 
                         protocol = 'unix'):

        if multinode:
            from rmake_plugins.multinode_client.build import buildcfg
            from rmake_plugins.multinode_client.server import client
            from rmake_plugins.multinode.server import servercfg
            buildcfg.updateConfig()
            servercfg.updateConfig()
        else:
            from rmake.server import client
        if protocol == 'unix':
            fd, path = tempfile.mkstemp(prefix='socket-', dir=self.rootDir)
            os.unlink(path)
            os.close(fd)
            uri = 'unix://%s' % path
        elif protocol == 'http':
            self.rbaServer = AuthorizationServer(NoIPPasswordHttpRequests)
            self.rbaServerPid = self.rbaServer.childPid
            self.rmakeCfg.rbuilderUrl = self.rbaServer.url()[:-1]
            port = testhelp.findPorts(1)[0]
            uri = 'http://localhost:%s' % port

        if reposName:
            rmakeCfg = copy.deepcopy(self.rmakeCfg)
            rmakeCfg.setServerName(reposName)
            rmakeCfg.reposUrl = self.cfg.repositoryMap[reposName]
            userInfo = self.cfg.user.find(reposName)
            rmakeCfg.reposUser.addServerGlob(reposName, *userInfo)
            buildCfg = copy.deepcopy(self.buildCfg)
        else:
            rmakeCfg = self.rmakeCfg
            buildCfg = self.buildCfg
        self.rmakeCfg.rmakeUrl = uri
        if protocol != 'unix':
            protocol, host = urllib.splittype(uri)
            host, rest = urllib.splithost(host)
            clientUri = '%s://%s:%s@%s%s' % (protocol, 'test', 'foo', host, rest)
        else:
            clientUri = uri

        buildCfg.rmakeUrl = clientUri
        rmakeClient = client.rMakeClient(clientUri)

        if multinode:
            port,  = testhelp.findPorts()
            rmakeCfg.messageBusHost = None
            rmakeCfg.messageBusPort = port

        assert(not self.rmakeServerPid)
        pid = os.fork()
        if pid:
            self.rmakeServerPid = pid
            self.checkRmakeServer()
            rmakeClient.ping(hook=self.checkRmakeServer)
            rmakeClient.addRepositoryInfo(buildCfg)
            if reposName:
                return rmakeClient, rmakeCfg, buildCfg
            else:
                return rmakeClient
        else:
            try:
                if multinode:
                    self.pluginMgr.enablePlugin('multinode')
                elif self.pluginMgr.hasPlugin('multinode'):
                    self.pluginMgr.disablePlugin('multinode')
                log.setVerbosity(log.DEBUG)
                logFile = logfile.LogFile(self.rmakeCfg.logDir + '/rmake-out.log')
                logFile.redirectOutput()
                rmakeServer = server.rMakeServer(uri, rmakeCfg, None, None,
                                                 pluginMgr=self.pluginMgr)
                signal.signal(signal.SIGTERM, rmakeServer._signalHandler)
                signal.signal(signal.SIGINT, rmakeServer._signalHandler)
                rmakeServer.serve_forever()
                os._exit(0)
            finally:
                os._exit(1)

    def getNodeCfg(self, port=None):
        from rmake.node import nodecfg
        nodeCfg = nodecfg.NodeConfiguration(False)
        for item, value in self.rmakeCfg.iteritems():
            if item in nodeCfg:
                nodeCfg[item] = value
            nodeCfg.buildFlavors = [deps.parseFlavor('is:x86')]
            nodeCfg.loadThreshold = 10
        nodeCfg.rmakeUrl = self.rmakeCfg.getServerUri()
        if port:
            nodeCfg.messageBusHost = None
            nodeCfg.messageBusPort = port
        return nodeCfg


    def startNode(self, nodeId=1, messageBusPort=None, slots=1, 
                  buildFlavors=None):
        from rmake.multinode import workernode
        if messageBusPort is None:
            messageBusPort = self.rmakeCfg.messageBusPort
        if not self.nodeCfg:
            self.nodeCfg = self.getNodeCfg()

        nodeCfg = copy.deepcopy(self.nodeCfg)
        nodeCfg.messageBusHost = None
        nodeCfg.messageBusPort = messageBusPort
        if buildFlavors is not None:
            nodeCfg.buildFlavors = buildFlavors

        pid = os.fork()
        if pid:
            self.nodes[nodeId] = pid
            return
        else:
            try:
                logFile = logfile.LogFile(
                                self.rmakeCfg.logDir + '/node%s.log' % nodeId)
                logFile.redirectOutput()
                server = workernode.rMakeWorkerNodeServer(nodeCfg,
                              messageBusInfo=('localhost', messageBusPort))
                server.serve_forever()
                os._exit(0)
            finally:
                os._exit(1)


    def getMonitor(self, client, showTroveLogs=True, showBuildLogs=True, 
                   jobId=None):
        port = testhelp.findPorts()[0]
        fd, path = tempfile.mkstemp(dir=self.workDir, prefix='monitor-')
        os.close(fd)
        os.remove(path)
        monitorUri = 'unix://%s' % path
        m = self.discardOutput(monitor.monitorJob, client, jobId, 
                               showTroveDetails=showTroveLogs,
                               showBuildLogs=showBuildLogs,
                               serve=False, uri=monitorUri)
        if jobId:
            self.discardOutput(m.subscribe, jobId)
        return m

    def newJob(self, *troveList, **kw):
        db = self.openRmakeDatabase()
        newTroveList = []
        for item in troveList:
            if isinstance(item, (tuple, list)):
                if isinstance(item[0], trove.Trove):
                    newTroveList.append(item[0].getNameVersionFlavor() + 
                                        (item[1],))
                else:
                    newTroveList.append(item)
            elif isinstance(item, trove.Trove):
                newTroveList.append(item.getNameVersionFlavor())
            else:
                newTroveList.append(item)
        troveList = newTroveList
        buildConfig = kw.pop('buildConfig', self.buildCfg)
        owner = kw.pop('owner', 'NONE')
        job = buildjob.BuildJob(None, troveList, **kw)
        job.owner = owner
        job.own()
        configDict = {'': buildConfig}
        for (n,v,f,c) in job.iterTroveList(True):
            if c not in configDict:
                trvConfig = copy.deepcopy(buildConfig)
                trvConfig.setContext(c)
                configDict[c] = trvConfig
            trvConfig = configDict[c]
            trvConfig.buildTroveSpecs.append((n, None, f, c))
        job.setConfigs(configDict)
        db.addJob(job)
        db.subscribeToJob(job)
        return job

    def makeBuildTroves(self, job):
        # no longer necessary - all jobs have buildTroves associated w/ them
        return [ job.getTrove(*x) for x in sorted(job.iterTroveList(True))]

    def newImageTrove(self, jobId, name, version, flavor, context='',
                      productName=None, imageType=None, buildName=None,
                      imageOptions=None):
        trv =  imagetrove.ImageTrove(jobId, name, version, flavor, 
                                     context=context)
        trv.setProductName(productName)
        trv.setImageType(imageType)
        trv.setBuildName(buildName)
        if imageOptions:
            trv.setImageOptions(imageOptions)
        return trv

    def newBuildTrove(self, jobId, name, version, flavor, context=''):
        if name.startswith('group-'):
            recipeType = buildtrove.RECIPE_TYPE_GROUP
        elif name.startswith('fileset-'):
            recipeType = buildtrove.RECIPE_TYPE_FILESET
        elif name.startswith('info-'):
            recipeType = buildtrove.RECIPE_TYPE_INFO
        else:
            recipeType = buildtrove.RECIPE_TYPE_PACKAGE
        return buildtrove.BuildTrove(jobId, name, version, flavor,
                                     context=context, recipeType=recipeType)

    def getDependencyHandler(self, job, repos):
        dh = dephandler.DependencyHandler(job.getPublisher(),
                                          logger.Logger('deps', '/dev/null'),
                                          list(job.iterTroves()), [])
        return dh

    def getRmakeHelper(self, uri=None, rmakeCfg=None, buildCfg=None):
        if uri is None:
            uri = ShimAddress(server.rMakeServer(None, self.rmakeCfg, None,
                quiet=True))
        if rmakeCfg is None:
            rmakeCfg = self.rmakeCfg
        if buildCfg is None:
            buildCfg = self.buildCfg
        return helper.rMakeHelper(uri, buildConfig=buildCfg, root=self.rootDir)

    def getRmakeClient(self, buildCfg=None):
        if buildCfg is None:
            buildCfg = self.buildCfg
        uri = buildCfg.getServerUri()
        return client.rMakeClient(uri)

    def buildTroves(self, *troveList):
        self.openRmakeRepository()
        db = self.openRmakeDatabase()
        job = buildjob.NewBuildJob(db, troveList, self.buildCfg)
        buildsubscriber._JobDbLogger(db).attach(job)
        b = builder.Builder(self.rmakeCfg, job)
        self.logFilter.add()
        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        b.build()
        logFile.restoreOutput()
        return b.job

    def genUUID(self, input):
        return sha1helper.md5ToString(sha1helper.md5String(input))

    def checkMonitor(self, m, val, sleep=5, events = None,
                     ignoreExtras = False):
        fullText = ''
        if isinstance(val, str):
            val = [val]
        if events is None:
            events = len(val)

        extras = []
        newValList = []
        for x in val:
            if x.endswith('\n'):
                x = x[:-1]
            newValList.append(x)
        val = newValList
        val = list(itertools.chain(*[x.split('\n') for x in val]))
        while val:
            txt = None
            startTime = time.time()
            while not txt and (time.time() - startTime) < sleep:
                rc, txt = self.captureOutput(m.handleRequestIfReady, sleep)
            txt = re.sub('\[[0-9][0-9]:[0-9][0-9]:[0-9][0-9] ?(AM|PM)?\]', '[TIME]', txt)
            if txt and txt[-1] == '\n':
                txt = txt[:-1]
            for line in txt.split('\n'):
                if line in val:
                    val.remove(line)
                elif not ignoreExtras:
                    extras.append(line)
            if not txt:
                break
        if not extras and not val:
            return
        errMsg = []
        if extras:
            errMsg.append('Got extra output lines:\n%r\n' % extras)
        if val:
            errMsg.append('Expected but did not get:\n%r\n' % val)
        raise RuntimeError(''.join(errMsg))

    def commitJobs(self, helper, jobIds, message=None,
                  commitOutdatedSources=False, sourceOnly=False,
                  waitForJob=False):
        if message is None:
            message = 'default message'
        return self.captureOutput(helper.commitJobs, jobIds, message,
                                  commitOutdatedSources=commitOutdatedSources,
                                  sourceOnly=sourceOnly, waitForJob=waitForJob)

    commitJob = commitJobs

    def createEventSubscriber(self, port):
        from rmake.messagebus import busclient
        from rmake.multinode import messages
        class EventSubscriber(subscriber.StatusSubscriber):
            listeners = { 'TROVE_BUILT'          : 'troveBuilt',
                          'TROVE_FAILED'         : 'troveFailed',
                          'TROVE_BUILDING'       : 'troveBuilding' }

            def __init__(self, port):
                subscriber.StatusSubscriber.__init__(self, None, None)
                bus = busclient.MessageBusClient('localhost', port, self)
                bus.subscribe('/event')
                bus.connect()
                self._troveBuilding = {}
                self._troveBuilt = {}
                self._troveFailed = {}
                self.bus = bus
                while not bus.isConnected():
                    bus.poll()
                bus.getSession().flush()

            def messageReceived(self, m):
                if isinstance(m, messages.EventList):
                    self._receiveEvents(self.apiVersion, m.getEventList()[1])

            def assertTroveBuilding(self, jobId, name, version, flavor, context=''):
                assert((jobId, (name, version, flavor, context)) in self._troveBuilding)

            def assertTroveBuilt(self, jobId, name, version, flavor, context=''):
                assert((jobId, (name, version, flavor, context)) in self._troveBuilt)

            def assertTroveFailed(self, jobId, name, version, flavor, context=''):
                assert((jobId, (name, version, flavor, context)) in self._troveFailed)

            def getTrovesBuilt(self, jobId, name, version, flavor, context=''):
                return self._troveBuilt[(jobId, (name, version, flavor, context))]

            def getFailureReason(self, jobId, name, version, flavor, context=''):
                return self._troveFailed[(jobId, (name, version, flavor, context))]

            def troveBuilding(self, (jobId, troveTuple), pid, settings):
                self._troveBuilding[jobId, troveTuple] = pid

            def troveBuilt(self, (jobId, troveTuple), binaryTroveList):
                self._troveBuilt[jobId, troveTuple] = binaryTroveList

            def troveFailed(self, (jobId, troveTuple), failureReason):
                self._troveFailed[jobId, troveTuple] = failureReason

            def poll(self):
                self.bus.poll()

        return EventSubscriber(port)

    def getNVF(self, name, version='1', flavor=''):
        source = name.endswith(':source')
        return (name, self._cvtVersion(version, source),
                deps.parseFlavor(flavor))

    def getRestartJob(self, job):
        db = self.openRmakeDatabase()
        jobConfig = db.getJobConfig(job.jobId)
        troveSpecs = jobConfig.buildTroveSpecs
        client = conaryclient.ConaryClient(jobConfig)
        jobConfig.reposName = self.rmakeCfg.reposName
        jobConfig.rmakeUrl = self.rmakeCfg.getServerUri()
        troveTups = buildcmd.getTrovesToBuild(jobConfig, client, troveSpecs)
        return self.newJob(buildConfig=jobConfig, *troveTups)

    def makeTroveTuple(self, troveName, version='', flavor=''):
        if '=' in troveName or '[' in troveName:
            assert(not version and not flavor)
            troveName, version, flavor = cmdline.parseTroveSpec(troveName)
            if flavor is None:
                flavor = ''
        else:
            if not version:
                version = '1'
        version = self._cvtVersion(version,
                                   source=troveName.endswith(':source'))
        flavor = deps.parseFlavor(flavor, raiseError=True)
        return (troveName, version, flavor)

    def getArchFlavor(self):
        flavor = self.cfg.flavor[0]
        newFlavor = deps.Flavor()
        ISD = deps.InstructionSetDependency
        newFlavor.addDeps(ISD, flavor.iterDepsByClass(ISD))
        return newFlavor

    def subscribeServer(self, client, job, multinode=False):
        if multinode:
            from rmake_plugins.multinode.build import builder
            from rmake.multinode.server import subscriber
            client = builder.BuilderNodeClient(self.rmakeCfg, job.jobId,
                                                 job)
            publisher = subscriber._RmakeBusPublisher(client)
            publisher.attach(job)
            while not client.bus.isRegistered():
                client.serve_once()
            return publisher
        else:
            from rmake.build import subscriber
            subscriber._RmakeServerPublisherProxy(client.uri).attach(job)

    def startMockRbuilder(self):
        rbuilder = mockrbuilder.MockRbuilder(testhelp.findPorts()[0],
                                             self.workDir + '/rbuilderlog')
        rbuilder.start()
        self.mockRbuilder = rbuilder
        self.buildCfg.rbuilderUrl = rbuilder.url
        self.buildCfg.rmakeUser = rbuilder.user


def stopProxy():
    global _proxy
    if _proxy is not None:
        _proxy.stop()
        _proxy = None
