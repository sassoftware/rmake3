#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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

