#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
"""
Along with apiutils, implements an API-validating and versioning scheme for 
xmlrpc calls.

The ApiProxy is instantiated with a reference to the class of the server it is 
communicating with, and uses that information to determine the expected format 
of the parameters to the class.  It freezes classes appropriately, and then
calls the server.

The ApiProxy also passes in as its first parameter a list of information.
that includes the ApiProxy version, and the version information about the 
server and the method.

The XMLApiServer is a wrapper around an XMLRPC server that manages the 
information passed in by an API Proxy.  It also validated and transforms the 
method parameters

A server class's public interface should be decorated with decorators
from apiutils that describe how to convert its parameters.

Server methods also will be passed in callData that includes the
calling version of the method.
"""
import itertools
import select
import socket
import sys
import time
import traceback
import xmlrpclib

from conary.lib import log
from conary.lib import coveragehook

from rmake import errors
from rmake.lib import apiutils
from rmake.lib import localrpc
from rmake.lib import server
from rmake.lib import auth
from rmake.lib.apiutils import api, api_parameters, api_return

# This version describes the current iteration of the API protocol.
_API_VERSION = 1


class ApiProxy(localrpc.ServerProxy):

    def __init__(self, apiClass, uri):
        self.apiClass = apiClass
        self.clientVersion = self.apiClass._CLASS_API_VERSION
        self.uri = uri
        localrpc.ServerProxy.__init__(self, uri)

    def __repr__(self):
        return "<ApiProxy>"

    def __str__(self):
        return "<ApiProxy>"

    def __getattr__(self, name):
        """ Get a proxy for an individual method.  """
        try:
            methodApi = getattr(self.apiClass, name)
        except AttributeError:
            raise ApiError, 'cannot find method %s in api' % name

        return _ApiMethod(self._ServerProxy__request, name, self.uri,
                          _API_VERSION, self.clientVersion, methodApi)

class _ApiMethod(xmlrpclib._Method):
    """ Api-aware method proxy for xmlrpc.  """

    def __init__(self, request, name, uri, metaApiVersion, clientVersion, 
                 methodApi): 
        """
            @param metaApiVersion: version of apirpc data.
            @param clientVersion: client's version the whole server API
            @param methodApi: client's description of this method's API
        """
        xmlrpclib._Method.__init__(self, request, name)
        self.__metaApiVersion = metaApiVersion
        self.__clientVersion = clientVersion
        self.__methodApi = methodApi
        self.__uri = uri

    def __call__(self, *args):
        """ 
            Calls the remote method with args.  Passes in extra first tuple
            of API callData.
        """
        methodVersion = self.__methodApi.version

        args = list(_freezeParams(self.__methodApi, args, methodVersion))
        callData = (self.__metaApiVersion, self.__clientVersion, methodVersion)

        try:
            passed, rv = xmlrpclib._Method.__call__(self, callData, *args)
        except socket.error, err:
            raise errors.OpenError(
                'Error communicating to server at %s: %s' % (self.__uri,
                                                             err.args[1]))
        if passed:
            return _thawReturn(self.__methodApi, rv, methodVersion)
        else:
            raise apiutils.thaw(rv[0], rv[1])

