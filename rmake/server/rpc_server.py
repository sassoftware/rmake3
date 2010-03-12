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


import logging
from twisted.application.internet import TCPServer
from twisted.application.service import MultiService
from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.web.xmlrpc import XMLRPC
from rmake.messagebus.client import BusClientService


log = logging.getLogger(__name__)


class ServerBusService(BusClientService):

    role = 'server'
    description = 'rMake RPC Server'

    def targetConnected(self):
        self.sendHeartbeat()

    def sendHeartbeat(self):
        self._send('heartbeat', nodeType='rpc')
        self._reactor.callLater(5, self.sendHeartbeat)


class ServerRPC(XMLRPC):

    def xmlrpc_test(self):
        return 'test'


class Server(MultiService):

    def __init__(self, reactor, jid, password, targetJID):
        MultiService.__init__(self)

        self.bus = ServerBusService(reactor, jid, password, targetJID)
        self.bus.setServiceParent(self)

        root = Resource()
        root.putChild('RPC2', ServerRPC())
        TCPServer(9999, Site(root)).setServiceParent(self)


def main():
    import optparse
    parser = optparse.OptionParser()
    parser.add_option('--debug', action='store_true')
    parser.add_option('-c', '--connect', default='rmake@localhost/rmake')
    parser.add_option('-j', '--jid', default='rserver@localhost/rmake')
    parser.add_option('-p', '--password', default='password')
    options, args = parser.parse_args()
    if args:
        parser.error("No arguments expected")

    from rmake.lib.logger import setupLogging
    setupLogging(consoleLevel=logging.DEBUG, consoleFormat='file',
            withTwisted=True)

    from twisted.internet import reactor
    service = Server(reactor, options.jid, options.password, options.connect)
    if options.debug:
        service.logTraffic = True
    service.startService()
    reactor.run()


if __name__ == '__main__':
    main()
