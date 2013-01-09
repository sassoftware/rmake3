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

from conary.deps import deps

from rmake.build import buildjob
from rmake.build import buildtrove
from rmake import failure
from rmake.lib import apiutils

class BuildJobTest(rmakehelp.RmakeHelper):
    def testJob(self):
        db = self.openRmakeDatabase()
        trv = self.addComponent('foo:source', '1.0', '!flavor')
        job = buildjob.NewBuildJob(db, [trv.getNameVersionFlavor()])
        job2 = apiutils.thaw('BuildJob', apiutils.freeze('BuildJob', job))
        assert(job2.jobId ==  job.jobId)
        assert(list(job2.iterTroveList()) == list(job.iterTroveList()))

    def testJobLogging(self):
        events = {}
        def _markEvent(apiVersion, eventList):
            for (event, subEvent), args in eventList:
                obj = args[0]
                events.setdefault(obj, []).append((event, args))

        def checkEvent(obj, *eventList):
            self.assertEqual([x[0] for x in events[obj]], list(eventList))
            events[obj] = []

        db = self.openRmakeDatabase()
        trv = self.addComponent('foo:source', '1.0', '')

        job = buildjob.NewBuildJob(db, [trv.getNameVersionFlavor()])
        bt = buildtrove.BuildTrove(job.jobId, *trv.getNameVersionFlavor())
        publisher = job.getPublisher()
        publisher.subscribeAll(_markEvent, dispatcher=True)
        job.setBuildTroves([bt])
        checkEvent(job, publisher.JOB_TROVES_SET)


        built = self.addComponent('foo:run', '1.0', 'flavor')
        repos = self.openRepository()
        cs = repos.createChangeSet([('foo:run', (None, None),
                                    (built.getVersion(), built.getFlavor()), 
                                    True)])
        bt.troveBuilding()
        checkEvent(bt, publisher.TROVE_STATE_UPDATED, publisher.TROVE_BUILDING)

        bt.log('some other state change')
        checkEvent(bt, publisher.TROVE_LOG_UPDATED)
        bt.troveBuilt([ x.getNewNameVersionFlavor() for x in cs.iterNewTroveList()])
        checkEvent(bt, publisher.TROVE_STATE_UPDATED, publisher.TROVE_BUILT)
        bt.troveFailed(failure.BuildFailed('failureReason', 'foo'))
        checkEvent(bt, publisher.TROVE_STATE_UPDATED, publisher.TROVE_FAILED)
        job.jobFailed('foo')
        checkEvent(job, publisher.JOB_STATE_UPDATED, publisher.JOB_FAILED)
        job.jobLoading('foo')
        checkEvent(job, publisher.JOB_STATE_UPDATED)
        job.jobLoaded({})
        checkEvent(job, publisher.JOB_STATE_UPDATED, publisher.JOB_LOADED)
        job.jobPassed('foo')
        checkEvent(job, publisher.JOB_STATE_UPDATED)
        checkEvent(bt)
        job.jobCommitting()
        checkEvent(job, publisher.JOB_STATE_UPDATED)
        job.jobCommitted([trv])
        checkEvent(job, publisher.JOB_STATE_UPDATED, publisher.JOB_COMMITTED)

    def testFindTroves(self):
        db = self.openRmakeDatabase()
        trv = self.addComponent('foo:source', '1.0', '')
        binTrove = self.addComponent('foo:run', '1.0', 'ssl,!readline')
        job = buildjob.NewBuildJob(db, [trv.getNameVersionFlavor()])
        job.addTrove('foo:source', trv.getVersion(), deps.parseFlavor('ssl'))

        results = job.findTrove(None,
                                ('foo:source', None, deps.parseFlavor('ssl')))
        assert(len(results) == 1)

        buildTrove = buildtrove.BuildTrove(job.jobId,
                                           *trv.getNameVersionFlavor())

        job.setBuildTroves([buildTrove])
        buildTrove = job.troves.values()[0]
        buildTrove.setBinaryTroves([binTrove.getNameVersionFlavor()])

        results = job.findTrove(None,
                            ('foo:run', None, deps.parseFlavor('!readline')))
        assert(len(results) == 1)
        assert(results[0][2] == deps.parseFlavor('ssl,!readline'))
