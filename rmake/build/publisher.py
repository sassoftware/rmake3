#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
        self._send(self.TROVE_RESOLVED, buildTrove, resolveResult)

    def troveStateUpdated(self, buildTrove, state, *args):
        self._send(self.TROVE_STATE_UPDATED, buildTrove, state,
                buildTrove.status)
        if buildTrove.isPreparing():
            self._send(self.TROVE_PREPARING_CHROOT, buildTrove, *args)
        elif buildTrove.isResolving():
            self._send(self.TROVE_RESOLVING, buildTrove, *args)
        if buildTrove.isBuilt():
            self._send(self.TROVE_BUILT, buildTrove, *args)
        if buildTrove.isPrebuilt():
            self._send(self.TROVE_PREBUILT, buildTrove, *args)
        if buildTrove.isDuplicate():
            self._send(self.TROVE_DUPLICATE, buildTrove, *args)
        elif buildTrove.isBuilding():
            self._send(self.TROVE_BUILDING, buildTrove, *args)
        elif buildTrove.isFailed():
            self._send(self.TROVE_FAILED, buildTrove, *args)
        if buildTrove.isPrepared():
            self._send(self.TROVE_PREPARED, buildTrove, *args)

    def troveLogUpdated(self, buildTrove, message):
        self._send(self.TROVE_LOG_UPDATED, buildTrove, buildTrove.state,
                   message)
