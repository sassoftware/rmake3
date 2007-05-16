#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

"""
Classes for extracting and examining authentification methods passed from 
external servers
"""
import base64
import fcntl
import IN
import pwd
import sys
import os
from SimpleXMLRPCServer import (SimpleXMLRPCServer, SimpleXMLRPCRequestHandler,
                                SimpleXMLRPCDispatcher)
import xmlrpclib
import socket
import SocketServer
import struct

from rmake.lib import localrpc

# Secure server support
try:
    from M2Crypto import SSL
    from M2Crypto.SSL import SSLError
    from M2Crypto.SSL import Connection as SSLConnection
except ImportError:
    SSLError = None.__class__
    SSL = None
    SSLConnection = None


class AuthObject(object):
    __slots__ = ['headers']

    def __init__(self, request):
        self.headers = None

    def setHeaders(self, headers):
        self.headers = headers

class HttpAuth(AuthObject):

    __slots__ = [ 'user', 'password']

    def __init__(self, request):
        AuthObject.__init__(self, request)
        self.user = None
        self.password = None

    def setHeaders(self, headers):
        self.headers = headers
        if 'Authorization' in self.headers:
            userInfo = self.headers['Authorization']
            userPass = base64.b64decode(userInfo[6:])
            if userPass.count(":") > 1:
                raise RuntimeError('Password may not contain colons')
            user, password = userPass.split(':')
            self.user = user
            self.password = password
        self.headers = headers

    def getUser(self):
        return self.user

    def getPassword(self):
        return self.password

    def __repr__(self):
        if self.user:
            return 'HttpAuth(user=%s)' % self.user
        else:
            return 'HttpAuth()'

class SocketAuth(HttpAuth):
    __slots__ = ['pid', 'uid', 'gid', 'socketUser']

    def __init__(self, request):
        # get the peer credentials
        buf = request.getsockopt(socket.SOL_SOCKET, IN.SO_PEERCRED, 12)
        creds = struct.unpack('iii', buf)
        self.pid = creds[0]
        self.uid = creds[1]
        self.gid = creds[2]
        HttpAuth.__init__(self, request)

    def getSocketUser(self):
        return pwd.getpwuid(self.uid).pw_name

    def __repr__(self):
        return 'SocketAuth(pid=%s, uid=%s, gid=%s)' % (self.pid, self.uid,
                                                       self.gid)

class QuietXMLRPCRequestHandler(SimpleXMLRPCRequestHandler):
    def __init__(self, *args, **kw):
        self.verbose = False
        SimpleXMLRPCRequestHandler.__init__(self, *args, **kw)

    def setVerbose(self, b=True):
        self.verbose = b

    def log_message(self, format, *args):
        if self.verbose:
            SimpleXMLRPCServer.log_message(self, format, *args)


class DelayableXMLRPCRequestHandler(QuietXMLRPCRequestHandler):
    def do_POST(self):
        # reads in from self.rfile.
        # gets response from self.server._marshaled_dispatch
        # we need to break in here and say if response is None, send
        # no response.
        # possibly send in requestHandler to allow user
        # to send response later.
        # sends response back.
        try:
            # get arguments
            data = self.rfile.read(int(self.headers["content-length"]))
            # In previous versions of SimpleXMLRPCServer, _dispatch
            # could be overridden in this class, instead of in
            # SimpleXMLRPCDispatcher. To maintain backwards compatibility,
            # check to see if a subclass implements _dispatch and dispatch
            # using that method if present.
            self.server._marshaled_dispatch(data,
                                        StreamXMLRPCResponseHandler(self),
                                        self.headers)
        except: # This should only happen if the module is buggy
            # internal error, report as HTTP server error
            self.send_response(500)
            self.end_headers()

    def finish(self):
        pass

    def _finish(self):
        SimpleXMLRPCRequestHandler.finish(self)

class XMLRPCResponseHandler(object):
    def __init__(self, request, debug=True):
        self.request = request
        self.debug = debug

    def callResponseFn(self, fn, *args, **kw):
        try:
            rv = fn(*args, **kw)
            self.sendResponse(rv)
        except:
            self.sendInternalError()

    def sendInternalError(self, tb):
        pass

    def close(self):
        pass

    def forkResponseFn(self, forkFunction, fn, *args, **kw):
        pid = forkFunction()
        if pid:
            if SSL and isinstance(self.request.request, SSLConnection):
                sslsocket = self.request.request
                socket = sslsocket.socket
                sslsocket.close = socket.close
                sslsocket.shutdown = socket.shutdown
                sslsocket.sslbio = None
                sslsocket.sockbio = None
            return
        try:
            try:
                rv = fn(*args, **kw)
                self.sendResponse(rv)
                os._exit(0)
            except:
                if self.debug:
                    from conary.lib import epdb
                    epdb.post_mortem()
                self.sendInternalError()
        finally:
            os._exit(1)

    def serializeResponse(self, response):
        if isinstance(response, xmlrpclib.Fault):
            response = xmlrpclib.dumps(response)
        else:
            response = (response,)
            response = xmlrpclib.dumps(response, methodresponse=1)
        return response

    def sendResponse(self, response):
        try:
            if isinstance(response, NoResponse):
                # do nothing, response will be handled by a forked process
                return
            elif isinstance(response, DelayedResponse):
                # do nothing, response has been delayed,
                # to be handled by another call to this method.
                self._delayed = True
                return
            response = self.serializeResponse(response)
            self.transferResponse(response)
            self.close()
        except:
            # internal error, report as HTTP server error
            self.sendInternalError()
            self.close()
            self.request.send_response(500)
            self.request.end_headers()


