from rmake_test import rmakehelp
from testutils import mock

from rmake.build import buildjob
from rmake.build import imagetrove

class JobStoreTest(rmakehelp.RmakeHelper):
    def testJobStoreImage(self):
        db = self.openRmakeDatabase()
        job = buildjob.BuildJob()
        trv = imagetrove.ImageTrove(None, *self.makeTroveTuple('group-foo'))
        trv.setProductName('product')
        trv.setImageType('imageType')
        job.addBuildTrove(trv)
        job.setMainConfig(self.buildCfg)
        db.addJob(job)
        db.subscribeToJob(job)
        newJob = db.getJob(job.jobId)
        newTrv, = newJob.troves.values()
        assert(isinstance(newTrv, imagetrove.ImageTrove))
        assert(newTrv.getProductName() == 'product')
        assert(newTrv.getImageType() == 'imageType')
        trv.setImageBuildId(31) # should automatically update
        trv.troveBuilding()
        newTrv = db.getTrove(job.jobId, *trv.getNameVersionFlavor())
        assert(newTrv.getImageBuildId() == 31)
        newJob = db.getJob(job.jobId)
        newTrv, = newJob.troves.values()
        assert(newTrv.getImageBuildId() == 31)


        trv.setImageBuildId(32) # should automatically update
        job.setBuildTroves(job.troves.values())
        newTrv = db.getTrove(job.jobId, *trv.getNameVersionFlavor())
        assert(newTrv.getImageBuildId() == 32)


