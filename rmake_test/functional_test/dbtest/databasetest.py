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


import os

from rmake_test import rmakehelp

from rmake.build import buildcfg
from rmake.build import buildjob
from rmake.server import server, servercfg
from rmake.lib import localrpc,logfile,recipeutil

from rmake import subscribers

class Databasetest(rmakehelp.RmakeHelper):

    def testJobConfig(self):
        db = self.openRmakeDatabase()
        db.jobStore.addJobConfig(1, '', self.buildCfg)
        db.commit()
        bc2 = db.jobStore.getJobConfig(1)
        assert(bc2.targetLabel == self.buildCfg.targetLabel)
        assert(bc2.resolveTroves == self.buildCfg.resolveTroves)

    def testSubscribers(self):
        s = subscribers.SubscriberFactory('foo', 'mailto', 'dbc@rpath.com')
        s['toName'] = 'Blah'
        s.watchEvent('JOB_UPDATED')

        db = self.openRmakeDatabase()
        db.subscriberStore.add(1, s)
        db.subscriberStore.get(s.subscriberId)

        assert(s.matches('JOB_UPDATED'))
        assert(s.matches('JOB_UPDATED', 'Built'))
        assert(not s.matches('TROVE_UPDATED', 'Built'))

        s = db.subscriberStore.getMatches(1, [[('JOB_UPDATED', ''), 'foo']])['JOB_UPDATED', ''][0]
        assert(s.matches('JOB_UPDATED'))
        assert(s.uri == 'dbc@rpath.com')
        assert(s['toName'] == 'Blah')
        assert(not db.subscriberStore.getMatches(1, [[('TROVE_UPDATED', ''), 'foo']]))
