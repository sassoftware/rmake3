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


import logging
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
            self.dispatcher.workerLogging(msg.records, msg.task_uuid)
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
