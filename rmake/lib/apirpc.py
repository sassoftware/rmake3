#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Along with apiutils, implements an API-validating and versioning scheme for 
rpc calls.

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
import urllib
import xmlrpclib

from conary.lib import coveragehook

from rmake import constants, errors

from rmake.lib import apiutils
from rmake.lib import localrpc
from rmake.lib import rpclib
from rmake.lib import server
from rmake.lib.apiutils import api, api_parameters, api_return
from rmake.lib import logger

# This version describes the current iteration of the API protocol.
_API_VERSION = 1

class ApiProxy(object):
    _apiMajorVersion = constants.apiMajorVersion
    _apiMinorVersion = constants.apiMinorVersion

    def __init__(self, apiClass, requestFn, uri):
        self.apiClass = apiClass
        self.uri = uri
        self._requestFn = requestFn
        self._methods = {}
        self._addMethods(apiClass)

    def __repr__(self):
        return "<ApiProxy>"

    def __str__(self):
        return "<ApiProxy>"

    def _addMethods(self, apiClass):
        for name, methodApi in apiClass._listClassMethods():
            self._methods[name] = methodApi

    def __getattr__(self, name):
        """ Get a proxy for an individual method.  """
        if name not in self._methods:
            raise ApiError, 'cannot find method %s in api' % name
        methodApi = self._methods[name]

        return _ApiMethod(self._requestFn, name, self.uri,
                          self._apiMajorVersion, self._apiMinorVersion,
                          methodApi)

class XMLApiProxy(ApiProxy, localrpc.ServerProxy):

    def __init__(self, apiClass, uri):
        localrpc.ServerProxy.__init__(self, uri)
        ApiProxy.__init__(self, apiClass, self._ServerProxy__request, uri)


class _ApiMethod(xmlrpclib._Method):
    """ Api-aware method proxy for xmlrpc.  """

    def __init__(self, request, name, loc, apiMajorVersion, apiMinorVersion,
                 methodApi):
        """
            @param metaApiVersion: version of apirpc data.
            @param clientVersion: client's version the whole server API
            @param methodApi: client's description of this method's API
        """
        xmlrpclib._Method.__init__(self, request, name)
        self._apiMajorVersion = apiMajorVersion
        self._apiMinorVersion = apiMinorVersion
        self.__methodApi = methodApi
        self.__loc = loc

    def __call__(self, *args):
        """ 
            Calls the remote method with args.  Passes in extra first tuple
            of API callData.
        """
        methodVersion = self.__methodApi.version

        args = list(_freezeParams(self.__methodApi, args, methodVersion))
        callData = dict(apiMajorVersion = self._apiMajorVersion,
                        apiMinorVersion = self._apiMinorVersion,
                        methodVersion = methodVersion)

        try:
            passed, rv = xmlrpclib._Method.__call__(self, callData, *args)
        except socket.error, err:
            if isinstance(self.__loc, str):
                uri = self.__loc
                type, host = urllib.splittype(uri)
                host, rest = urllib.splithost(host)
                user, host = urllib.splituser(host)
                if user:
                    user = '<user>:<password>@'
                else:
                    user = ''
                uri = '%s://%s%s%s' % (type, user, host, rest)
            else:
                uri = self.__loc
            raise errors.OpenError(
                'Error communicating to server at %s: %s' % (uri,
                                                             err.args[1]))
        if passed:
            return _thawReturn(self.__methodApi, rv, methodVersion)
        else:
            raise apiutils.thaw(rv[0], rv[1])

class BaseRPCLogger(logger.Logger):
    def logRPCCall(self, callData, methodName, args):
        pass

