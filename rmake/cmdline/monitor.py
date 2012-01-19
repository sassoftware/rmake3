#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


import os
import socket
import sys
import tempfile
import time

from rmake.build import buildjob, buildtrove
from rmake.subscribers import xmlrpc

def _getUri(client):
    if not isinstance(client.uri, str) or client.uri.startswith('unix://'):
        fd, tmpPath = tempfile.mkstemp()
        os.close(fd)
        uri = 'unix://' + tmpPath
    else:
        host = socket.gethostname()
        uri = 'http://%s' % host
        tmpPath = None
    return uri, tmpPath

def monitorJob(client, jobId, showTroveDetails=False, showBuildLogs=False,
               exitOnFinish=None, uri=None, serve=True, out=None,
               displayClass=None):
    if not uri:
        uri, tmpPath = _getUri(client)
    else:
        tmpPath = None
    if not displayClass:
        displayClass = JobLogDisplay

    try:
        display = displayClass(client, showBuildLogs=showBuildLogs, out=out,
                               exitOnFinish=exitOnFinish)
        client = client.listenToEvents(uri, jobId, display,
                                       showTroveDetails=showTroveDetails,
                                       serve=serve)
        return client
    finally:
        if serve and tmpPath:
            os.remove(tmpPath)

def waitForJob(client, jobId, uri=None, serve=True):
    if not uri:
        uri, tmpPath = _getUri(client)
    else:
        tmpPath = None
    try:
        display = SilentDisplay(client)
        display._primeOutput(jobId)
        return client.listenToEvents(uri, jobId, display, serve=serve)
    finally:
        if tmpPath:
            os.remove(tmpPath)

class _AbstractDisplay(xmlrpc.BasicXMLRPCStatusSubscriber):
    def __init__(self, client, showBuildLogs=True, out=None,
                 exitOnFinish=True):
        self.client = client
        self.finished = False
        self.exitOnFinish = True # override exitOnFinish setting
        self.showBuildLogs = showBuildLogs
        if not out:
            out = sys.stdout
        self.out = out

    def close(self):
        pass

    def _serveLoopHook(self):
        pass

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

    def _shouldExit(self):
        return self._isFinished() and self.exitOnFinish

    def _primeOutput(self, jobId):
        job = self.client.getJob(jobId, withTroves=False)
        if job.isFinished():
            self._setFinished()


class SilentDisplay(_AbstractDisplay):
    pass


class JobLogDisplay(_AbstractDisplay):

    def __init__(self, client, showBuildLogs=True, out=None,
                 exitOnFinish=None):
        _AbstractDisplay.__init__(self, client, out=out,
            showBuildLogs=showBuildLogs,
            exitOnFinish=exitOnFinish)
        self.buildingTroves = {}

    def _tailBuildLog(self, jobId, troveTuple):
        mark = self.buildingTroves.get((jobId, troveTuple), [0])[0]
        self.buildingTroves[jobId, troveTuple] =  [mark, True]
        self.out.write('Tailing %s build log:\n\n' % troveTuple[0])

    def _stopTailing(self, jobId, troveTuple):
        mark = self.buildingTroves.get((jobId, troveTuple), [0])[0]
        self.buildingTroves[jobId, troveTuple] = [ mark, False ]

    def _serveLoopHook(self):
        if not self.buildingTroves:
            return
        for (jobId, troveTuple), (mark, tail) in self.buildingTroves.items():
            if not tail:
                continue
            try:
                moreData, data, mark = self.client.getTroveBuildLog(jobId,
                                                                    troveTuple,
                                                                    mark)
            except:
                moreData = True
                data = ''
            self.out.write(data)
            if not moreData:
                del self.buildingTroves[jobId, troveTuple]
            else:
                self.buildingTroves[jobId, troveTuple][0] =  mark

    def _jobTrovesSet(self, jobId, troveData):
        self._msg('[%d] - job troves set' % jobId)

    def _jobStateUpdated(self, jobId, state, status):
        _AbstractDisplay._jobStateUpdated(self, jobId, state, status)
        state = buildjob._getStateName(state)
        if self._isFinished():
            self._serveLoopHook()
        self._msg('[%d] - State: %s' % (jobId, state))
        if status:
            self._msg('[%d] - %s' % (jobId, status))

    def _jobLogUpdated(self, jobId, state, status):
        self._msg('[%d] %s' % (jobId, status))

    def _troveStateUpdated(self, (jobId, troveTuple), state, status):
        isBuilding = (state in (buildtrove.TROVE_STATE_BUILDING,
                                buildtrove.TROVE_STATE_RESOLVING))
        state = buildtrove._getStateName(state)
        self._msg('[%d] - %s - State: %s' % (jobId, troveTuple[0], state))
        if status:
            self._msg('[%d] - %s - %s' % (jobId, troveTuple[0], status))
        if isBuilding and self.showBuildLogs:
            self._tailBuildLog(jobId, troveTuple)
        else:
            self._stopTailing(jobId, troveTuple)

    def _troveLogUpdated(self, (jobId, troveTuple), state, status):
        state = buildtrove._getStateName(state)
        self._msg('[%d] - %s - %s' % (jobId, troveTuple[0], status))

    def _trovePreparingChroot(self, (jobId, troveTuple), host, path):
        if host == '_local_':
            msg = 'Chroot at %s' % path
        else:
            msg = 'Chroot at Node %s:%s' % (host, path)
        self._msg('[%d] - %s - %s' % (jobId, troveTuple[0], msg))

    def _primeOutput(self, jobId):
        logMark = 0
        while True:
            newLogs = self.client.getJobLogs(jobId, logMark)
            if not newLogs:
                break
            logMark += len(newLogs)
            for (timeStamp, message, args) in newLogs:
                print '[%s] [%s] - %s' % (timeStamp, jobId, message)

        BUILDING = buildtrove.TROVE_STATE_BUILDING
        troveTups = self.client.listTrovesByState(jobId, BUILDING).get(BUILDING, [])
        for troveTuple in troveTups:
            self._tailBuildLog(jobId, troveTuple)

        _AbstractDisplay._primeOutput(self, jobId)
