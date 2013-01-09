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
from testutils import mock

from rmake.cmdline import buildcmd 

class BuildCommandTest(rmakehelp.RmakeHelper):
    def testGetConfigInfo(self):
        'RMK-973'
        fakeMan = self.workDir + '/not.a.man.7'
        file(fakeMan, 'w').write('\0')
        self.assertEquals(buildcmd._getConfigInfo(fakeMan), False)
        script = self.workDir + '/foo.sh'
        file(script, 'w').write('#!/bin/sh')
        self.assertEquals(buildcmd._getConfigInfo(script), True)
        fakescript = self.workDir + '/foo.fsh'
        file(fakescript, 'w').write('#!/bin/sh\n\0')
        self.assertEquals(buildcmd._getConfigInfo(fakescript), False)
        gif = self.workDir + '/foo.gif'
        file(gif, 'w').write('')
        self.assertEquals(buildcmd._getConfigInfo(gif), False)
