#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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

