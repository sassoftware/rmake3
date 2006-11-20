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
Client that contains most of the behavior available from the command line.

This client wraps around the low-level rMake Server client to provide
functionality that crosses client/server boundaries.
"""

import itertools
from optparse import OptionParser
import os
import sys
import tempfile
import time

from conary import conarycfg
from conary import conaryclient
from conary import state
from conary.build import use
from conary.deps import deps
from conary.lib import log
from conary.lib import options

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


    def __init__(self, uri=None, rmakeConfig=None, buildConfig=None, root='/',
                 guiPassword=False):
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

        self.conaryclient = conaryclient.ConaryClient(buildConfig,
                                                      passwordPrompter=pwPrompt)
        self.repos = self.conaryclient.getRepos()
        self.buildConfig = buildConfig
        self.rmakeConfig = rmakeConfig
        self.buildConfig.setServerConfig(rmakeConfig)



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

    def buildTroves(self, troveSpecList,
                    limitToHosts=None, recurseGroups=False):
        """
            Display the current build configuration for this helper.

            @param hidePasswords: If True, display <pasword> instead of
            the password in the output.
            @param prettyPrint: If True, print output in human-readable format
            that may not be parsable by a config reader.  If False, the
            configuration output should be valid as input for a configuration
            reader.
        """
        toBuild = buildcmd.getTrovesToBuild(self.conaryclient,
                                            troveSpecList,
                                            limitToHosts=limitToHosts)

        jobId = self.client.buildTroves(toBuild, self.buildConfig)
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

    def createChangeSet(self, jobId):
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
        jobList = [(x[0], (None, None), (x[1], x[2]), True) for x in binTroves]
        primaryTroveList = [ x for x in binTroves if ':' not in x[0]]
        cs = self.repos.createChangeSet(jobList, recurse=False,
                                        primaryTroveList=primaryTroveList)
        return cs

    def createChangeSetFile(self, jobId, path):
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
        jobList = [(x[0], (None, None), (x[1], x[2]), True) for x in binTroves]
        primaryTroveList = [ x for x in binTroves if ':' not in x[0]]
        self.repos.createChangeSetFile(jobList, path, recurse=False, 
                                       primaryTroveList=primaryTroveList)
        return True

    def commitJob(self, jobId, message=None, commitOutdatedSources=False,
                  commitWithFailures=True, waitForJob=False,
                  sourceOnly=False):
        """
            Commits a job.

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
        job = self.client.getJob(jobId)
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
            log.error('This job is not yet finished')
            return False
        if job.isFailed() and not commitWithFailures:
            log.error('This job has failures, not committing')
            return False
        if not list(job.iterBuiltTroves()):
            log.error('This job has no built troves to commit')
            return False
        self.client.startCommit(jobId)
        try:
            succeeded, data = commit.commitJob(self.conaryclient, job,
                                   self.rmakeConfig, message,
                                   commitOutdatedSources=commitOutdatedSources,
                                   sourceOnly=sourceOnly)
            if succeeded:
                self.client.commitSucceeded(jobId, data)
                print 'Committed:\n',
                print ''.join('    %s=%s[%s]\n' % x for x in sorted(data)),
                return True
            else:
                self.client.commitFailed(jobId, data)
                log.error(data)
                return False
        except Exception, err:
            self.client.commitFailed(jobId, str(err))
            log.error(err)
            return False

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

    def poll(self, jobId, showTroveLogs = False, showBuildLogs = False,
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
            @return: True if poll returns normally (and commit succeeds, if
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
                    print "You can restart commit by running 'rmake poll %s --commit'" % jobId
                raise
            if commit:
                return self.commitJob(jobId, commitWithFailures=False)
            return True
        finally:
            os.remove(tmpPath)
