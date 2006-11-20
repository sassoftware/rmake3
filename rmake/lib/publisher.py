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
from rmake import constants

class Publisher(object):

    states = set()

    def __init__(self):
        self.listeners = {}
        self.dispatchers = {}
        for state in self.states:
            setattr(self, state, state)
        self._toEmit = {}
        self._corked = False

    def cork(self):
        self._corked = True

    def uncork(self):
        toEmit = self._toEmit
        self._toEmit = {}
        for fn, (isDispatcher, eventList) in toEmit.iteritems():
            if not isDispatcher:
                for event, data in eventList:
                    fn(*data)
            else:
                fn(constants.subscriberApiVersion, eventList)

        self._corked = False

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
            for fn in self.dispatchers.get(event, []):
                fn(constants.subscriberApiVersion, [data])
            for fn in self.listeners.get(event, []):
                fn(*args)

    def subscribe(self, stateList, fn, dispatcher=False):
        if isinstance(stateList, str):
            stateList = [stateList]
        for state in stateList:
            if state not in self.states:
                raise ValueError("no such state '%s'" % state)
            if dispatcher:
                self.dispatchers.setdefault(state, []).append(fn)
            else:
                self.listeners.setdefault(state, []).append(fn)

    def unsubscribe(self, state, fn):
        self.listeners[state].remove(fn)

    def subscribeAll(self, fn, dispatcher=False):
        for state in self.getStates():
            self.subscribe(state, fn, dispatcher=dispatcher)

    def getStates(self):
        return self.states
