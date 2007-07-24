#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
    Internal subscribers for jobs.  Internal subscribers are within the same
    process as the BuildJob, and have their messages sent immediately after
    the publishing method is called.  External subscribers are sent an event
    list by the rMake Server.

    Subscribers listen to a job and its troves for particular state changes.
    When such events are received, the events are passed to functions
    based on the event type.

    Currently, there are 2 Internal Subscribers:
     * _JobDBLogger: listens to state changes and records them in the database.
     * _RmakeServerPublisherProxy: listens to events and passes them off to
       the rMake Server.

    NOTE: there is one other internal subscriber, the dependency handler.
"""
from conary.lib import log

from rmake.lib import apirpc
from rmake.lib import apiutils
from rmake.lib import subscriber
from rmake.lib.apiutils import thaw, freeze


# Internal Subscribers - not for general use
# These subscribers are used by the build job
# to update state, and to pass information back to the rmake server.

class _InternalSubscriber(subscriber.Subscriber):

    def __init__(self):
        subscriber.Subscriber.__init__(self)

    def attach(self, job):
        publisher = job.getPublisher()
        publisher.subscribe(self.listeners, self._receiveEvents,
                            dispatcher=True)

class _JobDbLogger(_InternalSubscriber):
    listeners = {
        'JOB_STATE_UPDATED'      : 'jobStateUpdated',
        'JOB_LOG_UPDATED'        : 'jobLogUpdated',
        'JOB_TROVES_SET'         : 'jobTrovesSet',
        'JOB_COMMITTED'          : 'jobCommitted',
        'TROVE_PREPARING_CHROOT' : 'trovePreparingChroot',
        'TROVE_RESOLVING'        : 'troveResolving',
        'TROVE_BUILDING'         : 'troveBuilding',
        'TROVE_BUILT'            : 'troveBuilt',
        'TROVE_FAILED'           : 'troveFailed',
        'TROVE_STATE_UPDATED'    : 'troveStateUpdated',
        'TROVE_LOG_UPDATED'      : 'troveLogUpdated',
    }

    def __init__(self, db):
        self.db = db
        _InternalSubscriber.__init__(self)

    def _receiveEvents(self, apiVersion, eventList):
        self.db.commitAfter(
            _InternalSubscriber._receiveEvents, self,
            apiVersion, eventList)

    def trovePreparingChroot(self, trove, host, path):
        self.db.trovePreparingChroot(trove)

    def troveBuilt(self, trove, troveList):
        self.db.troveBuilt(trove)

    def troveFailed(self, trove, failureReason):
        self.db.troveFailed(trove)

    def troveBuilding(self, trove, logPath, pid):
        self.db.troveBuilding(trove)

    def troveResolving(self, trove, hostName, logPath, pid):
        self.db.troveResolving(trove)

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

    def jobCommitted(self, job, troveTupleMap):
        self.db.jobCommitted(job, troveTupleMap)

class _RmakePublisherProxy(_InternalSubscriber):
    """
        Class that transmits events from internal build process -> 
         some location .
    """

    # we override the _receiveEvents method to just pass these
    # events on, thus we just use listeners as a list of states we subscribe to
    listeners = set([
        'JOB_STATE_UPDATED',
        'JOB_LOG_UPDATED',
        'JOB_TROVES_SET',
        'JOB_COMMITTED',
        'TROVE_PREPARING_CHROOT',
        'TROVE_BUILDING',
        'TROVE_BUILT',
        'TROVE_FAILED',
        'TROVE_RESOLVING',
        'TROVE_RESOLVED',
        'TROVE_STATE_UPDATED',
        'TROVE_LOG_UPDATED',
        ])

    def _freezeTroveEvent(self, event, buildTrove, eventData, eventList):
        newData = [ (buildTrove.jobId, buildTrove.getNameVersionFlavor(True)) ]
        newData.extend(eventData)
        eventList.append((event, newData))

    def _freezeJobEvent(self, event, job, eventData, eventList):
        newData = [ job.jobId ]
        newData.extend(eventData)
        eventList.append((event, newData))

    def _receiveEvents(self, apiVer, eventList):
        # Convert eventList from the format for _intrajob_ events
        # to the format for _extrajob_ events - we're passing this back
        # to the main server.  Where there was a job, we have a jobId, and None
        # where there was a trove, we have a jobId and trove tuple
        from rmake.build import buildjob
        from rmake.build import buildtrove
        newEventList = []
        for event, data in eventList:
            jobId =  data[0].jobId
            if isinstance(data[0], buildjob.BuildJob):
                self._freezeJobEvent(event, data[0], data[1:], newEventList)
            if isinstance(data[0], buildtrove.BuildTrove):
                self._freezeTroveEvent(event, data[0], data[1:], newEventList)
        if not newEventList:
            return
        newEventList = (apiVer, newEventList)
        self._emitEvents(jobId, newEventList)

    def _emitEvents(self, jobId, eventList):
        raise NotImplementedError

class _RmakeServerPublisherProxy(_RmakePublisherProxy):
    def __init__(self, uri):
        from rmake.server import server
        self.proxy = apirpc.XMLApiProxy(server.rMakeServer, uri)
        _RmakePublisherProxy.__init__(self)

    def _emitEvents(self, jobId, eventList):
        self.proxy.emitEvents(jobId, eventList)

class _EventListFreezer(object):
    """
        Internal method to freeze event lists for sending over xmlrpc.

        In their frozn format, events are 

        For job events:
            (event, jobId, *eventData)
        For trove events:
            (event,  (jobId, troveTuple), *eventData)

        This class is automatically registered as the freezer/thawer for 
        EventList items passed over xmlrpc.
    """

    name = 'EventList'
    # FIXME: Events should be thin object wrappers
    # so that we can abstract away some of this crap and put versioning
    # information in a reasonable place.

    @classmethod
    def freeze_JOB_TROVES_SET(class_, apiVer, data):
        return [ data[0], freeze('troveContextTupleList', data[1]) ]

    @classmethod
    def thaw_JOB_TROVES_SET(class_, apiVer, data):
        return [ data[0], thaw('troveContextTupleList', data[1]) ]

    @classmethod
    def freeze_JOB_COMMITTED(class_, apiVer, data):
        return [ data[0], freeze('troveContextTupleList', data[1]) ]

    @classmethod
    def thaw_JOB_COMMITTED(class_, apiVer, data):
        return [ data[0], thaw('troveContextTupleList', data[1]) ]

    @classmethod
    def freeze_TROVE_BUILT(class_, apiVer, data):
        return [ data[0], freeze('troveTupleList', data[1]) ]

    @classmethod
    def thaw_TROVE_BUILT(class_, apiVer, data):
        return [ data[0], thaw('troveTupleList', data[1]) ]

    @classmethod
    def freeze_TROVE_FAILED(class_, apiVer, data):
        return [ data[0], freeze('FailureReason', data[1]) ]

    @classmethod
    def thaw_TROVE_FAILED(class_, apiVer, data):
        return [ data[0], thaw('FailureReason', data[1]) ]

    @classmethod
    def thaw_TROVE_RESOLVED(class_, apiVer, data):
        return [ data[0], thaw('ResolveResult', data[1]) ]

    @classmethod
    def freeze_TROVE_RESOLVED(class_, apiVer, data):
        return [ data[0], freeze('ResolveResult', data[1]) ]


    @classmethod
    def __freeze__(class_, eventList):
        apiVer, eventList = eventList
        newEventList = []
        for ((event, subevent), data) in eventList:
            if not isinstance(data[0], int):
                data = [(data[0][0], freeze('troveContextTuple', data[0][1]))] + data[1:]
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
                data = [(data[0][0], thaw('troveContextTuple', data[0][1]))] + data[1:]
            fn = getattr(class_, 'thaw_' + event, None)
            if fn is not None:
                data = fn(apiVer, data)
            newEventList.append(((event, subevent), data))
        return apiVer, newEventList

apiutils.register(_EventListFreezer)
