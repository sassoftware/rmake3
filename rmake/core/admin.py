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
RPC controller for dispatcher administration functions.
"""


import logging
from twisted.application import service

from rmake.lib import apirpc
from rmake.lib.logger import logFailure

log = logging.getLogger(__name__)


class AdminController(apirpc.RPCServer, service.Service):

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
        dispatcher._addChild('admin', self)

    def startService(self):
        service.Service.startService(self)

        # Add workers in database to jabberlink whitelist.
        d = self.dispatcher.db.listRegisteredWorkers()
        def got_workers(workers):
            for jid, in workers:
                log.debug("Adding neighbor %s", jid)
                self.dispatcher.bus.listenNeighbor(jid)
        d.addCallback(got_workers)
        d.addErrback(logFailure)

    @apirpc.expose
    def registerWorker(self, jid):
        """Allow the given worker to connect to the cluster."""
        log.info("Registering worker %s", jid)
        d = self.dispatcher.db.registerWorker(jid)
        # Make it an initiating relationship at first since the worker may
        # already have tried and failed to connect. The next time the
        # dispatcher starts, though, the worker can connect immediately.
        d.addCallback(lambda _: self.dispatcher.bus.connectNeighbor(jid))
        return d

    @apirpc.expose
    def deregisterWorker(self, jid):
        """Disallow the given worker to connect to the cluster.

        Note that this currently doesn't take effect until the next time the
        dispatcher restarts, but may change in a future release.
        """
        log.info("Deregistering worker %s", jid)
        return self.database.deregisterWorker(jid)
