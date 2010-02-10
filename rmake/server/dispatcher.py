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

It creates commands, assigns them to nodes, and monitors the progress of the
commands.  Status updates are routed back to clients and to the database.
"""


import logging
import weakref
from twisted.application.service import Service
from rmake.lib.subscriber import StatusSubscriber
from rmake.multinode import messages
from rmake.messagebus.client import BusClientFactory, IBusClientService
from zope.interface import implements

# thawers
import rmake.build.subscriber
import rmake.worker.resolver

log = logging.getLogger(__name__)


class Dispatcher(Service):

    implements(IBusClientService)

    def __init__(self, reactor, busAddress):
        self.reactor = reactor
        self.busAddress = busAddress
        self.client = BusClientFactory('DSP2')
        self.client.subscriptions = [
                '/command',
                '/event',
                '/internal/nodes',
                '/nodestatus',
                '/commandstatus',
                ]
        self.connection = None
        self.subscriber = EventHandler(self)

    def startService(self):
        Service.startService(self)
        host, port = self.busAddress
        self.connection = self.reactor.connectTCP(host, port, self.client)
        self.client.service = self

    def stopService(self):
        Service.stopService(self)
        self.client.service = None
        if self.connection is not None:
            self.connection.disconnect()
            self.connection = None

    def busConnected(self):
        pass

    def busLost(self):
        pass

    def messageReceived(self, message):
        if isinstance(message, messages.NodeInfo):
            load = message.getNodeInfo().loadavg
            print 'Node %s: %.02f %.02f %.02f' % (message.getSessionId(),
                    load[0], load[1], load[2])
        elif isinstance(message, messages.NodeStatus):
            print 'Node %s: %s' % (message.getStatusId(), message.getStatus())
        elif isinstance(message, messages.CommandStatus):
            print 'Command %s: %s' % (message.getCommandId(),
                    message.headers.status)
        elif isinstance(message, messages.EventList):
            apiVer, eventList = message.getEventList()
            if apiVer == 1:
                self.subscriber._addEvent(message.getJobId(), eventList)
            else:
                log.error("Got event list with unknown API version %r", apiVer)
        else:
            print message
            print


class EventHandler(StatusSubscriber):
    """Process events and command results from workers."""

    def __init__(self, disp):
        StatusSubscriber.__init__(self, None, None)
        self.disp = weakref.proxy(disp)

    @StatusSubscriber.listen('TROVE_STATE_UPDATED')
    def troveStateUpdated(self, (jobId, troveTuple), state, status):
        print '%d %s{%s} changed state: %s %s' % (jobId, troveTuple[0],
                troveTuple[2], buildtrove.stateNames[state], status)
