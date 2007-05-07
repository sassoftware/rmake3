#
# Copyright (c) 2006-2007 rPath, Inc.  All rights reserved.
#
import time

from rmake.build import buildjob
from rmake.build import buildtrove
from rmake.lib import apirpc
from rmake.lib.apiutils import thaw, freeze

from rmake.server import server

class rMakeClient(object):
    """
        Client for communicating with rMake servers.

        @param uri: location server you wish to communicate with or server
        object.
        @type uri: URI starting with http, https, or file, OR server instance.
    """
    def __init__(self, uri):
        self.uri = uri
        self.proxy = apirpc.XMLApiProxy(server.rMakeServer, uri)

    def buildTroves(self, troveList, cfg):
        """
            Request to build the given sources and build environment.
            jobId of created job

            @param job: buildJob containing the troves to build and their
            configuration
            @type job: buildJob
            @rtype: int 
            @return: jobId of created job.
            @raise: rMakeError: If server cannot add job.
        """
        job = buildjob.BuildJob()
        troveList = [ buildtrove.BuildTrove(None, *x) for x in troveList ]
        for trove in troveList:
            job.addTrove(buildTrove=trove, *trove.getNameVersionFlavor())
        job.setMainConfig(cfg)
        return self.buildJob(job)

    def buildJob(self, job):
        return self.proxy.buildTroves(job)

    def stopJob(self, jobId):
        """
            Stops the given job.

            @param jobId: jobId to stop
            @type jobId: int or uuid
            @raise: rMakeError: If job is already stopped.
        """
        return self.proxy.stopJob(jobId)

    def deleteJobs(self, jobIdList):
        """
            Deletes the given jobs.

            @param jobIdList: list of jobIds to delete
            @type jobIdList: int or uuid list
        """
        return self.proxy.deleteJobs(jobIdList)

    def listJobs(self):
        """
            Lists all known jobIds

            @return: list of jobIds
        """
        return self.proxy.listJobs()

    def listTrovesByState(self, jobId, state=None):
        """
            Lists troves in a job by state.
            @param jobId: jobId or uuid for job.
            @param state: (optional) state to list troves by.  All states if 
                          left blank.
            @type state: build.buildtrove.TROVE_STATE_* or None

            @return: dict of trove lists by state.
            @rtype: {TROVE_STATE_* : [(name, version, flavor)]} dict.
        """
        if state is None:
            state = ''
        results = self.proxy.listTrovesByState(jobId, state)
        return dict((x[0], thaw('troveContextTupleList', x[1])) for x in results)

    def getStatus(self, jobId):
        """
            Return status for job

            @param jobId: jobId or UUID for job.
            @return: current status of job.
            @rtype: build.buildjob.JOB_STATE_*
        """
        return self.proxy.getStatus(jobId)

    def getJobConfig(self, jobId):
        """
            Return the configuration that was used for a job.

            @param jobId: jobId or UUID for job.
            @rtype: BuildConfiguration
        """
        return self.proxy.getJobConfig(jobId)

    def getJobLogs(self, jobId, mark = 0):
        """
            Return state logs for job.

            @param jobId: jobId or UUID for job.
            @param mark: location in log list to start job logs from.
            @rtype: list of (timeStamp, message, args) tuples
        """
        return self.proxy.getJobLogs(jobId, mark)

    def getTroveLogs(self, jobId, troveTuple, mark = 0):
        """
            Return state logs for trove.

            @param jobId: jobId or UUID for job.
            @param troveTuple: (name, version, flavor) for job.
            @param mark: location in log list to start logs from.
            @rtype: list of (timeStamp, message, args) tuples
        """
        return self.proxy.getTroveLogs(jobId, troveTuple, mark)

    def getTroveBuildLog(self, jobId, troveTuple, mark=0):
        """
            Return build log for trove.

            @param jobId: jobId or UUID for job.
            @param troveTuple: (name, version, flavor) tuple for trove.
            @param mark: location in file to start reading logs from.
            @return: (isBuilding, contents) tuple.  If isBuilding is True,
            more logs may be available later.
            @rtype: (boolean, string) tuple.
        """
        isBuilding, wrappedData, mark = self.proxy.getTroveBuildLog(jobId,
                                                              troveTuple, mark)
        return isBuilding, wrappedData.data, mark

    def getJob(self, jobId, withTroves=True, withConfigs=False):
        """
            Return job instance.
            @param jobId: jobId or UUID for job.
            @param withTroves: (default True) if True, include trove objects
            in job.  Otherwise only include pointers.
            @rtype: build.buildjob.BuildJob
            @raises: JobNotFound if job does not exist.
        """
        return self.getJobs([jobId], withTroves, withConfigs)[0]

    def getJobs(self, jobIds, withTroves=True, withConfigs=False):
        """
            Return job instance.
            @param jobId: jobId or UUID for job.
            @param withTroves: (default True) if True, include trove objects
            in job.  Otherwise only include pointers.
            @rtype: build.buildjob.BuildJob
            @raises: JobNotFound if job does not exist.
        """
        return [ thaw('BuildJob', x)
                 for x in self.proxy.getJobs(jobIds, withTroves, withConfigs) ]

    def listSubscribers(self, jobId):
        """
            Return subscribers for jobId
            @param jobId: jobId or UUID for job.
            @rtype: list of build.subscriber.Subscriber instances.
            @raises: JobNotFound if job does not exist.
        """
        return [ thaw('Subscriber', x)
                  for x in self.proxy.listSubscribers(jobId) ]

    def listChroots(self):
        return [ thaw('Chroot', x)
                  for x in self.proxy.listChroots() ]

    def archiveChroot(self, host, chrootPath, newPath):
        self.proxy.archiveChroot(host, chrootPath, newPath)

    def deleteChroot(self, host, chrootPath):
        self.proxy.deleteChroot(host, chrootPath)

    def deleteAllChroots(self):
        self.proxy.deleteAllChroots()

    def connectToChroot(self, host, chroot, command, superUser=False):
        host, port = self.proxy.startChrootServer(host, chroot, command,
                                                  superUser)
        from rmake.lib import telnetclient
        t = telnetclient.TelnetClient(host, port)
        return t

    def subscribe(self, jobId, subscriber):
        """
            Add subscriber to jobId.
            Subscribers are notified of events that happen to a given job, 
            and can be used to report or act on those events.

            @param jobId: jobId or UUID for job.
            @raises: JobNotFound if job does not exist.
        """
        subscriberId = self.proxy.subscribe(jobId, subscriber)
        subscriber.subscriberId = subscriberId

    def unsubscribe(self, subscriberId):
        """
            Remove subscriber from jobId.

            @param jobId: jobId or UUID for job.
            @raises: JobNotFound if job does not exist.
        """
        self.proxy.unsubscribe(subscriberId)

    def startCommit(self, jobIds):
        """
            Notify server that jobIds are being committed.

            @param jobIds: jobIds or UUIDs for jobs.
            @raises: JobNotFound if one of the jobs does not exist.
        """
        self.proxy.startCommit(jobIds)

    def commitFailed(self, jobIds, message):
        """
            Notify server that the jobs failed to commit due to reason in 
            message.

            @param jobId: jobIds or UUIDs for job.
            @param message: description of failure reason
            @raises: JobNotFound if some of jobs do not exist.
        """
        self.proxy.commitFailed(jobIds, message)

    def commitSucceeded(self, commitMap):
        """
            Notify server that a job failed to commit due to reason in message.

            @param commitMap: jobId -> troveTuple -> binaries
            Mapping from jobId -> build trove -> list of binaries created by
            that build trove.
            @type troveTupleList: {int : {troveTuple : [troveTuple]}} dict.
            @raises: JobNotFound if job does not exist.
        """
        jobIds = []
        finalMap = []
        for jobId, troveMap in commitMap.items():
            troveMap = [ (freeze('troveContextTuple', x[0]),
                          freeze('troveTupleList', x[1]))
                          for x in troveMap.items() ]
            finalMap.append(troveMap)
            jobIds.append(jobId)
        self.proxy.commitSucceeded(jobIds, finalMap)

    def ping(self, seconds=5, hook=None, sleep=0.1):
        """
            Check for availability of server.
            @param seconds: seconds to wait for ping to succeed
            @type seconds: float (default 5)
            @param hook: if not None, a function that is called after every
            ping failure.
            @type hook: function that takes no arguments
            @param sleep: seconds to sleep between each ping attempt.
            @type sleep: float (default 5)
            @return: True if ping succeeds (otherwise raises exception).
            @raise: errors.OpenError if ping fails
        """
        timeSlept = 0
        while timeSlept < seconds:
            try:
                return self.proxy.ping()
            except:
                if timeSlept < seconds:
                    if hook:
                        hook()
                    time.sleep(sleep)
                    timeSlept += sleep
                else:
                    raise


