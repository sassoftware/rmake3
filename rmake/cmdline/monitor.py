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
import select
import sys
import time

from conary.lib import util

from rmake.build import buildjob, buildtrove
from rmake.lib.apiutils import thaw, freeze
from rmake.lib import auth, localrpc
from rmake import subscribers
from rmake.subscribers import xmlrpc


def monitorJob(client, jobId, uri, showTroveLogs=False, showBuildLogs=False):
    receiver = XMLRPCJobLogReceiver(uri, client, showTroveLogs=showTroveLogs, 
                                    showBuildLogs=showBuildLogs)
    receiver.subscribe(jobId)
    receiver.serve_forever()

def waitForJob(client, jobId, uri):
    receiver = XMLRPCJobLogReceiver(uri, client, displayClass=SilentDisplay)
    receiver.subscribe(jobId)
    receiver.serve_forever()

class _AbstractDisplay(xmlrpc.BasicXMLRPCStatusSubscriber):
    def __init__(self, client, showBuildLogs=True, out=None):
        self.client = client
        self.finished = False
        self.showBuildLogs = showBuildLogs
        if not out:
            out = sys.stdout
        self.out = out

    def _msg(self, msg, *args):
        self.out.write('[%s] %s\n' % (time.strftime('%X'), msg))
        self.out.flush()

    def _jobStateUpdated(self, jobId, state, status):
        isFinished = (state in (buildjob.JOB_STATE_FAILED,
                                buildjob.JOB_STATE_BUILT))
        if isFinished:
            self._setFinished()

    def _setFinished(self):
        self.finished = True

    def _isFinished(self):
        return self.finished

    def _primeOutput(self, client, jobId):
        job = client.getJob(jobId, withTroves=False)
        if job.isFinished():
            self._setFinished()

class SilentDisplay(_AbstractDisplay):
    def _updateBuildLog(self):
        pass

class JobLogDisplay(_AbstractDisplay):

    def __init__(self, client, showBuildLogs=True, out=None):
        _AbstractDisplay.__init__(self, client, out)
        self.showBuildLogs = showBuildLogs
        self.buildingTrove = None

    def _tailBuildLog(self, jobId, troveTuple):
        self.buildingTrove = (jobId, troveTuple, 0)
        self.out.write('Tailing %s build log:\n\n' % troveTuple[0])

    def _updateBuildLog(self):
        if not self.buildingTrove:
            return

        jobId, troveTuple, mark = self.buildingTrove

        moreData = True

        moreData, data = self.client.getTroveBuildLog(jobId, troveTuple, mark)
        mark += len(data)
        self.out.write(data)
        if not moreData:
            self.buildingTrove = None
        else:
            self.buildingTrove = (jobId, troveTuple, mark)

    def _jobTrovesSet(self, jobId, troveData):
        self._msg('[%d] - job troves set' % jobId)

    def _jobStateUpdated(self, jobId, state, status):
        _AbstractDisplay._jobStateUpdated(self, jobId, state, status)
        state = buildjob._getStateName(state)
        self._msg('[%d] - State: %s' % (jobId, state))
        if status:
            self._msg('[%d] - %s' % (jobId, status))

    def _jobLogUpdated(self, jobId, state, status):
        self._msg('[%d] %s' % (jobId, status))

    def _troveStateUpdated(self, (jobId, troveTuple), state, status):
        isBuilding = (state == buildtrove.TROVE_STATE_BUILDING)
        state = buildtrove._getStateName(state)
        self._msg('[%d] %s - State: %s' % (jobId, troveTuple[0], state))
        if status:
            self._msg('[%d] %s - %s' % (jobId, troveTuple[0], status))
        if isBuilding and self.showBuildLogs:
            self._tailBuildLog(jobId, troveTuple)

    def _troveLogUpdated(self, (jobId, troveTuple), state, status):
        state = buildtrove._getStateName(state)
        self._msg('[%d] - %s - %s' % (jobId, troveTuple[0], status))

    def _primeOutput(self, client, jobId):
        logMark = 0
        while True:
            newLogs = client.getJobLogs(jobId, logMark)
            if not newLogs:
                break
            logMark += len(newLogs)
            for (timeStamp, message, args) in newLogs:
                print '[%s] [%s] - %s' % (timeStamp, jobId, message)

        BUILDING = buildtrove.TROVE_STATE_BUILDING
        troveTups = client.listTrovesByState(jobId, BUILDING).get(BUILDING, [])
        for troveTuple in troveTups:
            self._tailBuildLog(jobId, troveTuple)

        _AbstractDisplay._primeOutput(self, client, jobId)

class XMLRPCJobLogReceiver(object):
    def __init__(self, uri=None, client=None, displayClass=JobLogDisplay,
                 showTroveLogs=False, showBuildLogs=False, out=None):
        self.uri = uri
        self.client = client
        self.showTroveLogs = showTroveLogs
        self.showBuildLogs = showBuildLogs
        serverObj = None

        if uri:
            if isinstance(uri, str):
                import urllib
                type, url = urllib.splittype(uri)
                if type == 'unix':
                    util.removeIfExists(url)
                    serverObj = localrpc.UnixDomainXMLRPCServer(url,
                                                       logRequests=False)
                elif type == 'http':
                    # path is ignored with simple server.
                    host, path = urllib.splithost(url)
                    if ':' in host:
                        host, port = urllib.splitport(host)
                        port = int(port)
                    else:
                        port = 80
                    serverObj = auth.ReusableXMLRPCServer((host, port),
                                  requestHandler=auth.QuietXMLRPCRequestHandler)
                else:
                    raise NotImplmentedError
            else:
                serverObj = uri

        self.server = serverObj
        self.display = displayClass(self.client, showBuildLogs=showBuildLogs, 
                                    out=out)

        if serverObj:
            serverObj.register_instance(self)

    def subscribe(self, jobId):
        subscriber = subscribers.SubscriberFactory('monitor_', 'xmlrpc', self.uri)
        subscriber.watchEvent('JOB_STATE_UPDATED')
        subscriber.watchEvent('JOB_LOG_UPDATED')
        if self.showTroveLogs:
            subscriber.watchEvent('TROVE_STATE_UPDATED')
            subscriber.watchEvent('TROVE_LOG_UPDATED')
        self.jobId = jobId
        self.subscriber = subscriber
        self.client.subscribe(jobId, subscriber)

        self.display._primeOutput(self.client, jobId)


    def serve_forever(self):
        try:
            while True:
                self.handleRequestIfReady(1)
                self._serveLoopHook()
                if self.display._isFinished():
                    break
        finally:
            self.unsubscribe()

    def handleRequestIfReady(self, sleepTime=0.1):
        ready, _, _ = select.select([self.server], [], [], sleepTime)
        if ready:
            self.server.handle_request()

    def _serveLoopHook(self):
        self.display._updateBuildLog()

    def unsubscribe(self):
        if self.client:
            self.client.unsubscribe(self.subscriber.subscriberId)

    def _dispatch(self, methodname, args):
        if methodname.startswith('_'):
            raise NoSuchMethodError(methodname)
        else:
            rv = getattr(self.display, methodname)(*args)
            if rv is None:
                return ''

