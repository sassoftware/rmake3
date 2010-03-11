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
from rmake.lib.pubsub import Subscriber
from rmake.messagebus.client import BusService, RmakeHandler
from rmake.messagebus.common import getInfoForm, NS_RMAKE
from wokkel import disco
from wokkel import iwokkel
from zope.interface import implements


log = logging.getLogger(__name__)


class DispatcherHandler(RmakeHandler):

    implements(iwokkel.IDisco)
    def getDiscoInfo(self, requestor, target, nodeIdentifier=''):
        return [disco.DiscoIdentity('automation', 'rmake', 'rMake Dispatcher'),
                disco.DiscoFeature(NS_RMAKE),
                getInfoForm('dispatcher'),
                ]
    def getDiscoItems(self, requestor, target, nodeIdentifier=''):
        return []


class Dispatcher(BusService):

    def _getHandler(self):
        return DispatcherHandler()


class EventHandler(Subscriber):
    """Process events and command results from workers."""

    def __init__(self, disp):
        self.disp = weakref.proxy(disp)

    def troveStateUpdated(self, (jobId, troveTuple), state, status):
        print '%d %s{%s} changed state: %s %s' % (jobId, troveTuple[0],
                troveTuple[2], buildtrove.stateNames[state], status)


def main():
    import optparse
    parser = optparse.OptionParser()
    parser.add_option('-j', '--jid', default='rmake@localhost')
    options, args = parser.parse_args()
    if args:
        parser.error("No arguments expected")

    from rmake.lib.logger import setupLogging
    setupLogging(consoleLevel=logging.DEBUG)

    from twisted.internet import reactor
    import epdb;epdb.st()
    service = Dispatcher(reactor, options.jid)
    service.startService()
    reactor.run()


if __name__ == '__main__':
    main()
