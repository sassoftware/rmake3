#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
from rmake import constants

class Publisher(object):

    states = set()

    def __init__(self):
        for state in self.states:
            setattr(self, state, state)
        self.reset()

    def reset(self):
        self.listeners = {}
        self.dispatchers = {}
        self._toEmit = {}
        self._corked = 0

    def cork(self):
        self._corked += 1

    def uncork(self):
        if self._corked:
            self._corked -= 1
        if self._corked:
            return
        toEmit = self._toEmit
        self._toEmit = {}
        try:
            for fn, (isDispatcher, eventList) in toEmit.iteritems():
                if not isDispatcher:
                    for event, data in eventList:
                        fn(*data)
                else:
                    fn(constants.subscriberApiVersion, eventList)
        finally:
            # Make sure we're uncorked in case we have to send a
            # failure message.
            self._corked = 0

    def _emit(self, event, subevent, *args):
        data = ((event, subevent), args)
        if self._corked:
            for fn in self.dispatchers.get(event, []):
                if fn not in self._toEmit:
                    self._toEmit[fn] = (True, [data])
                else:
                    self._toEmit[fn][1].append(data)

            for fn in self.listeners.get(event, []):
                if fn not in self._toEmit:
                    self._toEmit[fn] = (False, [data])
                else:
                    self._toEmit[fn][1].append(data)

        else:
            self.cork()
            try:
                for fn in self.dispatchers.get(event, []):
                    fn(constants.subscriberApiVersion, [data])
                for fn in self.listeners.get(event, []):
                    fn(*args)
            except:
                # Clear the backlog so that failure messages
                # can get through.
                self._toEmit = {}
                self._corked = 0
                raise
            self.uncork()

    def subscribe(self, stateList, fn, dispatcher=False):
        if isinstance(stateList, str):
            stateList = [stateList]
        for state in stateList:
            if state not in self.states:
                raise ValueError("no such state '%s'" % state)
            if dispatcher:
                l = self.dispatchers.setdefault(state, [])
            else:
                l = self.listeners.setdefault(state, [])
            if fn not in l:
                l.append(fn)

    def unsubscribe(self, state, fn):
        self.listeners[state].remove(fn)

    def subscribeAll(self, fn, dispatcher=False):
        for state in self.getStates():
            self.subscribe(state, fn, dispatcher=dispatcher)

    def getStates(self):
        return self.states
