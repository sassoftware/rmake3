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



