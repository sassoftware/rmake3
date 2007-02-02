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
Monitor replacement under test.

This monitor replacement is better for jobs that are building many troves at
once.  It doesn't try to print all of their logs at once.
"""
import select
import sys
import time

from conary.lib import util

from rmake.build import buildjob, buildtrove
from rmake.cmdline import query
from rmake.lib.apiutils import thaw, freeze
from rmake.lib import auth, localrpc
from rmake import subscribers
from rmake.subscribers import xmlrpc

import termios
import fcntl
import os

from rmake.plugins import plugin

class MonitorPlugin(plugin.ClientPlugin):
    def client_preInit(self, main, argv):
        from rmake.cmdline import monitor
        monitor.monitorJob = monitorJob

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

def monitorJob(client, jobId, uri, showTroveLogs=False, showBuildLogs=False):
    receiver = XMLRPCJobLogReceiver(uri, client, showTroveLogs=showTroveLogs, 
                                    showBuildLogs=showBuildLogs)
    receiver.subscribe(jobId)
    receiver.serve_forever()

class _AbstractDisplay(xmlrpc.BasicXMLRPCStatusSubscriber):
    def __init__(self, client, showBuildLogs=True, out=None):
        self.client = client
        self.finished = False
        self.showBuildLogs = showBuildLogs
        self.troveStates = {}
        self.troveIndex = None
        self.troveDislay = False
        self.out = OutBuffer(out)

    def _msg(self, msg, *args):
        self.out.write('\r[%s] %s\n' % (time.strftime('%X'), msg))
        self.out.write('Command (press h for help)>')
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

    def close(self):
        self.erasePrompt()
        self.out.flush()

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
        self.promptFormat = '%(jobId)s %(name)s - %(state)s - (%(tailing)s) (press h for help)>'
        self.updatePrompt()

    def _msg(self, msg, *args):
        self.erasePrompt()
        self.out.write('[%s] %s\n' % (time.strftime('%X'), msg))
        self.writePrompt()

    def updatePrompt(self):
        if self.troveToWatch:
            state = self.state.getTroveState(*self.troveToWatch)
            state = buildtrove._getStateName(state)
            d = dict(jobId=self.troveToWatch[0], name=self.troveToWatch[1][0],
                     state=state)
        else:
            d = dict(jobId='(None)', name='(None)', state='')
        if self.watchTroves:
            tailing = 'Tailing'
        else:
            tailing = 'Not tailing'
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
        moreData, data, mark = self.client.getTroveBuildLog(jobId, troveTuple,
                                                            mark)
        if data:
            self.erasePrompt()
            if data[0] == '\n':
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
        if not self.troveToWatch:
            self.troveToWatch = jobId, troveList[0]
            self.updatePrompt()

    def _jobStateUpdated(self, jobId, state, status):
        _AbstractDisplay._jobStateUpdated(self, jobId, state, status)
        state = buildjob._getStateName(state)
        if self._isFinished():
            self._updateBuildLog()
        self._msg('[%d] - State: %s' % (jobId, state))
        if status:
            self._msg('[%d] - %s' % (jobId, status))

    def _jobLogUpdated(self, jobId, state, status):
        self._msg('[%d] %s' % (jobId, status))

    def _troveStateUpdated(self, (jobId, troveTuple), state, status):
        isBuilding = (state == buildtrove.TROVE_STATE_BUILDING)
        state = buildtrove._getStateName(state)
        self._msg('[%d] - %s - State: %s' % (jobId, troveTuple[0], state))
        if status and self._watchTrove(jobId, troveTuple):
            self._msg('[%d] - %s - %s' % (jobId, troveTuple[0], status))
        self.updatePrompt()

    def _troveLogUpdated(self, (jobId, troveTuple), state, status):
        if self._watchTrove(jobId, troveTuple):
            state = buildtrove._getStateName(state)
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

class DisplayState(xmlrpc.BasicXMLRPCStatusSubscriber):
    def __init__(self, client):
        self.troves = []
        self.jobs = {}
        self.states = {}
        self.buildingTroves = {}
        self.jobId = None
        self.client = client

    def subscribe(self, jobId):
        assert(not self.jobId)
        self.jobId = jobId
        job = self.client.getJob(jobId, withTroves=False)
        self.jobState = job.state
        if job.isBuilding():
            self.updateTrovesForJob(jobId)

    def jobActive(self, jobId):
        return self.jobState == JOB_STATE_BUILDING


    def getTroveState(self, jobId, troveTuple):
        return self.states[jobId, troveTuple]

    def getBuildingTroves(self):
        return [x[0] for x in self.states.iteritems()
                if x[1] == buildtrove.TROVE_STATE_BUILDING ]

    def updateTrovesForJob(self, jobId):
        self.troves = []
        self.states = {}
        for state, troveTupleList in self.client.listTrovesByState(jobId).items():
            for troveTuple in troveTupleList:
                self.troves.append((jobId, troveTuple))
                self.states[jobId, troveTuple] = state
        self.troves.sort()

    def _troveStateUpdated(self, (jobId, troveTuple), state, status):
        self.states[jobId, troveTuple] = state

    def _jobStateUpdated(self, jobId, state, status):
        self.jobState = state

    def _jobTrovesSet(self, jobId, troveList):
        self.updateTrovesForJob(jobId)

    def _isFinished(self):
        return self.jobState in (
                    buildjob.JOB_STATE_FAILED, buildjob.JOB_STATE_BUILT)

class DisplayManager(object):

    displayClass = JobLogDisplay
    stateClass = DisplayState

    def __init__(self, client, showBuildLogs, out=None):
        self.termInfo = set_raw_mode()
        if out is None:
            out = open('/dev/tty', 'w')
        self.state = self.stateClass(client)
        self.display = self.displayClass(client, self.state, out)
        self.client = client
        self.troveToWatch = None
        self.troveIndex = 0
        self.showBuildLogs = showBuildLogs

    def getCurrentTrove(self):
        if self.state.troves:
            return self.state.troves[self.troveIndex]
        else:
            return None

    def subscribe(self, jobId):
        self.state.subscribe(jobId)
        self.display._msg('Watching job %s' % jobId)

    def displayTrove(self, jobId, troveTuple):
        state = self.state.getTroveState(jobId, troveTuple)
        state = buildtrove._getStateName(state)

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
            elif cmd == 's':
                self.do_status()

        if self.showBuildLogs:
            for jobId, troveTuple in self.state.getBuildingTroves():
                self.display.updateBuildLog(jobId, troveTuple)

    def do_next(self):
        if self.state.troves:
            self.troveIndex = (self.troveIndex + 1) % len(self.state.troves)
            if self.getCurrentTrove():
                self.display.setTroveToWatch(*self.getCurrentTrove())
                self.displayTrove(*self.getCurrentTrove())

    def do_prev(self):
        if self.state.troves:
            self.troveIndex = (self.troveIndex - 1) % len(self.state.troves)
            if self.getCurrentTrove():
                self.display.setTroveToWatch(*self.getCurrentTrove())
                self.displayTrove(*self.getCurrentTrove())

    def do_help(self):
        print "<space>: Turn on, off log output"
        print "h: print help"
        print "n: move to next trove in list"
        print "s: display status on all troves"
        print "q: quit"

    def do_status(self):
        self.display.setWatchTroves(False)
        self.display.displayTroveStates()

    def do_switch_log(self):
        self.display.setWatchTroves(not self.display.getWatchTroves())

    def _isFinished(self):
        return self.state._isFinished()

    def close(self):
        self.display.close()
        restore_terminal(*self.termInfo)

    def _dispatch(self, methodname, args):
        if methodname.startswith('_'):
            raise NoSuchMethodError(methodname)
        else:
            # call display method
            method = getattr(self.state, methodname, None)
            if method:
                method(*args)
            method = getattr(self.display, methodname, None)
            if method:
                method(*args)
            return ''


class XMLRPCJobLogReceiver(object):

    def __init__(self, uri=None, client=None,
                 displayManagerClass=DisplayManager,
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
        self.manager = displayManagerClass(self.client,
                                           showBuildLogs=showBuildLogs, 
                                           out=out)

        if serverObj:
            serverObj.register_instance(self.manager)

    def subscribe(self, jobId):
        subscriber = subscribers.SubscriberFactory('monitor_', 'xmlrpc',
                                                   self.uri)
        subscriber.watchEvent('JOB_STATE_UPDATED')
        subscriber.watchEvent('JOB_LOG_UPDATED')
        subscriber.watchEvent('JOB_TROVES_SET')
        if self.showTroveLogs:
            subscriber.watchEvent('TROVE_STATE_UPDATED')
            subscriber.watchEvent('TROVE_LOG_UPDATED')
            subscriber.watchEvent('TROVE_PREPARING_CHROOT')
        self.jobId = jobId
        self.subscriber = subscriber
        self.client.subscribe(jobId, subscriber)
        self.manager.subscribe(jobId)

    def serve_forever(self):
        try:
            while True:
                self.handleRequestIfReady(.1)
                self._serveLoopHook()
                if self.manager._isFinished():
                    break
        finally:
            self.manager.close()
            self.unsubscribe()

    def handleRequestIfReady(self, sleepTime=0.1):
        ready, _, _ = select.select([self.server], [], [], sleepTime)
        if ready:
            self.server.handle_request()

    def _serveLoopHook(self):
        self.manager._serveLoopHook()

    def unsubscribe(self):
        if self.client:
            self.client.unsubscribe(self.subscriber.subscriberId)
