#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
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
                  'TROVE_LOADED',
                  'TROVE_STATE_UPDATED',
                  'TROVE_PREPARING_CHROOT',
                  'TROVE_BUILDING',
                  'TROVE_BUILT',
                  'TROVE_PREBUILT',
                  'TROVE_RESOLVING',
                  'TROVE_RESOLVED',
                  'TROVE_DUPLICATE',
                  'TROVE_PREPARED',
                  'TROVE_FAILED',
                  'JOB_LOG_UPDATED',
                  'JOB_STATE_UPDATED',
                  'JOB_TROVES_SET',
                  'JOB_COMMITTED',
                  'JOB_LOADED',
                  'JOB_FAILED',
        ])

    # these methods are called by the job and trove objects.
    # The publisher then publishes the right signal(s).

    def jobStateUpdated(self, job, state, status, *args):
        self._emit(self.JOB_STATE_UPDATED, state, job, state, status)
        if job.isFailed():
            self._emit(self.JOB_FAILED, '', job, *args)
        elif job.isLoaded():
            self._emit(self.JOB_LOADED, '', job, *args)

    def jobLogUpdated(self, job, message):
        self._emit(self.JOB_LOG_UPDATED, '', job, job.state, message)

    def buildTrovesSet(self, job):
        self._emit(self.JOB_TROVES_SET, '', job, list(job.iterTroveList(True)))

    def troveResolved(self, trove, resolveResult):
        self._emit(self.TROVE_RESOLVED, '', trove, resolveResult)

    def jobCommitted(self, job, troveTupleList):
        self._emit(self.JOB_COMMITTED, '', job, troveTupleList)

    def troveStateUpdated(self, buildTrove, state, oldState, *args):
        self._emit(self.TROVE_STATE_UPDATED, state, buildTrove, 
                   state, buildTrove.status)
        if buildTrove.isPreparing():
            self._emit(self.TROVE_PREPARING_CHROOT, '', buildTrove, *args)
        elif buildTrove.isResolving():
            self._emit(self.TROVE_RESOLVING, '', buildTrove, *args)
        if buildTrove.isBuilt():
            self._emit(self.TROVE_BUILT, '', buildTrove, *args)
        if buildTrove.isPrebuilt():
            self._emit(self.TROVE_PREBUILT, '', buildTrove, *args)
        if buildTrove.isDuplicate():
            self._emit(self.TROVE_DUPLICATE, '', buildTrove, *args)
        elif buildTrove.isBuilding():
            self._emit(self.TROVE_BUILDING, '', buildTrove, *args)
        elif buildTrove.isFailed():
            self._emit(self.TROVE_FAILED, '', buildTrove, *args)
        if buildTrove.isPrepared():
            self._emit(self.TROVE_PREPARED, '', buildTrove, *args)

    def troveLogUpdated(self, buildTrove, message):
        self._emit(self.TROVE_LOG_UPDATED, '', buildTrove, buildTrove.state,
                   message)
