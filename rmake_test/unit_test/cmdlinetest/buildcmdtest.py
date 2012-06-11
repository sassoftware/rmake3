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
