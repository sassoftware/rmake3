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
import sys
import tempfile
import time

from conary import conarycfg
from conary import conaryclient
from conary.conaryclient import cmdline
from conary import state
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
from rmake.server import servercfg
from rmake.server import client
from rmake import compat
from rmake import plugins

class rMakeHelper(object):
    """
    Client that contains most of the behavior available from the command line.

    This client wraps around the low-level rMake Server client to provide
    functionality that crosses client/server boundaries.

    example:
        > rmakeConfig = servercfg.rMakeConfiguration(readConfigFiles=True)
        > h = rMakeHelper(rmakeConfig.getServerUri(), rmakeConfig=rmakeConfig);
        > jobId = h.buildTroves('foo.recipe')
        > h.waitForJob(jobId)
        > if h.getJob(jobId).isPassed(): print "Foo recipe built!"
        > h.commitJob(jobId, message='Updated foo source component')

    @param uri: location to rmake server or rMake Server instance object.
    @type uri: string that starts with http, https, or unix://, or rMakeServer
    instance.
    @param rmakeConfig: Server Configuration
    @type rmakeConfig: rmake.server.servercfg.rMakeConfiguration instance
    (or None to read from filesystem)
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
        if not rmakeConfig:
            rmakeConfig = servercfg.rMakeConfiguration(True)

        if not buildConfig:
            buildConfig = buildcfg.BuildConfiguration(True, root)
            if conaryConfig:
                buildConfig.useConaryConfig(conaryConfig)

        if uri is None:
            uri = rmakeConfig.getServerUri()

        self.client = client.rMakeClient(uri)

        # this should use extend but extend used to be broken when
        # there were multiple entries
        for info in reversed(rmakeConfig.user):
            buildConfig.user.append(info)
        buildConfig.initializeFlavors()
        use.setBuildFlagsFromFlavor(None, buildConfig.buildFlavor, error=False)

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
        self.rmakeConfig = rmakeConfig
        self.buildConfig.setServerConfig(rmakeConfig)
        self.repos = self.getRepos()
        self.plugins = plugins

    def getConaryClient(self, buildConfig=None):
        if buildConfig is None:
            buildConfig = self.buildConfig
        buildConfig.setServerConfig(self.rmakeConfig)
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
        self.buildConfig.setDisplayOptions(hidePasswords=hidePasswords,
                                           prettyPrint=prettyPrint)
        self.buildConfig.display()


    def restartJob(self, jobId, troveSpecs=None):
        jobConfig = self.client.getJobConfig(jobId)
        troveSpecList = jobConfig.buildTroveSpecs
        if troveSpecs:
            troveSpecList.extend(troveSpecs)

        # FIXME: how do we determine what parts of the jobConfig get
        # overridden
        buildConfig = copy.deepcopy(self.buildConfig)
        buildConfig.jobContext = jobConfig.jobContext + [jobId]
        buildConfig.flavor = jobConfig.flavor
        buildConfig.buildFlavor = jobConfig.buildFlavor
        buildConfig.resolveTroves = jobConfig.resolveTroves
        buildConfig.resolveTrovesOnly = jobConfig.resolveTrovesOnly
        buildConfig.installLabelPath = jobConfig.installLabelPath
        return self.buildTroves(troveSpecList, buildConfig=buildConfig)

    def buildTroves(self, troveSpecList,
                    limitToHosts=None, recurseGroups=False, buildConfig=None):
        if buildConfig is None:
            buildConfig = self.buildConfig
        toBuild = buildcmd.getTrovesToBuild(self.getConaryClient(buildConfig),
                                            troveSpecList,
                                            limitToHosts=limitToHosts,
                                            recurseGroups=recurseGroups)

        jobId = self.client.buildTroves(toBuild, buildConfig)
        print 'Added Job %s' % jobId
        for (n,v,f) in sorted(toBuild):
            if f is not None and not f.isEmpty():
                f = '[%s]' % f
            else:
                f = ''
            print '  %s=%s/%s%s' % (n, v.trailingLabel(), v.trailingRevision(), f)

        return jobId

    def stopJob(self, jobId):
        """
            Stops the given job.

            @param jobId: jobId to stop
            @type jobId: int or uuid
            @raise: rMakeError: If job is already stopped.
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
        for troveTup in job.iterTroveList():
            trove = job.getTrove(*troveTup)
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
        cs = self.repos.createChangeSet(jobList, recurse=False,
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
        for troveTup in job.iterTroveList():
            trove = job.getTrove(*troveTup)
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
        self.repos.createChangeSetFile(jobList, path, recurse=recurse,
                                       primaryTroveList=primaryTroveList)
        return True

    def commitJobs(self, jobIds, message=None, commitOutdatedSources=False,
                   commitWithFailures=True, waitForJob=False,
                   sourceOnly=False):
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
        jobs = self.client.getJobs(jobIds)
        finalJobs = []
        for job in jobs:
            jobId = job.jobId
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

        self.client.startCommit(jobIds)
        try:
            succeeded, data = commit.commitJobs(self.getConaryClient(), jobs,
                                   self.rmakeConfig, message,
                                   commitOutdatedSources=commitOutdatedSources,
                                   sourceOnly=sourceOnly)
            if succeeded:
                def _sortCommitted(tup1, tup2):
                    return cmp((tup1[0].endswith(':source'), tup1),
                               (tup2[0].endswith(':source'), tup2))

                self.client.commitSucceeded(data)

                for jobId, troveTupleDict in sorted(data.iteritems()):
                    print
                    print 'Committed job %s:\n' % jobId,
                    for buildTroveTup, committedList in \
                                            sorted(troveTupleDict.iteritems()):
                        committedList = [ x for x in committedList
                                            if (':' not in x[0]
                                                or x[0].endswith(':source')) ]
                        print '    %s=%s[%s] ->' % buildTroveTup
                        print ''.join('       %s=%s[%s]\n' % x
                                      for x in sorted(committedList,
                                                      _sortCommitted))
                return True
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
        fd, tmpPath = tempfile.mkstemp()
        os.close(fd)
        uri = 'unix:' + tmpPath
        try:
            jobMonitor = monitor.waitForJob(self.client, jobId, uri)
        finally:
            os.remove(tmpPath)

    def startChrootSession(self, host, chroot, command, superUser=False):
        chrootConnection = self.client.connectToChroot(host, chroot,
                                         command, superUser=superUser)
        chrootConnection.interact()

    def archiveChroot(self, host, chrootPath, newPath=None):
        if newPath is None:
            newPath = chrootPath
        self.client.archiveChroot(host, chrootPath, newPath)
        print "Chroot moved to %s" % newPath

    def deleteChroot(self, host, chrootPath):
        self.client.deleteChroot(host, chrootPath)
        print "Chroot %s deleted" % chrootPath

    def listChroots(self):
        return self.client.listChroots()

    def watch(self, jobId, showTroveLogs = False, showBuildLogs = False,
             commit = False):
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
        fd, tmpPath = tempfile.mkstemp()
        os.close(fd)
        uri = 'unix:' + tmpPath
        try:
            try:
                jobMonitor = monitor.monitorJob(self.client, jobId, uri,
                                            showTroveLogs = showTroveLogs,
                                            showBuildLogs = showBuildLogs)
            except Exception, err:
                if commit:
                    print "Poll interrupted, not committing"
                    print "You can restart commit by running 'rmake watch %s --commit'" % jobId
                raise
            if commit:
                return self.commitJob(jobId, commitWithFailures=False)
            return not self.client.getJob(jobId, withTroves=False).isFailed()
        finally:
            os.remove(tmpPath)
    poll = watch # backwards compatibility


