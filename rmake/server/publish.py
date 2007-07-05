#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import os
import time
import traceback

from rmake.lib import pipereader

class _RmakeServerPublisher(object):
    """
        Sends job events from Rmake Server ->  Subscribers
    """
    def __init__(self, logger, db, forkCommand=os.fork):
        self.db = db
        self._fork = forkCommand
        self.logger = logger
        self.errorLimit = 100
        self.timeLimit = 60 * 5 # 5 minutes
        self.recentErrors = []
        self.errorTimes = []
        self.reader, self.writer = pipereader.makeMarshalPipes()
        self._events = {}
        # event queuing code - to eventually be moved to a separate 
        # process
        # min length of time between emits
        self._emitEventTimeThreshold = .2
        # max # of issues to queue before emit (overrides time threshold)
        self._emitEventSizeThreshold = 10  
        self._numEvents = 0                # number of queued events
        self._lastEmit = time.time()       # time of last emit
        self._emitPid = 0                  # pid for rudimentary locking

    def addEvent(self, jobId, eventList):
        self._events.setdefault(jobId, []).extend(eventList)
        self._numEvents += len(eventList)

    def emitEvents(self):
        self.harvestErrors()
        if not self._events or self._emitPid:
            return
        if ((time.time() - self._lastEmit) < self._emitEventTimeThreshold
            and self._numEvents < self._emitEventSizeThreshold):
            return
        events = self._events
        self._events = {}
        pid = self._fork('emitEvents')
        if pid:
            self._numEvents = 0
            self._lastEmit = time.time()
            self._emitPid = pid
            #self.debug('_emitEvents forked pid %d' % pid)
            return
        try:
            try:
                for jobId, eventList in events.iteritems():
                    self.db.reopen()
                    self._emitEvents(jobId, eventList)
                os._exit(0)
            except Exception, err:
                self.logger.error('Emit Events failed: %s\n%s', err, 
                                  traceback.format_exc())
                os._exit(1)
        finally:
            os._exit(1)

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

    def _emitEvents(self, jobId, eventList):
        """
            Publish events to all listening subscribers.
        """
        eventsBySubscriber = self._getEventListBySubscriber(self.db, jobId,
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

