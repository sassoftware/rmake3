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
import errno
import os
import socket
import sys
import time
import traceback

from conary import conaryclient
from conary.repository import changeset

from rmake import errors

from rmake import failure
from rmake.build import subscriber

from rmake.lib import logfile
from rmake.lib import logger
from rmake.lib import server

from rmake.lib.apiutils import thaw, freeze


class Command(server.Server):
    name = 'command'
    # handles one job then exists.
    def __init__(self, cfg, commandId, jobId):
        server.Server.__init__(self)
        self.cfg = cfg
        self.commandId = commandId
        self.jobId = jobId
        self._isErrored = False
        self._errorMessage = ''
        self._output = []
        self.readPipe = None

    def _exit(self, exitRc):
        sys.exit(exitRc)

    def shouldFork(self):
        return True

    def setWritePipe(self, writePipe):
        self.writePipe = writePipe

    def setReadPipe(self, readPipe):
        self.readPipe = readPipe

    def fileno(self):
        return self.readPipe.fileno()

    def handleRead(self):
        data = self.readPipe.handle_read()
        if data:
            self._handleData(data)

    def flushInputBuffer(self):
        if not self.readPipe:
            return
        for data in self.readPipe.readUntilClosed():
            self._handleData(data)

    def handleWrite(self):
        self.writePipe.handle_write()

    def _handleData(self, data):
        self._output.append(data)

    def getCommandId(self):
        return self.commandId

    def getChrootFactory(self):
        return None

    def getLogPath(self):
        commandId = (self.getCommandId().replace('/', '_')
                                                    .replace('~', '')
                                                    .replace(' ', ''))
        base =  self.cfg.getBuildLogDir(self.jobId)
        return '%s/%s.log' % (base, commandId)

    def runCommandAndExit(self):
        self._installSignalHandlers()
        try:
            self._try('Command', self._runCommand)
            os._exit(0)
        except SystemExit, err:
            os._exit(err.args[0])
        except:
            # error occurred, but we'll let our parent node send out the
            # "errored" message.
            os._exit(1)

    def _serveLoopHook(self):
        self.writePipe.handleWriteIfReady()
        self._collectChildren()

    def runCommandNoExit(self):
        try:
            self._try('Command', self._runCommand)
        except SystemExit, err:
            return err.args[0]
        return 0

    def _runCommand(self):
        self.commandStarted()
        self.logger = logger.Logger(self.name, self.getLogPath())
        self.logFile = logfile.LogFile(self.getLogPath())
        self.logFile.redirectOutput()
        try:
            self.logger.info('Running Command... (pid %s)' % os.getpid())
            try:
                self.runCommand()
            except SystemExit, err:
                raise
            except Exception, err:
                if isinstance(err, SystemExit) and not err.args[0]:
                    self.commandFinished()
                else:
                    self.commandErrored(err, traceback.format_exc())
                raise
            else:
                self.commandFinished()
        finally:
            self.logFile.restoreOutput()

    def isErrored(self):
        return self._isErrored

    def getFailureReason(self):
        return self.failureReason

    def setError(self, msg, tb=''):
        self._isErrored = True
        self.failureReason = failure.CommandFailed(self.commandId, str(msg), tb)

    def commandDied(self, status):
        self.flushInputBuffer()
        exitRc = os.WEXITSTATUS(status)
        signalRc = os.WTERMSIG(status)
        commandId = self.getCommandId()
        if exitRc or signalRc:
            if exitRc:
                msg = 'unexpectedly died with exit code %s'
                msg = msg % (exitRc)
            else:
                msg = 'unexpectedly killed with signal %s'
                msg = msg % (signalRc)
            self.setError(msg)
        self.commandFinished()

    def commandStarted(self):
        pass

    def commandFinished(self):
        pass

    def commandErrored(self, msg, tb=''):
        self.setError(msg, tb)