class ApiServer(server.Server):
    _apiMajorVersion = constants.apiMajorVersion
    _apiMinorVersion = constants.apiMinorVersion

    _debug = False
    def __init__(self, logger=None, forkByDefault = False):
        if logger is None:
            logger = BaseRPCLogger('server')
        server.Server.__init__(self, logger)
        self._forkByDefault = forkByDefault
        self._methods = {}
        self._addMethods(self)

    def _authCheck(self, callData, fn, *args, **kw):
        return True

    def _serveLoopHook(self):
        pass

    def _dispatch(self, methodName, (auth, responseHandler, params)):
        try:
            return self._dispatch2(methodName, auth, responseHandler, params)
        except Exception, err:
            responseHandler.sendResponse((False, _freezeException(err)))

    def _getMethod(self, methodName):
        if methodName.startswith('_'):
            raise NoSuchMethodError(methodName)
        if methodName not in self._methods:
            raise NoSuchMethodError(methodName)
        return self._methods[methodName]

    @classmethod
    def _listClassMethods(class_):
        for name in dir(class_):
            attr = getattr(class_, name)
            if hasattr(attr, 'allowed_versions') and hasattr(attr, '__call__'):
                yield name, attr

    def _listMethods(self):
        for name in dir(self):
            attr = getattr(self, name)
            if hasattr(attr, 'allowed_versions') and hasattr(attr, '__call__'):
                yield name, attr

    def _addMethods(self, apiServer):
        for name, attr in apiServer._listMethods():
            self._methods[name] = attr

    def _shouldMethodFork(self, method):
        if hasattr(method, 'forking'):
            return method.forking
        return self._forkByDefault

    def _dispatch2(self, methodName, auth, responseHandler, args):
        """Dispatches call to methodName, unfreezing data in args, checking
           method version as well.
        """
        method = self._getMethod(methodName)
        if not isinstance(args[0], dict):
            raise ApiError('Incompatible server API')
        callData = CallData(auth, args[0], self._logger, method,
                            responseHandler, debug=self._debug,
                            authMethod=self._authCheck)
        args = args[1:]
        apiMajorVersion = callData.getApiMajorVersion()
        apiMinorVersion = callData.getApiMinorVersion()
        methodVersion = callData.getMethodVersion()

        if apiMajorVersion != self._apiMajorVersion:
            raise ApiError('Incompatible server API; '
                'server supports %s, client supports %s' %
                    (self._apiMajorVersion, apiMajorVersion))

        if methodVersion not in method.allowed_versions:
            raise RuntimeError(
                    '%s: unsupported method version %s' % (methodName, version))

        args = list(_thawParams(method, args, methodVersion))

        timestr = time.strftime('%x %X')
        self._logger.logRPCCall(callData, methodName, args)
        if self._shouldMethodFork(method):
            responseHandler.forkResponseFn(lambda: self._fork(methodName),
                                           callData.callFunction, method,
                                           callData, *args)
        else:
            responseHandler.callResponseFn(callData.callFunction,
                                           method, callData, *args)

    def getReturnValue(self, rv, method, methodVersion):
        if rv != None:
            return True, _freezeReturn(method, rv, methodVersion)
        # By default, we return empty string since None is not allowed
        return True, ''

    @api(version=1)
    @api_parameters(1)
    @api_return(1, 'bool')
    def ping(self, callData):
        return True


