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
rMake Backend server
"""
import errno
import itertools
import pwd
import os
import shutil
import signal
import sys
import time
import traceback
import xmlrpclib

from conary.deps import deps
from conary.lib import log
from conary.lib import util

from rmake import errors
from rmake import plugins
from rmake.build import builder
from rmake.build import buildcfg
from rmake.build import buildjob
from rmake.build import subscriber
from rmake.server import publish
from rmake.db import database
from rmake.lib.apiutils import api, api_parameters, api_return, freeze, thaw
from rmake.lib import apirpc

class rMakeServer(apirpc.XMLApiServer):
    """
        rMake server.

        See rMake client for documentation of API.
    """

    _CLASS_API_VERSION = 1

    @api(version=1)
    @api_parameters(1, 'troveTupleList', 'BuildConfiguration')
    @api_return(1, 'int')
    def buildTroves(self, callData, sourceTroveTups, buildCfg):
        self.updateBuildConfig(buildCfg)
        job = self.newJob(buildCfg, sourceTroveTups)
        self._subscribeToJobInternal(job)
        self.db.queueJob(job)
        job.jobQueued()
        return job.jobId

    @api(version=1)
    @api_parameters(1, None)
    def stopJob(self, callData, jobId):
        jobId = self.db.convertToJobId(jobId)
        job = self.db.getJob(jobId, withTroves=True)
        self._stopJob(job)
        self.db.subscribeToJob(job)
        self._subscribeToJobInternal(job)
        job.jobStopped('User requested stop')

    @api(version=1)
    @api_parameters(1)
    @api_return(1, None)
    def listJobs(self, callData):
        return self.db.listJobs()

    @api(version=1)
    @api_parameters(1, None, None)
    @api_return(1, None)
    def listTrovesByState(self, callData, jobId, state):
        jobId = self.db.convertToJobId(jobId)
        if state == '':
            state = None
        data = self.db.listTrovesByState(jobId, state)
        return [(x[0], freeze('troveTupleList', x[1])) for x in data.iteritems()]

    @api(version=1)
    @api_parameters(1, None, 'bool')
    @api_return(1, None)
    def getJobs(self, callData, jobIds, withTroves=True):
        jobIds = self.db.convertToJobIds(jobIds)
        return [ freeze('BuildJob', x)
                 for x in self.db.getJobs(jobIds, withTroves=withTroves) ]

    @api(version=1)
    @api_parameters(1, None, None)
    @api_return(1, None)
    def getJobLogs(self, callData, jobId, mark):
        jobId = self.db.convertToJobId(jobId)
        if not self.db.jobExists(jobId):
            self.warning("%s tried to obtain logs for invlid JobId %s" % (
                        str(callData.auth), jobId))
            return []
        return [ tuple(str(x) for x in data) 
                    for data in self.db.getJobLogs(jobId, mark) ]

    @api(version=1)
    @api_parameters(1, None, 'troveTuple', 'int')
    @api_return(1, None)
    def getTroveLogs(self, callData, jobId, troveTuple, mark):
        jobId = self.db.convertToJobId(jobId)
        return [ tuple(str(x) for x in data) for data in self.db.getTroveLogs(jobId, troveTuple, mark) ]

    @api(version=1)
    @api_parameters(1, None, 'troveTuple', 'int')
    @api_return(1, None)
    def getTroveBuildLog(self, callData, jobId, troveTuple, mark):
        jobId = self.db.convertToJobId(jobId)
        trove = self.db.getTrove(jobId, *troveTuple)
        if not self.db.hasTroveBuildLog(trove):
            return False, xmlrpclib.Binary('')
        f = self.db.openTroveBuildLog(trove)
        f.seek(mark)
        return trove.isBuilding(), xmlrpclib.Binary(f.read())

    @api(version=1)
    @api_parameters(1, None)
    @api_return(1, None)
    def deleteJobs(self, callData, jobIdList):
        jobIdList = self.db.convertToJobIds(jobIdList)
        jobs = self.db.getJobs(jobIdList, withTroves=False)
        for job in jobs:
            if job.isBuilding():
                raise errors.RmakeError('cannot delete active job %s' % job.jobId)
        deletedJobIds = self.db.deleteJobs(jobIdList)
        return deletedJobIds

    @api(version=1)
    @api_parameters(1, None, 'Subscriber')
    @api_return(1, 'int')
    def subscribe(self, callData, jobId, subscriber):
        jobId = self.db.convertToJobId(jobId)
        self.db.addSubscriber(jobId, subscriber)
        return subscriber.subscriberId

    @api(version=1)
    @api_parameters(1, 'int')
    @api_return(1, 'Subscriber')
    def unsubscribe(self, callData, subscriberId):
        subscriber = self.db.getSubscriber(subscriberId)
        self.db.removeSubscriber(subscriberId)
        return subscriber

    @api(version=1)
    @api_parameters(1, None, 'str')
    @api_return(1, None)
    def listSubscribersByUri(self, callData, jobId, uri):
        jobId = self.db.convertToJobId(jobId)
        subscribers = self.db.listSubscribersByUri(jobId, uri)
        return [ thaw('Subscriber', x) for x in subscribers ]

    @api(version=1)
    @api_parameters(1, None)
    @api_return(1, None)
    def listSubscribers(self, callData, jobId):
        jobId = self.db.convertToJobId(jobId)
        subscribers = self.db.listSubscribers(jobId)
        return [ thaw('Subscriber', x) for x in subscribers ]

    @api(version=1)
    @api_parameters(1, None)
    def startCommit(self, callData, jobId):
        jobId = self.db.convertToJobId(jobId)
        job = self.db.getJob(jobId)
        pid = os.fork()
        if pid:
            self.info('jobCommitting forked pid %d' % pid)
            return
        else:
            try:
                self.db.subscribeToJob(job)
                self._subscribeToJob(job)
                job.jobCommitting()
                os._exit(0)
            finally:
                os._exit(1)

    @api(version=1)
    @api_parameters(1, None, 'str')
    def commitFailed(self, callData, jobId, message):
        jobId = self.db.convertToJobId(jobId)
        job = self.db.getJob(jobId)
        pid = os.fork()
        if pid:
            self.info('commitFailed forked pid %d' % pid)
            return
        else:
            try:
                self.db.subscribeToJob(job)
                self._subscribeToJob(job)
                job.jobCommitFailed(message)
                os._exit(0)
            finally:
                os._exit(1)

    @api(version=1)
    @api_parameters(1, None, 'troveTupleList')
    def commitSucceeded(self, callData, jobId, troveTupleList):
        jobId = self.db.convertToJobId(jobId)
        job = self.db.getJob(jobId)
        pid = os.fork()
        if pid:
            self.info('commitSucceeded forked pid %d' % pid)
            return
        else:
            try:
                self.db.subscribeToJob(job)
                self._subscribeToJob(job)
                job.jobCommitted(troveTupleList)
                os._exit(0)
            finally:
                os._exit(1)


    # --- callbacks from Builders -

    @api(version=1)
    @api_parameters(1, None, 'EventList')
    def emitEvents(self, callData, jobId, (apiVer, eventList)):
        # currently we assume that this apiVer is extraneous, just
        # a part of the protocol for EventLists.
        self._events.setdefault(jobId, []).extend(eventList)
        self._numEvents += len(eventList)
    # --- internal functions

    def newJob(self, buildCfg, sourceTroveTups):
        job = buildjob.NewBuildJob(self.db, sourceTroveTups, buildCfg,
                                   state=buildjob.JOB_STATE_QUEUED,
                                   uuid=buildCfg.uuid)
        return job

    def getBuilder(self, job, buildConfig):
        b = builder.Builder(self.cfg, buildConfig, job)
        self.plugins.callServerHook('server_builderInit', self, b)
        return b

    def updateBuildConfig(self, buildConfig):
        buildConfig.repositoryMap.update(self.cfg.getRepositoryMap())
        for serverName, user, password in self.cfg.getUserGlobs():
            buildConfig.user.addServerGlob(serverName, user, password)

    def _serveLoopHook(self):
        if not self._initialized:
            jobsToFail = self.db.getJobsByState(buildjob.JOB_STATE_STARTED)
            self._failCurrentJobs(jobsToFail, 'Server was stopped')
            self._initialized = True
        if not self.db.isJobBuilding():
            while True:
                job = self.db.popJobFromQueue()
                if job is None:
                    break
                if job.isFailed():
                    continue
                buildCfg = self.db.getJobConfig(job.jobId)
                buildCfg.setServerConfig(self.cfg)
                self._startBuild(job, buildCfg)
                break
        self._emitEvents()
        self._collectChildren()
        self.plugins.callServerHook('server_loop', self)

    def _shutDown(self):
        self.plugins.callServerHook('server_shutDown', self)
        # we've gotten a request to halt, kill all jobs (they've run
        # setpgrp) and then kill ourselves
        self._stopAllJobs()
        sys.exit(0)

    def _subscribeToJob(self, job):
        subscriber._RmakeServerPublisherProxy(self.uri).attach(job)

    def _subscribeToJobInternal(self, job):
        subscriber._RmakeServerPublisherProxy(self).attach(job)

    def _emitEvents(self):
        if not self._events or self._emitPid:
            return
        if ((time.time() - self._lastEmit) < self._emitEventTimeThreshold
            and self._numEvents < self._emitEventSizeThreshold):
            return
        events = self._events
        self._events = {}
        pid = os.fork()
        if pid:
            self._numEvents = 0
            self._lastEmit = time.time()
            self._emitPid = pid
            self.info('_emitEvents forked pid %d' % pid)
            return
        try:
            try:
                for jobId, eventList in events.iteritems():
                    self.db.reopen()
                    self._publisher.emitEvents(self.db, jobId, eventList)
                os._exit(0)
            except Exception, err:
                self.error('Emit Events failed: %s\n%s', err, 
                           traceback.format_exc())
                os._exit(1)
        finally:
            os._exit(1)

    def _startBuild(self, job, buildCfg):
        buildMgr = self.getBuilder(job, buildCfg)
        pid = os.fork()
        if pid:
            self._buildPids[pid] = job.jobId # mark this pid for potential 
                                             # killing later
            return job.jobId
        else:
            # we want to be able to kill this build process and
            # all its children with one swell foop.
            os.setpgrp()
            # restore default signal handlers, so we actually respond
            # to these.
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            signal.signal(signal.SIGINT, signal.default_int_handler)


            # need to reinitialize the database in the forked child process
            self.db.reopen()

            # note - we cannot call any callbacks before we fork 
            # until we have a forking xmlrpc server
            self.db.subscribeToJob(job)
            self._subscribeToJob(job)

            job.jobStarted("spawning process %s for build %s..." % (
                                                    os.getpid(), job.jobId,),
                                                    pid=os.getpid())
            job.log("Starting Build")
            # don't do anything else in here, buildAndExit has handling for
            # ensuring that exceptions are handled correctly.
            try:
                buildMgr.buildAndExit()
            finally:
                os._exit(2)

    def _failCurrentJobs(self, jobs, reason):
        from rmake.server.client import rMakeClient
        pid = os.fork()
        if pid:
            self.info('Fail current jobs forked pid %d' % pid)
            return
        try:
            client = rMakeClient(self.uri)
            # make sure the main process is up and running before we 
            # try to communicate w/ it
            client.ping()
            self.db.reopen()
            for job in jobs:
                self._subscribeToJob(job)
                self.db.subscribeToJob(job)
                publisher = job.getPublisher()
                job.jobFailed(reason)
            os._exit(0)
        finally:
            os._exit(1)

    def _pidDied(self, pid, status):
        apirpc.XMLApiServer._pidDied(self, pid, status)
        self._buildPids.pop(pid, None)

        if pid == self._emitPid: # rudimentary locking for emits
            self._emitPid = 0    # only allow one emitEvent process 
                                 # at a time.

        if pid == self.repositoryPid:
            self.error('Internal Repository died - shutting down rMake')
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
        elif not job.isRunning():
            raise errors.RmakeError('Cannot stop job %s - it is'
                                    ' already stopped' % job.jobId)

        if job.pid not in self._buildPids:
            self.warning('job %s is not in active job list')
            return
        else:
            try:
                os.kill(-job.pid, signal.SIGTERM)
            except OSError, err:
                if err.errno == errno.ESRCH:
                    # the process is already dead!
                    return
                raise

            timeSlept = 0
            while timeSlept < 20:
                pid, status = os.waitpid(job.pid, os.WNOHANG)
                if not pid:
                    time.sleep(.5)
                    timeSlept += .5
                    continue

                # yay, our kill worked.
                if os.WIFEXITED(status):
                    exitRc = os.WEXITSTATUS(status)
                    if exitRc:
                        self.warning('job %s (pid %s) exited with'
                                    ' exit status %s' % (job.jobId, pid, exitRc))
                else:
                    sigNum = os.WTERMSIG(status)
                    self.warning('job %s (pid %s) exited with'
                                ' signal %s' % (job.jobId, pid, sigNum))
                return

            if timeSlept >= 20:
                # we need to SIGKILL this guy, he did not respond to our
                # request.
                self.warning('job %s (pid %s) did not exit, trying harder') 
                try:
                    os.kill(-job.pid, signal.SIGTERM)
                except OSError, err:
                    if err.errno != errno. SRCH:
                        raise

    def _stopAllJobs(self):
        for pid, jobId in self._buildPids.items():
            try:
                os.kill(-os.getpgid(pid), signal.SIGTERM)
            except OSError, err:
                if err.errno != errno.ESRCH:
                    raise

        killed = []
        timeSlept = 0
        while timeSlept < 15 and self._buildPids:
            for pid in list(self._buildPids):
                try:
                    pid, status = os.waitpid(pid, os.WNOHANG)
                except OSError, err:
                    if err.errno in (errno.ESRCH, errno.ECHILD):
                        jobId = self._buildPids.pop(pid)
                        killed.append(jobId)
                        continue
                    else:
                        raise
                else:
                    if not pid:
                        continue
                jobId = self._buildPids.pop(pid)
                killed.append(jobId)
            time.sleep(.5)
            timeSlept += .5

        publishers = []
        jobs = self.db.getJobs(killed)
        for job in jobs:
            self._subscribeToJobInternal(job)
            self.db.subscribeToJob(job)
            publisher = job.getPublisher()
            publisher.cork()
            publishers.append(publisher)
            job.jobFailed('Halted by external event')

        # make all db and emit events at the same time.
        for publisher in publishers:
            publisher.uncork()


    def __init__(self, uri, cfg, repositoryPid, pluginMgr=None):
        self.uri = uri
        self.cfg = cfg
        self.repositoryPid = repositoryPid
        self.db = database.Database(cfg.getDbPath(),
                                    cfg.getDbContentsPath())
        if pluginMgr is None:
            pluginMgr = plugins.PluginManager([])
        self.plugins = pluginMgr

        # any jobs that were running before are not running now
        self._publisher = publish._RmakeServerPublisher()

        util.mkdirChain(self.cfg.logDir)
        self.xmlRpcLog = open(self.cfg.logDir + '/xmlrpc.log', 'w')
        apirpc.XMLApiServer.__init__(self, uri, logRequests=False,
                                     logStream=self.xmlRpcLog)
        self.queue = []
        self._initialized = False

        # event queuing code - to eventually be moved to a separate process
        self._events = {}
        self._emitEventTimeThreshold = .2  # min length of time between emits
        self._emitEventSizeThreshold = 10  # max # of issues to queue before
                                           # emit (overrides time threshold)

        self._numEvents = 0                # number of queued events
        self._lastEmit = time.time()       # time of last emit
        self._emitPid = 0                  # pid for rudimentary locking


        self._buildPids = {}         # forked jobs that are currently active
        self.plugins.callServerHook('server_postInit', self)
