#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

from rmake.lib import pubsub


class JobStatusPublisher(pubsub.Publisher):

    TROVE_LOADED = 'loaded'
    TROVE_PREBUILT = 'prebuilt'

    TROVE_RESOLVING = 'resolving'
    TROVE_RESOLVED = 'resolved'

    TROVE_PREPARING_CHROOT = 'chroot'
    TROVE_BUILDING = 'building'
    TROVE_BUILT = 'built'
    TROVE_FAILED = 'failed'
    TROVE_DUPLICATE = 'duplicate'
    TROVE_PREPARED = 'prepared'

    TROVE_STATE_UPDATED = 'updated'

    # these methods are called by the job and trove objects.
    # The publisher then publishes the right signal(s).

    def troveResolved(self, buildTrove, resolveResult):
        self._send(self.TROVE_RESOLVED, '', buildTrove, resolveResult)

    def troveStateUpdated(self, buildTrove, state, oldState, *args):
        self._send(self.TROVE_STATE_UPDATED, state, buildTrove, 
                   state, buildTrove.status)
        if buildTrove.isPreparing():
            self._send(self.TROVE_PREPARING_CHROOT, '', buildTrove, *args)
        elif buildTrove.isResolving():
            self._send(self.TROVE_RESOLVING, '', buildTrove, *args)
        if buildTrove.isBuilt():
            self._send(self.TROVE_BUILT, '', buildTrove, *args)
        if buildTrove.isPrebuilt():
            self._send(self.TROVE_PREBUILT, '', buildTrove, *args)
        if buildTrove.isDuplicate():
            self._send(self.TROVE_DUPLICATE, '', buildTrove, *args)
        elif buildTrove.isBuilding():
            self._send(self.TROVE_BUILDING, '', buildTrove, *args)
        elif buildTrove.isFailed():
            self._send(self.TROVE_FAILED, '', buildTrove, *args)
        if buildTrove.isPrepared():
            self._send(self.TROVE_PREPARED, '', buildTrove, *args)

    def troveLogUpdated(self, buildTrove, message):
        self._send(self.TROVE_LOG_UPDATED, '', buildTrove, buildTrove.state,
                   message)
