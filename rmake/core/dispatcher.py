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

"""
The dispatcher is responsible for moving a job through the build workflow.

It creates jobs, assigns them to nodes, and monitors the progress of the jobs.
Status updates are routed back to clients and to the database.
"""


import copy
import logging
from rmake.core.handler import getHandlerClass
from rmake.db import database
from rmake.errors import RmakeError
from rmake.lib import dbpool
from rmake.lib import rpc_pickle
from rmake.lib.apirpc import RPCServer, expose
from rmake.lib.daemon import setDebugHook
from rmake.lib.uuid import UUID
from rmake.messagebus.client import BusService
from rmake.messagebus.config import DispatcherConfig
from rmake.messagebus.interact import InteractiveHandler
from twisted.application.internet import TCPServer
from twisted.application.service import MultiService
from twisted.web.resource import Resource
from twisted.web.server import Site


log = logging.getLogger(__name__)


class DispatcherBusService(BusService):

    role = 'dispatcher'
    description = 'rMake Dispatcher'

    def __init__(self, cfg):
        BusService.__init__(self, cfg, other_handlers={
            'interactive': DispatcherInteractiveHandler(),
            })
        self.addObserver('heartbeat', self.onHeartbeat)

    def onHeartbeat(self, info, nodeType):
        print 'heartbeat from %s (%s)' % (info.sender, nodeType)


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


class Dispatcher(MultiService, RPCServer):

    def __init__(self, cfg):
        MultiService.__init__(self)

        self.pool = dbpool.ConnectionPool(cfg.databaseUrl)
        self.db = database.Database(cfg.databaseUrl,
                dbpool.PooledDatabaseProxy(self.pool))

        self.bus = DispatcherBusService(cfg)
        self.bus.setServiceParent(self)

        self.handlers = {}

        root = Resource()
        root.putChild('picklerpc', rpc_pickle.PickleRPCResource(self))
        TCPServer(9999, Site(root)).setServiceParent(self)

    def jobDone(self, job_uuid):
        if job_uuid in self.handlers:
            status = self.handlers[job_uuid].job.status
            if 200 <= status < 300:
                result = 'done'
            elif 400 <= status < 500:
                result = 'failed'
            else:
                result = 'finished'
            log.info("Job %s %s: %s", job_uuid, result, status.text)
            del self.handlers[job_uuid]
        else:
            log.warning("Tried to remove job %s but it is already gone.",
                    job_uuid)

    @expose
    def getJobs(self, callData, job_uuids):
        return self.pool.runWithTransaction(self.db.core.getJobs, job_uuids)

    @expose
    def createJob(self, callData, job):
        #job = copy.deepcopy(job)
        try:
            handlerClass = getHandlerClass(job.job_type)
        except KeyError:
            raise RmakeError("Job type %r is unsupported" % job.job_type)

        d = self.pool.runWithTransaction(self.db.core.createJob, job)
        @d.addCallback
        def post_create(newJob):
            log.info("Job %s of type %r started", newJob.job_uuid,
                    newJob.job_type)
            self.handlers[newJob.job_uuid] = handler = handlerClass(self,
                    newJob)
            handler.start()
            return newJob
        return d

    def _createJob(self, job):
        job = self.db.core.createJob(job)
        return job

    def updateJob(self, job, frozen=None, isDone=False):
        # TODO: pass update params directly because deepcopy is super expensive
        job = copy.deepcopy(job)
        return self.pool.runWithTransaction(self._updateJob, job,
                frozen=frozen, isDone=isDone)

    def _updateJob(self, job, frozen=None, isDone=False):
        self.db.core.updateJob(job, frozen=frozen, isDone=isDone)
        if isDone:
            self.jobDone(job.job_uuid)

    def createTask(self, task):
        task = copy.deepcopy(task)
        return self.pool.runWithTransaction(self.db.core.createTaskMaybe, task)


def main():
    import optparse
    import sys

    cfg = DispatcherConfig()
    parser = optparse.OptionParser()
    parser.add_option('--debug', action='store_true')
    parser.add_option('-c', '--config-file', action='callback', type='str',
            callback=lambda a, b, value, c: cfg.read(value))
    parser.add_option('--config', action='callback', type='str',
            callback=lambda a, b, value, c: cfg.configLine(value))
    options, args = parser.parse_args()
    if args:
        parser.error("No arguments expected")

    for name in ('xmppJID', 'xmppIdentFile'):
        if cfg[name] is None:
            sys.exit("error: Configuration option %r must be set." % name)

    from rmake.lib.logger import setupLogging
    setupLogging(consoleLevel=(options.debug and logging.DEBUG or
        logging.INFO), consoleFormat='file', withTwisted=True)
    setDebugHook()

    from twisted.internet import reactor
    service = Dispatcher(cfg)
    if options.debug:
        service.bus.logTraffic = True
    service.startService()
    reactor.run()


if __name__ == '__main__':
    main()
