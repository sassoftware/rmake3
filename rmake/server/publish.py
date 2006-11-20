#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
import traceback

from conary.lib import log


class _RmakeServerPublisher(object):
    """
        Sends job events from Rmake Server ->  Subscribers
    """
    def emitEvents(self, db, jobId, eventList):
        """
            Publish events to all listening subscribers.
        """
        eventsBySubscriber = self._getEventListBySubscriber(db, jobId, eventList)
        for subscriber, eventList in eventsBySubscriber.iteritems():
            try:
                subscriber._receiveEvents(subscriber.apiVersion, eventList)
            except Exception, err:
                log.error('Subscriber %s failed: %s\n%s', subscriber,
                          err, traceback.format_exc())

    def _getEventListBySubscriber(self, db, jobId, eventList):
        """
            For the given event list, return events sorted by subscriber.
            @return subscriber -> eventList dictionary.
        """
        subscribersByEvent = db.getSubscribersForEvents(jobId, eventList)
        if not subscribersByEvent:
            return {}
        eventsBySubscriber = {}
        for (event, subEvent), data in eventList:
            if (event, subEvent) not in subscribersByEvent:
                continue
            for subscriber in subscribersByEvent[event, subEvent]:
                eventsBySubscriber.setdefault(subscriber, []).append(
                                                ((event, subEvent), data))
        return eventsBySubscriber

