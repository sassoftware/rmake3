#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
The worker is in charge of taking build requests and monitoring them
until they complete.
"""
import select
import time
import traceback

from rmake.lib import pipereader
from rmake.lib import server

from rmake import failure
from rmake.worker import command
from rmake.worker import recorder
from rmake.worker.chroot import rootmanager

class CommandIdGen(object):
    def __init__(self):
        self._commandIds = {}

    def getBuildCommandId(self, buildTrove):
        str = 'BUILD-%s-%s' % (buildTrove.jobId, buildTrove.getName())
        return self._getCommandId(str)

    def getResolveCommandId(self, buildTrove):
        str = 'RESOLVE-%s-%s' % (buildTrove.jobId, buildTrove.getName())
        return self._getCommandId(str)

    def getStopCommandId(self, targetCommandId):
        str = 'STOP-%s' % (targetCommandId)
        return self._getCommandId(str)

    def getSessionCommandId(self, chrootPath):
        str = 'SESSION-%s' % (chrootPath)
        return self._getCommandId(str)


    def _getCommandId(self, str):
        self._commandIds.setdefault(str, 0)
        self._commandIds[str] += 1
        str += '-%s' % self._commandIds[str]
        return str

class Worker(server.Server):
    commandClasses = { 'build'    : command.BuildCommand,
                       'resolve'  : command.ResolveCommand,
                       'stop'     : command.StopCommand,
                       'session'  : command.SessionCommand }

    def __init__(self, serverCfg, logger, slots=1):
        self.cfg = serverCfg
        self.logger = logger
        server.Server.__init__(self, logger)
        self.cfg.checkBuildSanity()
        self.idgen = CommandIdGen()
        self.chrootManager = rootmanager.ChrootManager(self.cfg, self.logger)
        self._queuedCommands = []
        self._foundResult = False
        self.commands = []
        self.slots = slots

    def hasActiveTroves(self):
        return self.commands or self._queuedCommands

    def startTroveLogger(self, trove):
        r = recorder.BuildLogRecorder()
        r.attach(trove)
        logHost = r.getHost()
        logPort = r.getPort()
        pid = self._fork('BuildLogger for %s' % trove)
        if not pid:
            r._installSignalHandlers()
            r.serve_forever()
        else:
            r.close()
            trove.logPid = pid
        return logHost, logPort

    def stopTroveLogger(self, trove):
        if not hasattr(trove, 'logPid'):
            return
        pid = trove.logPid
        if self._isKnownPid(pid):
            self._killPid(pid)

    def buildTrove(self, buildCfg, jobId, trove, eventHandler,
                   buildReqs, crossReqs, targetLabel, logHost='', logPort=0, 
                   logPath=None, commandId=None, builtTroves=None):
        if not commandId:
            commandId = self.idgen.getBuildCommandId(trove)
        if logPath is None:
            logPath = trove.logPath
        if builtTroves is None:
            builtTroves = []

        chrootFactory = self.chrootManager.getRootFactory(buildCfg, buildReqs,
                                                          crossReqs, trove)
        self.queueCommand(self.commandClasses['build'], self.cfg, commandId,
                          jobId, eventHandler, buildCfg, chrootFactory,
                          trove, builtTroves, targetLabel, logHost, logPort, 
                          logPath)

    def resolve(self, resolveJob, eventHandler, commandId=None):
        if not commandId:
            commandId = self.idgen.getResolveCommandId(resolveJob.getTrove())
        jobId = resolveJob.getTrove().jobId
        self.queueCommand(self.commandClasses['resolve'], self.cfg, commandId,
                          jobId, eventHandler, resolveJob)

    def stopCommand(self, targetCommandId, commandId=None):
        targetCommand = self.getCommandById(targetCommandId)
        if not targetCommand:
            self.warning('Asked to stop unknown command %s' % targetCommandId)
            return
        if not commandId:
            commandId = self.idgen.getStopCommandId(targetCommandId)
        killFn = lambda pid: self._killPid(pid, killGroup=True,
                                           hook=self._serveLoopHook)
        self.runCommand(self.commandClasses['stop'], self.cfg, commandId,
                        targetCommand, killFn)
        targetCommand.trove.troveFailed('Stop requested')

    def startSession(self, host, chrootPath, commandLine, superUser=False):
        if host != '_local_':
            raise errors.RmakeError('Unknown host %s!' % host)
        chrootFactory = self.chrootManager.useExistingChroot(chrootPath,
                                                 useChrootUser=not superUser)
        commandId = self.idgen.getSessionCommandId(chrootPath)
        cmd = self.runCommand(self.commandClasses['session'], self.cfg,
                              commandId, chrootFactory, commandLine)
        while not cmd.getHostInfo() and not cmd.isErrored():
            self.serve_once()

        if cmd.isErrored():
            return False, cmd.getFailureReason()
        return True, cmd.getHostInfo()

    def deleteChroot(self, host, chrootPath):
        if host != '_local_':
            raise errors.RmakeError('Unknown host %s!' % host)
        self.chrootManager.deleteChroot(chrootPath)

    def archiveChroot(self, host, chrootPath, newPath):
        if host != '_local_':
            raise errors.RmakeError('Unknown host %s!' % host)
        return self.chrootManager.archiveChroot(chrootPath, newPath)

    def queueCommand(self, commandClass, cfg, *args):
        self._queuedCommands.append((commandClass, cfg, args))

    def listChroots(self):
        return self.chrootManager.listChroots()

    def _checkForResults(self):
        return self._serveLoopHook()

    def _serveLoopHook(self):
        if self._queuedCommands and (len(self.commands) < self.slots):
            commandTuple = self._queuedCommands.pop(0)
            commandClass, cfg, args = commandTuple
            self.runCommand(commandClass, cfg, *args)

        self._collectChildren()
        if self._foundResult:
            self._foundResult = False
            return True
        return False

    def handleRequestIfReady(self, sleep=0.1):
        ready = []
        if not self.commands:
            return
        try:
            ready = select.select(self.commands, [], [], sleep)[0]
        except select.error, err:
            pass
        except IOError, err:
            # this could happen because a pipe has been closed.  In this 
            # case, we should notice the pid dying shortly anyway and
            # we'll get our error message there.
            pass
        for command in ready:
            command.handleRead()

    def listQueuedCommands(self):
        return self._queuedCommands

    def listCommands(self):
        return self.commands

    def getCommandById(self, commandId):
        cmds = [ x for x in self.commands if x.getCommandId() == commandId]
        if not cmds:
            return None
        else:
            assert(len(cmds) == 1)
            return cmds[0]

    def runCommand(self, commandClass, cfg, commandId, *args):
        command = None
        try:
            # errors before this point imply a problem w/ the node.
            # Below this point it is a problem w/ the command.
            command = commandClass(cfg, commandId, *args)
            if command.shouldFork():
                inF, outF = pipereader.makeMarshalPipes()
                pid = self._fork('Command %s' % command.getCommandId())
                if not pid:
                    try:
                        self._resetSignalHandlers()
                        inF.close()
                        command.setWritePipe(outF)
                        command.runCommandAndExit()
                    finally:
                        os._exit(1)
                else:
                    command.pid = pid
                    outF.close()
                    command.setReadPipe(inF)
                    self.commands.append(command)
            else:
                command.runCommandNoExit()
                self.commandCompleted(command.getCommandId())
        except Exception, err:
            self.error(
                'Command %s got exception: %s: %s' % (commandId, err.__class__.__name__, err))
            tb = traceback.format_exc()
            self.commandErrored(commandId, str(err), tb)
            if command:
                command.commandErrored(str(err), tb)
        return command

    def _pidDied(self, pid, status, name=None):
        for command in list(self.commands):
            if pid == command.pid:
                self._foundResult = True
                command.commandDied(status)
                if command.isErrored():
                    f = command.getFailureReason()
                    self.error(f)
                    self.commandErrored(command.getCommandId(), f)
                else:
                    self.commandCompleted(command.getCommandId())
                if command.getChrootFactory():
                    self.chrootManager.rootFinished(command.getChrootFactory())
                self.commands.remove(command)
                break
        server.Server._pidDied(self, pid, status, name)

    def commandErrored(self, command, msg, tb=''):
        pass

    def commandCompleted(self, command):
        pass

    def stopAllCommands(self):
        for command in self.commands:
            self.stopCommand(command.commandId)
