#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Builder controls the process of building a set of troves.
"""
import random
import signal
import sys
import os
import time
import traceback

from conary import conaryclient
from conary.lib import util
from conary.repository import changeset

from rmake import failure
from rmake.build import buildtrove
from rmake.build import buildjob
from rmake.build import dephandler
from rmake.lib import logfile
from rmake.lib import logger
from rmake.lib import recipeutil
from rmake.lib import repocache
from rmake.worker import recorder
from rmake.worker import worker

class Builder(object):
    """
        Build manager for rMake.

        Basically:
            * get a set of troves in init.
            * load the troves to determine what packages they create,
              what flavors they use, and what build requirements they have.
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
    def __init__(self, serverCfg, job, jobContext=None, db=None):
        self.serverCfg = serverCfg
        self.buildCfg = job.getMainConfig()
        self.logger = BuildLogger(job.jobId,
                                  serverCfg.getBuildLogPath(job.jobId))
        self.logFile = logfile.LogFile(
                                    serverCfg.getBuildLogPath(job.jobId))
        self.repos = self.getRepos()
        self.job = job
        self.jobId = job.jobId
        self.db = db
        self.worker = worker.Worker(serverCfg, self.logger, serverCfg.slots)
        self.eventHandler = EventHandler(job, self.worker)
        if jobContext:
            self.setJobContext(jobContext)
        else:
            self.jobContext = []
        self.initialized = False


    def _installSignalHandlers(self):
        signal.signal(signal.SIGTERM, self._signalHandler)
        signal.signal(signal.SIGINT, self._signalHandler)
        def _interrupt(*args, **kw):
            import epdb
            if hasattr(epdb, 'serve'):
                epdb.serve()
            else:
                epdb.st()
        # if you kill the dispatcher w/ SIGUSR1 you'll get a breakpoint.
        signal.signal(signal.SIGUSR1, _interrupt)

    def _closeLog(self):
        self.logFile.close()
        self.logger.close()

    def setJobContext(self, jobList):
        self.jobContext = jobList

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
                        from conary.lib import epdb
                        epdb.post_mortem(sys.exc_info()[2])
                    os._exit(0)
        finally:
            os._exit(1)

    def initializeBuild(self):
        for buildCfg in self.job.iterConfigList():
            buildCfg.repositoryMap.update(
                                      self.serverCfg.getRepositoryMap())
            buildCfg.user.extend(self.serverCfg.reposUser)
            buildCfg.reposName = self.serverCfg.reposName

        self.initialized = True
        self.job.log('Build started - loading troves')
        buildTroves = recipeutil.getSourceTrovesFromJob(self.job,
                                                        self.serverCfg,
                                                        self.repos)
        self._matchTrovesToJobContext(buildTroves, self.jobContext)
        self.job.setBuildTroves(buildTroves)

        logDir = self.serverCfg.getBuildLogDir(self.job.jobId)
        util.mkdirChain(logDir)
        self.dh = dephandler.DependencyHandler(self.job.getPublisher(),
                                               self.logger, buildTroves,
                                               logDir)
        if not self._checkBuildSanity(buildTroves):
            return False
        return True

    def build(self):
        self.job.jobStarted("Starting Build %s (pid %s)" % (self.job.jobId,
                            os.getpid()), pid=os.getpid())
        # main loop is here.
        if not self.initialized:
            if not self.initializeBuild():
                return False

        if self.dh.moreToDo():
            while self.dh.moreToDo():
                self.worker.handleRequestIfReady()
                if self.worker._checkForResults():
                    self.resolveIfReady()
                elif self.dh.hasBuildableTroves():
                    trv, (buildReqs, crossReqs) = self.dh.popBuildableTrove()
                    self.buildTrove(trv, buildReqs, crossReqs)
                elif not self.resolveIfReady():
                    time.sleep(0.1)
            if self.dh.jobPassed():
                self.job.jobPassed("build job finished successfully")
                return True
            msg = ['Build job had failures:\n']
            for trove in sorted(self.job.iterPrimaryFailureTroves()):
                err = trove.getFailureReason().getShortError()
                msg.append('   * %s: %s\n' % (trove.getName(), err))
            self.job.jobFailed(''.join(msg))
        else:
            msg = ['Did not find any buildable troves:']
            for trove in sorted(self.job.iterPrimaryFailureTroves()):
                err = trove.getFailureReason().getShortError()
                msg.append('   * %s: %s\n' % (trove.getName(), err))
            self.job.jobFailed(''.join(msg))
        return False

    def buildTrove(self, troveToBuild, buildReqs, crossReqs):
        targetLabel = troveToBuild.cfg.getTargetLabel(troveToBuild.getVersion())
        troveToBuild.troveQueued('Waiting to be assigned to chroot')
        troveToBuild.disown()

        logData = self.startTroveLogger(troveToBuild)
        if troveToBuild.isDelayed():
            builtTroves = self.job.getBuiltTroveList()
        else:
            builtTroves = []
        self.worker.buildTrove(troveToBuild.cfg, troveToBuild.jobId,
                               troveToBuild, self.eventHandler, buildReqs,
                               crossReqs, targetLabel, logData,
                               builtTroves=builtTroves)

    def resolveIfReady(self):
        resolveJob = self.dh.getNextResolveJob()
        if resolveJob:
            resolveJob.getTrove().troveQueued('Ready for dep resolution')
            resolveJob.getTrove().disown()
            logData = self.startTroveLogger(resolveJob.getTrove())
            self.worker.resolve(resolveJob, self.eventHandler, logData)
            return True
        return False

    def _matchTrovesToJobContext(self, buildTroves, jobContext):
        trovesByNVF = {}
        for trove in buildTroves:
            trovesByNVF[trove.getNameVersionFlavor()] = trove

        for jobId in reversed(jobContext): # go through last job first.
            needed = {}
            configsNeeded = set()
            if not trovesByNVF:
                continue

            builtState = buildtrove.TROVE_STATE_BUILT
            trovesByState = self.db.listTrovesByState(jobId, builtState)
            for n,v,f,c in trovesByState.get(builtState, []):
                toBuild = trovesByNVF.pop((n,v,f), False)
                if toBuild:
                    needed[jobId, n,v,f,c] = toBuild
                    configsNeeded.add(c)
            if not needed:
                continue
            troveList = self.db.getTroves(needed)
            configDict = dict((x, self.db.getConfig(jobId, x)) for x in 
                            configsNeeded)
            for trove, toBuild in zip(troveList, needed.values()):
                buildReqs = False
                binaries = trove.getBinaryTroves()
                for troveTup in binaries:
                    if ':' not in troveTup[0]:
                        trv = self.repos.getTrove(withFiles=False,
                                                  *troveTup)
                        buildReqs = trv.getBuildRequirements()
                        loadedReqs = trv.getLoadedTroves()
                        break
                if buildReqs is False:
                    continue
                if set(loadedReqs) != set(toBuild.getLoadedTroves()):
                    continue
                oldCfg = configDict[trove.getContext()]
                newCfg = toBuild.getConfig()
                fastRebuild = (oldCfg.resolveTrovesOnly
                    and newCfg.resolveTrovesOnly
                    and oldCfg.resolveTroveTups == newCfg.resolveTroveTups
                    and oldCfg.flavor == newCfg.flavor)
                toBuild.trovePrebuilt(buildReqs, binaries,
                                      trv.getBuildTime(), fastRebuild,
                                      trove.logPath)

    def _checkBuildSanity(self, buildTroves):
        def _isSolitaryTrove(trv):
            return (trv.isRedirectRecipe() or trv.isFilesetRecipe())


        delayed = [ x for x in buildTroves if _isSolitaryTrove(x) ]
        if delayed and len(buildTroves) > 1:
            err = ('redirect and fileset packages must'
                   ' be alone in their own job')
            for trove in delayed:
                # publish failed status
                trove.troveFailed(failure.FailureReason('Trove failed sanity check: %s' % err))
            troveNames = ', '.join(x.getName().split(':')[0] for x in delayed)
            self.job.jobFailed(failure.FailureReason("Job failed sanity check: %s: %s" % (err, troveNames)))
            return False

        isGroup = [ x for x in buildTroves if x.isGroupRecipe() ]
        if isGroup and len(buildTroves) > 1:
            self.job.log("WARNING: Combining group troves with other troves"
                         " is EXPERIMENTAL - use at your own risk")
            time.sleep(3)
        return True

    def startTroveLogger(self, trove):
        key = ''.join([ chr(random.randrange(ord('a'), ord('z'))) 
                      for x in range(10) ])
        r = recorder.BuildLogRecorder(key)
        r.attach(trove)
        logHost = r.getHost()
        logPort = r.getPort()
        trove.logPath = r.getLogPath()
        pid = self.worker._fork('BuildLogger for %s' % trove)
        if not pid:
            try:
                r._installSignalHandlers()
                r.serve_forever()
            finally:
                os._exit(3)
        else:
            r.close()
            trove.logPid = pid
        return logHost, logPort, key

