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

from rmake.build import imagetrove
from rmake.cmdline import query

class TestDisplay(rmakehelp.RmakeHelper):

    def testDisplaySettings(self):
        trv = imagetrove.ImageTrove(1, *self.makeTroveTuple('group-foo'))
        trv.setProductName('product')
        trv.setImageType('imageType')
        job = self.newJob()
        job.addBuildTrove(trv)
        dcfg = query.DisplayConfig(mock.MockObject())
        rc, txt = self.captureOutput(query.displayTroveDetail, dcfg, job, trv)
        assert(txt == '''\
     group-foo=:linux/1-1-1
       State: Initialized         
imageType                 imageType
productName               product
urls                      []
''')
