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
            self.dispatcher.workerHeartbeat(msg.info.sender, msg.caps,
                    msg.tasks, msg.slots)
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
