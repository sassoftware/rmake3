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


from rmake_test import rmakehelp
from testutils import mock

from rmake.worker import rbuilderclient
from M2Crypto import m2xmlrpclib
import xmlrpclib

class RbuilderClientTest(rmakehelp.RmakeHelper):
    def testRbuilderClient(self):
        client = rbuilderclient.RbuilderClient('https://nonesuchhost.ff', 'foo', 'bar')
        self.failUnlessEqual(client.server._ServerProxy__host, 'foo:bar@nonesuchhost.ff')
        self.failUnlessEqual(client.server._ServerProxy__handler, '/xmlrpc-private')

        client = rbuilderclient.RbuilderClient('http://nonesuchhost.ff/rbuilder/', 'foo', 'bar')
        self.failUnlessEqual(client.server._ServerProxy__host, 'foo:bar@nonesuchhost.ff')
        self.failUnlessEqual(client.server._ServerProxy__handler, '/rbuilder/xmlrpc-private')

    def testNewBuildWithOptions(self):
        name,ver,flavor = self.makeTroveTuple('group-foo')
        client = rbuilderclient.RbuilderClient('https://nonesuchhost.ff', 'foo', 'bar')
        client.server = mock.MockObject()
        client.server.getProjectIdByHostname._mock.setReturn((False, 55), 'project')
        args = (55, 'buildName', 'group-foo', 
                ver.freeze(), flavor.freeze(),
                'buildType', {'foo':'bar'})
        client.server.newBuildWithOptions._mock.setReturn((False, 31), *args)
                                                    
        rc = client.newBuildWithOptions('project', name, ver, flavor, 'buildType', 'buildName',
                                        {'foo':'bar'})
        assert(rc == 31)
        # Test error raising
        client.server.newBuildWithOptions._mock.setReturn((True, ['error!']), 
                                                          *args)
        err = self.assertRaises(RuntimeError, 
                                client.newBuildWithOptions,
                                    'project', name, ver, 
                                    flavor, 'buildType', 'buildName',
                                    {'foo':'bar'})
        assert(str(err) == 'error!')
        client.server.getProjectIdByHostname._mock.setReturn((True, ['error2!']),
                                                             'project')
        err = self.assertRaises(RuntimeError, 
                                client.newBuildWithOptions,
                                    'project', name, ver, 
                                    flavor, 'buildType', 'buildName',
                                    {'foo':'bar'})
        assert(str(err) == 'error2!')

    def testStartImage(self):
        client = rbuilderclient.RbuilderClient('https://nonesuchhost.ff', 'foo', 'bar')
        client.server = mock.MockObject()
        client.server.startImageJob._mock.setReturn((False, True), 32)
        assert(client.startImage(32) is None)
        client.server.startImageJob._mock.assertCalled(32)
        client.server.startImageJob._mock.setReturn((True, ['error!']), 32)
        err = self.assertRaises(RuntimeError, client.startImage, 32)
        assert(str(err) == 'error!')
