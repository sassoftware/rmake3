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
