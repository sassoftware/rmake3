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
