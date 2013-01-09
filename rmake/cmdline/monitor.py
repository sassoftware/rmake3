#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


"""
Watch a running build job and output changes to the screen.
"""


import fcntl
import os
import select
import socket
import sys
import tempfile
import termios
import time
import traceback

from rmake import errors
from rmake.build import buildjob, buildtrove
from rmake.cmdline import query


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

class _AbstractDisplay(object):#xmlrpc.BasicXMLRPCStatusSubscriber):
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
        state = buildjob.stateNames[state]
        if self._isFinished():
            self._serveLoopHook()
        self._msg('[%d] - State: %s' % (jobId, state))
        if status:
            self._msg('[%d] - %s' % (jobId, status))

    def _jobLogUpdated(self, jobId, state, status):
        self._msg('[%d] %s' % (jobId, status))

    def _troveStateUpdated(self, (jobId, troveTuple), state, status):
        isBuilding = (state in (buildtrove.TroveState.BUILDING,
                                buildtrove.TroveState.RESOLVING))
        state = buildtrove.stateNames[state]
        self._msg('[%d] - %s - State: %s' % (jobId, troveTuple[0], state))
        if status:
            self._msg('[%d] - %s - %s' % (jobId, troveTuple[0], status))
        if isBuilding and self.showBuildLogs:
            self._tailBuildLog(jobId, troveTuple)
        else:
            self._stopTailing(jobId, troveTuple)

    def _troveLogUpdated(self, (jobId, troveTuple), state, status):
        state = buildtrove.stateNames[state]
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

        BUILDING = buildtrove.TroveState.BUILDING
        troveTups = self.client.listTrovesByState(jobId, BUILDING).get(BUILDING, [])
        for troveTuple in troveTups:
            self._tailBuildLog(jobId, troveTuple)

        _AbstractDisplay._primeOutput(self, jobId)

def set_raw_mode():
    fd = sys.stdin.fileno()
    oldTerm = termios.tcgetattr(fd)
    newattr = termios.tcgetattr(fd)
    newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSANOW, newattr)
    oldFlags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, oldFlags | os.O_NONBLOCK)
    return oldTerm, oldFlags

def restore_terminal(oldTerm, oldFlags):
    fd = sys.stdin.fileno()
    if oldTerm:
        termios.tcsetattr(fd, termios.TCSAFLUSH, oldTerm)
    if oldFlags:
        fcntl.fcntl(fd, fcntl.F_SETFL, oldFlags)


class _AbstractDisplay(object):#xmlrpc.BasicXMLRPCStatusSubscriber):
    def __init__(self, client, showBuildLogs=True, out=None):
        self.client = client
        self.finished = False
        self.showBuildLogs = showBuildLogs
        self.troveStates = {}
        self.troveIndex = None
        self.troveDislay = False
        self.out = OutBuffer(out)

    def close(self):
        pass

    def _msg(self, msg, *args):
        self.out.write('\r[%s] %s\n' % (time.strftime('%X'), msg))
        self.out.write('(h for help)>')
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

    def _dispatch(self, methodname, (callData, responseHandler, args)):
        if methodname.startswith('_'):
            raise NoSuchMethodError(methodname)
        else:
            responseHandler.sendResponse('')
            getattr(self, methodname)(*args)

class SilentDisplay(_AbstractDisplay):
    def _updateBuildLog(self):
        pass

