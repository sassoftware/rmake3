#
# Copyright (c) 2008 rPath, Inc.  All rights reserved.
#

"""
A (hopefully) smarter and (definitely) more extensible XMLRPC proxy
framework.
"""

import base64
import urlparse
import xmlrpclib
from httplib import HTTPConnection

from rmake.lib.localrpc import UnixDomainHTTPConnection

VERSION = 0.1


# Address definitions
ADDRESS_SCHEMAS = {}
class _AddressRegistrar(type):
    def __init__(self, *args, **kw):
        type.__init__(self, *args, **kw)
        if not self.parseable:
            return
        schemas = self.schemas or [self.schema]
        for schema in schemas:
            ADDRESS_SCHEMAS[schema] = self


def parseAddress(uri):
    if ':' in uri:
        schema, _ = uri.split(':', 1)
        if schema in ADDRESS_SCHEMAS:
            return ADDRESS_SCHEMAS[schema].fromURI(uri)
        else:
            raise TypeError("Unknown schema %r in URI %r %r" % (schema, uri, ADDRESS_SCHEMAS))
    else:
        raise TypeError("%r does not look like a URI" % uri)


class Address(object):
    __metaclass__ = _AddressRegistrar
    schema = None
    schemas = None
    parseable = False
    fields = []

    def __init__(self, schema=None):
        if schema is not None:
            self.schema = schema

    def __repr__(self):
        params = set(self.fields) & set(self.__dict__)
        params = ', '.join('%s=%r' % (key, self.__dict__[key])
            for key in sorted(params))
        return '%s(%s)' % (self.__class__.__name__, params)

    def __str__(self):
        return self.asString(False)

    def __cmp__(self, other):
        return cmp(self.__dict__, other.__dict__)

    def asString(self, withPassword=True):
        return '<%s object (schema=%r)>' % (self.__class__.__name__,
            self.schema)

    @staticmethod
    def getHTTPAuthorization():
        """
        Get value for HTTP Authorization header, or C{None} if none
        should be sent.
        """
        return None

    @staticmethod
    def getHTTPHost():
        """
        Get value for HTTP Host header. In cases where a hostname does
        not make sense, the default (this functon) is suitable.
        """
        return 'localhost.localdomain'


class HTTPAddress(Address):
    schema = 'http'
    schemas = ['http', 'https']
    parseable = True
    fields = ['host', 'port', 'handler', 'schema', 'user']

    defaultPort = 80
    defaultHTTPSPort = 443

    def __init__(self, host, port, handler, user=None, password=None,
      schema=None):
        super(HTTPAddress, self).__init__(schema)
        self.host = host
        self.port = port
        self.handler = handler

        self.user = user
        self.password = password

        if schema == 'https':
            self.defaultPort = self.defaultHTTPSPort
        if port is None:
            self.port = self.defaultPort

    def asString(self, withPassword=True):
        if ':' in self.host:
            hostPart = '[%s]:%d' % (self.host, self.port)
        else:
            hostPart = '%s:%d' % (self.host, self.port)

        if self.user:
            if self.password and withPassword:
                userPart ='%s:%s@' % (self.user, self.password)
            else:
                userPart ='%s@' % (self.user,)
        else:
            userPart = ''

        return '%s://%s%s%s' % (self.schema, userPart, hostPart, self.handler)

    def setPassword(self, user, password):
        self.user = user
        self.password = password

    @classmethod
    def fromURI(cls, uri):
        # Explode the URI
        schema, netloc, path, query, fragment = urlparse.urlsplit(uri)
        user, password, host, port = cls.splitHost(netloc)

        # Reassemble the path and everything after it.
        handler = urlparse.urlunsplit(('', '', path, query, fragment))

        ret = cls(host, port, handler, schema=schema)
        if user or password:
            ret.setPassword(user, password)
        return ret

    @staticmethod
    def splitHost(netloc):
        # User credentials
        if '@' in netloc:
            creds, netloc = netloc.rsplit('@', 1)
            if ':' in creds:
                user, password = creds.split(':', 1)
            else:
                user, password = creds, ''
        else:
            user = password = None

        # IPv6-like bracketed host
        if netloc:
            i = netloc.rfind(':')
            j = netloc.rfind(']')
            if i > j:
                port = netloc[i+1:]
                try:
                    port = int(port)
                except ValueError:
                    raise ValueError("nonnumeric port: %r" % port)
                netloc = netloc[:i]
            else:
                port = None
            if netloc[0] == '[' and netloc[-1] == ']':
                host = netloc[1:-1]
            else:
                host = netloc
        else:
            host, port = None, None

        return user, password, host, port

    def getHTTPHost(self):
        return '%s:%d' % (self.host, self.port)

    def getHTTPAuthorization(self):
        if self.user:
            return 'Basic ' + base64.b64encode('%s:%s' % (
                self.user, self.password))
        else:
            return None


