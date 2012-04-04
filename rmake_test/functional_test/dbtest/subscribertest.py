#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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



