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
"""
The dispatcher is in charge of taking a build request and monitoring it
until the build completes.
"""
import time
import traceback

from rmake.lib import server

from rmake.build import command
from rmake.build import failure
from rmake.build import rootmanager

class CommandIdGen(object):
    def __init__(self):
        self._commandIds = {}

    def getBuildCommandId(self, buildTrove):
        str = 'BUILD-%s-%s=%s[%s]' % (buildTrove.jobId, buildTrove.getName(),
                                      buildTrove.getVersion(),
                                      buildTrove.getFlavor())
        return self._getCommandId(str)

    def getStopCommandId(self, targetCommandId):
        str = 'STOP-%s' % (targetCommandId)

    def _getCommandId(self, str):
        self._commandIds.setdefault(str, 0)
        self._commandIds[str] += 1
        str += '-%s' % self._commandIds[str]
        return str

class Dispatcher(server.Server):
    commandClasses = { 'build' : command.BuildCommand,
                       'stop'  : command.StopCommand }

    def __init__(self, serverCfg, logger, forking=False, slots=1):
        self.cfg = serverCfg
        self.logger = logger
        server.Server.__init__(self, logger)
        self.idgen = CommandIdGen()
        self.chrootManager = rootmanager.ChrootManager(
                                         self.cfg.buildDir,
                                         self.cfg.chrootHelperPath,
                                         self.cfg, self.logger)
        self._queuedCommands = []
        self._foundResult = False
        self._forking = forking
        self.commands = []
        self.slots = slots

    def buildTrove(self, buildCfg, jobId, trove, buildReqs, targetLabel,
                   logHost='', logPort=0, commandId=None):
        if not commandId:
            commandId = self.idgen.getBuildCommandId(trove)
        chrootFactory = self.chrootManager.getRootFactory(buildCfg, buildReqs,
                                                          trove)
        self.queueCommand(self.commandClasses['build'], self.cfg, commandId, 
                          jobId, buildCfg, chrootFactory, trove,
                          targetLabel, logHost, logPort)

    def stopCommand(self, targetCommandId, commandId=None):
        targetCommand = self.getCommandById(targetCommandId)
        if not commandId:
            commandId = self.idgen.getStopCommandId(trove)
        self.runCommand(self.commandClasses['stop'], self.cfg, commandId, 
                        targetCommand, self._killPid)

    def queueCommand(self, commandClass, cfg, *args):
        self._queuedCommands.append((commandClass, cfg, args))

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

    def listQueuedCommands(self):
        return self._queuedCommands

    def listCommands(self):
        return self.commands

    def getCommandById(self, commandId):
        return [ x for x in self.commands if x.getCommandId() == commandId][0]

    def runCommand(self, commandClass, cfg, commandId, *args):
        try:
            # errors before this point imply a problem w/ the node.
            # Below this point it is a problem w/ the command.
            command = commandClass(cfg, commandId, *args)
            if not self._forking:
                rc =  command.runCommandNoExit()
                command.commandDied(rc)
                self._foundResult = True
            else:
                pid = self._fork('Command %s' % command.getCommandId())
                if not pid:
                    try:
                        self.client = None # remove all references to 
                                           # sockets, etc.
                        self._resetSignalHandlers()
                        command.runCommandAndExit()
                    finally:
                        os._exit(1)
                else:
                    command.pid = pid
                    self.commands.append(command)
        except Exception, err:
            self.error(
                'Command %s got exception: %s: %s' % (commandId, err.__class__.__name__, err))
            tb = traceback.format_exc()
            self.commandErrored(commandId, str(err), tb)

    def _pidDied(self, pid, status, name=None):
        for command in list(self.commands):
            if pid == command.pid:
                self._foundResult = True
                command.commandDied(status)
                if command.isErrored():
                    msg = command.getErrorMessage()
                    self.error(msg)
                    tb = traceback.format_exc()
                    self.commandErrored(command.getCommandId(), msg, tb)
                else:
                    self.commandCompleted(command.getCommandId())
                if command.getChrootFactory():
                    self.chrootManager.rootFinished(command.getChrootFactory())
                self.commands.remove(command)
                break

    def commandErrored(self, command, msg, tb=''):
        pass

    def commandCompleted(self, command):
        pass

    def stopAllCommands(self):
        for command in commands:
            self.stopCommand(command.commandId)