class BuildLogger(logger.Logger):
   def __init__(self, jobId, path):
        logger.Logger.__init__(self, 'build-%s' % jobId, path)

from rmake.lib import subscriber
class EventHandler(subscriber.StatusSubscriber):
    listeners = { 'TROVE_PREPARING_CHROOT' : 'trovePreparingChroot',
                  'TROVE_BUILT'            : 'troveBuilt',
                  'TROVE_PREPARED'         : 'trovePrepared',
                  'TROVE_FAILED'           : 'troveFailed',
                  'TROVE_RESOLVING'        : 'troveResolving',
                  'TROVE_RESOLVED'         : 'troveResolutionCompleted',
                  'TROVE_LOG_UPDATED'      : 'troveLogUpdated',
                  'TROVE_BUILDING'         : 'troveBuilding',
                  'TROVE_DUPLICATE'        : 'troveDuplicate',
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
        self.server.stopTroveLogger(t)
        t.troveBuilt(binaryTroveList)
        t.own()

    def trovePrepared(self, (jobId, troveTuple)):
        self._hadEvent = True
        t = self.job.getTrove(*troveTuple)
        self.server.stopTroveLogger(t)
        t.trovePrepared()
        t.own()

    def troveLogUpdated(self, (jobId, troveTuple), state, log):
        t = self.job.getTrove(*troveTuple)
        t.log(log)

    def troveFailed(self, (jobId, troveTuple), failureReason):
        self._hadEvent = True
        t = self.job.getTrove(*troveTuple)
        self.server.stopTroveLogger(t)
        t.troveFailed(failureReason)
        t.own()

    def troveResolving(self, (jobId, troveTuple), chrootHost, pid):
        t = self.job.getTrove(*troveTuple)
        t.troveResolvingBuildReqs(chrootHost, pid)

    def troveResolutionCompleted(self, (jobId, troveTuple), resolveResults):
        self._hadEvent = True
        t = self.job.getTrove(*troveTuple)
        t.troveResolved(resolveResults)
        t.own()

    def trovePreparingChroot(self, (jobId, troveTuple), chrootHost, chrootPath):
        t = self.job.getTrove(*troveTuple)
        t.creatingChroot(chrootHost, chrootPath)

    def troveBuilding(self, (jobId, troveTuple), pid):
        t = self.job.getTrove(*troveTuple)
        t.troveBuilding(pid)

    def troveDuplicate(self, (jobId, troveTuple), troveList):
        t = self.job.getTrove(*troveTuple)
        t.troveDuplicate(troveList)
        t.own()

    def troveStateUpdated(self, (jobId, troveTuple), state, status):
        if state not in (buildtrove.TROVE_STATE_FAILED,
                         buildtrove.TROVE_STATE_UNBUILDABLE,
                         buildtrove.TROVE_STATE_BUILT,
                         buildtrove.TROVE_STATE_DUPLICATE,
                         buildtrove.TROVE_STATE_RESOLVING,
                         buildtrove.TROVE_STATE_PREPARING,
                         buildtrove.TROVE_STATE_BUILDING):
            t = self.job.getTrove(*troveTuple)
            t._setState(state, status)
