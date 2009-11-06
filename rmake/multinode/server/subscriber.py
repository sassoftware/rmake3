#
# Copyright (c) 2009 rPath, Inc.
#
# All rights reserved.
#

from rmake.build.subscriber import *
from rmake.build.subscriber import _RmakePublisherProxy, _JobDbLogger


from rmake.multinode import messages
from rmake.multinode import nodetypes
from rmake.multinode import nodeclient

class rMakeServerNodeClient(nodeclient.NodeClient):
    sessionClass = 'SRV'
    name = 'rmake-server'

    def __init__(self, cfg, server):
        node = nodetypes.Server()
        nodeclient.NodeClient.__init__(self, cfg.getMessageBusHost(),
                cfg.messageBusPort, cfg, server, node)
        self.connect()

    def emitEvents(self, jobId, eventList):
        self.bus.sendSynchronousMessage('/event',
                                         messages.EventList(jobId, eventList))

class _RmakeBusPublisher(_RmakePublisherProxy):
    """
        Class that transmits events from internal build process -> rMake server.
    """

    # we override the _receiveEvents method to just pass these
    # events on, thus we just use listeners as a list of states we subscribe to
    listeners = set([
        'JOB_STATE_UPDATED',
        'JOB_LOG_UPDATED',
        'JOB_TROVES_SET',
        'JOB_COMMITTED',
        'JOB_LOADED',
        'JOB_FAILED',
        'TROVE_BUILDING',
        'TROVE_BUILT',
        'TROVE_FAILED',
        'TROVE_STATE_UPDATED',
        'TROVE_LOG_UPDATED',
        'TROVE_PREPARING_CHROOT',
        ])

    def __init__(self, client):
        self.client = client
        _RmakePublisherProxy.__init__(self)

    def attachToBuild(self, build):
        self.client = build.getWorker().client
        self.attach(build.getJob())

    def _freezeTroveEvent(self, event, buildTrove, *args, **kw):
        if buildTrove.amOwner():
             _RmakePublisherProxy._freezeTroveEvent(self, event, buildTrove,
                                                    *args, **kw)

    def _freezeJobEvent(self, event, job, *args, **kw):
        if job.amOwner():
             _RmakePublisherProxy._freezeJobEvent(self, event, job, *args, **kw)

    def _emitEvents(self, jobId, eventList):
        self.client.emitEvents(jobId, eventList)

