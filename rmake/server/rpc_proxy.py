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


class PublishChunk(object):
    """
    Encapsulates a chunk of data and the URI of the resource it goes with.
    
    Used for monitor streams, where the client may be subscribed to several
    resources simultaneously and needs to distinguish between updates from each.

    The exact location of chunk boundaries may or may not be meaningful,
    depending on the resource. For example, when tailing a logfile it generally
    does not matter where the boundary was placed, but in an XML status stream
    the boundary must be placed after the close of a top-level element.
    """
    def __init__(self, uri, data, final=False):
        self.uri = uri
        self.data = data
        self.final = final

    def __str__(self):
        header = '%d %s' % (len(self.data), self.uri)
        if self.final:
            header += ' final'
        return '\r\n'.join((header, self.data))


class MonitorResource(Resource):

    allowedMethods = ['TAIL', 'POST']

    def __init__(self, publisher):
        Resource.__init__(self)
        self.publisher = publisher

    def render_TAIL(self, request):
        uuid = os.urandom(20).encode('hex')
        #request.setHeader('content-type', 'application/octet-stream')
        request.setHeader('content-type', 'text/plain')
        request.setHeader('x-monitor-id', uuid)
        _add_headers(request)
        # Force the headers out so the client can get the UUID.
        request.write('')

        self.publisher.addSubscriber(uuid, self._emit, request)
        finished = request.notifyFinish()
        finished.addBoth(self._cleanup, uuid)

        return server.NOT_DONE_YET
    render_GET = render_TAIL

    def render_POST(self, request):
        data = request.content.read()
        chunk = PublishChunk('job/1234', data)
        self.publisher.emit(str(chunk))

        request.setResponseCode(http.NO_CONTENT)
        _add_headers(request)
        return ''

    def _cleanup(self, result, uuid):
        self.publisher.removeSubscriber(uuid)

    def _emit(self, document, request):
        request.write(document)


class ContinuableRequest(server.Request):

    """
    Extension of server.Request to handle 100-continue
    """

    def gotLength(self, length):
        server.Request.gotLength(self, length)

        expect = self.requestHeaders.getRawHeaders('expect')
        if expect and '100-continue' in expect:
            self.transport.write('%s 100 Continue\r\n\r\n'
                    % self.channel._version)


def main():
    from twisted.internet import reactor
    service = RPCProxy(reactor, 8191, ('localhost', 50900))
    service.startService()

    reactor.run()


if __name__ == '__main__':
    main()
