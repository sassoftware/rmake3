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
import time

from rmake.lib import apirpc
from rmake.lib.apiutils import thaw

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

    def buildTroves(self, sourceTroveTups, buildEnv):
        """
            Request to build the given sources and build environment.
            jobId of created job

            @param sourceTroveTups: list of source troves to build.
            @type sourceTroveTups: List of (name, version, flavor) tuples, where
            the flavor indicated the flavor to build the name=version source 
            trove.
            @param buildEnv: build configuration to use when buildings
            @type buildEnv: BuildConfiguration object.
            @rtype: int 
            @return: jobId of created job.
            @raise: rMakeError: If server cannot add job.
        """
        return self.proxy.buildTroves(sourceTroveTups, buildEnv)

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
        return dict((x[0], thaw('troveTupleList', x[1])) for x in results)

    def getStatus(self, jobId):
        """
            Return status for job

            @param jobId: jobId or UUID for job.
            @return: current status of job.
            @rtype: build.buildjob.JOB_STATE_*
        """
        return self.proxy.getStatus(jobId)

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
        isBuilding, wrappedData = self.proxy.getTroveBuildLog(jobId,
                                                              troveTuple, mark)
        return isBuilding, wrappedData.data

    def getJob(self, jobId, withTroves=True):
        """
            Return job instance.
            @param jobId: jobId or UUID for job.
            @param withTroves: (default True) if True, include trove objects
            in job.  Otherwise only include pointers.
            @rtype: build.buildjob.BuildJob
            @raises: JobNotFound if job does not exist.
        """
        return self.getJobs([jobId], withTroves)[0]

    def getJobs(self, jobIds, withTroves=True):
        """
            Return job instance.
            @param jobId: jobId or UUID for job.
            @param withTroves: (default True) if True, include trove objects
            in job.  Otherwise only include pointers.
            @rtype: build.buildjob.BuildJob
            @raises: JobNotFound if job does not exist.
        """
        return [ thaw('BuildJob', x)
                 for x in self.proxy.getJobs(jobIds, withTroves) ]

    def listSubscribers(self, jobId):
        """
            Return subscribers for jobId
            @param jobId: jobId or UUID for job.
            @rtype: list of build.subscriber.Subscriber instances.
            @raises: JobNotFound if job does not exist.
        """
        return [ thaw('Subscriber', x)
                  for x in self.proxy.listSubscribers(jobId) ]

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

    def startCommit(self, jobId):
        """
            Notify server that jobId is being committed.

            @param jobId: jobId or UUID for job.
            @raises: JobNotFound if job does not exist.
        """
        self.proxy.startCommit(jobId)

    def commitFailed(self, jobId, message):
        """
            Notify server that a job failed to commit due to reason in message.

            @param jobId: jobId or UUID for job.
            @param message: description of failure reason
            @raises: JobNotFound if job does not exist.
        """
        self.proxy.commitFailed(jobId, message)

    def commitSucceeded(self, jobId, troveTupleList):
        """
            Notify server that a job failed to commit due to reason in message.

            @param jobId: jobId or UUID for job.
            @param troveTupleList: binaries created by committing this job.
            @type troveTupleList: list of (name, version, flavor) tuples.
            @raises: JobNotFound if job does not exist.
        """
        self.proxy.commitSucceeded(jobId, troveTupleList)

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


