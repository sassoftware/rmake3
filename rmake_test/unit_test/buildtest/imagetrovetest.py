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

from rmake.build import imagetrove

class ImageTroveTest(rmakehelp.RmakeHelper):
    def testImageTrove(self):
        trv = imagetrove.ImageTrove(1, *self.makeTroveTuple('group-foo'))
        assert(trv.isSpecial())
        trv.setProductName('foo')
        assert(trv.getProductName() == 'foo')
        trv.setImageBuildId(23)
        assert(trv.getImageBuildId() == 23)
        assert(trv.getCommand() == 'image')
        trv.setImageType('imageType')
        assert(trv.getImageType() == 'imageType')
        options = trv.getImageOptions() 
        assert(options == {})
        trv.setImageOptions({'foo' : 'bar'})
        assert(trv.getImageOptions()  == {'foo' : 'bar'})
