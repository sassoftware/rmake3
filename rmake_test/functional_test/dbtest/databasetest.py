#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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


