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

from rmake import constants
from rmake import errors
from rmake import plugins
from rmake.lib import apirpc
from rmake.lib import apiutils
from rmake.lib.apiutils import thaw, freeze

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


# --------------------------------------------------------------



class JobStatusPublisher(Publisher):
    states = set(['TROVE_LOG_UPDATED',
                  'TROVE_STATE_UPDATED',
                  'TROVE_BUILDING',
                  'TROVE_BUILT',
                  'TROVE_FAILED',
                  'JOB_LOG_UPDATED',
                  'JOB_STATE_UPDATED',
                  'JOB_TROVES_SET',
                  'JOB_COMMITTED'])

    # these methods are called by the job and trove objects.
    # The publisher then publishes the right signal(s).

    def jobStateUpdated(self, job, state, status, *args):
        self._emit(self.JOB_STATE_UPDATED, state, job, state, status)

    def jobLogUpdated(self, job, message):
        self._emit(self.JOB_LOG_UPDATED, '', job, job.state, message)

    def buildTrovesSet(self, job):
        self._emit(self.JOB_TROVES_SET, '', job, list(job.iterTroveList()))

    def jobCommitted(self, job, troveTupleList):
        self._emit(self.JOB_COMMITTED, '', job, troveTupleList)

    def troveStateUpdated(self, buildTrove, state, oldState, *args):
        self._emit(self.TROVE_STATE_UPDATED, state, buildTrove, 
                   state, buildTrove.status)
        if buildTrove.isBuilt():
            self._emit(self.TROVE_BUILT, '', buildTrove, *args)
        elif buildTrove.isBuilding():
            self._emit(self.TROVE_BUILDING, '', buildTrove, *args)
        elif buildTrove.isFailed():
            self._emit(self.TROVE_FAILED, '', buildTrove, *args)

    def troveLogUpdated(self, buildTrove, message):
        self._emit(self.TROVE_LOG_UPDATED, '', buildTrove, buildTrove.state,
                   message)

#---------------------------------------------------------

# External subscribers - derive from the StatusSubscriber class
# to create a new subscriber to external events

class _Subscriber(object):

    listeners = {}

    def __init__(self):
        self.events = {}

    def _receiveEvents(self, apiVersion, eventList):
        for event, data in eventList:
            getattr(self, self.listeners[event[0]])(*data)

    def watchEvent(self, state, substates=set()):
        self.events.setdefault(state, {}).update(substates)


class StatusSubscriber(_Subscriber):

    fields = {}

    def __init__(self, subscriberId, uri):
        _Subscriber.__init__(self)
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

    def __deepcopy__(self, memo):
        s = self.__class__(self.subscriberId, self.uri)
        [ s.parse(*x.split(None, 1)) for x in self.freezeData()[1:] ]
        return s


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
                self.addEvent(event[0], event[1].split(','))

apiutils.register(apiutils.api_freezable(StatusSubscriber), name='Subscriber')

#--------------------------------------------------------------

# Internal Subscribers - not for general use
# These subscribers are used by the build job
# to update state, and to pass information back to the rmake server.
#

class _InternalSubscriber(_Subscriber):

    def __init__(self):
        self.job = None
        _Subscriber.__init__(self)

    def attach(self, job):
        assert(not self.job)
        self.job = job
        logger = job.getStatusLogger()
        logger.subscribe(self.listeners, self._receiveEvents, dispatcher=True)


class _JobDbLogger(_InternalSubscriber):
    listeners = {
        'JOB_STATE_UPDATED'    : 'jobStateUpdated',
        'JOB_LOG_UPDATED'      : 'jobLogUpdated',
        'JOB_TROVES_SET'       : 'jobTrovesSet',
        'JOB_COMMITTED'        : 'jobCommitted',
        'TROVE_BUILDING'       : 'troveBuilding',
        'TROVE_BUILT'          : 'troveBuilt',
        'TROVE_FAILED'         : 'troveFailed',
        'TROVE_STATE_UPDATED'  : 'troveStateUpdated',
        'TROVE_LOG_UPDATED'    : 'troveLogUpdated',
    }

    def __init__(self, db):
        self.db = db
        _InternalSubscriber.__init__(self)

    def _receiveEvents(self, apiVersion, eventList):
        self.db.commitAfter(
            _InternalSubscriber._receiveEvents, self,
            apiVersion, eventList)

    def troveBuilt(self, trove, cs):
        self.db.troveBuilt(trove)

    def troveFailed(self, trove):
        self.db.troveFailed(trove)

    def troveBuilding(self, trove):
        self.db.troveBuilding(trove)

    def troveStateUpdated(self, trove, state, status):
        self.db.updateTroveStatus(trove)

    def troveLogUpdated(self, trove, state, status):
        self.db.updateTroveLog(trove, status)

    def jobStateUpdated(self, job, state, status):
        self.db.updateJobStatus(job)

    def jobLogUpdated(self, job, state, status):
        self.db.updateJobLog(job, status)

    def jobTrovesSet(self, job, troveList):
        self.db.setBuildTroves(job)

    def jobCommitted(self, job, troveList):
        # it'd be good to update the trove binary troves here.
        # put I don't see how to do it.
        pass

