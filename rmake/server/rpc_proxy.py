import os
from twisted.web.resource import Resource
from twisted.web import http
from twisted.web import server
from rmake import constants
from rmake.messagebus.client import BusClientService

# thawers
import rmake.build.subscriber
import rmake.worker.resolver


class RPCProxy(BusClientService):

    sessionClass = 'proxy'
    subscriptions = []

    def __init__(self, reactor, listenPort, busAddress):
        BusClientService.__init__(self, reactor, busAddress)
        self.listenPort = listenPort
        self._port = None

        root = Resource()
        #root.putChild('monitor', MonitorResource(self))
        self.site = server.Site(root)
        self.site.requestFactory = ContinuableRequest

        self.subscribers = {}

    def startService(self):
        BusClientService.startService(self)

        self._port = self._reactor.listenTCP(self.listenPort, self.site)

    def stopService(self):
        BusClientService.stopService(self)

        if self._port is not None:
            self._port.stopListening()
            self._port = None

        self.client.service = None
        if self.connection is not None:
            self.connection.disconnect()
            self.connection = None

    #def busConnected(self):
    #    print 'connected'

    #def addSubscriber(self, uuid, handler, *args, **kwargs):
    #    print 'created', uuid
    #    self.subscribers[uuid] = (handler, args, kwargs)

    #def removeSubscriber(self, uuid):
    #    print 'destroyed', uuid
    #    del self.subscribers[uuid]

    #def emit(self, document):
    #    print 'emitting %d bytes' % len(document)
    #    for handler, args, kwargs in self.subscribers.values():
    #        handler(document, *args, **kwargs)

    def messageReceived(self, message):
        pass


def _add_headers(request):
    """Default headers for outgoing responses."""
    request.setHeader('server', 'rMake/%s %s' % (constants.version,
        server.version))
    request.setHeader('cache-control', 'no-cache')


def main():
    from twisted.internet import reactor
    service = RPCProxy(reactor, 8191, ('localhost', 50900))
    service.startService()

    reactor.run()


if __name__ == '__main__':
    main()
