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
Builder controls the process of building a set of troves.
"""

import signal
import sys
import os
import time
import traceback

from conary import conaryclient
from conary.repository import changeset

from rmake.build import buildjob
from rmake.build import dispatcher
from rmake.build import failure
from rmake.build import dephandler
from rmake.lib import logfile
from rmake.lib import logger
from rmake.lib import recipeutil
from rmake.lib import repocache

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
        self.dispatcher = dispatcher.Dispatcher(serverCfg, self.logger)

    def setDispatcher(self, dispatcher):
        self.dispatcher = dispatcher

    def getDispatcher(self):
        return self.dispatcher

    def getJob(self):
        return self.job

    def getRepos(self):
        repos = conaryclient.ConaryClient(self.buildCfg).getRepos()
        return repocache.CachingTroveSource(repos,
                                        self.serverCfg.getCacheDir())

    def info(self, state, message):
        self.logger.info(message)

    def _signalHandler(self, sigNum, frame):
        try:
            signal.signal(sigNum, signal.SIG_DFL)
            self.dispatcher.stopAllCommands()
            # NOTE: unfortunately, we can't send this out, it's entirely
            # possible the signal could have come from the rmake server.
            # instead, we'll have to let the server ensure our 
            # self.job.jobFailed('Received signal %s' % sigNum)
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
                self.job.exceptionOccurred(err, traceback.format_exc())
                self.logger.error(traceback.format_exc())
                self.logFile.restoreOutput()
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
                                               self.buildCfg, self.repos,
                                               self.logger, buildTroves)

        if not self._checkBuildSanity(buildTroves):
            return False

        self.job.log('Finding a buildable trove')
        self.dh.updateBuildableTroves()
        return True

    def build(self):
        # main loop is here.
        if not self.initializeBuild():
            return False

        if self.job.hasBuildableTroves():
            while True:
                if self.dispatcher._checkForResults():
                    self.dh.updateBuildableTroves()
                elif self.job.hasBuildableTroves():
                    self.buildTrove(self.job.iterBuildableTroves().next())
                elif self.job.hasBuildingTroves():
                    pass
                else:
                    break

            if self.dh.jobPassed():
                self.job.jobPassed("build job finished successfully")
                return True
            self.job.jobFailed("build job had failures")
        else:
            self.job.jobFailed('Did not find any buildable troves')
        return False

    def buildTrove(self, troveToBuild):
        buildReqs = self.dh.getBuildReqTroves(troveToBuild)
        self.job.log('Building %s' % troveToBuild.getName())
        targetLabel = self.buildCfg.getTargetLabel(troveToBuild.getVersion())
        self.dispatcher.buildTrove(self.buildCfg, troveToBuild.jobId,
                                   troveToBuild, buildReqs, targetLabel)

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
