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
