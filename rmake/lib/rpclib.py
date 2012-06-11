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


"""
Classes for extracting and examining authentification methods passed from 
external servers
"""
import base64
import IN
import pwd
import socket
import struct
from rmake.lib import xmlrpc_null



class AuthObject(object):
    __slots__ = ['headers']

    def __init__(self, request):
        self.headers = None

    def setHeaders(self, headers):
        self.headers = headers

    def getSocketUser(self):
        return None

    def getCertificateUser(self):
        return None

    def getUser(self):
        return None

    def getPassword(self):
        return None


class HttpAuth(AuthObject):

    __slots__ = [ 'user', 'password', 'ip_address' ]

    def __init__(self, request, client_address):
        AuthObject.__init__(self, request)
        self.user = None
        self.password = None
        self.ip_address = client_address[0]

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

    def getIP(self):
        return self.ip_address

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

    def __init__(self, request, client_address):
        # get the peer credentials
        buf = request.getsockopt(socket.SOL_SOCKET, IN.SO_PEERCRED, 12)
        creds = struct.unpack('iii', buf)
        self.pid = creds[0]
        self.uid = creds[1]
        self.gid = creds[2]
        HttpAuth.__init__(self, request, ('127.0.0.1', None))

    def getSocketUser(self):
        return pwd.getpwuid(self.uid).pw_name

    getUser = getSocketUser

    def getIP(self):
        return '127.0.0.1'

    def __repr__(self):
        return 'SocketAuth(pid=%s, uid=%s, gid=%s)' % (self.pid, self.uid,
                                                       self.gid)


class CertificateAuth(HttpAuth):
    __slots__ = ['certFingerprint', 'certUser']

    def __init__(self, request, client_address):
        super(CertificateAuth, self).__init__(request, client_address)
        self.certFingerprint = None
        self.certUser = None

    def setPeerCertificate(self, x509):
        self.certFingerprint = None
        self.certUser = None
        for i in range(x509.get_ext_count()):
            extension = x509.get_ext_at(i)
            if extension.get_name() != 'subjectAltName':
                continue
            for entry in extension.get_value().split(','):
                kind, value = entry.split(':', 1)
                if kind != 'email':
                    continue
                if not value.endswith('@siteUserName.identifiers.rpath.internal'):
                    continue
                self.certFingerprint = x509.get_fingerprint('sha1')
                self.certUser = value.rsplit('@', 1)[0]
                break

    def getCertificateUser(self):
        return self.certUser

    def getUser(self):
        if self.certUser:
            return self.certUser
        return HttpAuth.getUser(self)

            else:
                socket = self.request.request
            # Python 2.7 tries to shutdown() first which the parent must not do
            # after handing off
            socket.close()