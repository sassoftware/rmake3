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
