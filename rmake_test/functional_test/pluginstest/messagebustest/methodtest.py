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


import os

from rmake_test import rmakehelp

from conary.deps import deps

from rmake import errors

from rmake.lib import apirpc
from rmake.lib.apiutils import api, api_parameters, api_return, freeze, thaw

class Node(apirpc.ApiServer):
    _CLASS_API_VERSION = 1
    sessionClass = 'NODE'

    @api(version=1)
    @api_parameters(1, 'flavor')
    @api_return(1, 'flavor')
    def getResults(self, callData, value):
        return value

    @api(version=1)
    @api_parameters(1, 'str')
    @api_return(1, 'str')
    def raiseError(self, callData, value):
        raise errors.RmakeError(value)

    def messageReceived(self, m):
        pass

    def __init__(self, messageBusPort):
        apirpc.ApiServer.__init__(self)
        self.client = busclient.MessageBusClient('localhost', messageBusPort,
                                                 dispatcher=self,
                                                 sessionClass=self.sessionClass,
                                                 connectionTimeout=10)
        self.client.logger.setQuietMode()

    def poll(self):
        return self.client.poll

class NodeClient(object):
    def __init__(self, client, sessionId):
        self.proxy = busclient.SessionProxy(Node, client, sessionId)

    def getResults(self, flavor):
        return self.proxy.getResults(flavor)

    def raiseError(self, str):
        return self.proxy.raiseError(str)

class MethodTest(rmakehelp.RmakeHelper):

    def importPlugins(self):
        global busclient, messagebus
        from rmake.messagebus import busclient
        from rmake.multinode.server import messagebus

    def testMethods(self):
        messageBusPort = self.startMessageBus()
        node = Node(messageBusPort)
        while not node.client.isRegistered():
            node.client.poll()
        pid = os.fork()
        if not pid:
            try:
                try:
                    node.client.serve()
                except Exception, err:
                    print err
            finally:
                os._exit(0)
        try:
            client = busclient.MessageBusClient('localhost', messageBusPort,
                                                dispatcher=None,
                                                sessionClass='NODE_CLI')
            while not client.isRegistered():
                client.poll()
            client = NodeClient(client, node.client.getSessionId())

            f = deps.parseFlavor('is:x86')
            assert(client.getResults(f) == f)
            try:
                client.raiseError('a')
                assert 0, 'should have raised error'
            except errors.RmakeError, err:
                assert(str(err) == 'a')
        finally:
            self._kill(pid)

    def testMessageBusMethods(self):
        messageBusPort = self.startMessageBus()
        node = Node(messageBusPort)
        while not node.client.isRegistered():
            node.client.poll()
        adminClient = messagebus.MessageBusRPCClient(node.client)
        xx = adminClient.listSessions()
        assert(xx == {node.client.getSessionId(): node.client.getSessionClass()})
        xx = adminClient.listQueueLengths()
        assert(xx == {node.client.getSessionId(): 0})
