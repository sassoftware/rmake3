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
import weakref
from rmake.messagebus.client import BusService


log = logging.getLogger(__name__)


class Dispatcher(BusService):

    role = 'dispatcher'
    description = 'rMake Dispatcher'

    def __init__(self, reactor, jid, password):
        BusService.__init__(self, reactor, jid, password)
        self.addObserver('heartbeat', self.onHeartbeat)

    def onHeartbeat(self, info, nodeType):
        print 'heartbeat from %s (%s)' % (info.sender, nodeType)


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
    setupLogging(consoleLevel=logging.DEBUG, consoleFormat='file',
            withTwisted=True)

    from twisted.internet import reactor
    service = Dispatcher(reactor, options.jid, options.password)
    if options.debug:
        service.logTraffic = True
    service.startService()
    reactor.run()


if __name__ == '__main__':
    main()
