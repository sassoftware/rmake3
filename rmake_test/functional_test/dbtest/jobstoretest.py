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


import os

from rmake_test import rmakehelp

from rmake import errors
from rmake.build import buildtrove

class JobStoreTest(rmakehelp.RmakeHelper):

    def testListTrovesByState(self):
        db = self.openRmakeDatabase()

        atrv = self.Component('a:source')[0]
        btrv = self.Component('b:source')[0]
        ctrv = self.Component('c:source')[0]
        dtrv = self.Component('d:source')[0]
        etrv = self.Component('e:source')[0]

        job = self.newJob(atrv, btrv, ctrv, dtrv, etrv)
        a,b,c,d,e = buildTroves = self.makeBuildTroves(job)

        trv, cs = self.Component('a:runtime')
        db.subscribeToJob(job)
        job.getPublisher().cork()
        job.setBuildTroves(buildTroves)
        a.troveBuilt(cs)
        b.troveFailed('foo')
        c.troveBuilding()
        job.getPublisher().uncork()
        jobId = job.jobId
        results = db.listTrovesByState(jobId)
        (a,b,c,d,e) = [ x.getNameVersionFlavor(True) for x in (a,b,c,d,e)]
        assert(set(results[buildtrove.TROVE_STATE_INIT]) == set([d, e]))
        assert(results[buildtrove.TROVE_STATE_BUILDING] == [c])
        assert(results[buildtrove.TROVE_STATE_FAILED] == [b])
        assert(results[buildtrove.TROVE_STATE_BUILT] == [a])

        results = db.listTrovesByState(jobId, buildtrove.TROVE_STATE_INIT)
        assert(set(results[buildtrove.TROVE_STATE_INIT]) == set([d, e]))
        assert(len(results) == 1)

    def testGetJobsAndTroves(self):
        db = self.openRmakeDatabase()
        atrv = self.Component('a:source')[0]

        arun, arunCs = self.Component('a:runtime')
        btrv = self.Component('b:source')[0]
        job1 = self.newJob(atrv)
        job1.jobBuilding('foo')
        a, = buildTroves = self.makeBuildTroves(job1)
        job1.setBuildTroves(buildTroves)

        a.troveBuilt(arunCs)

        job2 = self.newJob(btrv)
        b, = buildTroves = self.makeBuildTroves(job2)
        job2.setBuildTroves(buildTroves)

        jobId1 = job1.jobId
        jobId2 = job2.jobId
        job1, job2 = db.getJobs([job1.jobId, job2.jobId], withTroves=True)
        assert(job1.jobId == jobId1)
        assert(job1.isBuilding())
        assert(job2.jobId == jobId2)

        newA = list(job1.iterTroves())[0]
        newB = list(job2.iterTroves())[0]

        assert(newA.isBuilt())

        assert(a.getNameVersionFlavor() == 
               newA.getNameVersionFlavor())
        assert(b.getNameVersionFlavor() ==
               newB.getNameVersionFlavor())
        assert(list(a.iterBuiltTroves()) == list(newA.iterBuiltTroves()))

        # okay, now just get the troves
        newA, newB = db.getTroves([(a.jobId, a.name, a.version, a.flavor, a.context),
                                   (b.jobId, b.name, b.version, b.flavor, a.context)])
        assert(a.getNameVersionFlavor() == 
               newA.getNameVersionFlavor())
        assert(b.getNameVersionFlavor() ==
               newB.getNameVersionFlavor())
        assert(list(a.iterBuiltTroves()) == list(newA.iterBuiltTroves()))

    def testMissing(self):
        db = self.openRmakeDatabase()
        atrv = self.Component('a:source')[0]

        job1 = self.newJob(atrv)
        a, = buildTroves = self.makeBuildTroves(job1)
        job1.setBuildTroves(buildTroves)

        try:
            db.getJobs([job1.jobId,999])
        except errors.JobNotFound, err:
            assert(str(err) == 'JobNotFound: Could not find job with jobId 999')

        try:
            db.getTroves([(a.jobId, a.name, a.version, a.flavor, a.context), 
                          (a.jobId, 'blah:source', a.version, a.flavor, a.context)])
        except errors.TroveNotFound, err:
            assert(str(err) == 'TroveNotFound: Could not find trove blah:source=/localhost@rpl:linux/1.0-1[]{} with jobId 1')


    def testUUID(self):
        db = self.openRmakeDatabase()
        atrv = self.Component('a:source')[0]
        uuid = self.genUUID('testUUID')
        job = self.newJob(atrv, uuid=uuid)

        assert(db.convertToJobIds([uuid, job.jobId]) == [job.jobId, job.jobId])
        assert(db.getJob(job.jobId).uuid == uuid)

    def testGetJobsWithContexts(self):
        # RMK-529 - getJobs fails when getting multiple jobs that used
        # contexts
        fooSource = self.addComponent('foo:source')
        barSource = self.addComponent('bar:source')
        job1 = self.newJob((fooSource, 'context1'))
        job2 = self.newJob((barSource, 'context2'))
        db = self.openRmakeDatabase()
        jobs = db.getJobs([job1.jobId, job2.jobId], withTroves=True)
        assert(jobs[0].iterTroveList(withContexts=True).next() == (fooSource.getNameVersionFlavor() + ('context1',)))
        jobs = db.getJobs([job1.jobId, job2.jobId], withTroves=False)
        assert(jobs[0].iterTroveList(withContexts=True).next() == (fooSource.getNameVersionFlavor() + ('context1',)))
