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
