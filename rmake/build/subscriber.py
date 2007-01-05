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

    def troveBuilt(self, trove, troveList):
        self.db.troveBuilt(trove)

    def troveFailed(self, trove, failureReason):
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
        self.proxy = apirpc.XMLApiProxy(server.rMakeServer, uri)
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
            jobId =  data[0].jobId
            if isinstance(data[0], buildjob.BuildJob):
                newData = [ data[0].jobId ]
            if isinstance(data[0], buildtrove.BuildTrove):
                newData = [ (data[0].jobId, data[0].getNameVersionFlavor()) ]
            newData.extend(data[1:])
            newEventList.append((event, newData))
        newEventList = (apiVer, newEventList)

        self.proxy.emitEvents(jobId, newEventList)

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

apiutils.register(_EventListFreezer)
