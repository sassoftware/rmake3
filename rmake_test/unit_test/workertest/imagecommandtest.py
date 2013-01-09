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


from rmake_test import rmakehelp
from testutils import mock
import time

from rmake import errors
from rmake.build import imagetrove
from rmake.worker import imagecommand
from rmake.worker import rbuilderclient

class ImageCommandTest(rmakehelp.RmakeHelper):
    def testImageCommand(self):
        eventHandler = mock.MockObject()
        mock.mock(rbuilderclient, 'RbuilderClient')
        self.buildCfg.configLine('rmakeUser foo bar')
        self.buildCfg.rbuilderUrl = 'http://foo'
        trv = imagetrove.ImageTrove(1, *self.makeTroveTuple('group-foo'))
        trv.setProductName('product')
        cmd = imagecommand.ImageCommand(self.rmakeCfg, 'commandId', 1, eventHandler,
                                        self.buildCfg, trv)
        client = cmd.client
        client.newBuildWithOptions._mock.setDefaultReturn(21)
        cmd.logger = mock.MockObject()
        mock.mockMethod(cmd.watchImage)
        cmd.runAttachedCommand()
        cmd.watchImage._mock.assertCalled(21)
        client.startImage._mock.assertCalled(21)
        client.newBuildWithOptions._mock.assertCalled('product', 'group-foo', 
                                                      trv.getVersion(), trv.getFlavor(),
                                                      trv.getImageType(), 
                                                      trv.getBuildName(),
                                                      trv.getImageOptions())
        client.newBuildWithOptions._mock.raiseErrorOnAccess(RuntimeError('error!'))
        cmd.runAttachedCommand()
        assert(trv.isFailed())
        assert(str(trv.getFailureReason()) == 'Failed while building: error!')

    def testWatchImage(self):
        eventHandler = mock.MockObject()
        mock.mock(rbuilderclient, 'RbuilderClient')
        self.buildCfg.configLine('rmakeUser foo bar')
        self.buildCfg.rbuilderUrl = 'http://foo'
        mock.mock(time, 'sleep')
        trv = imagetrove.ImageTrove(1, *self.makeTroveTuple('group-foo'))
        trv.setProductName('product')
        cmd = imagecommand.ImageCommand(self.rmakeCfg, 'commandId', 1, eventHandler,
                                        self.buildCfg, trv)
        client = cmd.client
        client.server.getBuildStatus._mock.setReturns(
                        [(False, {'message' : 'foo', 'status' : 10}),
                         (False, {'message' : 'foo', 'status' : 10}),
                         (False, {'message' : 'bar', 'status' : 300})],
                        21)
        rc, txt = self.captureOutput(cmd.watchImage, 21)
        assert(txt == '''\
21: foo
21: bar
''')
        client.server.getBuildStatus._mock.setReturns(
                        [(True, 'Error with build')],
                        31)
        err = self.assertRaises(errors.RmakeError, cmd.watchImage, 31)
