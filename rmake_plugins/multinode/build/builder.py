#
# Copyright (c) 2006-2009 rPath, Inc.  All Rights Reserved.
#
from rmake import failure

from rmake.build import builder
from rmake.build import buildtrove

from rmake.lib import server

from rmake.worker import worker

from rmake.multinode import messages
from rmake.multinode import nodeclient
from rmake.multinode import nodetypes

class WorkerClient(server.Server):
    """
        Used by build manager to speak w/ worker + receive updates on 
        troves.
    """
    def __init__(self, cfg, job, db):
        server.Server.__init__(self)
        self.client = BuilderNodeClient(cfg, job.jobId, self)
        self.hasUpdate = False
        self.eventHandler = builder.EventHandler(job, self.client)

    def eventsReceived(self, jobId, eventList):
        self.eventHandler._receiveEvents(self.eventHandler.apiVersion, 
                                         eventList)

    def buildTrove(self, buildCfg, jobId, buildTrove, eventHandler,
                   buildReqs, crossReqs, targetLabel, logData,
                   builtTroves=None):
        buildTrove.disown()
        self.client.buildTrove(buildCfg, jobId, buildTrove,
                               buildReqs, crossReqs, targetLabel, logData,
                               builtTroves=builtTroves)

    def actOnTrove(self, commandName, buildCfg, jobId, buildTrove, 
                   eventHandler, logData):
        buildTrove.disown()
        self.client.actOnTrove(commandName, buildCfg, jobId, 
                               buildTrove, logData)

    def resolve(self, resolveJob, eventHandler, logData):
        resolveJob.getTrove().disown()
        self.client.resolveTrove(resolveJob, logData)

    def loadTroves(self, job, loadTroves, eventHandler, reposName):
        job.disown()
        self.client.loadTroves(job, loadTroves, reposName)

    def commandErrored(self, commandInfo, failureReason):
        buildTrove = commandInfo.getTrove()
        buildTrove.own()
        buildTrove.troveFailed(failureReason)

    def commandCompleted(self, commandInfo):
        # we'll wait for the "Trove built" message.
        pass

    def stopAllCommands(self):
        self.client.stopAllCommands()

    def hasActiveTroves(self):
        return bool(self.client._commands)

    def _checkForResults(self):
        if self.eventHandler.hadEvent():
            self.eventHandler.reset()
            return True
        return False

    def handleRequestIfReady(self):
        self.client.poll()
        self.client._collectChildren()


class BuilderNodeClient(nodeclient.NodeClient):

    sessionClass = 'BLD'

    def __init__(self, cfg, jobId, server):
        self.jobId = jobId
        self._commands = {}
        self.idgen = worker.CommandIdGen()

        node = nodetypes.BuildManager()
        nodeclient.NodeClient.__init__(self, cfg.getMessageBusHost(),
                cfg.messageBusPort, cfg, server, node, logMessages=False)

        self.bus.connect()
        self.bus.subscribe('/event?jobId=%s' % jobId)

    def emitEvents(self, jobId, eventList):
        m = messages.EventList(jobId, eventList)
        self.bus.sendSynchronousMessage('/event', m)

    def messageReceived(self, m):
        nodeclient.NodeClient.messageReceived(self, m)
        if isinstance(m, messages.EventList):
            self.server.eventsReceived(*m.getEventList())
        elif isinstance(m, messages.CommandStatus):
            commandId = m.getCommandId()
            commandInfo = self._commands[commandId]
            if commandId not in self._commands:
                #self.bus.unsubscribe('/commandstatus?commandId=%s' % commandId)
                return
            if m.isErrored():
                self.server.commandErrored(commandInfo, m.getFailureReason())
                del self._commands[commandId]
                #self.bus.unsubscribe('/commandstatus?commandId=%s' % commandId)
            if m.isCompleted():
                self.server.commandCompleted(commandInfo)
                del self._commands[commandId]
                #self.bus.unsubscribe('/commandstatus?commandId=%s' % commandId)

    def stopTroveLogger(self, trove):
        if not hasattr(trove, 'logPid'):
            return
        pid = trove.logPid
        if self._isKnownPid(pid):
            self._killPid(pid)

    def stopAllCommands(self):
        for commandId in self._commands:
            self.stopCommand(commandId)
        self.bus.flush()

    def stopCommand(self, commandId):
        newCommandId = self.idgen.getStopCommandId(commandId)
        m = messages.StopCommand(newCommandId, self.jobId,
                                 targetCommandId=commandId)
        self.bus.sendMessage('/command', m)

    def buildTrove(self, buildCfg, jobId, buildTrove, buildReqs, crossReqs,
                   targetLabel, logData, builtTroves=None):
        commandId = self.idgen.getBuildCommandId(buildTrove)
        m = messages.BuildCommand(commandId, buildCfg, jobId, buildTrove,
                                  buildReqs, crossReqs, targetLabel, logData, 
                                  builtTroves)
        self.bus.sendMessage('/command', m)
        self.bus.subscribe('/commandstatus?commandId=%s' % commandId)
        self._commands[commandId] = m

    def actOnTrove(self, commandName, buildCfg, jobId, 
                   buildTrove, logData):
        commandId = self.idgen.getActionCommandId(commandName, buildTrove)
        m = messages.ActionCommand(commandId, commandName, buildCfg, jobId,
                                   buildTrove, logData)
        self.bus.sendMessage('/command', m)
        self.bus.subscribe('/commandstatus?commandId=%s' % commandId)
        self._commands[commandId] = m

    def resolveTrove(self, resolveJob, logData):
        commandId = self.idgen.getResolveCommandId(resolveJob.getTrove())
        jobId = resolveJob.getTrove().jobId
        m = messages.ResolveCommand(commandId, jobId, resolveJob, logData)
        self.bus.sendMessage('/command', m)
        self.bus.subscribe('/commandstatus?commandId=%s' % commandId)
        self._commands[commandId] = m

    def loadTroves(self, job, loadTroves, reposName):
        commandId = self.idgen.getLoadCommandId(job)
        m = messages.LoadCommand(commandId, job, loadTroves, reposName)
        self.bus.sendMessage('/command', m)
        self.bus.subscribe('/commandstatus?commandId=%s' % commandId)
        self._commands[commandId] = m

    def poll(self, *args, **kw):
        return self.bus.poll(*args, **kw)
