#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import socket

from rmake.lib import apirpc

from rmake_plugins.messagebus import busclient

from rmake_plugins.multinode_client import messages

class NodeClient(apirpc.ApiServer):

    sessionClass = 'Anonymous'

    subscriptions = []
    

    def __init__(self, messageBusHost, messageBusPort, cfg, server, node=None,
                 logMessages=True):
        self.subscriptions = list(self.subscriptions) # copy from class
        self.cfg = cfg
        self.server = server
        self.node = node
        if logMessages:
            messageLogPath = cfg.logDir + '/messages/%s.log' % self.name
            logPath = cfg.logDir + '/%s.log' % self.name
        else:
            messageLogPath = logPath = None
        self.bus = busclient.MessageBusClient(messageBusHost,
                                              messageBusPort,
                                              dispatcher=self,
                                              sessionClass=self.sessionClass,
                                              logPath=logPath,
                                              messageLogPath=messageLogPath,
                                              subscriptions=self.subscriptions)
        apirpc.ApiServer.__init__(self, self.bus.logger)

    def messageReceived(self, m):
        if isinstance(m, messages.ConnectedResponse):
            if self.node:
                m = messages.RegisterNodeMessage()
                m.set(self.node)
                self.bus.sendMessage('/register', m)

    def getBusClient(self):
        return self.bus

    def handleRequestIfReady(self, sleepTime):
        self.poll(sleepTime, maxIterations=1)

    def isConnected(self):
        return self.bus.isConnected()

    def poll(self, *args, **kw):
        try:
            return self.bus.poll(*args, **kw)
        except socket.error, err:
            self.error('Socket connection died: %s' % err.args[1])
            self._halt = 1

    def disconnect(self):
        self.bus.close()

    def connect(self):
        self.bus.connect()
