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


from conary_test import recipes

from rmake_test import rmakehelp

from conary.deps import deps

from rmake import failure
from rmake.build import buildtrove
from rmake.lib import apiutils
from rmake.lib import repocache

class BuildTroveTest(rmakehelp.RmakeHelper):
    def testBuildTrove(self):
        trv = self.addComponent('blah:source', '1.0')
        bt = buildtrove.BuildTrove(1, trv.getName(), trv.getVersion(),
                                   trv.getFlavor())
        f = failure.MissingDependencies([(trv.getNameVersionFlavor(),
                              deps.parseDep('trove: blam trove:foo'))])
        bt.setFailureReason(f)
        frz = apiutils.freeze('BuildTrove', bt)
        bt2 = apiutils.thaw('BuildTrove', frz)
        assert(bt2.getFailureReason() == bt.getFailureReason())
        assert(bt2.getFlavor() == bt.getFlavor())
