#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
    Contains the DispatcherServer class and Dispatcher XMLRPC client.

    The DispatcherServer takes in requests to perform commands and passes
    those requests onto available nodes if any.

    The DispatcherClient provides and XMLRPC-over-messagebus interface
    to the dispatcher for querying the dispatcher status out-of-band.
"""
import os
import signal

from conary.deps import deps
from conary.lib import util

from rmake import errors
from rmake.lib.apiutils import api, api_parameters, api_return, freeze, thaw

from rmake.build import buildjob
from rmake.build import buildtrove
from rmake.lib import apirpc
from rmake.lib import flavorutil
from rmake.lib import logger
from rmake.lib import server
from rmake.server import publish

from rmake.messagebus import busclient

from rmake.multinode import messages
from rmake.multinode import nodeclient
from rmake.multinode import nodetypes


class DispatcherServer(server.Server):
    """
        The Dispatcher is given a list of packages to resolve and build
        and determines where the best location to build them is.
    """
    def __init__(self, cfg, db):
        self.client = DispatcherNodeClient(cfg.getMessageBusHost(),
                cfg.messageBusPort, cfg, self)
        server.Server.__init__(self, self.client.getLogger())
        subscriberLog = logger.Logger('subscriber', cfg.getSubscriberLogPath())

        # In multinode rMake, publishing events to external subscribers
        # is done by a process forked from the dispatcher (since the
        # dispatcher gets all events anyway) instead of passing them
        # back to the rMake XMLRPC front end.
        self._publisher = publish._RmakeServerPublisher(subscriberLog,
                                                        db, self._fork)
        # detaile data about the nodes is stored in the NodeList.
        self._nodes = NodeList(db, self._logger)

        # commands that haven't been assigned to a node.
        self._queuedCommands = []
        self._queuedCommandsById = {}
        self.db = db

    def getClient(self):
        return self.client

    def _installSignalHandlers(self):
        self.client._installSignalHandlers()
        def _interrupt(*args, **kw):
            import epdb
            if hasattr(epdb, 'serve'):
                epdb.serve()
            else:
                epdb.st()
        # if you kill the dispatcher w/ SIGUSR1 you'll get a breakpoint.
        import signal
        signal.signal(signal.SIGUSR1, _interrupt)

    def listNodes(self):
        return [ x.sessionId for x in self._nodes.getNodes() ]

    def listQueuedCommands(self):
        return [ x.getMessageId() for x in self._queuedCommands ]

    def listAssignedCommands(self):
        return self._nodes.getCommandAssignments()

    def getNodeByName(self, nodeName):
        try:
            return self._nodes.getNodeByName(nodeName)
        except IndexError:
            raise errors.RmakeError('No such node %s' % nodeName)

    def getNamesByIds(self, idList):
            return self._nodes.getNamesByIds(idList)

    def requestCommandAssignment(self, *commands):
        """
            Entry point from message bus to assign commands.  We
            will assign the command if we can.
        """
        for command in commands:
            if isinstance(command, messages.StopCommand):
                # stop commands _always_ get assigned immediately.
                self.handleStopCommand(command)
            else:
                # just queue this command, we'll pull it off the queue 
                # ASAP in assignQueuedCommands if possible.
                self._queuedCommands.append(command)
                self._queuedCommandsById[command.getCommandId()] = command
        self._assignQueuedCommands()

    def handleStopCommand(self, command):
        targetId = command.getTargetCommandId()
        node = self._nodes.getNodeForCommand(targetId)
        if node is not None:
            self._nodes.assignCommand(command, node)
            self._sendCommandToNode(command, node)
        elif targetId in self._queuedCommandsById:
            command = self._queuedCommandsById[targetId]
            self._queuedCommands.remove(command)
        else:
            # guess we don't know about this command or its node is gone.
            self.warning('dropped stop command for %s' % targetId)

    def _assignQueuedCommands(self):
        """
            Attempts to assign queued commands if there are available nodes
        """
        if not self._queuedCommands:
            return
        # attempt to assign commands.  See what the node manager
        # thinks we can assign.
        assignments = self._nodes.assignCommands(list(self._queuedCommands))
        for (command, node) in assignments:
            self._sendCommandToNode(command, node)
            self._queuedCommands.remove(command)
            self._queuedCommandsById.pop(command.getCommandId())

    def _sendCommandToNode(self, command, node):
        self.log('sending %s to node %s' % (command.getCommandId(),
                                            node.sessionId))
        self.client.assignCommand(command, node)

    def nodeRegistered(self, sessionId, node):
        """
            Entry point from messagebus client to alert dispatcher that
            a node connected.
        """
        self.log('Worker node %s connected' % sessionId)
        self._nodes.add(sessionId, node)
        self._assignQueuedCommands()

    def nodeUpdated(self, sessionId, nodeInfo, commandIds):
        """
            Entry point from messagebus client to alert dispatcher that
            a node connected.
        """
        if sessionId in self._nodes:
            self._nodes.updateStatus(sessionId, nodeInfo, commandIds)
            self._assignQueuedCommands()
        else:
            self.log('Discarding heartbeat from unknown %s' % sessionId)

    def nodeDisconnected(self, sessionId):
        """
            Entry point from messagebus client to alert dispatcher that
            a node disconnected.
        """
        if sessionId in self._nodes:
            self.log('Worker node %s diconnected' % sessionId)
            self._nodes.remove(sessionId)
            self._assignQueuedCommands()

    def commandCompleted(self, commandId):
        """
            Entry point from messagebus client.
        """
        command = self._nodes.removeCommand(commandId)
        self._assignQueuedCommands()

    def commandErrored(self, commandId):
        """
            Entry point from messagebus client.
        """
        command = self._nodes.removeCommand(commandId)
        self._assignQueuedCommands()

    def commandInProgress(self, commandId):
        """
            Entry point from messagebus client.
        """
        pass

    def eventsOccurred(self, sessionId, jobId, (apiVer, eventList)):
        """
            Entry point from messagebus client that new events were sent.
        """
        # send all events to the publisher, which will send them
        # off to connected subscribers.
        self._publisher.addEvent(jobId, eventList)

    def _serveLoopHook(self):
        self._publisher.emitEvents()
        self._collectChildren()

    def _pidDied(self, pid, status, name=None):
        server.Server._pidDied(self, pid, status, name=name)
        if pid == self._publisher._emitPid: # rudimentary locking for emits
            self._publisher._emitPid = 0    # only allow one emitEvent process
                                            # at a time.

    def serve(self):
        self.serve_forever()

    def handleRequestIfReady(self, sleepTime=0.1):
        self.client.handleRequestIfReady(sleepTime)
        self._halt = self._halt or self.client._halt

    def log(self, text):
        self.client.getBusClient().logger.info(text)

class DispatcherNodeClient(nodeclient.NodeClient):
    """
        Low level interface between Dispatcher and Message Bus.

        Also provides the XMLRPC-over-messagebus interface.
    """
    sessionClass = 'DSP' # type information used by messagebus to classify
                         # connections.
    name = 'dispatcher'  # Name used by logging.

    # NodeClient uses this list and automatically subscribes to these
    # message channels.

    subscriptions =  ['/register?nodeType=%s' % nodetypes.WorkerNode.nodeType,
                      '/command',
                      '/event',
                      '/internal/nodes',
                      '/nodestatus',
                      '/commandstatus']


    def _signalHandler(self, sigNum, frame):
        if sigNum == signal.SIGINT:
            # SIGINT should be handled by the rMakeServer, which is the parent
            # pid of Dispatcher.
            self.error('SIGINT caught and ignored.')
        else:
            nodeclient.NodeClient._signalHandler(self, sigNum, frame)

    @api(version=1)
    @api_return(1, None)
    def listNodes(self, callData):
        return self.server.listNodes()

    @api(version=1)
    @api_return(1, None)
    def listQueuedCommands(self, callData):
        return self.server.listQueuedCommands()

    @api(version=1)
    @api_return(1, None)
    def listAssignedCommands(self, callData):
        return self.server.listAssignedCommands()

    @api(version=1)
    @api_parameters(1, None)
    @api_return(1, None)
    def getNodeByName(self, callData, nodeName):
        node = self.server.getNodeByName(nodeName)
        return node.sessionId

    @api(version=1)
    @api_parameters(1, None)
    @api_return(1, None)
    def getNamesByIds(self, callData, idList):
        return self.server.getNamesByIds(idList)

    def messageReceived(self, m):
        """
            Handles messages from the messagebus.
        """
        nodeclient.NodeClient.messageReceived(self, m)
        if isinstance(m, messages.RegisterNodeMessage):
            self.server.nodeRegistered(m.getSessionId(), m.getNode())
        elif isinstance(m, messages.NodeInfo):
            self.server.nodeUpdated(m.getSessionId(), m.getNodeInfo(),
                                    m.getCommands())
        elif isinstance(m, messages._Command):
            if m.getTargetNode():
                # we've already assigned this command
                return
            self.server.log('Received Command: %s' % m.getCommandId())
            self.server.requestCommandAssignment(m)
        elif isinstance(m, messages.EventList):
            self.server.eventsOccurred(m.getSessionId(), m.getJobId(),
                                       m.getEventList())
        elif isinstance(m, messages.NodeStatus):
            if m.isDisconnected():
                self.server.nodeDisconnected(m.getStatusId())
        elif isinstance(m, messages.CommandStatus):
            if m.isCompleted():
                self.server.commandCompleted(m.getCommandId())
            elif m.isInProgress():
                self.server.commandInProgress(m.getCommandId())
            elif m.isErrored():
                self.server.commandErrored(m.getCommandId())

    def assignCommand(self, command, node):
        command.setTargetNode(node.sessionId)
        self.getBusClient().sendMessage('/command', command)


class DispatcherRPCClient(object):
    def __init__(self, client, sessionId):
        self.proxy = busclient.SessionProxy(DispatcherNodeClient, client,
                                            sessionId)

    def listNodes(self):
        return self.proxy.listNodes()

    def listQueuedCommands(self):
        return self.proxy.listQueuedCommands()

    def listAssignedCommands(self):
        return self.proxy.listAssignedCommands()

    def getNodeByName(self, nodeName):
        return self.proxy.getNodeByName(nodeName)

    def getNamesByIds(self, idList):
        return self.proxy.getNamesByIds(idList)

class NodeList(object):
    def __init__(self, nodeDb, logger=None):
        self._nodes = {}
        self._assignedCommands = {}
        self._commands = {}
        self._openSlots = {}
        self._openChroots = {}
        self._commandsByJob = {}
        self.nodeDb = nodeDb
        self.logger = logger

    def add(self, sessionId, node):
        node.sessionId = sessionId
        self._nodes[sessionId] = node
        self._assignedCommands[sessionId] = []
        self._openSlots[sessionId] = node.slots
        self._openChroots[sessionId] = node.chrootLimit
        self.nodeDb.addNode(node.name, node.host, node.slots, node.buildFlavors,
                            node.chroots)

    def remove(self, sessionId):
        node = self._nodes.pop(sessionId, None)
        self.nodeDb.removeNode(node.name)
        for command in self._assignedCommands.pop(sessionId, []):
            self._commands.pop(command.getCommandId())
        self._openSlots.pop(sessionId, None)
        self._openChroots.pop(sessionId, None)

    def getNodeForCommand(self, commandId):
        if commandId in self._commands:
            sessionId, command = self._commands[commandId]
            return self._nodes.get(sessionId, None)
        return None

    def getNodeByName(self, name):
        return [ x for x in self._nodes.values() if x.name == name ][0]

    def getNamesByIds(self, idList):
        return dict((x, self._nodes[x].name) for x in idList
                     if x in self._nodes)

    def __contains__(self, sessionId):
        return sessionId in self._nodes

    def _getScore(self, node):
        usedSlots = node.slots - self._openSlots[node.sessionId]
        if usedSlots == 0:
            return 0
        else:
            return usedSlots / float(node.slots)

    def rankNodes(self, nodeList):
        return sorted(nodeList, key = lambda x: (self._getScore(x),
                                                 int(x.nodeInfo.loadavg[0]),
                                               ))

    def getNodes(self):
        return self._nodes.values()

    def getOpenNodes(self, requiresChroot=False):
        availNodes = [ self._nodes[x[0]]
                       for x in self._openSlots.iteritems() if x[1] > 0 ]
        if requiresChroot:
            availNodes = [ x for x in availNodes
                           if self._openChroots[x.sessionId] > 0 ]
        # only return nodes whose load average is below their threshold
        return [ x for x in availNodes
                 if x.nodeInfo.getLoadAverage(1) < x.loadThreshold ]

    def getCommandAssignments(self):
        # returns commandId, sessionId pairs
        return [ (x[0], x[1][0]) for x in self._commands.items() ]

    def getNodeForFlavors(self, flavors, requiresChroot=False):
        nodes = []
        for node in self.getOpenNodes(requiresChroot=requiresChroot):
            if not flavors:
                nodes.append(node)
                continue
            for flavor in flavors:
                found = False
                archFlavor = flavorutil.getArchFlags(flavor, getTarget=False,
                                                     withFlags=False)
                for buildFlavor in node.buildFlavors:
                    filteredFlavor = deps.filterFlavor(flavor, [buildFlavor,
                                                                archFlavor])
                    if buildFlavor.stronglySatisfies(filteredFlavor):
                        found = True
                        break
                if not found:
                    break
            if found:
                nodes.append(node)
        if not nodes:
            return None
        return self.rankNodes(nodes)[0]

    def updateStatus(self, sessionId, nodeInfo, commandIds):
        #self.db.updateNode(sessionId, nodeInfo)
        self._nodes[sessionId].nodeInfo = nodeInfo
        assignedCommandIds = [ x.getCommandId() for x in 
                             self._assignedCommands[sessionId] ]
        for commandId in commandIds:
            if commandId not in self._commands:
                # FIXME: need to tell the node to stop working on it
                self.logger.warning('%s working on unknown command %s' % (sessionId, commandId))
                pass
        for commandId in (set(assignedCommandIds) - set(commandIds)):
            self.logger.warning('%s dropped command %s' % (sessionId, commandId))
            # FIXME: this command is no longer being worked on.
            # how did we miss this?
            self.removeCommand(commandId)

    def removeCommand(self, commandId):
        sessionId, command = self._commands.pop(commandId, (None, None))
        if not sessionId:
            return

        self.logger.info('removing command: %s' % commandId)

        if sessionId in self._openSlots:
            self._openSlots[sessionId] += 1
        if sessionId in self._openChroots and command.requiresChroot():
            self._openChroots[sessionId] += 1
        commandsByJob = self._commandsByJob.get(command.getJobId(), [])
        if command in commandsByJob:
            commandsByJob.remove(command)
        if command in self._assignedCommands[sessionId]:
            self._assignedCommands[sessionId].remove(command)
        return command

    def _logDict(self, title, data):
        self.logger.info('%s:' % title)
        for item in sorted([ '\t%s: %s' % (x, y) for x, y in data.iteritems() ]):
            self.logger.info(item)

    def assignCommand(self, command, node):
        sessionId = node.sessionId
        self._commands[command.getCommandId()] = sessionId, command
        self._commandsByJob.setdefault(command.getJobId(), []).append(
                                                                  command)
        self._assignedCommands[sessionId].append(command)
        self._logDict('Current OpenSlots', self._openSlots)
        self._openSlots[sessionId] -= 1
        if command.requiresChroot():
            self._logDict('Current OpenChroots', self._openChroots)
            self._openChroots[sessionId] -= 1

        self.logger.info('assigned %s to %s' % (command.getCommandId(), node.host))

    def assignCommands(self, commands):
        l = []
        for command in commands:
            flavors = command.getRequiredFlavors()
            node = self.getNodeForFlavors(flavors,
                                     requiresChroot=command.requiresChroot())
            if node is None:
                continue
            self.assignCommand(command, node)
            l.append((command, node))
        return l

    def getCommandsForJob(self, jobId):
        return self._commandsByJob.get(jobId, [])

