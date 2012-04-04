# -*- mode: python -*-
#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

#test
from conary_test import rephelp

#rmake
from rmake.lib import procutil

class ProcUtilTest(rephelp.RepositoryHelper):
    def testProcUtil(self):
        m = procutil.MachineInformation()
        m.update()
        assert(str(m))
        # how do I verify information from here?

    def testFreezeProcUtil(self):
        m = procutil.MachineInformation()
        m.update()
        d = m.__freeze__()
        xx = procutil.MachineInformation.__thaw__(d)
        assert(xx == m)
        xx.update()
        assert(xx != m)