class _RmakeServerPublisher(_InternalSubscriber):
    """
        Sends job events from Rmake Server ->  Subscribers
    """
    def __init__(self):
        _InternalSubscriber.__init__(self)

    def emitEvents(self, db, jobId, eventList):
        eventsBySubscriber = self._processEvents(db, jobId, eventList)
        for subscriber, eventList in eventsBySubscriber.iteritems():
            try:
                subscriber._receiveEvents(subscriber.apiVersion, eventList)
            except Exception, err:
                log.error('Subscriber %s failed: %s\n%s', subscriber,
                          err, traceback.format_exc())

    def _processEvents(self, db, jobId, eventList):
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

class _RmakeServerPublisherProxy(_InternalSubscriber):
    """
        Class that transmits events from internal build process -> rMake server.
    """

    # we override the _receiveEvents method to just pass these
    # events on, thus we just use listeners as a list of states we subscribe to
    listeners = set([
        'JOB_STATE_UPDATED',
        'JOB_LOG_UPDATED',
        'JOB_TROVES_SET',
        'JOB_COMMITTED',
        'TROVE_STATE_UPDATED',
        'TROVE_LOG_UPDATED',
        ])

    def __init__(self, uri):
        from rmake.server import server
        self.proxy = apirpc.ApiProxy(server.rMakeServer, uri)
        _InternalSubscriber.__init__(self)

    def _receiveEvents(self, apiVer, eventList):
        # Convert eventList from the format for _intrajob_ events
        # to the format for _extrajob_ events - we're passing this back
        # to the main server.  Where there was a job, we have a jobId, and None
        # where there was a trove, we have a jobId and trove tuple
        from rmake.build import buildjob
        from rmake.build import buildtrove
        newEventList = []
        for event, data in eventList:
            if isinstance(data[0], buildjob.BuildJob):
                newData = [ data[0].jobId ]
            if isinstance(data[0], buildtrove.BuildTrove):
                newData = [ (data[0].jobId, data[0].getNameVersionFlavor()) ]
            newData.extend(data[1:])
            newEventList.append((event, newData))
        newEventList = (apiVer, newEventList)

        self.proxy.emitEvents(self.job.jobId, newEventList)

class EventListFreezer(object):
    name = 'EventList'
    # FIXME: Events should be thin object wrappers
    # so that we can abstract away some of this crap and put versioning
    # information in a reasonable place.

    @classmethod
    def freeze_JOB_TROVES_SET(class_, apiVer, data):
        return [ data[0], freeze('troveTupleList', data[1]) ]

    @classmethod
    def thaw_JOB_TROVES_SET(class_, apiVer, data):
        return [ data[0], thaw('troveTupleList', data[1]) ]

    @classmethod
    def freeze_JOB_COMMITTED(class_, apiVer, data):
        return [ data[0], freeze('troveTupleList', data[1]) ]

    @classmethod
    def thaw_JOB_COMMITTED(class_, apiVer, data):
        return [ data[0], thaw('troveTupleList', data[1]) ]

    @classmethod
    def __freeze__(class_, eventList):
        apiVer, eventList = eventList
        newEventList = []
        for ((event, subevent), data) in eventList:
            if not isinstance(data[0], int):
                data = [(data[0][0], freeze('troveTuple', data[0][1]))] + data[1:]
            fn = getattr(class_, 'freeze_' + event, None)
            if fn is not None:
                data = fn(apiVer, data)

            newEventList.append(((event, subevent), data))
        return apiVer, newEventList

    @classmethod
    def __thaw__(class_, eventList):
        apiVer, eventList = eventList
        newEventList = []
        for ((event, subevent), data) in eventList:
            if not isinstance(data[0], int):
                data = [(data[0][0], thaw('troveTuple', data[0][1]))] + data[1:]
            fn = getattr(class_, 'thaw_' + event, None)
            if fn is not None:
                data = fn(apiVer, data)
            newEventList.append(((event, subevent), data))
        return apiVer, newEventList

apiutils.register(EventListFreezer)