class JobLogDisplay(_AbstractDisplay):

    def __init__(self, client, state, out=None):
        _AbstractDisplay.__init__(self, client, out)
        self.troveToWatch = None
        self.watchTroves = False
        self.buildingTroves = {}
        self.state = state
        self.lastLen = 0
        self.promptFormat = '%(jobId)s %(name)s%(context)s - %(state)s - (%(tailing)s) ([h]elp)>'
        self.updatePrompt()

    def close(self):
        self.out.write('\n')
        self.out.flush()

    def _msg(self, msg, *args):
        self.erasePrompt()
        self.out.write('[%s] %s\n' % (time.strftime('%X'), msg))
        self.writePrompt()

    def updatePrompt(self):
        if self.troveToWatch:
            if self.troveToWatch not in self.state.troves:
                self.troveToWatch = self.state.troves[0]
            state = self.state.getTroveState(*self.troveToWatch)
            state = buildtrove.stateNames[state]
            name = self.troveToWatch[1][0].split(':', 1)[0] # remove :source
            context = self.troveToWatch[1][3]
            d = dict(jobId=self.troveToWatch[0], name=name, state=state,
                     context=(context and '{%s}' % context or ''))
        else:
            d = dict(jobId='(None)', name='(None)', state='', context='')
        if not self.state.jobActive():
            tailing = 'Job %s' % self.state.getJobStateName()
        elif self.watchTroves:
            tailing = 'Details on'
        else:
            tailing = 'Details off'
        d['tailing'] = tailing
        self.prompt = self.promptFormat % d
        self.erasePrompt()
        self.writePrompt()

    def erasePrompt(self):
        self.out.write('\r%s\r' % (' '*self.lastLen))

    def writePrompt(self):
        self.out.write(self.prompt)
        self.lastLen = len(self.prompt)
        self.out.flush()

    def setWatchTroves(self, watchTroves=True):
        self.watchTroves = watchTroves
        self.updatePrompt()

    def getWatchTroves(self):
        return self.watchTroves

    def setTroveToWatch(self, jobId, troveTuple):
        self.troveToWatch = jobId, troveTuple
        self.updatePrompt()

    def _watchTrove(self, jobId, troveTuple):
        if not self.watchTroves:
            return False
        return self.troveToWatch == (jobId, troveTuple)

    def displayTroveStates(self):
        if not self.troveToWatch:
            return
        self.erasePrompt()
        job = self.client.getJob(self.troveToWatch[0])
        query.displayTrovesByState(job, out=self.out)
        self.writePrompt()

    def setPrompt(self, promptFormat):
        self.promptFormat = promptFormat
        self.updatePrompt()

    def updateBuildLog(self, jobId, troveTuple):
        if not self._watchTrove(jobId, troveTuple):
            return
        mark = self.getMark(jobId, troveTuple)
        if mark is None:
            return
        try:
            moreData, data, mark = self.client.getTroveBuildLog(jobId,
                                                                troveTuple,
                                                                mark)
        except:
            return
        if data and data != '\n': 
            self.erasePrompt()
            if data[0] == '\n':
                # we've already got a \n because we've cleared
                # the prompt.
                data = data[1:]
            self.out.write(data)
            if data[-1] != '\n':
                self.out.write('\n')
            self.writePrompt()
        if not moreData:
            mark = None
        self.setMark(jobId, troveTuple, mark)

    def getMark(self, jobId, troveTuple):
        if (jobId, troveTuple) not in self.buildingTroves:
            # display max 80 lines of back log
            self.buildingTroves[jobId, troveTuple] = -80
        return self.buildingTroves[jobId, troveTuple]

    def setMark(self, jobId, troveTuple, mark):
        self.buildingTroves[jobId, troveTuple] = mark

    def _jobTrovesSet(self, jobId, troveList):
        self._msg('[%d] - job troves set' % jobId)
        self.troveToWatch = jobId, troveList[0]
        self.updatePrompt()

    def _jobStateUpdated(self, jobId, state, status):
        _AbstractDisplay._jobStateUpdated(self, jobId, state, status)
        state = buildjob.stateNames[state]
        if self._isFinished() and self.troveToWatch:
            self.updateBuildLog(*self.troveToWatch)
        self._msg('[%d] - State: %s' % (jobId, state))
        if status:
            self._msg('[%d] - %s' % (jobId, status))
        self.updatePrompt()

    def _jobLogUpdated(self, jobId, state, status):
        self._msg('[%d] %s' % (jobId, status))

    def _troveStateUpdated(self, (jobId, troveTuple), state, status):
        isBuilding = (state == buildtrove.TroveState.BUILDING)
        state = buildtrove.stateNames[state]
        if troveTuple[3]:
            name = '%s{%s}' % (troveTuple[0], troveTuple[3])
        else:
            name = troveTuple[0]
        self._msg('[%d] - %s - State: %s' % (jobId, name, state))
        if status and self._watchTrove(jobId, troveTuple):
            self._msg('[%d] - %s - %s' % (jobId, name, status))
        self.updatePrompt()

    def _troveLogUpdated(self, (jobId, troveTuple), state, status):
        if self._watchTrove(jobId, troveTuple):
            state = buildtrove.stateNames[state]
            self._msg('[%d] - %s - %s' % (jobId, troveTuple[0], status))

    def _trovePreparingChroot(self, (jobId, troveTuple), host, path):
        if not self._watchTrove(jobId, troveTuple):
            return
        if host == '_local_':
            msg = 'Chroot at %s' % path
        else:
            msg = 'Chroot at Node %s:%s' % (host, path)
        self._msg('[%d] - %s - %s' % (jobId, troveTuple[0], msg))

