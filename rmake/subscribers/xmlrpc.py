#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
from rmake.lib import localrpc
from rmake.lib.apiutils import freeze, thaw

from rmake.lib.subscriber import StatusSubscriber

# To use the xmlrpc proxy:
# Subscribe using xmlrpc http://<youraddress>
# Derive from BasicXMLRPCStatusSubscriber 

class BasicXMLRPCStatusSubscriber(StatusSubscriber):
    """
        Receiving end of XMLRPC call with event list.
    """
    listeners = {
        'JOB_STATE_UPDATED'     : '_jobStateUpdated',
        'JOB_LOG_UPDATED'       : '_jobLogUpdated',
        'JOB_TROVES_SET'        : '_jobTrovesSet',
        'JOB_COMMITTED'         : '_jobCommitted',
        'TROVE_STATE_UPDATED'   : '_troveStateUpdated',
        'TROVE_LOG_UPDATED'     : '_troveLogUpdated',
        'TROVE_PREPARING_CHROOT' : '_trovePreparingChroot',
    }

    def receiveEvents(self, apiVer, eventList):
        eventList = thaw('EventList', (apiVer, eventList))[1]
        return self._receiveEvents(apiVer, eventList)

    def _jobTrovesSet(self, jobId, troveList):
        pass

    def _jobCommitted(self, jobId, troveList):
        pass

    def _jobLogUpdated(self, jobId, state, status):
        pass

    def _jobStateUpdated(self, jobId, state, status):
        pass

    def _troveStateUpdated(self, (jobId, troveTuple), state, status):
        pass

    def _troveLogUpdated(self, (jobId, troveTuple), state, status):
        pass

    def _trovePreparingChroot(self, (jobId, troveTuple), host, path):
        pass

class _XMLRPCSubscriberProxy(StatusSubscriber):
    """
        Sends job events over xmlrpc.

        The events sent are as follows:

            jobTrovesSet(jobId, troveData)
                - the job state was updated to set the given jobs.
                  - troveData is a list of (troveTup, state, status) tuples

            jobStateUpdated(jobId, job.state, job.status) 
                - the job state was changed.  State is defined in buildjob.

            troveStateUpdated(jobId, troveTup, trove.state)
                - the job state was updated.  State is defined in buildtrove.
    """
    # NOTE: Do not derive from this class unless you 
    # want to send different types of messages.
    protocol = 'xmlrpc'

    listeners = set(['JOB_STATE_UPDATED',
                 'JOB_LOG_UPDATED',
                 'JOB_TROVES_SET',
                 'JOB_COMMITTED',
                 'TROVE_LOG_UPDATED',
                 'TROVE_STATE_UPDATED',
                 'TROVE_PREPARING_CHROOT',
                 ])

    def __init__(self, *args, **kw):
        StatusSubscriber.__init__(self, *args, **kw)
        self.proxy = localrpc.ServerProxy(self.uri)

    def _receiveEvents(self, apiVer, eventList):
        if apiVer > self.apiVersion:
            apiVer = self.apiVersion
        eventList = freeze('EventList', (apiVer, eventList))[1]
        self.proxy.receiveEvents(self.apiVersion, eventList)
