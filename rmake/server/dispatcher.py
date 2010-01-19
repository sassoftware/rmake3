from twisted.application.service import Service
from rmake.multinode import messages
from rmake.messagebus.client import BusClientFactory, IBusClientService
from zope.interface import implements

# thawers
import rmake.build.subscriber
import rmake.worker.resolver


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
            events = self.parseEvents(message.getEventList())
            for event in events:
                print 'Job %s event: %s' % (message.getJobId(), event)
        else:
            print message
            print

    @staticmethod
    def parseEvents(eventList):
        out = []
        api, eventList = eventList
        for (event, subEvent), params in eventList:
            if event == 'JOB_STATE_UPDATED':
                from rmake.build import buildjob
                out.append('Job status changed: %s %s' % (
                    buildjob.stateNames[subEvent], params[2]))
            elif event == 'TROVE_STATE_UPDATED':
                from rmake.build import buildtrove
                nvfc = '%s{%s}' % (params[0][1][0], params[0][1][3])
                out.append('Trove %s status changed: %s %s' % (
                    nvfc, buildtrove.stateNames[subEvent], params[2]))
            elif event == 'JOB_COMMITTED':
                troves = params[1]
                out.append('Job committed %d troves' % len(troves))
            elif event in ('TROVE_LOG_UPDATED',):
                pass
            else:
                out.append('Unknown event: %s %s' % (event, subEvent))
        return out
