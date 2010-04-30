#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#


import cPickle
import logging
import rmake.errors
from rmake.lib import apirpc
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
        request = cPickle.dumps((method, args, kwargs), 2)
        return self._transport.request(self._address, self.contentType,
                request, self._filter_response)

    @staticmethod
    def _filter_response(response):
        return cPickle.loads(response.read())


class PickleRPCResource(Resource):

    def __init__(self, server):
        self.methodstore = server

    def render_POST(self, request):
        request.content.seek(0, 0)
        request.setHeader('content-type', 'application/python-pickle')

        callData = self._getCallData(request)

        def call_func():
            funcName, args, kwargs = cPickle.loads(request.content.read())
            return self.methodstore._callMethod(funcName, callData, args,
                    kwargs)
        d = defer.maybeDeferred(call_func)

        def on_ok(result):
            return (True, result)
        def on_error(failure):
            if failure.check(rmake.errors.RmakeError):
                return (False, failure.value)
            else:
                log.error("Unhandled exception in RPC method:\n%s",
                        failure.getTraceback())
                return (False, rmake.errors.InternalServerError())
        d.addCallbacks(on_ok, on_error)

        @d.addCallback
        def do_render(result):
            request.write(cPickle.dumps(result, 2))
            request.finish()

        @d.addErrback
        def render_crashed(failure):
            logger.logFailure(failure, "Crash in RPC response rendering:")
            request.setResponseCode(500)
            request.finish()

        return NOT_DONE_YET

    def _getCallData(self, request):
        return apirpc.CallData(auth=None, clientAddr=request.getClientIP())
