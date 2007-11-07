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

from rmake import errors
from rmake import failure
from rmake.worker import command
from rmake.worker.chroot import rootmanager

class Worker(server.Server):
    """
        The worker manages all operations that performed on an individual
        package: currently resolving its dependencies and building it.
    """
    # Plugins may override the command class used to perform a particular
    # command by modifying this dict.
    commandClasses = { 'build'    : command.BuildCommand,
                       'resolve'  : command.ResolveCommand,
                       'stop'     : command.StopCommand,
                       'session'  : command.SessionCommand }

    def __init__(self, serverCfg, logger, slots=1):
        """
            param serverCfg: server.servercfg.rMakeConfiguration instance
            param logger: lib.logger.Logger instance
            param slots: number of commands that can be run at once
            on this node.
        """
        self.cfg = serverCfg
        self.logger = logger
        server.Server.__init__(self, logger)
        self.cfg.checkBuildSanity()
        self.idgen = CommandIdGen()
        self.chrootManager = rootmanager.ChrootManager(self.cfg, self.logger)
        self._foundResult = False
        self._queuedCommands = [] # list of command classes + parameters
                                  # for commands waiting to be run
        self.commands = [] # list of command objects currently running
        self.slots = slots

    def hasActiveTroves(self):
        return self.commands or self._queuedCommands

    def buildTrove(self, buildCfg, jobId, trove, eventHandler,
                   buildReqs, crossReqs, targetLabel, logData=None,
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
                          trove, builtTroves, targetLabel, logData,
                          logPath)

    def resolve(self, resolveJob, eventHandler, logData, commandId=None):
        if not commandId:
            commandId = self.idgen.getResolveCommandId(resolveJob.getTrove())
        jobId = resolveJob.getTrove().jobId
        self.queueCommand(self.commandClasses['resolve'], self.cfg, commandId,
                          jobId, eventHandler, logData, resolveJob)

    def stopCommand(self, targetCommandId, commandId=None):
        targetCommand = self.getCommandById(targetCommandId)
        if not targetCommand:
            self.warning('Asked to stop unknown command %s' % targetCommandId)
            return
        if not commandId:
            commandId = self.idgen.getStopCommandId(targetCommandId)
        def killFn(pid):
            self._killPid(pid, killGroup=True,
                          hook=self._serveLoopHook)
        self.runCommand(self.commandClasses['stop'], self.cfg, commandId,
                        targetCommand, killFn)
        targetCommand.trove.troveFailed('Stop requested')

    def startSession(self, host, chrootPath, commandLine, superUser=False,
                     buildTrove=None):
        if host != '_local_':
            raise errors.RmakeError('Unknown host %s!' % host)
        try:
            chrootFactory = self.chrootManager.useExistingChroot(chrootPath,
                                     useChrootUser=not superUser,
                                     buildTrove=buildTrove)
            commandId = self.idgen.getSessionCommandId(chrootPath)
            cmd = self.runCommand(self.commandClasses['session'], self.cfg,
                                  commandId, chrootFactory, commandLine)
        except errors.RmakeError, err:
            f = failure.ChrootFailed('%s: %s' % (chrootPath, err))
            return False, f
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
        """
            Called to do maintenance inbetween accepting requests.

            Checks for commands that have been added to the queue
            and starts them running if there's space.  Looks for
            children that have died that were forked by this process
            and handles them.
        """
        # called once every .1 seconds when serving.
        if self._queuedCommands and (len(self.commands) < self.slots):
            commandTuple = self._queuedCommands.pop(0)
            commandClass, cfg, args = commandTuple
            if not self.runCommand(commandClass, cfg, *args):
                self.queueCommand(commandClass, cfg, *args)

        self._collectChildren()
        if self._foundResult:
            self._foundResult = False
            return True
        return False

    def stopTroveLogger(self, trove):
        if not hasattr(trove, 'logPid'):
            return
        pid = trove.logPid
        if self._isKnownPid(pid):
            self._killPid(pid)

    def handleRequestIfReady(self, sleep=0.1):
        """
            Called during serve loop to look for information being
            returned from commands.  Passes any read data to the local
            command instance for parsing.
        """
        # If a command involves forking, there are two versions of the 
        # command object: one kept in the worker, its sibling forked
        # command that is doing the actual work.  Information is passed
        # back to the worker via pipes that are read here, and then
        # parsed by the worker-held instance of the command.
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
            # commands know how to handle their own information.
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
        """
            Start the given command by instantiating the given class.

            Returns the command object that was created unless there
            was an error instantiating the command object, in which
            case None is returned.

            The function may also return False, which means that the
            command could not be run at this time (but did not error)

            If the command is forked, then the command object is appended
            the the list of running commands.
        """
        command = None
        try:
            # errors before this point imply a problem w/ the node.
            # Below this point it is a problem w/ the command.
            command = commandClass(cfg, commandId, *args)
            if not command.isReady():
                return False
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
        """
            Called automatically from collectChildren, after a pid has 
            been collected through waitpid().

            If the pid is for a command, then we call status functions,
            commandCompleted and commandErrored, which can be overridden
            by plugins.
        """
        if name is None:
            name = self._pids.get(pid, 'Unknown')
        self.info('Pid %s (%s) died' % (pid, name))
        for command in list(self.commands):
            if pid == command.pid:
                self._foundResult = True
                command.commandDied(status)
                if command.isErrored():
                    self.info('%s (Pid %s) errored' % (name, pid))
                    f = command.getFailureReason()
                    self.error(f)
                    self.commandErrored(command.getCommandId(), f)
                else:
                    self.info('%s (Pid %s) completed' % (name, pid))
                    self.commandCompleted(command.getCommandId())
                if command.getChrootFactory():
                    self.chrootManager.chrootFinished(
                                         command.getChrootFactory().getRoot())
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


class CommandIdGen(object):
    """
        Tracker and generator for command ids to ensure that each
        commandId is unique.
    """
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

