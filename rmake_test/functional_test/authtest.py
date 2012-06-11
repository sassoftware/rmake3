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
from StringIO import StringIO
from testutils import mock

from conary_test import recipes
from rmake import errors
from rmake_test import rmakehelp

class AuthenticationTest(rmakehelp.RmakeHelper):

    def testBasic(self):
        self.pluginMgr.enablePlugin('multinode')
        self.pluginMgr.installImporter()
        repos = self.openRepository()
        rmakeClient = self.startRmakeServer(protocol='http', multinode=True)
        assert(not rmakeClient.listJobs())

        self.buildCfg.rmakeUser = ('foo', 'bar')
        # put in a bad userName, password, make sure it fails
        self.buildCfg.rmakeUrl += '/'
        rmakeClient = self.getRmakeClient()
        try:
            rmakeClient.listJobs()
            assert(0)
        except errors.InsufficientPermission, err:
            assert(str(err) == 'Access denied.  Make sure your rmakeUser configuration variable contains a user and password accepted by the rBuilder instance at %s' % self.rmakeCfg.rbuilderUrl)

        # put in no username, password
        self.buildCfg.rmakeUser = None
        rmakeClient = self.getRmakeClient()
        try:
            rmakeClient.listJobs()
            assert(0)
        except errors.InsufficientPermission, err:
            assert(str(err) == "No user given - check to make sure you've set rmakeUser config variable to match a user and password accepted by the rBuilder instance at %s" % self.rmakeCfg.rbuilderUrl)

    def testExtraSlash(self):
        # make sure the right url is called when there's an extra / in there
        origUrlOpen = urllib2.urlopen
        def urlopen(url):
            if 'pwCheck' in url:
                assert(url.count('//') == 1)
                return StringIO('<auth valid="true"></auth>')
            else:
                return origUrlOpen(url)
                
        self.mock(urllib2, 'urlopen', urlopen)
        self.pluginMgr.enablePlugin('multinode')
        self.pluginMgr.installImporter()
        repos = self.openRepository()
        rmakeClient = self.startRmakeServer(protocol='http', multinode=True)
        self.buildCfg.rmakeUser = ('test', 'foo') # working user/pass
        rmakeClient = self.getRmakeClient()
        assert(not rmakeClient.listJobs())
