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

from rmake.build import buildstate

class BuildStateTest(rmakehelp.RmakeHelper):
    def testJobFinished(self):
        bs = buildstate.AbstractBuildState([])
        built = set([mock.MockObject()])
        failed = set([mock.MockObject()])
        duplicate = set([mock.MockObject()])
        prepared = set([mock.MockObject()])
        bs.getBuiltTroves = lambda: built
        bs.getFailedTroves = lambda: failed
        bs.getDuplicateTroves = lambda: duplicate
        bs.getPreparedTroves = lambda: prepared
        bs.troves = built | failed | duplicate | prepared
        assert(bs.jobFinished())
        assert(not bs.jobPassed())
        # add an unbuilt trove
        bs.troves |= set([mock.MockObject()])
        assert(not bs.jobFinished())
        bs.troves  = built | duplicate | prepared
        assert(bs.jobPassed())
