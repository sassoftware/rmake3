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
from rmake import subscribers
from rmake.build import buildtrove

class JobStoreTest(rmakehelp.RmakeHelper):

    def testSubscribe(self):
        tup = self.addComponent('foo:source', '1').getNameVersionFlavor()
        s1 = subscribers.SubscriberFactory('foo', 'xmlrpc', 'unix:/tmp/foo')
        s2 = subscribers.SubscriberFactory('bam', 'xmlrpc', 'unix:/tmp/bar')
        s1.watchEvent('TROVE_EVENT_UPDATED')
        s2.watchEvent('TROVE_EVENT_UPDATED')
        db = self.openRmakeDatabase()
        db.subscriberStore.add(1, s1)
        db.subscriberStore.add(1, s2)
        db.commit()
        results = db.getSubscribersForEvents(1, [(('TROVE_EVENT_UPDATED', 4),
                                                  ((1, tup), 4, 'foo')),
                                                 (('TROVE_EVENT_UPDATED', 5),
                                                  ((1, tup), 5, 'foo'))])

        # make sure the results for the two events return the same subscriber
        # instances - we'll then be creating a reverse dict based on those
        # instances.
        assert(set(results['TROVE_EVENT_UPDATED', 4]) 
                == set(results['TROVE_EVENT_UPDATED', 5]))
