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
