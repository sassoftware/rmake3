#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
