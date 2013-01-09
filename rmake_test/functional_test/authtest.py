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
