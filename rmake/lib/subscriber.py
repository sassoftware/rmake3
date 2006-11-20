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
from rmake.lib import apiutils
from rmake import constants
from rmake import plugins

class Subscriber(object):

    listeners = {}

    def __init__(self):
        self.events = {}

    def _receiveEvents(self, apiVersion, eventList):
        for event, data in eventList:
            getattr(self, self.listeners[event[0]])(*data)

    def watchEvent(self, state, substates=set()):
        self.events.setdefault(state, set()).update(substates)

class _AbstractStatusSubscriber(Subscriber):

    fields = {}

    def __init__(self, subscriberId, uri):
        Subscriber.__init__(self)
        self.subscriberId = subscriberId
        self.uri = uri
        self.apiVersion = constants.subscriberApiVersion
        self._state = {}
        for field, default in self.fields.iteritems():
            self[field] = default

    def __getitem__(self, key):
        return self._state[key]

    def __setitem__(self, key, val):
        self._state[key] = val

    def iteritems(self):
        return self._state.iteritems()

    def iterEvents(self):
        if not self.events:
            return ((x, []) for x in self.listeners)
        return self.events.iteritems()

    def matches(self, event, subState=None):
        if event in self.events:
            subEvent = self.events[event]
            if not subState or not subEvent or (subState in subEvent):
                return True
        return False


class FreezableStatusSubscriberMixin(object):

    def freezeData(self):
        lst = [ '%s %s' % (self.protocol, self.uri) ]
        lst.append('apiVersion %s' % self.apiVersion)
        for event, subEvents in self.iterEvents():
            if subEvents:
                lst.append('event %s+%s' % (event, ','.join(subEvents)))
            else:
                lst.append('event %s' % (event))
        for field, data in self.iteritems():
            if data != self.fields[field]:
                lst.append('%s %s' % (field, data))
        return lst

    def __freeze__(self):
        return (self.subscriberId, self.freezeData())

    @staticmethod
    def __thaw__(frz):
        subscriberId, data = frz
        protocol, uri = data[0].split(None, 1)
        new = plugins.SubscriberFactory(subscriberId, protocol, uri)
        for line in data[1:]:
            field, val = line.split(None, 1)
            new.parse(field, val)
        return new



class StatusSubscriber(_AbstractStatusSubscriber, 
                       FreezableStatusSubscriberMixin):

    def parse(self, field, data):
        if field not in self.fields:
            getattr(self, 'parse_' + field)(data)
        else:
            self[field] = data

    def parse_apiVersion(self, data):
        self.apiVersion = data

    def parse_event(self, data):
        event = data.split(None)
        for event in data.split():
            fields = event.split('+', 1)
            if len(fields) == 1:
                self.watchEvent(event)
            else:
                self.watchEvent(fields[0], fields[1].split(','))

    def __deepcopy__(self, memo):
        s = self.__class__(self.subscriberId, self.uri)
        [ s.parse(*x.split(None, 1)) for x in self.freezeData()[1:] ]
        return s


apiutils.register(apiutils.api_freezable(StatusSubscriber), name='Subscriber')
