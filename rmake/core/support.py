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
from rmake.lib.logger import logFailure
from rmake.lib.uuid import UUID
from rmake.messagebus import message
from rmake.messagebus.client import BusService
from rmake.messagebus.interact import InteractiveHandler
from twisted.application.internet import TimerService

log = logging.getLogger(__name__)


class DispatcherBusService(BusService):

    description = 'rMake Dispatcher'

    def __init__(self, dispatcher, cfg):
        self.dispatcher = dispatcher
        BusService.__init__(self, cfg, other_handlers={
            'interactive': DispatcherInteractiveHandler(),
            })

    def messageReceived(self, msg):
        if isinstance(msg, message.TaskStatus):
            self.dispatcher.updateTask(msg.task)
        elif isinstance(msg, message.Heartbeat):
            self.dispatcher.workerHeartbeat(msg.info.sender, msg)
        elif isinstance(msg, message.LogRecords):
            self.dispatcher.workerLogging(msg.records, msg.job_uuid,
                    msg.task_uuid)
        else:
            BusService.messageReceived(self, msg)

    def onNeighborDown(self, jid):
        self.dispatcher.workerDown(jid)


class DispatcherInteractiveHandler(InteractiveHandler):

    def interact_show(self, msg, words):
        what = words.pop(0)
        if what == 'job':
            uuids = []
            for uuid in words:
                try:
                    uuids.append(UUID(uuid))
                except ValueError:
                    return "Bad UUID '%s'" % (uuid,)

            d = self.parent.parent.getJobs(None, uuids)

            @d.addCallback
            def on_get(jobs):
                out = ['']
                for uuid, job in zip(uuids, jobs):
                    if job is not None:
                        out.append('Job %s ' % job.job_uuid)
                        out.append('  Type: %s' % job.job_type)
                        out.append('  Owner: %s' % job.owner)
                    else:
                        out.append('Job %s not found' % uuid)
                return '\n'.join(out)

            return d
        else:
            return "Usage: show job <uuid>"


class WorkerChecker(TimerService):

    threshold = 4

    def __init__(self, dispatcher):
        TimerService.__init__(self, 5, self.checkWorkers)
        self.dispatcher = dispatcher

    def checkWorkers(self):
        for info in self.dispatcher.workers.values():
            info.expiring += 1
            if info.expiring > self.threshold:
                self.dispatcher.workerDown(info.jid)


class JobPruner(TimerService):

    def __init__(self, dispatcher):
        TimerService.__init__(self, 60, self.pruneJobs)
        self.dispatcher = dispatcher

    def pruneJobs(self):
        d = self.dispatcher.db.getExpiredJobs()
        @d.addCallback
        def got_jobs(jobs):
            if not jobs:
                return
            log.info("Deleting %d expired jobs", len(jobs))
            return self.dispatcher.deleteJobs(jobs)
        d.addErrback(logFailure)
        return d
