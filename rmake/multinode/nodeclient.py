#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
