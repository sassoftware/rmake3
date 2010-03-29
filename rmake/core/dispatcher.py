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


import logging
from rmake.core.handler import getHandler
from rmake.db import database
from rmake.errors import RmakeError
from rmake.lib import dbpool
from rmake.lib import rpc_pickle
from rmake.lib.apirpc import RPCServer, expose
from rmake.lib.uuid import UUID
from rmake.messagebus.client import BusService
from rmake.messagebus.interact import InteractiveHandler
from twisted.application.internet import TCPServer
from twisted.application.service import MultiService
from twisted.web.resource import Resource
from twisted.web.server import Site


log = logging.getLogger(__name__)


class DispatcherBusService(BusService):

    role = 'dispatcher'
    description = 'rMake Dispatcher'

    def __init__(self, reactor, jid, password):
        BusService.__init__(self, reactor, jid, password, other_handlers={
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

    def __init__(self, reactor, jid, password):
        MultiService.__init__(self)

        dbpath = 'postgres://rmake'
        self.pool = dbpool.ConnectionPool(dbpath)
        self.db = database.Database(dbpath,
                dbpool.PooledDatabaseProxy(self.pool))

        self.bus = DispatcherBusService(reactor, jid, password)
        self.bus.setServiceParent(self)

        self.handlers = {}

        root = Resource()
        root.putChild('picklerpc', rpc_pickle.PickleRPCResource(self))
        TCPServer(9999, Site(root)).setServiceParent(self)

    def jobDone(self, job_uuid):
        if job_uuid in self.handlers:
            log.info("Job %s done", job_uuid)
            del self.handlers[job_uuid]
        else:
            log.warning("Job %s done but it is already finished", job_uuid)

    @expose
    def getJobs(self, callData, job_uuids):
        return self.pool.runWithTransaction(self.db.core.getJobs, job_uuids)

    @expose
    def createJob(self, callData, job):
        return self.pool.runWithTransaction(self._createJob, job)

    def _createJob(self, job):
        job = self.db.core.createJob(job)
        try:
            handler = self.handlers[job.job_uuid] = getHandler(job.job_type,
                    self, job)
        except KeyError:
            raise RmakeError("Job type %r is unsupported" % job.job_type)
        from twisted.internet import reactor
        reactor.callFromThread(handler.do, 'init')
        return job

    def updateJob(self, job, frozen=None, isDone=False):
        return self.pool.runWithTransaction(self._updateJob, job,
                frozen=frozen, isDone=isDone)

    def _updateJob(self, job, frozen=None, isDone=False):
        self.db.core.updateJob(job, frozen=frozen, isDone=isDone)
        if isDone:
            log.debug("Deleting job %s", job.job_uuid)
            del self.handlers[job.job_uuid]


def main():
    import optparse
    parser = optparse.OptionParser()
    parser.add_option('--debug', action='store_true')
    parser.add_option('-j', '--jid', default='rmake@localhost/rmake')
    parser.add_option('-p', '--password', default='password')
    options, args = parser.parse_args()
    if args:
        parser.error("No arguments expected")

    from rmake.lib.logger import setupLogging
    setupLogging(consoleLevel=(options.debug and logging.DEBUG or
        logging.INFO), consoleFormat='file', withTwisted=True)

    from twisted.internet import reactor
    service = Dispatcher(reactor, options.jid, options.password)
    if options.debug:
        service.logTraffic = True
    service.startService()
    reactor.run()


if __name__ == '__main__':
    main()
