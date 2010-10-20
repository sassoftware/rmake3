#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Wrapper around rmake.worker that receives and sends messages to the dispatcher.
"""
import os
import signal
import socket
import time
import traceback

from conary import errors

from rmake import failure
from rmake.build import subscriber
from rmake.lib import logger
from rmake.lib import osutil
from rmake.lib import procutil
from rmake.lib import server
from rmake.lib.apiutils import api, api_parameters, api_return, freeze, thaw
from rmake.worker import command
from rmake.worker import worker

from rmake.messagebus import busclient
from rmake.multinode import messages
from rmake.multinode import nodetypes
from rmake.multinode import nodeclient

class rMakeWorkerNodeServer(worker.Worker):
    """
        Class that wraps worker functionality from rmake.worker.worker.  Actual
        communication w/ messagebus is handled in worker.client

        @param cfg: node cfg
        @type cfg: rmake_node.nodecfg.NodeConfiguration
        @param messageBusInfo: override information for how to get to the 
                               messagebus
        @type messageBusInfo: (host, port)
    """

    def __init__(self, cfg, messageBusInfo=None):
        serverLogger = logger.Logger('rmake-node',
                                     logPath=cfg.logDir + '/rmake-node.log')
        try:
            serverLogger.info('Starting rMake Node (pid %s)' % os.getpid())
            worker.Worker.__init__(self, cfg, serverLogger,
                                   slots=cfg.slots)
            #calculates current state of the rmake chroot directory.
            chroots = self.listChroots()
            self.client = WorkerNodeClient(cfg, self,
                                           procutil.MachineInformation(),
                                           chroots=chroots,
                                           messageBusInfo=messageBusInfo)
            self.lastStatusSent = 0
            self.statusPeriod = 60
        except Exception, err:
            self.error('Error initializing Node Server:\n  %s\n%s', err,
                                   traceback.format_exc())
            raise

    def busConnected(self, sessionId):
        pass

    def receivedResolveCommand(self, info):
        eventHandler = DirectRmakeBusPublisher(info.getJobId(), self.client)
        self.resolve(info.getResolveJob(), eventHandler, info.getLogData(),
                     commandId=info.getCommandId())

    def receivedActionCommand(self, info):
        eventHandler = DirectRmakeBusPublisher(info.getJobId(), self.client)
        self.actOnTrove(info.getCommandName(),
                        info.getBuildConfig(),
                        info.getJobId(), info.getTrove(),
                        eventHandler, info.getLogData(), 
                        commandId=info.getCommandId())

    def receivedLoadCommand(self, info):
        eventHandler = DirectRmakeBusPublisher(info.getJobId(), self.client)
        self.loadTroves(info.getJob(), info.getLoadTroves(), eventHandler,
            info.getReposName(), commandId=info.getCommandId())

    def receivedBuildCommand(self, info):
        # allow state changes in the trove before/after we actually fork the 
        # command
        RmakeBusPublisher(info.getJobId(), self.client).attach(info.getTrove())
        # create an eventHandler which will take events from the command
        # and send them to the messagebus.
        eventHandler = DirectRmakeBusPublisher(info.getJobId(), self.client)
        self.buildTrove(info.getBuildConfig(), info.getJobId(),
                        info.getTrove(), eventHandler,
                        info.getBuildReqs(), info.getCrossReqs(),
                        info.getTargetLabel(), info.getLogInfo(),
                        bootstrapReqs=info.getBootstrapReqs(),
                        builtTroves=info.getBuiltTroves(),
                        commandId=info.getCommandId())

    def receivedStopCommand(self, info):
        # pass command on to worknode underneath.
        self.stopCommand(commandId=info.getCommandId(),
                         targetCommandId=info.getTargetCommandId())

    def _installSignalHandlers(self):
        worker.Worker._installSignalHandlers(self)
        # if you kill the dispatcher w/ SIGUSR1 you'll get a breakpoint.
        # just let signals be handled normally
        def _interrupt(*args, **kw):
            import epdb
            if hasattr(epdb, 'serve'):
                epdb.serve()
            else:
                epdb.st()
        import signal
        signal.signal(signal.SIGUSR1, _interrupt)


    def _signalHandler(self, signal, frame):
        server.Server._signalHandler(self, signal, frame)
        os.kill(os.getpid(), signal)

    def _serveLoopHook(self):
        # Called every .1 seconds or so when polling for 
        # new requests.
        # Sends status update about the machine.
        if not self.client.isConnected():
            self.client.connect()
            return
        if (time.time() - self.lastStatusSent) > self.statusPeriod:
            if self.client:
                self.lastStatusSent = time.time()
                info = procutil.MachineInformation()
                commandIds = [ x.getCommandId() for x in self.commands]
                commandIds += [ x[2][0] for x in self._queuedCommands ]
                self.client.updateStatus(info, commandIds)
        worker.Worker._serveLoopHook(self)

    def handleRequestIfReady(self, sleep):
        # override standard worker's poll mechanism to check the bus 
        # instead.
        try:
            self.client.poll(timeout=sleep, maxIterations=1)
        except socket.error, err:
            self.error('Socket connection died: %s' % err.args[1])
            time.sleep(sleep)
        # passing 0 to tell it we've arleady slept if necessary.
        return worker.Worker.handleRequestIfReady(self, 0)

    def commandErrored(self, commandId, msg, tb=''):
        """
            Called by worker after command finishes with error.
            Pass any command errors back to the message bus where they'll 
            be dealt with.
        """
        self.client.commandErrored(commandId, msg, tb)

    def commandCompleted(self, commandId):
        """
            Called by worker after command finishes with error.
            Pass any command errors back to the message bus where they'll 
            be dealt with.
        """
        self.client.commandCompleted(commandId)

class WorkerNodeClient(nodeclient.NodeClient):
    """
        Manages worker node's low-level connection to the messagebus.
        When it receives messages it parses them and passes the information
        up to the WorkerNodeServer.  It also accepts commands from
        the node server and passes the information back to the
        message bus.

        Initialization parameters:
        @param cfg: node configuration
        @param server: rMakeServerClass to call when messages received
        @param nodeInfo: procutils.MachineInformation object describing
        the current state of the node.
    """

    sessionClass = 'WORKER' # type information used by messagebus to classify
                            # connections.
    name = 'rmake-node'     # name used by logging

    def __init__(self, cfg, server, nodeInfo, chroots, messageBusInfo=None):
        # Create a nodeType describing this client that will be passed
        # to the message bus and made available to interested listeners
        # (like the dispatcher)
        node = nodetypes.WorkerNode(name=cfg.name,
                                    host=cfg.hostName,
                                    slots=cfg.slots,
                                    jobTypes=cfg.jobTypes,
                                    buildFlavors=cfg.buildFlavors,
                                    loadThreshold=cfg.loadThreshold,
                                    nodeInfo=nodeInfo, chroots=chroots,
                                    chrootLimit=cfg.chrootLimit)

        # grab the message bus location from the rmake server.
        from rmake_plugins.multinode_client.server import client
        rmakeClient = client.rMakeClient(cfg.rmakeUrl)
        if not messageBusInfo:
            messageBus = None
            while not messageBus:
                try:
                    messageBus = rmakeClient.getMessageBusInfo()
                except errors.UncatchableExceptionClasses, e:
                    raise
                except Exception, e:
                    server.error('Could not contact rmake server at %r - waiting 5 seconds and retrying.', cfg.rmakeUrl)
                if not messageBus:
                    time.sleep(5)
                    
            messageBusHost, messageBusPort = messageBus.host, messageBus.port
        else:
            messageBusHost, messageBusPort = messageBusInfo
        nodeclient.NodeClient.__init__(self, messageBusHost,
                                       messageBusPort,
                                       cfg, server, node)
        # Never give up on reconnecting to the messagebus, we want
        # nodes to keep attempting to reconnect forever.
        self.getBusClient().setConnectionTimeout(-1)

    def updateStatus(self, info, commandIds):
        """
            Send current status of node to messagebus to be picked up 
            by dispatcher
            @param info: current status of this node
            @type info: procutil.MachineInformation
        """
        m = messages.NodeInfo(info, commandIds)
        self.bus.sendMessage('/nodestatus', m)

    def messageReceived(self, m):
        """
            Direct messages accepted by rMake Node.
            @param m: messages.Message subclass.
        """
        nodeclient.NodeClient.messageReceived(self, m)
        if isinstance(m, messages.ConnectedResponse):
            self.bus.subscribe('/command?targetNode=%s' % m.getSessionId())
            self.server.busConnected(m.getSessionId())
        elif isinstance(m, messages.BuildCommand):
            self.server.info('Received build command')
            self.server.receivedBuildCommand(m)
        elif isinstance(m, messages.ActionCommand):
            self.server.info('Received action command')
            self.server.receivedActionCommand(m)
        elif isinstance(m, messages.StopCommand):
            self.server.info('Received stop command')
            self.server.receivedStopCommand(m)
        elif isinstance(m, messages.ResolveCommand):
            self.server.info('Received resolve command')
            self.server.receivedResolveCommand(m)
        elif isinstance(m, messages.LoadCommand):
            self.server.info('Received load command')
            self.server.receivedLoadCommand(m)
        else:
            self.server.info('Received unknown command')

    def commandErrored(self, commandId, message, traceback=''):
        """
            Send status to messagebus about command commandId
        """
        m = messages.CommandStatus()
        if not isinstance(message, failure.FailureReason):
            failureReason = failure.CommandFailed(commandId, message, traceback)
        else:
            failureReason = message
        m.set(commandId, m.ERROR, failureReason)
        self.bus.sendMessage('/commandstatus', m)

    def commandCompleted(self, commandId):
        """
            Send status to messagebus about worker command commandId
        """
        m = messages.CommandStatus()
        m.set(commandId, m.COMPLETED)
        self.bus.sendMessage('/commandstatus', m)

    def emitEvents(self, jobId, eventList):
        """
            Send in-progress status updates on events affecting troves
        """
        m = messages.EventList()
        m.set(jobId, eventList)
        # send synchronous message tells the node not to return until
        # the messages are sent.  We want events to be high-priority
        # messages that get
        self.bus.sendSynchronousMessage('/event', m)

    @api(version=1)
    @api_return(1, None)
    def listChroots(self, callData):
        """
            Part of node XMLRPC interface.  List all chroot names
            known about for this node.
        """
        return self.server.listChroots()

    @api(version=1)
    @api_return(1, None)
    def listCommands(self, callData):
        """
            Part of node XMLRPC interface.  List all commands that are
            Currently queued or active on this node.
        """
        return (
            [ x.getCommandId() for x in self.server.listQueuedCommands() ],
            [ (x.getCommandId(), x.pid) for x in self.server.listCommands() ])

    @api(version=1)
    @api_parameters(1, 'str', 'str', 'bool', None)
    @api_return(1, None)
    def startChrootSession(self, callData, chrootPath, command, 
                           superUser=False, buildTrove=None):
        """
            Part of rMake node XMLRPC interface.  The rMake
            server uses these methods to communicate directly to a
            node without going through the dispatcher.

            Basically a passthrough
            to worker.startSession.
            Returns (True, (hostName, port)) if the connection succeeds.
            Returns (False, FailureReason) if it fails.
        """
        if buildTrove:
            buildTrove = thaw('BuildTrove', buildTrove)
        passed, results =  self.server.startSession('_local_', chrootPath,
                                                    command, superUser, buildTrove)
        if not passed:
            results = freeze('FailureReason', results)
        return passed, results

    @api(version=1)
    @api_parameters(1, 'str', 'str')
    @api_return(1, None)
    def archiveChroot(self, callData, chrootPath, newPath):
        """
            Part of rMake node XMLRPC interface.  The rMake
            server uses these methods to communicate directly to a
            node without going through the dispatcher.
        """
        return self.server.archiveChroot('_local_', chrootPath, newPath)

    @api(version=1)
    @api_parameters(1, 'str')
    @api_return(1, None)
    def deleteChroot(self, callData, chrootPath):
        """
            Part of rMake node XMLRPC interface.  The rMake
            server uses these methods to communicate directly to a
            node without going through the dispatcher.

            Basically a passthrough to deleteChroot.
        """
        return self.server.deleteChroot('_local_', chrootPath)


class WorkerNodeRPCClient(object):
    """
        XMLRPC client for communicating to rMake Node.

        client: connected messagebus session.
        sessionId: sessionId of rMake node to communicate with.
    """
    def __init__(self, client, sessionId):
        self.proxy = busclient.SessionProxy(WorkerNodeClient, client, sessionId)

    def listCommands(self):
        return self.proxy.listCommands()

    def listChroots(self):
        return self.proxy.listChroots()

    def getStatus(self):
        raise NotImplementError

    def startChrootSession(self, chrootPath, command, superUser=False, 
                           buildTrove=None):
        """
            Starts a chroot session on the given node.
        """
        if buildTrove is None:
            buildTrove = ''
        else:
            buildTrove = freeze('BuildTrove', buildTrove)
        return self.proxy.startChrootSession(chrootPath, command, superUser, 
                                            buildTrove)

    def archiveChroot(self, chrootPath, newPath):
        return self.proxy.archiveChroot(chrootPath, newPath)

    def deleteChroot(self, chrootPath):
        return self.proxy.deleteChroot(chrootPath)

class RmakeBusPublisher(subscriber._RmakePublisherProxy):
    """
        Receives events in unfrozen form, freezes them and puts them
        on the message bus.

        @param jobId: jobId for the events being logged
        @param client: WorkerNodeClient instance
    """
    def __init__(self, jobId, client):
        self.jobId = jobId
        self.client = client
        subscriber._RmakePublisherProxy.__init__(self)

    def _emitEvents(self, apiVer, eventList):
        self.client.emitEvents(self.jobId, eventList)

class DirectRmakeBusPublisher(RmakeBusPublisher):
    """
        Receives events already frozen and publishes them directly.
        Overrides _receiveEvents where events are frozen.
    """
    def _freezeEvents(self, apiVer, frozenEventList):
        """
            Events on this bus are already frozen (they come from
            the command)
        """
        return self.jobId, frozenEventList
