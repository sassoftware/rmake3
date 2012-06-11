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


import errno
import os
import tempfile


class _CredStore(object):

    def __init__(self, path):
        self.path = path

    def _iter(self):
        try:
            fObj = open(self.path)
        except IOError, err:
            if err.errno == errno.ENOENT:
                return
            raise

        for line in fObj:
            line = line.strip()
            if line:
                yield line.split(' ', 1)

    def _get(self, key):
        for key2, value2 in self._iter():
            if key == key2:
                return value2
        return None

    def _set(self, key, value):
        fDesc, tempName = tempfile.mkstemp(dir=os.path.dirname(self.path))
        fObj = os.fdopen(fDesc, 'w')

        for key2, value2 in self._iter():
            if key2 != key:
                print >> fObj, key2, value2
        print >> fObj, key, value

        fObj.flush()
        os.fsync(fDesc)
        os.chmod(tempName, 0600)
        os.rename(tempName, self.path)
        fObj.close()

    @staticmethod
    def _random():
        return os.urandom(16).encode('hex')


class XmppClientCredentials(_CredStore):
    """
    Identity of a node that will create and register a random user on a
    particular domain at startup. The identity file will store one user@host
    for each domain that it has connected to.
    """

    def get(self, targetDomain):
        userpass = self._get(targetDomain)
        if userpass:
            username, password = userpass.split(' ', 1)
        else:
            username = self._random()
            password = self._random()
        return username, targetDomain, password

    def set(self, user, targetDomain, password):
        self._set(targetDomain, ' '.join((user, password)))


class XmppServerCredentials(_CredStore):
    """
    Identity of a node that will create and register a specific user@host on
    startup.  The identity file will store one password for each uer@host that
    it has connected as.
    """

    def get(self, targetUserHost):
        username, domain = targetUserHost
        password = self._get('%s@%s' % (username, domain))
        if not password:
            password = self._random()
        return username, domain, password

    def set(self, user, domain, password):
        self._set('%s@%s' % (user, domain), password)
