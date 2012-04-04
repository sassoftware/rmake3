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
