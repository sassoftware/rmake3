from testutils import mock

from rmake_test import rmakehelp

from rmake.build import imagetrove
from rmake.lib import recipeutil
from rmake.lib import repocache

class RecipeUtilTest(rmakehelp.RmakeHelper):
    def testGetSourceTrovesFromJob(self):
        repos = mock.mockClass(repocache.CachingTroveSource)()
        trv1 = self.newBuildTrove(1, *self.makeTroveTuple('bar:source'))
        trv1Tup = trv1.getNameVersionFlavor(True)
        trv1.setConfig(self.buildCfg)
        job = self.newJob()
        job.addBuildTrove(trv1)
        mock.mockFunction(recipeutil.loadSourceTroves, {trv1Tup: 'result'})

        rc = recipeutil.getSourceTrovesFromJob(job, [trv1], repos,
            self.rmakeCfg.reposName)
        self.failUnlessEqual(rc, {trv1Tup: 'result'})
        args, kw = recipeutil.loadSourceTroves._mock.popCall()
        assert(args[3] == [trv1])

        
    
    

