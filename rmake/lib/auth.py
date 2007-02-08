#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

"""
Classes for extracting and examining authentification methods passed from 
external servers
"""
import fcntl
import IN
from SimpleXMLRPCServer import (SimpleXMLRPCServer, SimpleXMLRPCRequestHandler,
                                SimpleXMLRPCDispatcher)
import socket
import struct

from rmake.lib import localrpc

class HttpAuth(object):

    __slots__ = []

    def __init__(self):
        pass

    def __repr__(self):
        return 'HttpAuth()' 

class SocketAuth(object):
    __slots__ = ['pid', 'uid', 'gid']

    def __init__(self, sock):
        # get the peer credentials
        buf = sock.getsockopt(socket.SOL_SOCKET, IN.SO_PEERCRED, 12)
        creds = struct.unpack('iii', buf)
        self.pid = creds[0]
        self.uid = creds[1]
        self.gid = creds[2]

    def __repr__(self):
        return 'SocketAuth(pid=%s, uid=%s, gid=%s)' % (self.pid, self.uid, 
                                                       self.gid)


class AuthAwareXMLRPCMixin(object):
    def _getAuth(self, request, client_address):
        return None

    def verify_request(self, request, client_address):
        self.auth = self._getAuth(request, client_address)
        return True

    def _dispatch(self, method, params):
        return SimpleXMLRPCDispatcher._dispatch(self, method,
                                                (self.auth, params))


# FIXME: need to rename lib.xmlrpc or to combine all the xmlrpc server addons.
class ReusableXMLRPCServer(SimpleXMLRPCServer):
    def server_bind(self):
        self.allow_reuse_address = True
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)
        SimpleXMLRPCServer.server_bind(self)

class QuietXMLRPCRequestHandler(SimpleXMLRPCRequestHandler):
    def __init__(self, *args, **kw):
        self.verbose = False
        SimpleXMLRPCRequestHandler.__init__(self, *args, **kw)

    def setVerbose(self, b=True):
        self.verbose = b

    def log_message(self, format, *args):
        if self.verbose:
            SimpleXMLRPCServer.log_message(self, format, *args)


class AuthAwareXMLRPCServer(AuthAwareXMLRPCMixin, ReusableXMLRPCServer):
    def __init__(self, *args, **kw):
        ReusableXMLRPCServer.__init__(self, *args, **kw)

    def _getAuth(self, request, client_address):
        return HttpAuth()

    def server_bind(self):
        # cheat and add code to allow reusable addresses
        # here, w/o adding another mixin or super class.
        self.allow_reuse_address = True
        fcntl.fcntl(self.socket.fileno(), fcntl.FD_CLOEXEC)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)
        ReusableXMLRPCServer.server_bind(self)


class AuthAwareUnixDomainXMLRPCServer(AuthAwareXMLRPCMixin,
                                      localrpc.UnixDomainXMLRPCServer):

    def __init__(self, *args, **kw):
        localrpc.UnixDomainXMLRPCServer.__init__(self, *args, **kw)

    def _getAuth(self, request, client_address):
        return SocketAuth(request)
