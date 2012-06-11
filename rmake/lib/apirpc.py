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




import inspect
from conary.lib.util import rethrow
from rmake import errors


def expose(func):
    """Decorator -- Mark a method as exposed for RPC."""
    func.rpc_exposed = True
    func.rpc_callData = False
    return func


def exposeWithCallData(func):
    """Decorator -- Mark a method as exposed for RPC with call data.

    The method should take a first argument (after self) called "callData".
    """
    func.rpc_exposed = True
    func.rpc_callData = True
    return func


class RPCServer(object):

    def __init__(self, children=()):
        self._rpc_children = dict(children)

    def _addChild(self, child, server):
        self._rpc_children[child] = server

    def _callMethod(self, methodName, callData, args, kwargs):
        if not methodName.startswith('_'):
            if '.' in methodName:
                first, rest = methodName.split('.', 1)
                server = self._rpc_children.get(first)
                if server:
                    return server._callMethod(rest, callData, args, kwargs)
            else:
                m = getattr(self, methodName, None)
                if m and getattr(m, 'rpc_exposed', False):
                    # Collapse arguments to a tuple early to make API error
                    # detection easier.
                    filler = ArgFiller.fromFunc(m)
                    if m.rpc_callData:
                        args = (self, callData) + args
                    else:
                        args = (self,) + args

            sock = self.server.socket
            if getattr(sock, 'socket', None):
                # m2crypto doesn't seem to pass close() through to the
                # underlying listener socket.
                sock.socket.close()
                    try:
                        args = filler.fill(args, kwargs)
                    except:
                        # Client passed wrong arguments.
                        rethrow(errors.APIError)

                    # Pull 'self' back out before invoking.
                    args = args[1:]
                    return m(*args)

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


class ArgFiller(object):
    """
    Tool for turning a function's positional + keyword arguments into a
    simple list as if positional.
    """
    _NO_DEFAULT = []

    def __init__(self, name, names, defaults):
        if not defaults:
            defaults = ()
        self.name = name
        self.names = tuple(names)
        self.numMandatory = len(names) - len(defaults)
        self.defaults = ((self._NO_DEFAULT,) * self.numMandatory) + defaults

    @classmethod
    def fromFunc(cls, func):
        names, posName, kwName, defaults = inspect.getargspec(func)
        assert not posName and not kwName # not supported [yet]
        return cls(func.func_name, names, defaults)

    def fill(self, args, kwargs):
        total = len(args) + len(kwargs)
        if total < self.numMandatory:
            raise TypeError("Got %d arguments but expected at least %d "
                    "to method %s" % (total, self.numMandatory, self.name))
        if len(args) + len(kwargs) > len(self.names):
            raise TypeError("Got %d arguments but expected no more than "
                    "%d to method %s" % (total, len(self.names), self.name))
        newArgs = []
        for n, (name, default) in enumerate(zip(self.names, self.defaults)):
            if n < len(args):
                # Input as positional
                newArgs.append(args[n])
                if name in kwargs:
                    raise TypeError("Got two values for argument %s to "
                            "method %s" % (name, self.name))
            elif name in kwargs:
                # Input as keyword
                newArgs.append(kwargs.pop(name))
            elif default is not self._NO_DEFAULT:
                # Not input but default available
                newArgs.append(default)
            else:
                # Missing
                raise TypeError("Missing argument %s to method %s"
                        % (name, self.name))
        if kwargs:
            raise TypeError("Got unexpected argument %s to method %s"
                    % (sorted(kwargs)[0], self.name))
        return tuple(newArgs)
