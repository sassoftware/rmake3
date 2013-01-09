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


from testutils import mock

from rmake_test import rmakehelp

from rmake.build import buildtrove
from rmake.build import dephandler
from rmake.build import imagetrove

class DephandlerTest(rmakehelp.RmakeHelper):
    def testHasSpecialTroves(self):
        dh = mock.MockInstance(dephandler.DependencyHandler)
        dh._mock.enableMethod('hasSpecialTroves')
        dh._mock.set(inactiveSpecial=['foo'])
        assert(dh.hasSpecialTroves())
        dh._mock.set(inactiveSpecial = [])
        assert(not dh.hasSpecialTroves())

    def testInit(self):
        bt = buildtrove.BuildTrove(1, *self.makeTroveTuple('foo:source'))
        bt.setConfig(self.buildCfg)
        it = imagetrove.ImageTrove(1, *self.makeTroveTuple('group-foo'))
        publisher = mock.MockObject()
        dh = dephandler.DependencyHandler(publisher, None,
                                          [bt], [it])
        assert(dh.moreToDo())
        bt.troveBuilt([])
        assert(dh.hasSpecialTroves())
        assert(dh.popSpecialTrove() == it)
        assert(dh.specialTroves)
