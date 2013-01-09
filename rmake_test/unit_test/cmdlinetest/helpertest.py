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

from rmake.cmdline import helper

class TestHelper(rmakehelp.RmakeHelper):
    def getMockHelper(self):
        h = mock.MockInstance(helper.rMakeHelper)
        h._mock.set(buildConfig=self.cfg)
        mock.mockMethod(h.buildConfig.initializeFlavors)
        return h
        
    def testCreateImageJob(self):
        h = self.getMockHelper()
        h._mock.enableMethod('createImageJob')
        repos = h.getRepos()
        repos.findTroves._mock.setReturn(
            {('group-foo', None, None) : [self.makeTroveTuple('group-foo')]},
            self.cfg.buildLabel, 
            {('group-foo', None, None) : [('imageType', '', {'option' : 'value'})]},
            self.cfg.buildFlavor)
        job = h.createImageJob('project', 
                    [('group-foo', 'imageType', {'option' : 'value'})])
        trove, = list(job.iterTroves())
        assert(trove.isSpecial())
        assert(trove.getNameVersionFlavor() == self.makeTroveTuple('group-foo'))
        assert(trove.getImageOptions() == {'option' : 'value'})
        assert(trove.getProductName() == 'project')
        assert(trove.getImageType() == 'imageType')
