#!/usr/bin/python
from testutils import mock
from rmake_test import rmakehelp

from rmake.build import buildcfg

from rmake import compat

class TestrMakeBuildContext(rmakehelp.RmakeHelper):
    def testDefaultBuildReqs(self):
        conaryV = mock.MockObject()
        try:
            self.mock(compat, 'ConaryVersion', conaryV)
            conaryV().supportsDefaultBuildReqs._mock.setReturn(True)
            reload(buildcfg)
            cfg = buildcfg.BuildConfiguration(readConfigFiles=False)
            self.assertEquals(cfg.defaultBuildReqs, [])
            conaryV().supportsDefaultBuildReqs._mock.setReturn(False)
            reload(buildcfg)
            cfg = buildcfg.BuildConfiguration(readConfigFiles=False)
            self.assertEquals('conary-build:runtime' in cfg.defaultBuildReqs, True)
            self.assertEquals('filesystem' in cfg.defaultBuildReqs, True)
        finally:
            self.unmock()
            reload(buildcfg)

