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
