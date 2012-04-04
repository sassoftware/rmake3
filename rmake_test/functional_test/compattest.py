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

from rmake import compat
from conary import constants

class CompatTest(rmakehelp.RmakeHelper):
    def testCompatCheck(self):
        cv = compat.ConaryVersion('1.0.29')
        assert(not cv.supportsCloneCallback())
        cv = compat.ConaryVersion('1.0.29_changeset')
        # _changeset must not make conary assume latest (RMK-1077)
        assert(not cv.supportsCloneCallback())
        cv = compat.ConaryVersion('1.0.30')
        assert(cv.supportsCloneCallback())
        self.logFilter.add()
        compat.ConaryVersion._warnedUser = False
        cv = compat.ConaryVersion('foo')
        self.logFilter.compare(['warning: nonstandard conary version "foo". Assuming latest.'])
        assert(cv.supportsCloneCallback())

        cv = compat.ConaryVersion('1.1.18')
        assert(cv.supportsCloneNoTracking())
        cv = compat.ConaryVersion('1.1.16')
        assert(not cv.supportsCloneNoTracking())
        cv = compat.ConaryVersion('1.0.30')
        assert(not cv.supportsCloneNoTracking())
        cv = compat.ConaryVersion('2.0')
        assert(not cv.signAfterPromote())
        cv = compat.ConaryVersion('1.2.7')
        assert(cv.signAfterPromote())
        cv = compat.ConaryVersion('2.0.28')
        assert(cv.supportsDefaultBuildReqs())
