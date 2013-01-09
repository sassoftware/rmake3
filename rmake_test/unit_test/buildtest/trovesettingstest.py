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

from rmake.build import trovesettings
from rmake.lib import apiutils

from conary.lib import cfgtypes

class TestTroveSettings(rmakehelp.RmakeHelper):
    def testTroveSettings(self):
        class MyTroveSettings(trovesettings.TroveSettings):
            cfgOption = cfgtypes.CfgString 

        xx = MyTroveSettings()
        xx.cfgOption = 'foobar'
        yy = apiutils.thaw('TroveSettings', apiutils.freeze('TroveSettings', xx))
        assert(yy.cfgOption == 'foobar')
