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
import os
import socket
import sys
import time

from optparse import OptionParser

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

from rmake import compat
from rmake import errors
from rmake import plugins
from rmake.build import buildcfg
from rmake.build import buildjob
from rmake.build import imagetrove
from rmake.cmdline import buildcmd
from rmake.cmdline import cmdutil
from rmake.cmdline import commit
from rmake.cmdline import monitor
from rmake.cmdline import query
from rmake.server import client

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
                 guiPassword=False, plugins=None, configureClient=True,
                 clientCert=None):
        if rmakeConfig:
            log.warning('rmakeConfig parameter is now deprecated')
        if not buildConfig:
            buildConfig = buildcfg.BuildConfiguration(True, root)

        if configureClient:
            if uri is None:
                uri = buildConfig.getServerUri()
            if clientCert is None:
                clientCert = buildConfig.clientCert

            self.client = client.rMakeClient(uri, clientCert)

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

    def updateBuildConfig(self, buildConfig=None):
        if buildConfig is None:
            buildConfig = self.buildConfig
        self.client.addRepositoryInfo(buildConfig)

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

    def createRestartJob(self, jobId, troveSpecs=None, updateSpecs=None,
                         excludeSpecs=None, updateConfigKeys=None,
                         clearBuildList=False, clearPrebuiltList=False):
        job = self.client.getJob(jobId, withConfigs=True)
        troveSpecList = []
        oldTroveDict = {}
        configDict = {}
        recurseGroups = job.getMainConfig().recurseGroups
        if not excludeSpecs:
            excludeSpecs = []

        self.updateBuildConfig()
        for contextStr, jobConfig in job.getConfigDict().iteritems():
            if not clearBuildList:
                troveSpecList += [ (x[0], x[1], x[2], contextStr)
                                    for x in jobConfig.buildTroveSpecs ]
            oldTroveDict[contextStr] = [ x.getNameVersionFlavor()
                                         for x in job.iterTroves()
                                         if x.context == contextStr ]
            cfg = copy.deepcopy(self.buildConfig)

            for context in contextStr.split(','):
                if context:
                    if cfg.hasSection(context):
                        cfg.setContext(context)
                    else:
                        log.warning('Context %s used in job %s does not exist' % (context, jobId))
            jobConfig.reposName = self.buildConfig.reposName
            # a bug in how jobConfigs are stored + thawed
            # (related to relative paths) causes :memory: not to get
            # transferred correctly over the wire.  We reset the root
            # to :memory: here since the bugfix is conary based.
            jobConfig.root = ':memory:'
            # make sure we have the necessary user information and
            # repositoryMap info to contact the internal repository
            # (in every context).
            jobConfig.user.extend(cfg.user)
            jobConfig.repositoryMap.update(cfg.repositoryMap)
            jobConfig.entitlement.extend(cfg.entitlement)
            if not updateConfigKeys:
                cfg = jobConfig
            elif 'all' in updateConfigKeys:
                pass
            else:
                for key in updateConfigKeys:
                    if key not in cfg:
                        raise errors.ParseError('Unknown value for updateConfigKeys: "%s"' % key)
                    jobConfig[key] = cfg[key]
                cfg = jobConfig

            for spec in excludeSpecs:
                if isinstance(spec, tuple):
                    spec, context = cmdutil.getSpecStringFromTuple(spec)
                else:
                    spec, context = cmdutil.parseTroveSpecContext(spec)
                if context is None or context == contextStr:
                    cfg.addMatchRule('-%s' % spec)
            configDict[contextStr] = cfg

        mainConfig = configDict['']
        if clearPrebuiltList:
            mainConfig.jobcontext = []
        else:
            mainConfig.jobContext += [jobId]
        if troveSpecs:
            troveSpecList.extend(troveSpecs)
        return self._createBuildJob(troveSpecList, buildConfig=mainConfig,
                                    configDict=configDict,
                                    recurseGroups=recurseGroups,
                                    updateSpecs=updateSpecs,
                                    oldTroveDict=oldTroveDict)

    def displayJob(self, job, quiet=False):
        verbose = log.getVerbosity() <= log.DEBUG
        return buildcmd.displayBuildInfo(job, verbose=verbose,
                                         quiet=quiet)

    def buildJob(self, job, quiet=False):
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
        else:
            print jobId
        return jobId

    def createBuildJob(self, troveSpecList, limitToHosts=None,
                       limitToLabels=None, recurseGroups=False,
                       buildConfig=None, matchSpecs=None, rebuild=False):
        # added to limit api for createBuildJob to the bits that should
        # be passed in from the front end.
        return self._createBuildJob(troveSpecList, limitToHosts=limitToHosts,
                                    limitToLabels=limitToLabels,
                                    recurseGroups=recurseGroups,
                                    buildConfig=buildConfig,
                                    matchSpecs=matchSpecs,
                                    rebuild=rebuild)

    def _createBuildJob(self, troveSpecList, limitToHosts=None,
                        limitToLabels=None, recurseGroups=False,
                        buildConfig=None, configDict=None, matchSpecs=None,
                        oldTroveDict=None, updateSpecs=None,
                        rebuild=False):
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
        self.updateBuildConfig(buildConfig=buildConfig)
        conaryClient = self.getConaryClient(buildConfig)

        job = buildcmd.getBuildJob(buildConfig,
                                   conaryClient,
                                   troveSpecList,
                                   recurseGroups=recurseGroups,
                                   configDict=configDict,
                                   updateSpecs=updateSpecs,
                                   oldTroveDict=oldTroveDict,
                                   rebuild=rebuild)
        conaryClient.close()
        conaryClient.db.close()
        return job

    def loadJobFromFile(self, loadPath):
        job = buildjob.BuildJob.loadFromFile(loadPath)
        for cfg in job.iterConfigList():
            cfg.repositoryMap.update(self.buildConfig.repositoryMap)
            cfg.user.extend(self.buildConfig.user)
        return job

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
                   sourceOnly=False, updateRecipes=True, excludeSpecs=None,
                   writeToFile=None):
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
            @param writeToFile: if set to a path, the changeset is written to
            that path instead of committed to the repository (Advanced)
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
        if excludeSpecs:
            excludeSpecs = [ cmdutil.parseTroveSpec(x) for x in excludeSpecs ]

        self.client.startCommit(jobIds)
        try:
            succeeded, data = commit.commitJobs(self.getConaryClient(), jobs,
                                   self.buildConfig.reposName, message,
                                   commitOutdatedSources=commitOutdatedSources,
                                   sourceOnly=sourceOnly,
                                   excludeSpecs=excludeSpecs,
                                   writeToFile=writeToFile)
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
            recipes = list(set(recipes))
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
        jobMonitor = monitor.waitForJob(self.client, jobId)
        return not self.client.getJob(jobId, withTroves=False).isFailed()

    def startChrootSession(self, jobId, troveSpec, command, 
                           superUser=False, chrootHost=None, chrootPath=None):
        job = self.client.getJob(jobId, withTroves=False)
        if not troveSpec:
            troveTups = list(job.iterTroveList(True))
            if len(troveTups) > 1:
                raise errors.RmakeError('job has more than one trove in it, must specify trovespec to chroot into')

        else:
            newTroveSpec = cmdutil.parseTroveSpec(troveSpec)
            newTroveSpec = (newTroveSpec[0].split(':')[0] + ':source',) + newTroveSpec[1:]
            troveTups = job.findTrovesWithContext(None, [newTroveSpec])[newTroveSpec]
            if len(troveTups) > 1:
                err = ['%s matches more than one trove:' % troveSpec]
                for troveTup in troveTups:
                    err.append('  %s=%s[%s]{%s}' % troveTup)
                raise errors.RmakeError('\n'.join(err))
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
        try:
            jobMonitor = monitor.monitorJob(self.client, jobId,
                                            showTroveDetails = showTroveLogs,
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
    poll = watch # backwards compatibility

    def buildTroves(self, *args, **kw):
        """
            Backwards compatibility interface.
        """
        infoOnly = kw.pop('infoOnly', False)
        quiet = kw.pop('quiet', False)
        job = self.createBuildJob(*args, **kw)
        if infoOnly:
            self.displayJob(job, quiet=quiet)
        else:
            return self.buildJob(job, quiet=quiet)

    def restartJob(self, *args, **kw):
        """
            Backwards compatibility interface.
        """
        infoOnly = kw.pop('infoOnly', False)
        quiet = kw.pop('quiet', False)
        job = self.createRestartJob(*args, **kw)
        if infoOnly:
            self.displayJob(job, quiet=quiet)
        else:
            return self.buildJob(job, quiet=quiet)

    def displayJobInfo(self, jobId, proxy, out=sys.stdout):
        """
        Display the info and logs for a given job.
        """
        query.displayJobInfo(client=proxy,
                             jobId=jobId,
                             troveSpecs=[],
                             displayTroves=False,
                             displayDetails=False,
                             showLogs=True,
                             showBuildLogs=True,
                             showFullVersions=False,
                             showFullFlavors=False,
                             showLabels=False,
                             showTracebacks=False,
                             showConfig=False,
                             jobLimit=20,
                             activeOnly=False,
                             out=out)

    def createImageJob(self, productName, imageList):
        allTroveSpecs = {}
        finalImageList = []
        for image in imageList:
            image = list(image)
            if len(image) < 4:
                image.append('')
            # Make it easy to append more parameters extensibly later
            image = image[0:4]
            finalImageList.append(image)

        for troveSpec, imageType, imageOptions, buildName in finalImageList:
            if isinstance(troveSpec, str):
                troveSpec = cmdline.parseTroveSpec(troveSpec)
            allTroveSpecs.setdefault(troveSpec, []).append((imageType, 
                                                            buildName,
                                                            imageOptions))
        cfg = self.buildConfig
        cfg.initializeFlavors()
        repos = self.getRepos()
        results = repos.findTroves(cfg.buildLabel, allTroveSpecs, 
                                   cfg.buildFlavor)

        def getContextName(buildName):
            return buildName.replace(' ', '_')

        contextCache = set()

        i = 1
        job = buildjob.BuildJob()
        for troveSpec, troveTupList in results.iteritems():
            for imageType, buildName, imageOptions in allTroveSpecs[troveSpec]:
                for name, version, flavor in troveTupList:
                    context = getContextName(buildName)
                    while not context or context in contextCache:
                        if buildName:
                            context = '%s_(%d)' %(context, i)
                        else:
                            context = 'Image_%d' %i
                        i += 1
                    contextCache.add(context)
                    imageTrove = imagetrove.ImageTrove(None, 
                                                       name, version, flavor,
                                                       context=context)
                    imageTrove.setImageType(imageType)
                    imageTrove.setImageOptions(imageOptions)
                    imageTrove.setProductName(productName)
                    imageTrove.setBuildName(buildName)
                    job.setTroveConfig(imageTrove, cfg)
                    job.addTrove(name, version, flavor, context, imageTrove)
        job.setMainConfig(cfg)
        return job
