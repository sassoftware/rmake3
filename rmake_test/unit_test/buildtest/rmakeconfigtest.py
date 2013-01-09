#!/usr/bin/python
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
