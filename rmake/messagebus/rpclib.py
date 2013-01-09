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


import sys
from rmake.messagebus import messages

from rmake.lib import apirpc
from rmake.lib import rpclib

class ResultsReceived(Exception):
    def __init__(self, results):
        self.results = results

    def get(self):
        return self.results


class MessageBusXMLRPCResponseHandler(rpclib.XMLRPCResponseHandler):
    def __init__(self, message, server):
        self.request = message
        self.server = server

    def serializeResponse(self, response):
        isOk, response = response

        if isOk:
            msg = messages.MethodResponse()
        else:
            msg = messages.MethodError()
        msg.set(self.request, response)
        return msg

    def transferResponse(self, message):
        self.server.sendMessage(message)

    def sendInternalError(self):
        err = apirpc._freezeException(sys.exc_info()[1])
        self.server.logger.exception("Unhandled exception in XMLRPC method:")
        self.server.sendMessage(self.serializeResponse((False, err)))


class SessionProxy(apirpc.ApiProxy):
    """
        Used to speak w/ one other client using RPC-like interface.
        The user is responsible for polling the client.
    """
    def __init__(self, apiClass, client, sessionId):
        apirpc.ApiProxy.__init__(self, apiClass)
        self._client = client
        self._sessionId = sessionId
        session = client.getSession()
        self._address = '[%s]:%s' % (session.host, session.port)

    def _marshal_call(self, methodName, params):
        if self._client.getSessionId() == self._sessionId:
            # Support for short-circuiting calls to yourself.
            m = self._client.makeRemoteMethodMessage(
                            self._sessionId, methodName, params)
            self._client.getSession().stamp(m)
            handler = ShimMessageBusResponseHandler(m)
            self._client._callLocalMethod(m, handler=handler)
            msg = handler.getResponse()
        else:
            if not self._client.isConnected():
                self._client.connect()
            while not self._client.isRegistered():
                self._client.poll()
            self._client.callRemoteMethod(self._sessionId, methodName, params)
            try:
                while True:
                    self._client.poll()
            except ResultsReceived, results:
                msg = results.get()
        return (not msg.isError(), msg.getReturnValue())


class ShimMessageBusResponseHandler(MessageBusXMLRPCResponseHandler):
    def __init__(self, message):
        self.response = None
        self.request = message

    def transferResponse(self, response):
        self.response = response

    def getResponse(self):
        return self.response
