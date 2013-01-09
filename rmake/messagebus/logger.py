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


import logging
import time

from rmake.messagebus.message import LogRecords


class LogRelay(object):
    """
    Relay log records to a message bus server.

    Records will be sent at most once every 0.25 seconds.
    """

    DEADLINE = 0.25

    def __init__(self, sendFunc, task):
        self.sendFunc = sendFunc
        self.task = task
        self.buffered = []
        self.last_send = 0
        self.delayed_call = None

    def _formatException(self, ei):
        return logging._defaultFormatter.formatException(ei)

    def emitMany(self, records):
        for record in records:
            # Don't send traceback objects over the wire if it can be helped.
            if record.exc_info and not record.exc_text:
                record.exc_text = self._formatException(record.exc_info)
            record.exc_info = None
            self.buffered.append(record)
        self.maybeFlush()

    def emit(self, record):
        self.emitMany([record])

    def maybeFlush(self):
        if self.delayed_call or not self.buffered:
            # Nothing to do, or there's already a delayed call scheduled.
            return
        deadline = self.last_send + self.DEADLINE
        now = time.time()
        if now > deadline:
            # It's been long enough so go ahead and send it immediately.
            self.flush()
            return

        # Not long enough to send immediately, so schedule a call.
        from twisted.internet import reactor
        delay = deadline - now
        self.delayed_call = reactor.callLater(delay, self.flush)

    def flush(self):
        if not self.buffered:
            return

        # If there's a delayed flush in-flight (or if this *is* the delayed
        # flush) then cancel and clear it.
        if self.delayed_call:
            if self.delayed_call.active():
                self.delayed_call.cancel()
            self.delayed_call = None

        records, self.buffered = self.buffered, []
        msg = LogRecords(records, self.task.job_uuid, self.task.task_uuid)
        self.sendFunc(msg)
        self.last_send = time.time()

    def close(self):
        self.flush()
