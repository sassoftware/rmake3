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
