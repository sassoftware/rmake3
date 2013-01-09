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


import logging
from rmake import errors
from rmake.lib import apirpc
from rmake.lib import chutney
from rmake.lib import logger
from rmake.lib import rpcproxy
from twisted.internet import defer
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET

log = logging.getLogger(__name__)


class PickleServerProxy(rpcproxy.GenericServerProxy):

    contentType = 'application/python-pickle'

    def _request(self, method, args, kwargs):
        ok, result = self._marshal_call(method, args, kwargs)
        if ok:
            return result
        else:
            raise result

    def _marshal_call(self, method, args, kwargs):
        request = chutney.dumps((method, args, kwargs))
        return self._transport.request(self._address, self.contentType,
                request, self._filter_response)

    @staticmethod
    def _filter_response(response):
        return chutney.loads(response.read())


class PickleRPCResource(Resource):

    def __init__(self, server):
        self.methodstore = server

    def render_POST(self, request):
        request.content.seek(0, 0)
        request.setHeader('content-type', 'application/python-pickle')

        callData = self._getCallData(request)

        def call_func():
            funcName, args, kwargs = chutney.load(request.content)
            return self.methodstore._callMethod(funcName, callData, args,
                    kwargs)
        d = defer.maybeDeferred(call_func)

        def on_ok(result):
            return (True, result)
        def on_error(failure):
            if failure.check(errors.RmakeError):
                return (False, failure.value)
            else:
                log.error("Unhandled exception in RPC method:\n%s",
                        failure.getTraceback())
                return (False, errors.InternalServerError())
        d.addCallbacks(on_ok, on_error)

        @d.addCallback
        def do_render(result):
            request.write(chutney.dumps(result))
            request.finish()

        @d.addErrback
        def render_crashed(failure):
            logger.logFailure(failure, "Crash in RPC response rendering:")
            request.setResponseCode(500)
            request.finish()

        return NOT_DONE_YET

    def _getCallData(self, request):
        return apirpc.CallData(auth=None, clientAddr=request.getClientIP())
