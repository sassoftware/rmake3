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

import logging
import time

from rmake.messagebus.message import LogRecords


class LogRelay(logging.Handler):
    """
    Relay log records to a message bus server.

    Records will be sent at most once every 0.25 seconds.
    """

    DEADLINE = 0.25

    def __init__(self, client, task_uuid):
        logging.Handler.__init__(self)
        self.client = client
        self.task_uuid = task_uuid
        self.buffered = []
        self.last_send = 0
        self.delayed_call = None

    def emit(self, record):
        self.buffered.append(record)
        self.maybe_flush()

    def maybe_flush(self):
        if self.delayed_call or not self.buffered:
            # Nothing to do, or there's already a delayed call scheduled.
            return
        deadline = self.last_send + self.DEADLINE
        now = time.time()
        if now > deadline:
            # It's been long enough so go ahead and send it immediately.
            self.flush()
            return

        # Not long enough to send immediately, so schedule a call. A small
        # constant is added to the delay to prevent fibrillation if callLater
        # returns sooner than expected.
        from twisted.internet import reactor
        delay = deadline - now + 0.05
        self.delayed_call = reactor.callLater(delay, self.flush)

    def flush(self):
        if not self.buffered or not self.client:
            return

        # If there's a delayed flush in-flight (or if this *is* the delayed
        # flush) then cancel and clear it.
        if self.delayed_call:
            if self.delayed_call.active():
                self.delayed_call.cancel()
            self.delayed_call = None

        records, self.buffered = self.buffered, []
        msg = LogRecords(records, self.task_uuid)
        self.client.sendToTarget(msg)
        self.last_send = time.time()

    def close(self):
        self.flush()
        self.client = None
        logging.Handler.close(self)


def createLogRelay(logBase, client, task_uuid, propagate=False):
    relay = LogRelay(client, task_uuid)
    logger = logging.getLogger(logBase)
    logger.propagate = propagate
    logger.addHandler(relay)
    return logger, relay