class StreamXMLRPCResponseHandler(XMLRPCResponseHandler):

    def sendInternalError(self):
        self.request.send_response(500)
        self.request.end_headers()

    def close(self):
        self.request.wfile.flush()
        self.request.wfile.close()
        self.request.rfile.close()
        try:
            # FIXME: not possible w/ ssl connection 
            # after a fork, but still needed otherwise.
            # This seems to work.
            if not (SSL and isinstance(self.request.request, SSLConnection)):
                self.request.connection.shutdown(1)
            self.request.connection.close()
        except socket.error:
            pass

    def transferResponse(self, responseString):
        self.request.send_response(200)
        self.request.send_header("Content-type", "text/xml")
        self.request.send_header("Content-length", str(len(responseString)))
        self.request.end_headers()
        self.request.wfile.write(responseString)

class ResponseModifier(object):
    pass

class NoResponse(ResponseModifier):
    pass

class DelayedResponse(ResponseModifier):
    pass

class DelayableXMLRPCDispatcher(SimpleXMLRPCDispatcher):
    def __init__(self, *args, **kw):
        SimpleXMLRPCDispatcher.__init__(self, *args, **kw)
        self.authMethod = None

    def setAuthMethod(self, authMethod):
        self.authMethod = authMethod

    def _getAuth(self, request, client_address):
        if self.authMethod:
            return self.authMethod(request)
        else:
            return None

    def verify_request(self, request, client_address):
        self.auth = self._getAuth(request, client_address)
        return True

    def _marshaled_dispatch(self, data, responseHandler, headers):
        params, method = xmlrpclib.loads(data)
        if self.auth:
            self.auth.setHeaders(headers)
        # generate response
        try:
            self._dispatch(method, self.auth, responseHandler, params)
        except Fault, fault:
            responseHandler.sendResponse(fault)
        except:
            responseHandler.sendResponse(
                xmlrpclib.Fault(1, "%s:%s" % (sys.exc_type, sys.exc_value)))

    def _dispatch(self, method, auth, response_method, params):
        params = (self.auth, response_method, params)
        SimpleXMLRPCDispatcher._dispatch(self, method, params)

class DelayableXMLRPCServer(DelayableXMLRPCDispatcher, SimpleXMLRPCServer):
    def __init__(self, path, requestHandler=DelayableXMLRPCRequestHandler,
                 logRequests=1, ssl=False, sslCert=None):
        self.sslCert = sslCert
        self.ssl = ssl

        SimpleXMLRPCServer.__init__(self, path, requestHandler, logRequests)
        DelayableXMLRPCDispatcher.__init__(self)

    def server_bind(self):
        self.allow_reuse_address = True
        fcntl.fcntl(self.socket.fileno(), fcntl.FD_CLOEXEC)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)
        SimpleXMLRPCServer.server_bind(self)
        if self.ssl:
            if SSL is None:
                print "Please install m2crypto"
                sys.exit(1)
            ctx = SSL.Context("sslv23")
            ctx.load_cert_chain(self.sslCert, self.sslCert)
            self.socket = SSL.Connection(ctx, self.socket)

    def handle_request(self):
        try:
            return SimpleXMLRPCServer.handle_request(self)
        except SSLError, e:
            return

class UnixDomainDelayableXMLRPCRequestHandler(
                                     localrpc.UnixDomainHTTPRequestHandler,
                                     DelayableXMLRPCRequestHandler):
    pass

class UnixDomainDelayableXMLRPCServer(DelayableXMLRPCDispatcher,
                                      SocketServer.UnixStreamServer):
        def __init__(self, path,
                     requestHandler=UnixDomainDelayableXMLRPCRequestHandler,
                     logRequests=1):
            self.logRequests = logRequests
            DelayableXMLRPCDispatcher.__init__(self)
            umask = os.umask(0)
            SocketServer.UnixStreamServer.__init__(self, path, requestHandler)
            os.umask(umask)

