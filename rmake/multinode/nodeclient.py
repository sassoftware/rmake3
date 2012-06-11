#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


import socket

from rmake.lib import apirpc

from rmake.messagebus import busclient
from rmake.multinode import messages


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
        self.bus.disconnect()

    def connect(self):
        self.bus.connect()
