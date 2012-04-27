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


import urllib2
import urllib

from conary.repository.netrepos import netauth

from rmake import errors

class AuthenticationManager(object):

    def __init__(self, url, db):
        self.pwCheckUrl = url
        self.db = db

    def authCheck(self, user, challenge, ip='127.0.0.1'):
        if self.db.auth.checkCache((user, challenge, ip)):
            return True
        isValid = False
        if self.pwCheckUrl:
            if not user or not challenge:
                raise errors.InsufficientPermission("""\
No user given - check to make sure you've set rmakeUser config variable to match a user and password accepted by the rBuilder instance at %s""" % self.pwCheckUrl)

            try:
                #url = "%s/pwCheck?user=%s;password=%s;remote_ip=%s" \
                #        % (self.pwCheckUrl, urllib.quote(user),
                #           urllib.quote(challenge), urllib.quote(ip))
                # at some point we should start sending remote_ip
                if self.pwCheckUrl.endswith('/'):
                    url = self.pwCheckUrl + "pwCheck"
                else:
                    url = self.pwCheckUrl + "/pwCheck"
                query = '%s?user=%s;password=%s' \
                          % (url, urllib.quote(user), urllib.quote(challenge))
                f = urllib2.urlopen(query)
                xmlResponse = f.read()
                p = netauth.PasswordCheckParser()
                p.parse(xmlResponse)
                isValid = p.validPassword()
            except Exception, e:
                # FIXME: this is a very broad exception handler
                isValid = False

        if not isValid:
            raise errors.InsufficientPermission("""\
Access denied.  Make sure your rmakeUser configuration variable contains a user and password accepted by the rBuilder instance at %s""" % self.pwCheckUrl)
        else:
            self.db.auth.cache((user, challenge, ip))
            return True
