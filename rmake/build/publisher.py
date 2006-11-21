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
    Internal publisher for jobs and troves.  See build/subscriber.py for
    subscribers.  Jobs and troves trigger this publisher when their state
    changes.
"""

import traceback

from conary.lib import log

from rmake.lib import apirpc
from rmake.lib import apiutils
from rmake.lib import publisher
from rmake.lib import subscriber
from rmake.lib.apiutils import thaw, freeze


class JobStatusPublisher(publisher.Publisher):
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