class OutBuffer(object):
    def __init__(self, fd):
        if fd is None: 
            fd = sys.stdout.fileno()
        elif not isinstance(out, int):
            fd = out.fileno()
        self.fd = fd
        self.data = []

    def write(self, data):
        self.data.append(data)

    def fileno(self):
        return self.fd

    def flush(self):
        while self.data:
            self.check()

    def check(self):
        while self.data:
            ready = select.select([], [self.fd], [], 0.1)[1]
            if not ready:
                return
            rc = os.write(self.fd, self.data[0])
            if rc < len(self.data[0]):
                self.data[0] = self.data[0][rc:]
            else:
                self.data.pop(0)

class DisplayState(object):#xmlrpc.BasicXMLRPCStatusSubscriber):
    def __init__(self, client):
        self.troves = []
        self.states = {}
        self.buildingTroves = {}
        self.jobId = None
        self.client = client
        self.jobState = None

    def _primeOutput(self, jobId):
        #assert(not self.jobId)
        self.jobId = jobId
        job = self.client.getJob(jobId, withTroves=False)
        self.jobState = job.state
        if job.isBuilding() or job.isFinished() or job.isFailed():
            self.updateTrovesForJob(jobId)

    def jobActive(self):
        return self.jobState in (
            buildjob.JOB_STATE_STARTED,
            buildjob.JOB_STATE_LOADING,
            buildjob.JOB_STATE_LOADED,
            buildjob.JOB_STATE_BUILD,
          )

    def getJobStateName(self):
        if self.jobState is None:
            return 'None'
        return buildjob.stateNames[self.jobState]


    def isFailed(self, jobId, troveTuple):
        return (self.getTroveState(jobId, troveTuple)
                == buildtrove.TroveState.FAILED)

    def isBuilding(self, jobId, troveTuple):
        return self.getTroveState(jobId, troveTuple) in (
                                            buildtrove.TroveState.BUILDING,
                                            buildtrove.TroveState.PREPARING,
                                            buildtrove.TroveState.RESOLVING)

    def isFailed(self, jobId, troveTuple):
        # don't iterate through unbuildable - they are failures due to 
        # secondary causes.
        return self.getTroveState(jobId, troveTuple) in (
                                            buildtrove.TroveState.FAILED,)

    def findTroveByName(self, troveName):
        startsWith = None
        for jobId, troveTuple in sorted(self.states):
            if troveTuple[0].split(':', 1)[0] == troveName:
                # exact matches take priority
                return (jobId, troveTuple)
            elif troveTuple[0].startswith(troveName) and startsWith is None:
                startsWith = (jobId, troveTuple)
        return startsWith

    def getTroveState(self, jobId, troveTuple):
        return self.states[jobId, troveTuple]

    def getBuildingTroves(self):
        return [ x[0] for x in self.states.iteritems()
                 if x[1] in (buildtrove.TroveState.BUILDING, 
                             buildtrove.TroveState.RESOLVING) ]

    def updateTrovesForJob(self, jobId):
        self.troves = []
        self.states = {}
        for state, troveTupleList in self.client.listTrovesByState(jobId).items():
            for troveTuple in troveTupleList:
                self.troves.append((jobId, troveTuple))
                self.states[jobId, troveTuple] = state
        self.troves.sort()

    def _troveStateUpdated(self, (jobId, troveTuple), state, status):
        if (jobId, troveTuple) not in self.states:
            self.updateTrovesForJob(jobId)
        else:
            self.states[jobId, troveTuple] = state

    def _jobStateUpdated(self, jobId, state, status):
        self.jobState = state
        if self._isBuilding():
            self.updateTrovesForJob(jobId)

    def _jobTrovesSet(self, jobId, troveList):
        self.updateTrovesForJob(jobId)

    def _isBuilding(self):
        return self.jobState in (buildjob.JOB_STATE_BUILD, 
                                 buildjob.JOB_STATE_STARTED)

    def _isFinished(self):
        return self.jobState in (
                    buildjob.JOB_STATE_FAILED, buildjob.JOB_STATE_BUILT)

