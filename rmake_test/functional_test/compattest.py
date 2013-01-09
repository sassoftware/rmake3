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
