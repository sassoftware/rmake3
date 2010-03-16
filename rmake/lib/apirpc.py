#
# Copyright (c) 2006-2010 rPath, Inc.
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

from rmake import errors


def expose(func):
    """Decorator -- Mark a method as exposed for RPC."""
    func.rpc_exposed = True
    return func


class RPCServer(object):

    def _callMethod(self, methodName, callData, args, kwargs):
        if not methodName.startswith('_'):
            m = getattr(self, methodName, None)
            if m and getattr(m, 'rpc_exposed', False):
                return m(callData, *args, **kwargs)
        raise NoSuchMethodError(methodName)


class ApiError(errors.RmakeError):
    pass


class NoSuchMethodError(ApiError):
    def __init__(self, method):
        self.method = method
        ApiError.__init__(self, 'No such method: %s' % method)


class CallData(object):
    """Container for information about a RPC request.

    Specifically, it is used to relay details on who made the call and what
    authorizations they possess.
    """

    def __init__(self, auth, clientAddr):
        self.auth = auth
        self.clientAddr = clientAddr
