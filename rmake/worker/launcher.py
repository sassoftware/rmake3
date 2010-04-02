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
#

"""
The launcher is the root process of a worker node. It forks to handle incoming
jobs and accumulates messages to and distributes messages from the dispatcher
to the worker processes via a UNIX socket.

The launcher must re-exec after forking to prevent Twisted state from escaping
into the worker process.
"""

import logging
import os
import socket
import sys
from rmake.lib.twisted_extras.pickle_proto import PickleProtocol
from rmake.lib.twisted_extras.socketpair import socketpair
from rmake.messagebus import message
from rmake.messagebus.client import BusClientService
from rmake.messagebus.config import BusClientConfig
from rmake.messagebus.interact import InteractiveHandler
from rmake.worker import executor
from twisted.application.service import MultiService
from twisted.internet.error import ProcessDone, ProcessTerminated
from twisted.internet.protocol import ProcessProtocol

log = logging.getLogger(__name__)


class LauncherService(MultiService):

    def __init__(self, cfg):
        MultiService.__init__(self)
        self.cfg = cfg
        self.bus = LauncherBusService(cfg)
        self.bus.setServiceParent(self)

    def launch(self):
        from twisted.internet import reactor

        worker = LaunchedWorker(self)
        transport, sock = socketpair(worker.net, socket.AF_UNIX, reactor)

        args = [sys.executable, executor.__file__]
        reactor.spawnProcess(worker, sys.executable, args,
                os.environ, childFDs={0:0, 1:1, 2:2, 3:sock.fileno()})

        sock.close()


class LauncherBusService(BusClientService):

    role = 'worker'
    description = 'rMake Worker'

    def __init__(self, cfg):
        BusClientService.__init__(self, cfg, other_handlers={
            'interactive': LauncherInteractiveHandler(),
            })


class LauncherInteractiveHandler(InteractiveHandler):

    def __init__(self, *args, **kwargs):
        InteractiveHandler.__init__(self, *args, **kwargs)
        self.callbacks = {}

    def interact_test(self, msg, words):
        self.parent.parent.launch()


class LaunchedWorker(ProcessProtocol):

    def __init__(self, launcher):
        self.launcher = launcher
        self.net = LaunchedWorkerSocket(self)
        self.pid = None

    def connectionMade(self):
        self.pid = self.transport.pid
        log.debug("Executor %s started", self.pid)

        msg = message.StartWork(self.launcher.cfg)
        self.net.sendMessage(msg)

    def processEnded(self, failure):
        if failure.check(ProcessDone):
            log.debug("Executor %s terminated normally", self.pid)
            return
        elif failure.check(ProcessTerminated):
            if failure.value.signal:
                log.warning("Executor %s terminated with signal %s",
                        self.pid, failure.value.signal)
            else:
                log.warning("Executor %s terminated with status %s",
                        self.pid, failure.value.signal)
        else:
            log.error("Executor %s terminated due to an unknown error:\%s",
                    self.pid, failure.getTraceback())

        # FIXME: cleanup whatever the executor was handling


class LaunchedWorkerSocket(PickleProtocol):

    def __init__(self, worker):
        self.worker = worker

    def messageReceived(self, msg):
        print 'msg: %r' % msg


def main():
    import optparse
    cfg = BusClientConfig()
    parser = optparse.OptionParser()
    parser.add_option('--debug', action='store_true')
    parser.add_option('-c', '--config-file', action='callback', type='str',
            callback=lambda a, b, value, c: cfg.read(value))
    parser.add_option('--config', action='callback', type='str',
            callback=lambda a, b, value, c: cfg.configLine(value))
    options, args = parser.parse_args()
    if args:
        parser.error("No arguments expected")

    for name in ('dispatcherJID', 'xmppIdentFile'):
        if cfg[name] is None:
            sys.exit("error: Configuration option %r must be set." % name)

    from rmake.lib.logger import setupLogging
    setupLogging(consoleLevel=(options.debug and logging.DEBUG or
        logging.INFO), consoleFormat='file', withTwisted=True)

    from twisted.internet import reactor
    service = LauncherService(cfg)
    if options.debug:
        service.bus.logTraffic = True
    service.startService()
    reactor.run()


main()
