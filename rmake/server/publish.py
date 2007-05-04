#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import time
import traceback

from rmake.lib import pipereader

class _RmakeServerPublisher(object):
    """
        Sends job events from Rmake Server ->  Subscribers
    """
    def __init__(self, logger):
        self.logger = logger
        self.errorLimit = 100
        self.timeLimit = 60 * 5 # 5 minutes
        self.recentErrors = []
        self.errorTimes = []
        self.reader, self.writer = pipereader.makeMarshalPipes()

    def harvestErrors(self):
        error = self.reader.handleReadIfReady()
        while error:
            errorTime, uri, msg = error
            idx = 0
            while ((idx < len(self.errorTimes)) and
                   (time.time() - self.errorTimes[idx]) > self.timeLimit):
                idx += 1
            self.errorTimes = self.errorTimes[idx:]
            self.recentErrors = self.recentErrors[idx:]
            if (uri, msg) in self.recentErrors:
                idx = self.recentErrors.index((uri, msg))
                del self.recentErrors[idx]
                del self.errorTimes[idx]
                # it will get readded at the end
            else:
                self.logger.error('Subscriber %s failed: %s', uri, msg)
            self.errorTimes.append(errorTime)
            self.recentErrors.append((uri, msg))
            self.recentErrors = self.recentErrors[-self.errorLimit:]
            self.errorTimes = self.errorTimes[-self.errorLimit:]
            error = self.reader.handleReadIfReady()

    def emitEvents(self, db, jobId, eventList):
        """
            Publish events to all listening subscribers.
        """
        eventsBySubscriber = self._getEventListBySubscriber(db, jobId,
                                                            eventList)
        for subscriber, eventList in eventsBySubscriber.iteritems():
            try:
                subscriber._receiveEvents(subscriber.apiVersion, eventList)
            except Exception, err:
                self.writer.send((time.time(), subscriber.uri, str(err)))
        while self.writer.hasData():
            self.writer.handleWriteIfReady(sleep=10)

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

