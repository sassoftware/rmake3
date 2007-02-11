#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Builder controls the process of building a set of troves.
"""
import signal
import sys
import os
import time
import traceback

from conary import conaryclient
from conary.repository import changeset

from rmake import failure
from rmake.build import buildtrove
from rmake.build import buildjob
from rmake.build import dephandler
from rmake.lib import logfile
from rmake.lib import logger
from rmake.lib import recipeutil
from rmake.lib import repocache
from rmake.worker import worker

class Builder(object):
    """
        Build manager for rMake.

        Basically:
            * get a set of troves in init.
            * load the troves to determine what packages they create,
              while flavors they use, and what build requirements they have.
            * while buildable troves left:
                * build one trove.
                * commit to internal repos if successful.

        Almost all passing of information from the builder is done through 
        subscription.  Instances register to listen to particular events on 
        the trove and job objects.  Those events are triggered by changing the
        states of the trove objects.

        Instances that listen on this side of the rMake server are called
        "Internal subscribers" - the database is one, the message passer that
        lets the rmake server know about status updates is another.

        See build/subscribe.py for more information.

        @param serverCfg: rmake server Configuration.  Used to determine 
        location to commit troves.
        @type serverCfg: rmake.server.servercfg.rMakeConfiguration
        @param buildCfg: build configuration, describes all parameters for 
        build.
        @type buildCfg: rmake.build.buildcfg.BuildConfiguration instance.
    """
    def __init__(self, serverCfg, buildCfg, job):
        self.serverCfg = serverCfg
        self.buildCfg = buildCfg
        self.logger = BuildLogger(job.jobId,
                                  serverCfg.getBuildLogPath(job.jobId))
        self.logFile = logfile.LogFile(
                                    serverCfg.getBuildLogPath(job.jobId))
        self.repos = self.getRepos()
        self.job = job
        self.jobId = job.jobId
        self.worker = worker.Worker(serverCfg, self.logger, serverCfg.slots)
        self.eventHandler = EventHandler(job, self.worker)

    def _closeLog(self):
        self.logFile.close()
        self.logger.close()

    def setWorker(self, worker):
        self.worker = worker

    def getWorker(self):
        return self.worker

    def getJob(self):
        return self.job

    def getRepos(self):
        repos = conaryclient.ConaryClient(self.buildCfg).getRepos()
        if self.serverCfg.useCache:
            return repocache.CachingTroveSource(repos,
                                            self.serverCfg.getCacheDir())
        return repos

    def info(self, state, message):
        self.logger.info(message)

    def _signalHandler(self, sigNum, frame):
        try:
            signal.signal(sigNum, signal.SIG_DFL)
            self.worker.stopAllCommands()
            self.job.jobFailed('Received signal %s' % sigNum)
            os.kill(os.getpid(), sigNum)
        finally:
            os._exit(1)

    def buildAndExit(self):
        try:
            try:
                signal.signal(signal.SIGTERM, self._signalHandler)
                self.logFile.redirectOutput() # redirect all output to the log 
                                              # file.
                                              # We do this to ensure that
                                              # output we don't control,
                                              # such as conary output, is
                                              # directed to a file.
                self.build()
                os._exit(0)
            except Exception, err:
                self.logger.error(traceback.format_exc())
                self.job.exceptionOccurred(err, traceback.format_exc())
                self.logFile.restoreOutput()
                try:
                    self.worker.stopAllCommands()
                finally:
                    if sys.stdin.isatty():
                        # this sets us back to be connected with the controlling
                        # terminal (owned by our parent, the rmake server)
                        import epdb
                        epdb.post_mortem(sys.exc_info()[2])
                    os._exit(0)
        finally:
            os._exit(1)

    def initializeBuild(self):
        self.job.log('Build started - loading troves')
        buildTroves = recipeutil.getSourceTrovesFromJob(self.job,
                                                        self.buildCfg,
                                                        self.repos)
        self.job.setBuildTroves(buildTroves)

        self.dh = dephandler.DependencyHandler(self.job.getPublisher(),
                                               self.buildCfg,
                                               self.logger, buildTroves)

        if not self._checkBuildSanity(buildTroves):
            return False
        return True

    def build(self):
        self.job.jobStarted("Starting Build %s (pid %s)" % (self.job.jobId,
                            os.getpid()), pid=os.getpid())
        # main loop is here.
        if not self.initializeBuild():
            return False

        if self.dh.moreToDo():
            while self.dh.moreToDo():
                self.worker.handleRequestIfReady()
                if self.worker._checkForResults():
                    self.resolveIfReady()
                elif self.dh.hasBuildableTroves():
                    trv, buildReqs = self.dh.popBuildableTrove()
                    self.buildTrove(trv, buildReqs)
                elif not self.resolveIfReady():
                    time.sleep(0.1)
            if self.dh.jobPassed():
                self.job.jobPassed("build job finished successfully")
                return True
            self.job.jobFailed("build job had failures")
        else:
            self.job.jobFailed('Did not find any buildable troves')
        return False

    def buildTrove(self, troveToBuild, buildReqs):
        self.job.log('Building %s' % troveToBuild.getName())
        targetLabel = self.buildCfg.getTargetLabel(troveToBuild.getVersion())
        troveToBuild.troveQueued('Waiting to be assigned to chroot')
        troveToBuild.disown()
        logHost, logPort = self.worker.startTroveLogger(troveToBuild)
        self.worker.buildTrove(self.buildCfg, troveToBuild.jobId,
                               troveToBuild, self.eventHandler, buildReqs,
                               targetLabel, logHost, logPort)

    def resolveIfReady(self):
        resolveJob = self.dh.getNextResolveJob()
        if resolveJob:
            self.worker.resolve(resolveJob, self.eventHandler)
            return True
        return False

    def _checkBuildSanity(self, buildTroves):
        def _referencesOtherTroves(trv):
            return (trv.isGroupRecipe() or trv.isRedirectRecipe()
                    or trv.isFilesetRecipe())

        delayed = [ x for x in buildTroves if _referencesOtherTroves(x) ]
        if delayed and len(buildTroves) > 1:
            err = ('group, redirect, and fileset packages must'
                   ' be alone in their own job')
            for trove in delayed:
                # publish failed status
                trove.troveFailed(failure.FailureReason('Trove failed sanity check: %s' % err))
            troveNames = ', '.join(x.getName().split(':')[0] for x in delayed)
            self.job.jobFailed(failure.FailureReason("Job failed sanity check: %s: %s" % (err, troveNames)))
            return False
        return True

class BuildLogger(logger.Logger):
   def __init__(self, jobId, path):
        logger.Logger.__init__(self, 'build-%s' % jobId, path)

from rmake.lib import subscriber
class EventHandler(subscriber.StatusSubscriber):
    listeners = { 'TROVE_PREPARING_CHROOT' : 'trovePreparingChroot',
                  'TROVE_BUILT'            : 'troveBuilt',
                  'TROVE_FAILED'           : 'troveFailed',
                  'TROVE_RESOLVING'        : 'troveResolving',
                  'TROVE_RESOLVED'         : 'troveResolutionCompleted',
                  'TROVE_LOG_UPDATED'      : 'troveLogUpdated',
                  'TROVE_BUILDING'         : 'troveBuilding',
                  'TROVE_STATE_UPDATED'    : 'troveStateUpdated' }

    def __init__(self, job, server):
        self.server = server
        self.job = job
        self._hadEvent = False
        subscriber.StatusSubscriber.__init__(self, None, None)

    def hadEvent(self):
        return self._hadEvent

    def reset(self):
        self._hadEvent = False

    def troveBuilt(self, (jobId, troveTuple), binaryTroveList):
        self._hadEvent = True
        t = self.job.getTrove(*troveTuple)
        if hasattr(t, 'logPid'):
            self.server._killPid(t.logPid)
        t.troveBuilt(binaryTroveList)
        t.own()

    def troveLogUpdated(self, (jobId, troveTuple), state, log):
        t = self.job.getTrove(*troveTuple)
        t.log(log)

    def troveFailed(self, (jobId, troveTuple), failureReason):
        self._hadEvent = True
        t = self.job.getTrove(*troveTuple)
        if hasattr(t, 'logPid'):
            self.server._killPid(t.logPid)
        t.troveFailed(failureReason)
        t.own()

    def troveResolving(self, (jobId, troveTuple), chrootHost):
        t = self.job.getTrove(*troveTuple)
        t.resolvingDependencies()

    def troveResolutionCompleted(self, (jobId, troveTuple), resolveResults):
        self._hadEvent = True
        t = self.job.getTrove(*troveTuple)
        t.troveResolved(resolveResults)
        t.own()

    def trovePreparingChroot(self, (jobId, troveTuple), chrootHost, chrootPath):
        t = self.job.getTrove(*troveTuple)
        t.creatingChroot(chrootHost, chrootPath)

    def troveBuilding(self, (jobId, troveTuple), logPath, pid):
        t = self.job.getTrove(*troveTuple)
        t.troveBuilding(logPath, pid)

    def troveStateUpdated(self, (jobId, troveTuple), state, status):
        if state not in (buildtrove.TROVE_STATE_FAILED,
                         buildtrove.TROVE_STATE_BUILT,
                         buildtrove.TROVE_STATE_PREPARING,
                         buildtrove.TROVE_STATE_BUILDING):
            t = self.job.getTrove(*troveTuple)
            t._setState(state, status)
