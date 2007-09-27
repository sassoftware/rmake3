#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Client that contains most of the behavior available from the command line.

This client wraps around the low-level rMake Server client to provide
functionality that crosses client/server boundaries.
"""

import copy
import itertools
from optparse import OptionParser
import os
import socket
import sys
import tempfile
import time

from conary import conarycfg
from conary import conaryclient
from conary.conaryclient import cmdline
from conary import state
from conary import versions
from conary.build import use
from conary.deps import deps
from conary.lib import log
from conary.lib import options
from conary.repository import trovesource

from rmake import errors
from rmake.build import buildcfg
from rmake.build import buildjob
from rmake.cmdline import buildcmd
from rmake.cmdline import commit
from rmake.cmdline import monitor
from rmake.cmdline import cmdutil
from rmake.server import client
from rmake import compat
from rmake import plugins

class rMakeHelper(object):
    """
    Client that contains most of the behavior available from the command line.

    This client wraps around the low-level rMake Server client to provide
    functionality that crosses client/server boundaries.

    example:
        > h = rMakeHelper();
        > jobId = h.buildTroves('foo.recipe')
        > h.waitForJob(jobId)
        > if h.getJob(jobId).isPassed(): print "Foo recipe built!"
        > h.commitJob(jobId, message='Updated foo source component')

    @param uri: location to rmake server or rMake Server instance object.
    @type uri: string that starts with http, https, or unix://, or rMakeServer
    instance.
    @param rmakeConfig: Server Configuration (now deprecated)
    @type rmakeConfig: Unused parameter kept for bw compatibility
    @param buildConfig: rMake Build Configuration
    @type buildConfig: rmake.build.buildcfg.BuildConfiguration instance
    (or None to read from filesystem)
    @param root: Root directory to search for configuration files under.
    @type root: string
    @param guiPassword: If True, pop up a gui window for password prompts
    needed for accessing conary repositories.
    @type guiPassword: boolean
    """
    BUILD_RECURSE_GROUPS_BINARY = buildcmd.BUILD_RECURSE_GROUPS_BINARY
    BUILD_RECURSE_GROUPS_SOURCE = buildcmd.BUILD_RECURSE_GROUPS_SOURCE

    def __init__(self, uri=None, rmakeConfig=None, buildConfig=None, root='/',
                 guiPassword=False, plugins=None):
        if rmakeConfig:
            log.warning('rmakeConfig parameter is now deprecated')
        if not buildConfig:
            buildConfig = buildcfg.BuildConfiguration(True, root)

        if uri is None:
            uri = buildConfig.getServerUri()

        self.client = client.rMakeClient(uri)

        if guiPassword:
            try:
                from rmake.cmdline import password
                pwPrompt = password.PasswordPrompter(buildConfig).getPassword
            except ImportError, err:
                log.error('Could not load gtk password prompter - %s', err)
                pwPrompt = None
        else:
            pwPrompt = None
        self.pwPrompt = pwPrompt

        self.buildConfig = buildConfig
        self.plugins = plugins

    def getConaryClient(self, buildConfig=None):
        if buildConfig is None:
            buildConfig = self.buildConfig
        self.client.addRepositoryInfo(buildConfig)
        return conaryclient.ConaryClient(buildConfig,
                                         passwordPrompter=self.pwPrompt)

    def getRepos(self, buildConfig=None):
        return self.getConaryClient(buildConfig).getRepos()

    def displayConfig(self, hidePasswords=True, prettyPrint=True):
        """
            Display the current build configuration for this helper.

            @param hidePasswords: If True, display <pasword> instead of
            the password in the output.
            @param prettyPrint: If True, print output in human-readable format
            that may not be parsable by a config reader.  If False, the
            configuration output should be valid as input.
        """
        self.buildConfig.initializeFlavors()
        if not self.buildConfig.buildLabel:
            self.buildConfig.buildLabel = self.buildConfig.installLabelPath[0]
        self.buildConfig.setDisplayOptions(hidePasswords=hidePasswords,
                                           prettyPrint=prettyPrint)
        self.buildConfig.display()



    def restartJob(self, jobId, troveSpecs=None, updateSpecs=None,
                   excludeSpecs=None):
        job = self.client.getJob(jobId, withConfigs=True)
        troveSpecList = []
        oldTroveDict = {}
        configDict = {}
        mainConfig = copy.deepcopy(self.buildConfig)
        recurseGroups = job.getMainConfig().recurseGroups
        if not excludeSpecs:
            excludeSpecs = []

        for contextStr, jobConfig in job.getConfigDict().iteritems():
            troveSpecList += [ (x[0], x[1], x[2], contextStr)
                                for x in jobConfig.buildTroveSpecs ]
            oldTroveDict[contextStr] = [ x.getNameVersionFlavor()
                                         for x in job.iterTroves()
                                         if x.context == contextStr ]
            if not contextStr:
                cfg = mainConfig
            else:
                cfg = copy.deepcopy(self.buildConfig)
            configDict[contextStr] = cfg
            for context in contextStr.split(','):
                if context:
                    if cfg.hasSection(context):
                        cfg.setContext(context)
                    else:
                        log.warning('Context %s used in job %s does not exist' % (context, jobId))
                # FIXME: how do we determine what parts of the jobConfig get
                # overridden
                cfg.flavor = jobConfig.flavor
                cfg.buildFlavor = jobConfig.buildFlavor
                cfg.resolveTroves = jobConfig.resolveTroves
                cfg.resolveTrovesOnly = jobConfig.resolveTrovesOnly
                cfg.installLabelPath = jobConfig.installLabelPath
                if recurseGroups:
                    cfg.matchTroveRule = jobConfig.matchTroveRule
                for spec in excludeSpecs:
                    if isinstance(spec, tuple):
                        spec, context = cmdutil.getSpecStringFromTuple(spec)
                    else:
                        spec, context = cmdutil.parseTroveSpecContext(spec)
                    if context is None or context == contextStr:
                        cfg.addMatchRule('-%s' % spec)

        mainConfig.jobContext += [jobId]
        if troveSpecs:
            troveSpecList.extend(troveSpecs)
        return self.buildTroves(troveSpecList, buildConfig=mainConfig,
                                configDict=configDict,
                                recurseGroups=recurseGroups,
                                updateSpecs=updateSpecs,
                                oldTroveDict=oldTroveDict)

    def buildTroves(self, troveSpecList,
                    limitToHosts=None, limitToLabels=None, recurseGroups=False,
                    buildConfig=None, configDict=None, matchSpecs=None,
                    quiet=False, infoOnly=False, updateSpecs=None,
                    oldTroveDict=None):

        if not isinstance(troveSpecList, (list, tuple)):
            troveSpecList = [troveSpecList]
        if configDict:
            buildConfig = configDict['']
        else:
            if buildConfig is None:
                buildConfig = self.buildConfig
            if not recurseGroups:
                # only use default match rules when recursing.
                buildConfig.clearMatchRules()
        if limitToHosts:
            buildConfig.limitToHosts(limitToHosts)
        if limitToLabels:
            buildConfig.limitToLabels(limitToLabels)
        if matchSpecs:
            for matchSpec in matchSpecs:
                buildConfig.addMatchRule(matchSpec)

        job = buildcmd.getBuildJob(buildConfig,
                                   self.getConaryClient(buildConfig),
                                   troveSpecList,
                                   recurseGroups=recurseGroups,
                                   configDict=configDict,
                                   updateSpecs=updateSpecs,
                                   oldTroveDict=oldTroveDict)

        if infoOnly:
            verbose = log.getVerbosity() <= log.DEBUG
            return buildcmd.displayBuildInfo(job, verbose=verbose,
                                             quiet=quiet)
        jobId = self.client.buildJob(job)
        if not quiet:
            print 'Added Job %s' % jobId
            for (n,v,f) in sorted(job.iterTroveList()):
                if f is not None and not f.isEmpty():
                    f = '[%s]' % f
                else:
                    f = ''
                print '  %s=%s/%s%s' % (n, v.trailingLabel(),
                                           v.trailingRevision(), f)
        return jobId

    def stopJob(self, jobId):
        """
            Stops the given job.

            @param jobId: jobId to stop
            @type jobId: int or uuid
            @raise: RmakeError: If job is already stopped.
        """
        stopped = self.client.stopJob(jobId)

    def getJob(self, jobId, withTroves=True):
        return self.client.getJob(jobId, withTroves=withTroves)

    def createChangeSet(self, jobId, troveSpecs=None):
        """
            Creates a changeset object with all the built troves for a job.

            @param jobId: jobId or uuid for a given job.
            @type jobId: int or uuid
            @return: conary changeset object
            @rtype: conary.repository.changeset.ReadOnlyChangeSet
            @raise: JobNotFound: If job does not exist
        """
        job = self.client.getJob(jobId)
        binTroves = []
        for trove in job.iterTroves():
            binTroves.extend(trove.iterBuiltTroves())
        if not binTroves:
            log.error('No built troves associated with this job')
            return None
        if troveSpecs:
            troveSpecs = cmdline.parseTroveSpecs(troveSpecs)
            source = trovesource.SimpleTroveSource(binTroves)
            results = source.findTroves(None, troveSpecs)
            binTroves = itertools.chain(*results.values())
        jobList = [(x[0], (None, None), (x[1], x[2]), True) for x in binTroves]
        primaryTroveList = [ x for x in binTroves if ':' not in x[0]]
        cs = self.getRepos().createChangeSet(jobList, recurse=False,
                                             primaryTroveList=primaryTroveList)
        return cs

    def createChangeSetFile(self, jobId, path, troveSpecs=None):
        """
            Creates a changeset file with all the built troves for a job.

            @param jobId: jobId or uuid for a given job.
            @type jobId: int or uuid
            @return: False if changeset not created, True if it was.
            @raise: JobNotFound: If job does not exist
        """
        job = self.client.getJob(jobId)
        binTroves = []
        for trove in job.iterTroves():
            binTroves.extend(trove.iterBuiltTroves())
        if not binTroves:
            log.error('No built troves associated with this job')
            return False
        if troveSpecs:
            troveSpecs = [ cmdline.parseTroveSpec(x) for x in troveSpecs ]
            source = trovesource.SimpleTroveSource(binTroves)
            results = source.findTroves(None, troveSpecs)
            binTroves = list(itertools.chain(*results.values()))
            primaryTroveList = binTroves
            recurse = True
        else:
            recurse = False
            primaryTroveList = [ x for x in binTroves if ':' not in x[0]]

        jobList = [(x[0], (None, None), (x[1], x[2]), True) for x in binTroves ]
        self.getRepos().createChangeSetFile(jobList, path, recurse=recurse,
                                            primaryTroveList=primaryTroveList)
        return True

    def commitJobs(self, jobIds, message=None, commitOutdatedSources=False,
                   commitWithFailures=True, waitForJob=False,
                   sourceOnly=False, updateRecipes=True, excludeSpecs=[]):
        """
            Commits a set of jobs.

            Committing in rMake is slightly different from committing in 
            conary.  rMake uses the conary "clone" command to move the binary
            stored in its internal repository out into the repository the
            source component came from.

            @param jobId: jobId or uuid for a given job.
            @type jobId: int or uuid
            @param message: Message to use for source commits.
            @type message: str
            @param commitOutdatedSources: if True, allow commit of sources
            even if someone else has changed the source component outside
            of rMake before you.
            @param commitWithFailures: if True, allow commit of this job
            even if parts of the job have failed.
            @param waitForJob: if True, wait for the job to finish if necessary
            before committing.
            @param sourceOnly: if True, only commit the source component.
            @return: False if job failed to commit, True if it succeeded.
            @raise: JobNotFound: If job does not exist
        """
        if not isinstance(jobIds, (list, tuple)):
            jobIds = [jobIds]
        jobs = self.client.getJobs(jobIds, withConfigs=True)
        finalJobs = []
        for job in jobs:
            jobId = job.jobId
            if job.isCommitting():
                raise errors.RmakeError("Job %s is already committing" % job.jobId)
            if not job.isFinished() and waitForJob:
                print "Waiting for job %s to complete before committing" % jobId
                try:
                    self.waitForJob(jobId)
                except Exception, err:
                    print "Wait interrupted, not committing"
                    print "You can restart commit by running 'rmake commit %s'" % jobId
                    raise
                job = self.client.getJob(jobId)
            if not job.isFinished():
                log.error('Job %s is not yet finished' % jobId)
                return False
            if job.isFailed() and not commitWithFailures:
                log.error('Job %s has failures, not committing' % jobId)
                return False
            if not list(job.iterBuiltTroves()):
                log.error('Job %s has no built troves to commit' % jobId)
                return False
            finalJobs.append(job)

        jobs = [ x for x in finalJobs if not x.isCommitted() ]
        jobIds = [ x.jobId for x in finalJobs ]

        if not jobs:
            log.error('Job(s) already committed')
            return False
        excludeSpecs = [ cmdutil.parseTroveSpec(x) for x in excludeSpecs ]

        self.client.startCommit(jobIds)
        try:
            succeeded, data = commit.commitJobs(self.getConaryClient(), jobs,
                                   self.buildConfig.reposName, message,
                                   commitOutdatedSources=commitOutdatedSources,
                                   sourceOnly=sourceOnly,
                                   excludeSpecs=excludeSpecs)
            if succeeded:
                def _sortCommitted(tup1, tup2):
                    return cmp((tup1[0].endswith(':source'), tup1),
                               (tup2[0].endswith(':source'), tup2))
                def _formatTup(tup):
                    args = [tup[0], tup[1]]
                    if tup[2].isEmpty():
                        args.append('')
                    else:
                        args.append('[%s]' % buildTroveTup[2])
                    if not tup[3]:
                        args.append('')
                    else:
                        args.append('{%s}' % buildTroveTup[3])
                    return '%s=%s%s%s' % tuple(args)

                self.client.commitSucceeded(data)

            else:
                self.client.commitFailed(jobIds, data)
                log.error(data)
                return False
        except errors.uncatchableExceptions, err:
            self.client.commitFailed(jobIds, str(err))
            raise
        except Exception, err:
            self.client.commitFailed(jobIds, str(err))
            log.error(err)
            raise
        sourceComponents = []
        for jobId, troveTupleDict in sorted(data.iteritems()):
            print
            print 'Committed job %s:\n' % jobId,
            for buildTroveTup, committedList in \
                                    sorted(troveTupleDict.iteritems()):
                committedList = [ x for x in committedList
                                    if (':' not in x[0]
                                        or x[0].endswith(':source')) ]
                sourceComponents += [ x for x in committedList 
                                     if x[0].endswith(':source') ]
                print '    %s ->' % _formatTup(buildTroveTup)
                print ''.join('       %s=%s[%s]\n' % x
                              for x in sorted(committedList,
                                              _sortCommitted))
        if updateRecipes:
            # After the build is done, update .recipe files with the
            # committed versions.
            recipes = []
            for config in job.iterConfigList():
                for name, version, flavor in config.buildTroveSpecs:
                    if (os.path.exists(name)
                        and name.endswith('.recipe')):
                        recipes.append(name)
            if recipes:
                commit.updateRecipes(self.getRepos(), self.buildConfig, recipes,
                                     sourceComponents)
        return True

    commitJob = commitJobs # for bw compat

    def deleteJobs(self, jobIdList):
        """
            Deletes the given jobs.

            @param jobIdList: list of jobIds to delete
            @type jobIdList: int or uuid list
        """
        deleted = self.client.deleteJobs(jobIdList)
        print 'deleted %d jobs' % len(deleted)

    def waitForJob(self, jobId):
        """
            Waits for the given job to complete.

            Creates a silent subscriber that returns when the job is finished.
            @rtype: None
        """
        if (not isinstance(self.client.uri, str)
            or self.client.uri.startswith('unix://')):
            fd, tmpPath = tempfile.mkstemp()
            os.close(fd)
            uri = 'unix://' + tmpPath
        else:
            host = socket.gethostname()
            uri = 'http://%s' % host
            tmpPath = None
        try:
            jobMonitor = monitor.waitForJob(self.client, jobId, uri)
            return not self.client.getJob(jobId, withTroves=False).isFailed()
        finally:
            if tmpPath:
                os.remove(tmpPath)

    def startChrootSession(self, jobId, troveSpec, command, 
                           superUser=False, chrootHost=None, chrootPath=None):
        job = self.client.getJob(jobId, withTroves=False)
        newTroveSpec = cmdutil.parseTroveSpec(troveSpec)
        newTroveSpec = (newTroveSpec[0].split(':')[0] + ':source',) + newTroveSpec[1:]
        troveTups = job.findTrovesWithContext(None, [newTroveSpec])[newTroveSpec]
        if len(troveTups) > 1:
            err = ['%s matches more than one trove:']
            for troveTup in troveTups:
                err.append('  %s=%s[%s]{%s}' % troveTup)
            raise RmakeError('\n'.join(err))
        troveTup = troveTups[0]
        chrootConnection = self.client.connectToChroot(jobId, troveTup,
                                                       command,
                                                       superUser=superUser,
                                                       chrootHost=chrootHost, 
                                                       chrootPath=chrootPath)
        chrootConnection.interact()

    def archiveChroot(self, host, chrootPath, newPath=None):
        if newPath is None:
            newPath = chrootPath
        self.client.archiveChroot(host, chrootPath, newPath)
        print "Chroot moved to %s" % newPath

    def deleteChroot(self, host, chrootPath):
        self.client.deleteChroot(host, chrootPath)
        print "Chroot %s deleted" % chrootPath

    def deleteAllChroots(self):
        self.client.deleteAllChroots()
        print "Chroots deleted"

    def listChroots(self):
        return self.client.listChroots()

    def watch(self, jobId, showTroveLogs = False, showBuildLogs = False,
              commit = False, message = None):
        """
            Displays information about a currently running job.  Always displays
            high-level information like "Job building", "Job stopped".  Displays
            state and log information for troves based on options.

            @param jobId: jobId or uuid for a given job.
            @type jobId: int or uuid
            @param showTroveLogs: If True, display trove state log information
            @param showBuildLogs: If True, display build log for troves.
            @param commit: If True, commit job upon completion.
            @return: True if watch returns normally (and commit succeeds, if
            commit requested).
            @rtype: bool
        """
        if self.client.uri.startswith('unix://'):
            fd, tmpPath = tempfile.mkstemp()
            os.close(fd)
            uri = 'unix://' + tmpPath
        else:
            host = socket.gethostname()
            uri = 'http://%s' % host
            tmpPath = None
        try:
            try:
                jobMonitor = monitor.monitorJob(self.client, jobId, uri,
                                                showTroveLogs = showTroveLogs,
                                                showBuildLogs = showBuildLogs,
                                                exitOnFinish=commit)
            except Exception, err:
                if commit:
                    print "Poll interrupted, not committing"
                    print "You can restart commit by running 'rmake watch %s --commit'" % jobId
                raise
            if commit:
                return self.commitJob(jobId, commitWithFailures=False,
                                      message=message)
            return not self.client.getJob(jobId, withTroves=False).isFailed()
        finally:
            if tmpPath:
                os.remove(tmpPath)
    poll = watch # backwards compatibility


