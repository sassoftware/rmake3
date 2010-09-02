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
Build-related server methods for the rMake dispatcher.
"""

import itertools
import logging
import os
import random
import sys
import traceback
import urllib
import xmlrpclib

from conary.lib import util

from rmake import errors
from rmake.core.types import RmakeJob
from rmake.build import buildjob
from rmake.build import constants as buildconst
from rmake.build import database
from rmake.server import auth
from rmake.lib.apirpc import RPCServer, expose
from rmake.lib import logger
from rmake.lib import osutil
from rmake.lib.rpcproxy import ShimAddress


class BuildServer(RPCServer):
    """
    Expose an interface for dealing with trove build jobs

    Exposed under the "build" namespace, e.g. server.build.getRepositoryInfo()
    """

    def __init__(self, dispatcher, tbs_cfg):
        self.dispatcher = dispatcher
        self.db = None
        self.tbs_cfg = tbs_cfg

    def _post_setup(self):
        self.db = database.JobStore(self.dispatcher.pool)

    @expose
    def createJob(self, job, firehose=None):
        core_job = RmakeJob(job.jobUUID, job_type=buildconst.BUILD_JOB,
                owner='<unknown>', data=job)
        ret = []
        def callback(_, cu):
            dx = self.db.createJob(cu, job)
            # Save the result
            dx.addCallback(lambda jobId: ret.append(jobId))
            return dx

        d = self.dispatcher.createJob(core_job, firehose=firehose,
                callbackInTrans=callback)

        # Return the result collected inside the callback
        d.addCallback(lambda _: ret[0])
        return d

    @expose
    def getRepositoryInfo(self):
        """Return info on how to contact the internal repository."""
        return {
                'reposName': self.tbs_cfg.reposName,
                'repositoryMap': self.tbs_cfg.getRepositoryMap(),
                'reposUser': list(self.tbs_cfg.reposUser),
                'conaryProxy': self.tbs_cfg.getProxyUrl() or '',
                }


class BuildServer_UNPORTED(object):

    def listJobs(self, callData, activeOnly, jobLimit):
        return self.db.listJobs(activeOnly=activeOnly, jobLimit=jobLimit)

    def listTrovesByState(self, callData, jobId, state):
        jobId = self.db.convertToJobId(jobId)
        if state == '':
            state = None
        data = self.db.listTrovesByState(jobId, state)
        return [(x[0], freeze('troveContextTupleList', x[1])) for x in data.iteritems()]

    def getJobs(self, callData, jobIds, withTroves=True, withConfigs=True):
        callData.logger.logRPCDetails('getJobs', jobIds=jobIds,
                                      withTroves=withTroves,
                                      withConfigs=withConfigs)
        jobIds = self.db.convertToJobIds(jobIds)
        return [ x.__freeze__(sanitize=True)
                 for x in self.db.getJobs(jobIds, withTroves=withTroves,
                                          withConfigs=withConfigs) ]

    def getJobConfig(self, callData, jobId):
        jobId = self.db.convertToJobId(jobId)
        jobCfg = self.db.getJobConfig(jobId)
        return jobCfg

    def getJobLogs(self, callData, jobId, mark):
        jobId = self.db.convertToJobId(jobId)
        if not self.db.jobExists(jobId):
            self.warning("%s tried to obtain logs for invlid JobId %s" % (
                        str(callData.auth), jobId))
            return []
        return [ tuple(str(x) for x in data) 
                    for data in self.db.getJobLogs(jobId, mark) ]

    def getTroveLogs(self, callData, jobId, troveTuple, mark):
        jobId = self.db.convertToJobId(jobId)
        return [ tuple(str(x) for x in data) for data in self.db.getTroveLogs(jobId, troveTuple, mark) ]

    def getTroveBuildLog(self, callData, jobId, troveTuple, mark):
        jobId = self.db.convertToJobId(jobId)
        trove = self.db.getTrove(jobId, *troveTuple)
        if not self.db.hasTroveBuildLog(trove):
            return not trove.isFinished(), xmlrpclib.Binary(''), 0
        f = self.db.openTroveBuildLog(trove)
        if mark < 0:
            f.seek(0, 2)
            end = f.tell()
            f.seek(max(end + mark, 0))
        else:
            f.seek(mark)
        return not trove.isFinished(), xmlrpclib.Binary(f.read()), f.tell()

    def listChroots(self, callData):
        chroots = self.db.listChroots()
        chrootNames = self.worker.listChrootsWithHost()
        finalChroots = []
        for chroot in chroots:
            if (chroot.host, chroot.path) not in chrootNames:
                # this has been removed from the file system
                self.db.removeChroot(chroot.host, chroot.path)
            else:
                finalChroots.append(chroot)
        return [ freeze('Chroot', x) for x in finalChroots ]

    def startChrootServer(self, callData, jobId, troveTuple, command,
                          superUser, chrootHost, chrootPath):
        jobId = self.db.convertToJobId(jobId)
        trove = self.db.getTrove(jobId, *troveTuple)
        if not chrootHost:
            if not trove.getChrootPath():
                raise errors.RmakeError('Chroot does not exist')
            chrootHost = trove.getChrootHost()
            chrootPath = trove.getChrootPath()
        success, data =  self.worker.startSession(chrootHost,
                                                  chrootPath,
                                                  command,
                                                  superUser=superUser,
                                                  buildTrove=trove)
        if not success:
            raise errors.RmakeError('Chroot failed: %s' % data)
        return data


    def archiveChroot(self, callData, host, chrootPath, newPath):
        if self.db.chrootIsActive(host, chrootPath):
            raise errors.RmakeError('Chroot is in use!')
        newPath = self.worker.archiveChroot(host, chrootPath, newPath)
        self.db.moveChroot(host, chrootPath, newPath)

    def startCommit(self, callData, jobIds):
        jobIds = self.db.convertToJobIds(jobIds)
        jobs = self.db.getJobs(jobIds)
        for job in jobs:
            self._subscribeToJob(job)
            job.own()
            job.jobCommitting()

    def commitFailed(self, callData, jobIds, message):
        jobIds = self.db.convertToJobIds(jobIds)
        jobs = self.db.getJobs(jobIds)
        for job in jobs:
            self._subscribeToJob(job)
            job.own()
            job.jobCommitFailed(message)

    def commitSucceeded(self, callData, jobIds, commitMap):
        jobIds = self.db.convertToJobIds(jobIds)
        # split commitMap and recombine
        finalMap = []
        for jobId, troveMap in itertools.izip(jobIds, commitMap):
            troveMap = dict((thaw('troveContextTuple', x[0]),
                            thaw('troveTupleList', x[1])) for x in troveMap)
            finalMap.append((jobId, troveMap))
        jobs = self.db.getJobs(jobIds, withTroves=True)
        for (jobId, troveMap), job in itertools.izip(finalMap, jobs):
            self._subscribeToJob(job)
            job.own()
            job.jobCommitted(troveMap)

    # --- callbacks from Builders

    def emitEvents(self, callData, jobId, (apiVer, eventList)):
        # currently we assume that this apiVer is extraneous, just
        # a part of the protocol for EventLists.
        self._publisher.addEvent(jobId, eventList)

    def listNodes(self, callData):
        return []

    def getMessageBusInfo(self, callData):
        return ''

    # --- internal functions

    def getBuilder(self, job):
        b = builder.Builder(self.cfg, job, db=self.db)
        self.plugins.callServerHook('server_builderInit', self, b)
        return b

    def updateBuildConfig(self, buildConfig):
        buildConfig.repositoryMap.update(self.cfg.getRepositoryMap())
        for serverName, user, password in self.cfg.getUserGlobs():
            buildConfig.user.addServerGlob(serverName, user, password)
        proxyUrl = self.cfg.getProxyUrl()
        if proxyUrl:
            if hasattr(buildConfig,'proxyMap'):
                if not buildConfig.proxyMap:
                    buildConfig.proxyMap.update('conary:http*', '*', [proxyUrl])
            else:
                if not buildConfig.conaryProxy:
                    buildConfig.conaryProxy['http'] = proxyUrl
                    buildConfig.conaryProxy['https'] = proxyUrl

    def _serveLoopHook(self):
        if not self._initialized and hasattr(self, 'worker'):
            self.db.auth.resetCache()
            jobsToFail = []
            for state in buildjob.ACTIVE_STATES:
                jobsToFail += self.db.getJobsByState(state)
            self._failCurrentJobs(jobsToFail, 'Server was stopped')
            self._initializeNodes()
            self._initialized = True

        while not self._halt:
            # start one job from the cue.  This loop should be
            # exited after one successful start.
            job = self._getNextJob()
            if job is None:
                break
            # tell everyone else on the queue that they've been bumped up one
            jobIds = self.db.listJobIdsOnQueue()
            queuedJobs = self.db.getJobs(jobIds,
                                         withTroves=False, withConfigs=False)
            for idx, queuedJob in enumerate(queuedJobs):
                self._subscribeToJobInternal(queuedJob)
                if not idx:
                    queuedJob.jobQueued(
                        'Job Queued - You are next in line for processing')
                else:
                    queuedJob.jobQueued(
                        'Job Queued - Builds ahead of you: %d' % idx)

            try:
                self._startBuild(job)
            except Exception, err:
                self._subscribeToJob(job)
                job.exceptionOccurred('Failed while initializing',
                                      traceback.format_exc())
            break
        self._publisher.emitEvents()
        self._collectChildren()
        self.plugins.callServerHook('server_loop', self)

    def _getNextJob(self):
        if not self._canBuild():
            return
        while True:
            job = self.db.popJobFromQueue()
            if job is None:
                break
            if job.isFailed():
                continue
            job.own()
            return job

    def _canBuild(self):
        # NOTE: Because there is more than one root manager for the local
        # machine, we cannot have more than one process building at the 
        # same time in the single-node version of rMake.  They would conflict
        # over the use of particular chroots.
        return not self.db.isJobBuilding()

    def _shutDown(self):
        # we've gotten a request to halt, kill all jobs (they've run
        # setpgrp) and then kill ourselves
        if self.db:
            self._stopAllJobs()
            self._killAllPids()
        if hasattr(self, 'plugins') and self.plugins:
            self.plugins.callServerHook('server_shutDown', self)
        sys.exit(0)

    def _subscribeToJob(self, job):
        for subscriber in self._subscribers:
            subscriber.attach(job)

    def _subscribeToBuild(self, build):
        for subscriber in self._subscribers:
            if hasattr(subscriber, 'attachToBuild'):
                subscriber.attachToBuild(build)
            else:
                subscriber.attach(build.getJob())

    def _subscribeToJobInternal(self, job):
        for subscriber in self._internalSubscribers:
            subscriber.attach(job)

    def _initializeNodes(self):
        self.db.deactivateAllNodes()
        chroots = self.worker.listChroots()
        self.db.addNode('_local_', 'localhost.localdomain', self.cfg.slots,
                        [], chroots)

    def _startBuild(self, job):
        pid = self._fork('Job %s' % job.jobId, close=True)
        if pid:
            self._buildPids[pid] = job.jobId # mark this pid for potential 
                                             # killing later
            return job.jobId
        else:
            try:
                try:
                    # we want to be able to kill this build process and
                    # all its children with one swell foop.
                    os.setpgrp()
                    self.db.reopen()

                    buildMgr = self.getBuilder(job)
                    self._subscribeToBuild(buildMgr)
                    # Install builder-specific signal handlers.
                    buildMgr._installSignalHandlers()
                    # need to reinitialize the database in the forked child 
                    # process
                    buildCfg = job.getMainConfig()

                    if buildCfg.jobContext:
                        buildMgr.setJobContext(buildCfg.jobContext)
                    # don't do anything else in here, buildAndExit has 
                    # handling for ensuring that exceptions are handled 
                    # correctly.
                    buildMgr.buildAndExit()
                except Exception, err:
                    tb = traceback.format_exc()
                    buildMgr.logger.error('Build initialization failed: %s' %
                                          err, tb)
                    job.exceptionOccurred(err, tb)
            finally:
                os._exit(2)

    def _failCurrentJobs(self, jobs, reason):
        if self.uri is None:
            self.warning('Cannot fail current jobs without a URI')
            return False
        from rmake.server.client import rMakeClient
        pid = self._fork('Fail current jobs')
        if pid:
            self.debug('Fail current jobs forked pid %d' % pid)
            return
        try:
            client = rMakeClient(self.uri)
            # make sure the main process is up and running before we 
            # try to communicate w/ it
            client.ping()
            for job in jobs:
                self._subscribeToJob(job)
                publisher = job.getPublisher()
                job.jobFailed(reason)
            os._exit(0)
        except:
            self.exception('Error stopping current jobs')
            os._exit(1)

    def _failJob(self, jobId, reason):
        pid = self._fork('Fail job %s' % jobId)
        if pid:
            self.debug('Fail job %s forked pid %d' % (jobId, pid))
            return
        try:
            from rmake.server.client import rMakeClient
            client = rMakeClient(self.uri)
            # make sure the main process is up and running before we 
            # try to communicate w/ it
            client.ping()
            job = self.db.getJob(jobId)
            self._subscribeToJob(job)
            publisher = job.getPublisher()
            job.own()
            job.jobFailed(reason)
            os._exit(0)
        except:
            self.exception('Error stopping job %s' % jobId)
            os._exit(1)

    def _pidDied(self, pid, status, name=None):
        jobId = self._buildPids.pop(pid, None)
        if jobId and status:
            job = self.db.getJob(jobId)
            if job.isBuilding() or job.isQueued():
                self._failJob(jobId, self._getExitMessage(pid, status, name))
        apirpc.XMLApiServer._pidDied(self, pid, status, name)

        if pid == self._publisher._emitPid: # rudimentary locking for emits
            self._publisher._pidDied(pid, status)  # only allow one
                                                   # emitEvent process
                                                   # at a time.

        if pid == self.proxyPid:
            if not self._halt:
                self.error("""
    Internal proxy died - shutting down rMake.
    The Proxy can die on startup due to an earlier unclean shutdown of 
    rMake.  Check for a process that ends in conary/server/server.py.  If such 
    a process exists, you will have to kill it manually.  Otherwise check
    %s for a detailed message""" % self.cfg.getProxyLogPath())
                self._halt = 1
            self.proxyPid = None
        if pid == self.repositoryPid:
            if not self._halt:
                self.error("""
    Internal Repository died - shutting down rMake.
    The Repository can die on startup due to an earlier unclean shutdown of 
    rMake.  Check for a process that ends in conary/server/server.py.  If such 
    a process exists, you will have to kill it manually.  Otherwise check
    %s for a detailed message""" % self.cfg.getReposLogPath())
                self._halt = 1
            self.repositoryPid = None
        self.plugins.callServerHook('server_pidDied', self, pid, status)

    def _stopJob(self, job):
        if job.isQueued(): # job isn't started yet, just stop it.
                           # FIXME: when we make this multiprocess,
                           # there will be a race condition here.
                           # We'll have to hold the queue lock
                           # while we make this check.
            return
        elif job.isCommitting():
            return
        elif not job.isRunning():
            raise errors.RmakeError('Cannot stop job %s - it is'
                                    ' already stopped' % job.jobId)

        if job.pid not in self._buildPids:
            self.warning('job %s is not in active job list', job.jobId)
            return
        else:
            self._killPid(job.pid, killGroup=True,
                          hook=self.handleRequestIfReady)

    def _stopAllJobs(self):
        for pid, jobId in self._buildPids.items():
            self._killPid(pid, hook=self.handleRequestIfReady, killGroup=True)
        self._serveLoopHook()

    def _exit(self, exitCode):
        sys.exit(exitCode)

    def _fork(self, name, close=False):
        pid = apirpc.XMLApiServer._fork(self, name)
        if pid:
            return pid
        if close:
            self._close()
        else:
            self.db.reopen()
        return pid

    def _close(self):
        apirpc.XMLApiServer._close(self)
        if getattr(self, 'db', None):
            self.db.close()

    def _setUpInternalUser(self):
        user = ''.join([chr(random.randint(ord('a'),
                           ord('z'))) for x in range(10)])
        password = ''.join([chr(random.randint(ord('a'), 
                                ord('z'))) for x in range(10)])
        if isinstance(self.uri, str):
            schema, url = urllib.splittype(self.uri)
            if schema in ('http', 'https'):
                host, rest = urllib.splithost(url)
                olduser, host = urllib.splituser(host)
                uri = '%s://%s:%s@%s%s' % (schema, user, password, host, rest)
                self.uri = uri

        self.internalAuth = (user, password)

    def DISABLED__init__(self, uri, cfg, repositoryPid=None, proxyPid=None,
                 pluginMgr=None, quiet=False):
        util.mkdirChain(cfg.logDir)
        logPath = cfg.logDir + '/rmake.log'
        rpcPath = cfg.logDir + '/xmlrpc.log'
        serverLogger = ServerLogger()
        serverLogger.disableRPCConsole()
        serverLogger.logToFile(logPath)
        serverLogger.logRPCToFile(rpcPath)
        if quiet:
            serverLogger.setQuietMode()
        else:
            if cfg.verbose:
                logLevel = logging.DEBUG
            else:
                logLevel = logging.INFO
            serverLogger.enableConsole(logLevel)
        serverLogger.info('*** Started rMake Server at pid %s (serving at %s)' % (os.getpid(), uri))
        try:
            osutil.setproctitle('rmake server %s' % (uri,))
        except:
            pass
        try:
            self._initialized = False
            self.db = None

            # forked jobs that are currently active
            self._buildPids = {}

            self.uri = uri
            self.cfg = cfg
            self.repositoryPid = repositoryPid
            self.proxyPid = proxyPid
            apirpc.XMLApiServer.__init__(self, uri, logger=serverLogger,
                                 forkByDefault = True,
                                 sslCertificate=cfg.getSslCertificatePath(),
                                 caCertificate=cfg.getCACertificatePath())
            self._setUpInternalUser()
            self.db = database.Database(cfg.getDbPath(),
                                        cfg.getDbContentsPath())
            self.auth = auth.AuthenticationManager(cfg.getAuthUrl(), self.db)

            if pluginMgr is None:
                pluginMgr = plugins.PluginManager([])
            self.plugins = pluginMgr

            # any jobs that were running before are not running now
            subscriberLog = logger.Logger('susbscriber',
                                          self.cfg.getSubscriberLogPath())
            self._publisher = publish._RmakeServerPublisher(subscriberLog,
                                                            self.db,
                                                            self._fork)
            self.worker = worker.Worker(self.cfg, self._logger)
            dbLogger = subscriber._JobDbLogger(self.db)
            # note - it's important that the db logger
            # comes first, before the general publisher,
            # so that whatever published is actually 
            # recorded in the DB.
            self._subscribers = [dbLogger]
            if self.uri:
                s = subscriber._RmakeServerPublisherProxy(self.uri)
            else:
                # testsuite path - external subscribers also go through
                # internal interface when the server is not run as a separate
                # process.
                s = subscriber._RmakeServerPublisherProxy(ShimAddress(self))
            self._subscribers.append(s)

            self._internalSubscribers = [dbLogger]
            s = subscriber._RmakeServerPublisherProxy(ShimAddress(self))
            self._internalSubscribers.append(s)
            self.plugins.callServerHook('server_postInit', self)
        except errors.uncatchableExceptions:
            raise
        except Exception, err:
            self.error('Error initializing rMake Server:\n  %s\n%s', err,
                        traceback.format_exc())
            self._try('halt', self._shutDown)
            raise