class ShimAddress(Address):
    schema = 'shim'
    fields = ['server']

    def __init__(self, server):
        super(Address, self).__init__()
        self.server = server

    def asString(self, withPassword=True):
        serverType = self.server.__class__
        return '%s://%s.%s' % (self.schema, 
            serverType.__module__, serverType.__name__)


class UnixAddress(HTTPAddress):
    schema = 'unix'
    schemas = ['unix'] # prevent fall-through from HTTPAddress
    parseable = True
    fields = ['path']

    # Dummies for fields that HTTP uses but that don't make sense
    # for UNIX sockets.
    host = 'localhost.localdomain'
    port = 80
    handler = '/'
    user = password = None

    def __init__(self, path):
        super(Address, self).__init__()
        self.path = path

    def asString(self, withPassword=True):
        return '%s://%s' % (self.schema, self.path)

    @classmethod
    def fromURI(cls, uri):
        if not uri.startswith('unix://'):
            raise ValueError("Invalid unix socket URI %r" % uri)
        return cls(uri[7:])


class ProtocolError(RuntimeError):
    def __init__(self, address, status, reason):
        RuntimeError.__init__(self)
        self.address = address
        self.status = status
        self.reason = reason

    def __repr__(self):
        return 'ProtocolError(%r, %r, %r)' % (self.address,
            self.status, self.reason)

    def __str__(self):
        return '<ProtocolError %d %s for %s>' % (self.status, self.reason,
            self.address)


# Transport definitions
class Transport(object):
    def __init__(self, **kwargs):
        """
        NB: To simplify calling conventions, subclasses should accept
        arbitrary keyword arguments, and pass them to their superclass.
        """
        pass

    def request(self, address, request_body):
        raise NotImplementedError

    @staticmethod
    def getparser():
        return xmlrpclib.getparser()

    def parse_request(self, data):
        parser, unmarshaller = self.getparser()
        parser.feed(data)
        parser.close()
        return unmarshaller.close(), unmarshaller.getmethodname()

    def parse_response(self, response):
        parser, unmarshaller = self.getparser()

        while True:
            data = response.read(1024)
            if not data:
                break
            parser.feed(data)

        response.close()
        parser.close()
        return unmarshaller.close()


class HTTPTransport(Transport):
    connectionClass = HTTPConnection
    userAgent = "rpath_xmlrpclib/%s (www.rpath.com)" % VERSION
    contentType = 'text/xml'

    def __init__(self, connectionClass=None, **kwargs):
        super(HTTPTransport, self).__init__(**kwargs)
        if connectionClass:
            self.connectionClass = connectionClass

    def request(self, address, request_body):
        conn = self.make_connection(address)
        self.send_request(conn, address)
        self.send_host(conn, address)
        self.send_user_agent(conn)
        self.send_authorization(conn, address)
        self.send_content(conn, request_body)

        response = conn.getresponse()
        if response.status != 200:
            raise ProtocolError(address, response.status, response.reason)

        ret = self.parse_response(response)
        self.close_connection(conn)

        if len(ret) == 1:
            return ret[0]
        else:
            return ret

    def make_connection(self, address):
        return self.connectionClass(address.host, address.port)

    @staticmethod
    def send_request(conn, address):
        conn.putrequest('POST', address.handler,
            skip_host=True, skip_accept_encoding=True)

    @staticmethod
    def send_host(conn, address):
        conn.putheader('Host', address.getHTTPHost())

    def send_user_agent(self, conn):
        conn.putheader('User-agent', self.userAgent)

    @staticmethod
    def send_authorization(conn, address):
        auth = address.getHTTPAuthorization()
        if auth is not None:
            conn.putheader('Authorization', auth)

    def send_content(self, conn, request_body):
        conn.putheader('Content-type', self.contentType)
        conn.putheader('Content-length', str(len(request_body)))
        conn.endheaders()
        if request_body:
            conn.send(request_body)

    @staticmethod
    def close_connection(conn):
        conn.close()


class ShimTransport(Transport):
    def __init__(self, **kwargs):
        self._response = None

    def request(self, address, request_body):
        params, method = self.parse_request(request_body)
        address.server._dispatch(method, (None, self, params))
        return self._response

    # Callbacks from server dispatcher
    def forkResponseFn(self, _forkFn, fn, *args, **kwargs):
        self._response = fn(*args, **kwargs)

    def callResponseFn(self, fn, *args, **kwargs):
        self._response = fn(*args, **kwargs)

    def sendResponse(self, response):
        self._response = response