class XMLApiServer(ApiServer):
    """ API-aware server wrapper for XMLRPC. """

    # if set to True, will try to send exceptions to a debug prompt on 
    # the console before returning them across the wire

    def __init__(self, uri=None, logger=None, forkByDefault=False, 
                 sslCertificate=None, localOnly=False):
        """ @param serverObj: The XMLRPCServer that will serve data to 
            the _dispatch method.  If None, caller is responsible for 
            giving information to be dispatched.
        """
        ApiServer.__init__(self, logger, forkByDefault=forkByDefault)
        self.uri = uri
        if uri:
            if isinstance(uri, str):
                import urllib
                type, url = urllib.splittype(uri)
                if type == 'unix':
                    serverObj = rpclib.UnixDomainDelayableXMLRPCServer(url,
                                                            logRequests=False)
                    serverObj.setAuthMethod(rpclib.SocketAuth)
                elif type in ('http', 'https'):
                    # path is ignored with simple server.
                    host, path = urllib.splithost(url)
                    if ':' in host:
                        host, port = urllib.splitport(host)
                        port = int(port)
                    else:
                        port = 80
                    # Make serving on localhost not necessarily resolve to only
                    # serving locally
                    if host == 'localhost' and not localOnly:
                        host = ''

                    serverObj = rpclib.DelayableXMLRPCServer((host, port),
                                                         logRequests=False,
                                                         ssl=type=='https',
                                                         sslCert=sslCertificate)
                    serverObj.setAuthMethod(rpclib.HttpAuth)
            else:
                serverObj = uri
        else:
            serverObj = None

        self.server = serverObj

        if serverObj:
            serverObj.register_instance(self)

    def _close(self):
        ApiServer._close(self)
        if self.server:
            self.server.server_close()

    def handleRequestIfReady(self, sleepTime=0.1):
        try:
            ready, _, _ = select.select([self.server], [], [], sleepTime)
        except select.error, err:
            ready = None
        if ready:
            self.server.handle_request()

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
    if isinstance(val, rpclib.ResponseModifier):
        return val
    returnType = api.returnType[version]
    if returnType is None:
        return val
    if isinstance(returnType, tuple):
        return returnType[0](val)
    return returnType.__freeze__(val)

def _freezeException(err):
    try:
        frzMethod = None
        errorClass = err.__class__
        if apiutils.canHandle(str(errorClass), err):
            frzMethod = str(errorClass)
        elif apiutils.canHandle(errorClass.__name__, err):
            frzMethod = errorClass.__name__
        else:
            frzMethod = 'Exception'
        return frzMethod, apiutils.freeze(frzMethod, err)
    except Exception, err2:
        if frzMethod == 'Exception':
            raise
        err = err2
        frzMethod = 'Exception'
        return frzMethod, apiutils.freeze(frzMethod, err)

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
    if r is not None:
        val = r.__thaw__(val)
    return val

class ApiError(Exception):
    pass

class NoSuchMethodError(ApiError):
    def __init__(self, method):
        self.method = method
        ApiError.__init__(self, 'No such method: %s' % method)

class CallData(object):
    __slots__ = ['auth', 'apiMajorVersion', 'apiMinorVersion', 'methodVersion',
                 'logger', 'method', 'responseHandler', 'debug',
                 'authMethod']
    def __init__(self, auth, callData, logger, method, responseHandler,
                 debug=False, authMethod=None):
        self.apiMajorVersion = callData['apiMajorVersion']
        self.apiMinorVersion = callData['apiMinorVersion']
        self.methodVersion = callData['methodVersion']
        self.auth = auth
        self.logger = logger
        self.method = method
        self.responseHandler = responseHandler
        self.debug = debug
        self.authMethod = authMethod

    def callFunction(self, fn, *args, **kw):
        try:
            if self.authMethod:
                self.authMethod(self, fn, *args, **kw)
            rv =  fn(*args, **kw)
            if isinstance(rv, rpclib.ResponseModifier):
                return rv
            if rv != None:
                rv =  _freezeReturn(self.method, rv, self.methodVersion)
            else:
                rv = ''
            response = (True, rv)
        except Exception, err:
            response = (False, _freezeException(err))
            if self.debug:
                from conary.lib import epdb
                epdb.post_mortem(sys.exc_info()[2])
        return response

    def respondWithFunction(self, fn, *args, **kw):
        self.responseHandler.callResponseFn(self.callFunction, fn, *args, **kw)

    def respond(self, response):
        self.responseHandler.sendResponse((True, response))

    def respondWithException(self, exception):
        self.responseHandler.sendResponse((False, _freezeException(exception)))

    def delay(self):
        return rpclib.DelayedResponse()

    def getApiMajorVersion(self):
        return self.apiMajorVersion

    def getApiMinorVersion(self):
        return self.apiMinorVersion

    def getMethodVersion(self):
        return self.methodVersion

    def getAuth(self):
        return self.auth



