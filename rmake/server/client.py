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

from rmake.lib import apirpc
from rmake.lib.apiutils import thaw

from rmake.server import server

class rMakeClient(object):
    def __init__(self, uri):
        self.uri = uri
        self.proxy = apirpc.ApiProxy(rMakeServer, uri)

    def buildTroves(self, sourceTroveTups, buildEnv):
        return self.proxy.buildTroves(sourceTroveTups, buildEnv)

    def stopJob(self, jobId):
        return self.proxy.stopJob(jobId)

    def deleteJobs(self, jobIdList):
        return self.proxy.deleteJobs(jobIdList)

    def listJobs(self):
        return self.proxy.listJobs()

    def listTrovesByState(self, jobId, state=None):
        if state is None:
            state = ''
        results = self.proxy.listTrovesByState(jobId, state)
        return dict((x[0], thaw('troveTupleList', x[1])) for x in results)

    def getStatus(self, jobId):
        return self.proxy.getStatus(jobId)

    def getJobLogs(self, jobId, mark = 0):
        return self.proxy.getJobLogs(jobId, mark)

    def getTroveLogs(self, jobId, troveTuple, mark = 0):
        return self.proxy.getTroveLogs(jobId, troveTuple, mark)

    def getTroveBuildLog(self, jobId, troveTuple, mark=0):
        isBuilding, wrappedData = self.proxy.getTroveBuildLog(jobId,
                                                              troveTuple, mark)
        return isBuilding, wrappedData.data

    def getJob(self, jobId, withTroves=True):
        return self.getJobs([jobId], withTroves)[0]

    def getJobs(self, jobIds, withTroves=True):
        return [ thaw('BuildJob', x)
                 for x in self.proxy.getJobs(jobIds, withTroves) ]

    def listSubscribers(self, jobId):
        return [ thaw('Subscriber', x)
                  for x in self.proxy.listSubscribers(jobId) ]

    def listSubscribersByUri(self, jobId, uri):
        return [ thaw('Subscriber', x)
                  for x in self.proxy.listSubscribersByUri(jobId, uri) ]

    def subscribe(self, jobId, subscriber):
        subscriberId = self.proxy.subscribe(jobId, subscriber)
        subscriber.subscriberId = subscriberId

    def unsubscribe(self, subscriberId):
        self.proxy.unsubscribe(subscriberId)

    def startCommit(self, jobId):
        self.proxy.startCommit(jobId)

    def commitFailed(self, jobId, message):
        self.proxy.commitFailed(jobId, message)

    def commitSucceeded(self, jobId, troveTupleList):
        self.proxy.commitSucceeded(jobId, troveTupleList)

    def ping(self, seconds=5, hook=None, sleep=0.1):
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