class UnixDomainHTTPTransport(HTTPTransport):
    connectionClass = UnixDomainHTTPConnection

    def make_connection(self, address):
        return self.connectionClass(address.path)


# SSL transport is available when M2Crypto is installed
try:
    from M2Crypto import SSL
    from M2Crypto.httpslib import HTTPSConnection
except ImportError:
    class HTTPSTransport(object):
        def __init__(self, **kwargs):
            raise RuntimeError("HTTPS transport is not available because "
                "M2Crypto is not installed")
else:
    class ExtendedHTTPSConnection(HTTPSConnection):
        def __init__(self, *args, **kwargs):
            self.ignoreCommonName = kwargs.pop('ignoreCommonName', False)
            HTTPSConnection.__init__(self, *args, **kwargs)

        def connect(self):
            self.sock = SSL.Connection(self.ssl_ctx)
            if self.session:
                self.sock.set_session(self.session)
            if self.ignoreCommonName:
                self.sock.clientPostConnectionCheck = None
            self.sock.connect((self.host, self.port))


    class HTTPSTransport(HTTPTransport):
        connectionClass = ExtendedHTTPSConnection

        def __init__(self, ssl_ctx=None, key_file=None, cert_file=None,
          ignoreCommonName=False, **kwargs):
            super(HTTPSTransport, self).__init__(**kwargs)
            if ssl_ctx:
                self.ssl_ctx = ssl_ctx
            else:
                self.ssl_ctx = SSL.Context('sslv23')
                if key_file:
                    if not cert_file:
                        cert_file = key_file
                    self.ssl_ctx.load_cert(cert_file, key_file)
            self.ignoreCommonName = ignoreCommonName

        def make_connection(self, address):
            return self.connectionClass(address.host, address.port,
                ssl_context=self.ssl_ctx, ignoreCommonName=self.ignoreCommonName)


# Generic server proxy machinery
class Method(object):
    def __init__(self, send, name):
        self._send = send
        self._name = name

    def __repr__(self):
        return '%s(%r, %r)' % (self.__class__.__name__,
            self._send, self._name)

    def __call__(self, *args):
        return self._send(self._name, args)

    def __getattr__(self, name):
        # Allow calls like proxy.foo.bar(), passed as method "foo.bar"
        fullName = self._name + '.' + name
        if name.startswith('_'):
            raise AttributeError(
                "Cannot marshal private method %s" % fullName, name)
        return type(self)(self._request, fullName)


class BaseServerProxy(object):
    _methodClass = Method

    def __init__(self):
        pass

    def _request(self, method, params):
        """
        Pre-marshalling -- determine which method is to be called, do
        API version checks, etc. This is typically independent of how
        the call is to be sent and received. This is the place to turn
        failure return values into an exception.
        """
        return self._marshal_call(method, params)

    def _marshal_call(self, method, params):
        """
        Actually marshal the call (e.g. to XMLRPC), feed it to the
        transport, and demarshal the raw response.
        """
        return None

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(
                "Cannot marshal private method %s" % name, name)
        return self._methodClass(self._request, name)


# Server proxy with support for transports and addresses
class GenericServerProxy(BaseServerProxy):
    _defaultTransports = {
        'http': HTTPTransport,
        'https': HTTPSTransport,
        'shim': ShimTransport,
        'unix': UnixDomainHTTPTransport,
      }

    def __init__(self, address, transport=None, encoding=None, **kwargs):
        if isinstance(address, basestring):
            self._address = parseAddress(address)
        else:
            self._address = address
        if transport:
            self._transport = transport
        elif address:
            self._transport = self._getDefaultTransport(self._address.schema,
                kwargs)
        else:
            raise ValueError("No address and no transport given")
        self._encoding = encoding

    def _getDefaultTransport(self, schema, kwargs):
        if schema in self._defaultTransports:
            transportFactory = self._defaultTransports[schema]
            return transportFactory(**kwargs)
        else:
            raise ValueError("No default transport available for schema %r"
                % schema)

    def _request(self, method, params):
        return self._marshal_call(method, params)

    def _marshal_call(self, method, params):
        request = self._dumps(params, method, encoding=self._encoding)
        return self._transport.request(self._address, request)

    @staticmethod
    def _dumps(params, method, encoding):
        return xmlrpclib.dumps(tuple(params), method, encoding=encoding)

    def __repr__(self):
        return '<GenericServerProxy for %s>' % self._address
