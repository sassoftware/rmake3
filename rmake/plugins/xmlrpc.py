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
        'JOB_STATE_UPDATED'    : '_jobStateUpdated',
        'JOB_LOG_UPDATED'      : '_jobLogUpdated',
        'JOB_TROVES_SET'       : '_jobTrovesSet',
        'JOB_COMMITTED'        : '_jobCommitted',
        'TROVE_STATE_UPDATED'  : '_troveStateUpdated',
        'TROVE_LOG_UPDATED'    : '_troveLogUpdated',
    }

    def receiveEvents(self, apiVer, eventList):
        eventList = thaw('EventList', (apiVer, eventList))[1]
        return self._receiveEvents(apiVer, eventList)

    def _jobTrovesSet(self, callData, jobId, troveList):
        pass

    def _jobCommitted(self, callData, jobId, troveList):
        pass

    def _jobLogUpdated(self, callData, jobId, state, status):
        pass

    def _jobStateUpdated(self, callData, jobId, state, status):
        pass

    def _troveStateUpdated(self, callData, (jobId, troveTuple), state, status):
        pass

    def _troveLogUpdated(self, callData, (jobId, troveTuple), state, status):
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
                 ])

    def __init__(self, *args, **kw):
        StatusSubscriber.__init__(self, *args, **kw)
        self.proxy = localrpc.ServerProxy(self.uri)

    def _receiveEvents(self, apiVer, eventList):
        if apiVer > self.apiVersion:
            apiVer = self.apiVersion
        eventList = freeze('EventList', (apiVer, eventList))[1]
        self.proxy.receiveEvents(self.apiVersion, eventList)
