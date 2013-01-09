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

from rmake.build import buildtrove
from rmake.build import imagetrove


class BuildTroveTest(rmakehelp.RmakeHelper):
    def testRegisteredBuildTrove(self):
        assert(buildtrove._troveClassesByType['build'] == buildtrove.BuildTrove)
        assert(buildtrove._troveClassesByType['image'] == imagetrove.ImageTrove)

    def testIsSpecial(self):
        bt = buildtrove.BuildTrove(1, *self.makeTroveTuple('foo:source'))
        assert(not bt.isSpecial())
        bt = imagetrove.ImageTrove(1, *self.makeTroveTuple('foo'))
        assert(bt.isSpecial())

    def testGetClassForTroveType(self):
        assert(buildtrove.getClassForTroveType('build') == buildtrove.BuildTrove)
        assert(buildtrove.getClassForTroveType('image') == imagetrove.ImageTrove)

    def testDisplay(self):
        bt = buildtrove.BuildTrove(1, *self.makeTroveTuple('foo:source'))
        assert(str(bt) == "<BuildTrove('foo:source=localhost@rpl:linux[]')>")
