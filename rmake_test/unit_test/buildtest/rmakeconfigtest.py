#!/usr/bin/python
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