class XMLApiServer(server.Server):
    """ API-aware server wrapper for XMLRPC. """

    # if set to True, will try to send exceptions to a debug prompt on 
    # the console before returning them across the wire
    debug = False

    def __init__(self, uri=None, logRequests=True):
        """ @param serverObj: The XMLRPCServer that will serve data to 
            the _dispatch method.  If None, caller is responsible for 
            giving information to be dispatched.
        """
        server.Server.__init__(self)
        self.uri = uri
        if uri:
            if isinstance(uri, str):
                import urllib
                type, url = urllib.splittype(uri)
                if type == 'unix':
                    serverObj = auth.AuthAwareUnixDomainXMLRPCServer(url, logRequests=logRequests)
                elif type == 'http':
                    # path is ignored with simple server.
                    host, path = urllib.splithost(url)
                    if ':' in host:
                        host, port = urllib.splitport(host)
                        port = int(port)
                    else:
                        port = 80

                    serverObj = auth.AuthAwareXMLRPCServer((host, port), logRequests=logRequests)
                elif type == 'https':
                    raise NotImplementedError
            else:
                serverObj = uri
        else:
            serverObj = None

        self.server = serverObj

        if serverObj:
            serverObj.register_instance(self)

    def handleRequestIfReady(self, sleepTime):
        try:
            ready, _, _ = select.select([self.server], [], [], sleepTime)
        except select.error, err:
            ready = None
        if ready:
            self.server.handle_request()

    def _serveLoopHook(self):
        pass

    def _dispatch(self, methodname, (auth, args)):
        try:
            rv = self._dispatch2(methodname, (auth, args))
        except Exception, err:
            if self.debug:
                if sys.stdin.isatty() and sys.stdout.isatty():
                    import epdb
                    epdb.post_mortem(sys.exc_info()[2])
            return False, self._freezeException(err)
        else:
            return True, rv

    def _freezeException(self, err):
        errorClass = err.__class__
        if apiutils.isRegistered(str(errorClass)):
            frzMethod = str(errorClass)
        elif apiutils.isRegistered(errorClass.__name__):
            frzMethod = errorClass.__name__
        else:
            frzMethod = 'Exception'
        return frzMethod, apiutils.freeze(frzMethod, err)

    def _dispatch2(self, methodname, (auth, args)):
        """Dispatches call to methodname, unfreezing data in args, checking
           method version as well.
        """
        method = getattr(self, methodname, None)
        if not method:
            raise NoSuchMethodError(methodname)

        callData = CallData(auth, args[0])
        args = args[1:]
        apiVersion    = callData.getApiVersion()
        clientVersion = callData.getClientVersion()
        methodVersion = callData.getMethodVersion()

        if apiVersion != _API_VERSION:
            raise ApiError('Incompatible server API')


        if clientVersion != self._CLASS_API_VERSION:
            raise RuntimeError(
                    '%s: unsupported client version %s' % (methodname, version))

        if methodVersion not in method.allowed_versions:
            raise RuntimeError(
                    '%s: unsupported method version %s' % (methodname, version))

        args = list(_thawParams(method, args, methodVersion))

        timestr = time.strftime('%x %X')
        log.info('[%s] method: %s\n    credentials: %s' % (timestr, methodname,
                                                           auth))
        rv = method(callData, *args)

        if rv != None:
            rv = _freezeReturn(method, rv, methodVersion)
            return rv

        # By default, we return empty string since None is not allowed
        return ''

    @api(version=1)
    @api_parameters(1)
    @api_return(1, 'bool')
    def ping(self, callData):
        return True

# ---- helper functions

def _freezeParams(api, paramList, version):
    paramTypes = api.params[version]
    if len(paramTypes) != len(paramList):
        raise ApiError, 'Wrong number of parameters to %s' % api
    rv = []
    for paramType, param in itertools.izip(paramTypes, paramList):
        if paramType is None:
            yield param
        elif isinstance(paramType , tuple):
            yield paramType[0](param)
        else:
            yield paramType.__freeze__(param)

def _freezeReturn(api, val, version):
    returnType = api.returnType[version]
    if returnType is None:
        return val
    if isinstance(returnType, tuple):
        return returnType[0](val)
    return returnType.__freeze__(val)

def _thawParams(api, paramList, version):
    paramTypes = api.params[version]
    if len(paramTypes) < len(paramList):
        raise ApiError, 'Wrong number of parameters to %s' % api
    rv = []
    for paramType, param in itertools.izip(paramTypes, paramList):
        if paramType is None:
            yield param
        elif isinstance(paramType, tuple):
            yield paramType[1](param)
        else:
            yield paramType.__thaw__(param)

def _thawReturn(api, val, version):
    r = api.returnType[version]
    if r is None:
        return val
    if isinstance(r, tuple):
        return paramType[1](param)
    return r.__thaw__(val)

class ApiError(Exception):
    pass

class NoSuchMethodError(ApiError):
    def __init__(self, method):
        self.method = method
        ApiError.__init__(self, 'No such method: %s' % method)

class CallData(object):
    __slots__ = ['auth', 'apiVersion', 'clientVersion', 'methodVersion']
    def __init__(self, auth, callTuple):
        apiVersion, clientVersion, methodVersion = callTuple
        self.apiVersion = apiVersion
        self.clientVersion = clientVersion
        self.methodVersion = methodVersion
        self.auth = auth

    def getApiVersion(self):
        return self.apiVersion

    def getClientVersion(self):
        return self.clientVersion

    def getMethodVersion(self):
        return self.methodVersion

    def getAuth(self):
        return self.auth