class BuildCommand(Command):

    name = 'build-command'

    def __init__(self, serverCfg, commandId, jobId, eventHandler, buildCfg,
                 chrootFactory, trove, targetLabel, logHost='', logPort=0,
                 logPath=None, uri=None):
        Command.__init__(self, serverCfg, commandId, jobId)
        self.eventHandler = eventHandler
        self.buildCfg = buildCfg
        self.chrootFactory = chrootFactory
        self.trove = trove
        self.targetLabel = targetLabel
        self.logHost = logHost
        self.logPort = logPort
        self.logPath = logPath
        self.readPipe = None
        self.failureReason = None
        self.uri = None

    def _signalHandler(self, signal, frame):
        self.failureReason = failure.Stopped('Signal %s received' % signal)
        Command._signalHandler(self, signal, frame)

    def _shutDown(self):
        if self.failureReason:
            self.trove.troveFailed(self.failureReason)
        try:
            self.chroot.stop()
        except OSError, err:
            if err.errno != errno.ESRCH:
                raise
            else:
                return
        except errors.OpenError, err:
            pass
        self._killPid(self.chroot.pid)
        Command._shutDown(self)

    def _handleData(self, (jobId, eventList)):
        self.eventHandler._receiveEvents(*thaw('EventList', eventList))

    def getTrove(self):
        return self.trove

    def getChrootFactory(self):
        return self.chrootFactory

    def runCommand(self):
        try:
            try:
                trove = self.trove
                trove.getPublisher().reset()
                PipePublisher(self.writePipe).attach(trove)
                trove.creatingChroot(self.cfg.getName(),
                                     self.chrootFactory.getChrootName())
                self.chrootFactory.create()
                self.chroot = self.chrootFactory.start()
            except Exception, err:
                # sends off messages to all listeners that this trove failed.
                trove.chrootFailed(str(err), traceback.format_exc())
                return
            n,v,f = trove.getNameVersionFlavor()
            logPath, pid = self.chroot.buildTrove(self.buildCfg,
                                                  self.targetLabel,
                                                  n, v, f, self.logHost,
                                                  self.logPort)
            # sends off message that this trove is building.
            self.chroot.subscribeToBuild(n,v,f)
            if self.logPath:
                logPath = self.logPath
            trove.troveBuilding(logPath, pid)
            self.serve_forever()
        except SystemExit, err:
            self.writePipe.flush()
            raise
        except Exception, err:
            self.writePipe.flush()
            # even if there's an exception in here, we don't really
            # want to retry the build.
            reason = failure.InternalError(str(err), traceback.format_exc())
            trove.troveFailed(reason)
            raise

    def handleRequestIfReady(self, sleep):
        time.sleep(sleep)

    def _serveLoopHook(self):
        try:
            self.writePipe.handleWriteIfReady()
            if self.chroot.checkSubscription():
                self.getResults()
                self._halt = True
                return
        except SystemExit, err:
            raise
        except Exception, err:
            reason = failure.InternalError(str(err), traceback.format_exc())
            self.getTrove().troveFailed(reason)
            raise

    def getResults(self):
        try:
            trove = self.trove
            repos = conaryclient.ConaryClient(self.buildCfg).getRepos()
            buildResult = self.chroot.checkResults(
                                            *self.trove.getNameVersionFlavor())
            if buildResult.isBuildSuccess():
                csFile = buildResult.getChangeSetFile()
                cs = changeset.ChangeSetFromFile(csFile)
                repos.commitChangeSet(cs)
                # sends off message that this trove built successfully
                troveList = [x.getNewNameVersionFlavor() for
                             x in cs.iterNewTroveList() ]
                trove.troveBuilt(troveList)
                del cs # this makes sure the changeset closes the fd.
                self.chroot.stop()
                if self.buildCfg.cleanAfterCook:
                    self.chrootFactory.clean()
                return
            else:
                reason = buildResult.getFailureReason()
                trove.troveFailed(reason)
                # passes through to killRoot at the bottom.
        except Exception, e:
            reason = failure.InternalError(str(e), traceback.format_exc())
            trove.troveFailed(reason)
        self.chroot.stop()

class StopCommand(Command):

    name = 'stop-command'

    def __init__(self, cfg, commandId, targetCommand, killFn):
        Command.__init__(self, cfg, commandId, targetCommand.jobId)
        self.targetCommand = targetCommand
        self.killFn = killFn

    def runCommand(self):
        self.killFn(self.targetCommand.pid)

    def commandDied(self, status):
        Command.commandDied(self, status)
        try:
            pid, status = os.waitpid(self.targetCommand.pid, os.WNOHANG)
        except OSError, err:
            if err.errno == errno.ECHILD:
                pass
            elif err.errno == errno.ESRCH:
                pass
            else:
                raise
        else:
            self.setError('%s did not die!' % self.targetCommand.getCommandId())

class SessionCommand(Command):

    name = 'session-command'

    def __init__(self, serverCfg, commandId, chrootFactory, command):
        Command.__init__(self, serverCfg, commandId, 0)
        self.chrootFactory = chrootFactory
        self.command = command
        self.hostInfo = []

    def getTrove(self):
        return self.trove

    def getChrootFactory(self):
        return self.chrootFactory

    def runCommand(self):
        self.chrootFactory.create()
        self.chroot = self.chrootFactory.start()
        port = self.chroot.startSession(self.command)
        self.writePipe.send((socket.getfqdn(), port))
        self.writePipe.flush()
        self.serve_forever()

    def _pidDied(self, pid, status, name=None):
        if pid == self.chroot.pid:
            self.chrootFactory.unmount()
            self._halt = True

    def _handleData(self, output):
        self.hostInfo = output

    def getHostInfo(self):
        return self.hostInfo

class PipePublisher(subscriber._RmakePublisherProxy):
    """
        Class that transmits events from internal build process -> rMake server.
    """

    # we override the _receiveEvents method to just pass these
    # events on, thus we just use listeners as a list of states we subscribe to

    def __init__(self, pipeWriter):
        self.pipeWriter = pipeWriter
        subscriber._RmakePublisherProxy.__init__(self)

    def _emitEvents(self, jobId, eventList):
        self.pipeWriter.send((jobId, freeze('EventList', eventList)))
        self.pipeWriter.flush()

def attach(trove, p):
    _RmakeBusPublisher(client).attach(trove)
