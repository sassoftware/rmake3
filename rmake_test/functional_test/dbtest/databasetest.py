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