class DisplayManager(object):#xmlrpc.BasicXMLRPCStatusSubscriber):

    displayClass = JobLogDisplay
    stateClass = DisplayState

    def __init__(self, client, showBuildLogs, out=None, exitOnFinish=None):
        self.termInfo = set_raw_mode()
        if out is None:
            out = open('/dev/tty', 'w')
        self.state = self.stateClass(client)
        self.display = self.displayClass(client, self.state, out)
        self.client = client
        self.troveToWatch = None
        self.troveIndex = 0
        self.showBuildLogs = showBuildLogs
        if exitOnFinish is None:
            exitOnFinish = False
        self.exitOnFinish = exitOnFinish

    def _receiveEvents(self, *args, **kw):
        methodname = '_receiveEvents'
        method = getattr(self.state, methodname, None)
        if method:
            try:
                method(*args)
            except errors.uncatchableExceptions:
                raise
            except Exception, err:
                print 'Error in handler: %s\n%s' % (err,
                                                    traceback.format_exc())
        method = getattr(self.display, methodname, None)
        if method:
            try:
                method(*args)
            except errors.uncatchableExceptions:
                raise
            except Exception, err:
                print 'Error in handler: %s\n%s' % (err,
                                                    traceback.format_exc())
        return ''

    def getCurrentTrove(self):
        if self.state.troves:
            return self.state.troves[self.troveIndex]
        else:
            return None

    def _primeOutput(self, jobId):
        self.state._primeOutput(jobId)
        self.display._msg('Watching job %s' % jobId)
        if self.getCurrentTrove():
            self.displayTrove(*self.getCurrentTrove())


    def displayTrove(self, jobId, troveTuple):
        self.display.setTroveToWatch(jobId, troveTuple)
        state = self.state.getTroveState(jobId, troveTuple)
        state = buildtrove.stateNames[state]

    def _serveLoopHook(self):
        ready = select.select([sys.stdin], [], [], 0.1)[0]
        if ready:
            cmd = sys.stdin.read(1)
            if cmd == '\x1b':
                cmd += sys.stdin.read(2)
            if cmd == ' ':
                self.do_switch_log()
            elif cmd == 'n' or cmd == '\x1b[C':
                self.do_next()
            elif cmd == 'p' or cmd == '\x1b[D':
                self.do_prev()
            elif cmd == 'q':
                sys.exit(0)
            elif cmd == 'h':
                self.do_help()
            elif cmd == 'b':
                self.do_next_building()
            elif cmd == 'f':
                self.do_next_failed()
            elif cmd == 'i':
                self.do_info()
            elif cmd == 'l':
                self.do_log()
            elif cmd == 's':
                self.do_status()
            elif cmd == 'g':
                self.do_goto()

        if self.showBuildLogs:
            for jobId, troveTuple in self.state.getBuildingTroves():
                self.display.updateBuildLog(jobId, troveTuple)

    def do_next(self):
        if not self.state.troves:
            return
        self.troveIndex = (self.troveIndex + 1) % len(self.state.troves)
        if self.getCurrentTrove():
            self.displayTrove(*self.getCurrentTrove())

    def do_next_building(self):
        if not self.state.troves:
            return
        startIndex = self.troveIndex
        self.troveIndex = (self.troveIndex + 1) % len(self.state.troves)
        while (not self.state.isBuilding(*self.getCurrentTrove())
               and self.troveIndex != startIndex):
            self.troveIndex = (self.troveIndex + 1) % len(self.state.troves)
        if self.troveIndex != startIndex:
            self.displayTrove(*self.getCurrentTrove())

    def do_goto(self):
        if not self.state.troves:
            print 'No troves loaded yet'
            return
        self.display.erasePrompt()
        restore_terminal(*self.termInfo)
        try:
            troveName = raw_input("\nName or part of name of trove: ")
            troveInfo = self.state.findTroveByName(troveName)
            if not troveInfo:
                print 'No trove starting with "%s"' % troveName
                self.display.writePrompt()
                return
            while not self.getCurrentTrove() == troveInfo:
                self.troveIndex = (self.troveIndex + 1) % len(self.state.troves)
            self.displayTrove(*self.getCurrentTrove())
        finally:
            self.termInfo = set_raw_mode()

    def do_next_failed(self):
        if not self.state.troves:
            return
        startIndex = self.troveIndex
        self.troveIndex = (self.troveIndex + 1) % len(self.state.troves)
        while (not self.state.isFailed(*self.getCurrentTrove())
               and self.troveIndex != startIndex):
            self.troveIndex = (self.troveIndex + 1) % len(self.state.troves)
        if self.troveIndex != startIndex:
            self.displayTrove(*self.getCurrentTrove())

    def do_prev(self):
        if not self.state.troves:
            return
        self.troveIndex = (self.troveIndex - 1) % len(self.state.troves)
        if self.getCurrentTrove():
            self.displayTrove(*self.getCurrentTrove())

    def do_info(self):
        if not self.getCurrentTrove():
            return
        jobId, troveTuple = self.getCurrentTrove()
        job = self.client.getJob(jobId)
        trove = job.getTrove(*troveTuple)
        dcfg = query.DisplayConfig(self.client, showTracebacks=True)
        self.display.setWatchTroves(False)
        self.display.erasePrompt()
        query.displayTroveDetail(dcfg, job, trove, out=self.display.out)
        self.display.writePrompt()

    def do_log(self):
        if not self.getCurrentTrove():
            return
        jobId, troveTuple = self.getCurrentTrove()
        job = self.client.getJob(jobId)
        trove = job.getTrove(*troveTuple)
        moreData, data, mark = self.client.getTroveBuildLog(jobId,
                                                            troveTuple, 0)
        if not data:
            self.display._msg('No log yet.')
            return
        fd, path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(data)
        try:
            os.system('less %s' % path)
        finally:
            os.remove(path)

    def do_help(self):
        print
        print "<space>: Turn on/off tailing of log"
        print "<left>/<right>: move to next/prev trove in list"
        print "b: move to next building trove"
        print "f: move to next failed trove"
        print "g: go to a particular trove"
        print "h: print help"
        print "i: display info for this trove"
        print "l: display log for this trove in less"
        print "q: quit"
        print "s: display status on all troves"

    def do_status(self):
        self.display.setWatchTroves(False)
        self.display.displayTroveStates()

    def do_switch_log(self):
        self.display.setWatchTroves(not self.display.getWatchTroves())

    def _isFinished(self):
        return self.display._isFinished()

    def _shouldExit(self):
        return self._isFinished() and self.exitOnFinish

    def close(self):
        self.display.close()
        restore_terminal(*self.termInfo)
