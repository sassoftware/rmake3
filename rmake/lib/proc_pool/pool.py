#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


# Adapted from ampoule, provided under the MIT License:
# Copyright (c) 2008 Valentino Volonghi, Matthew Lefkowitz
# Copyright (c) 2009 Canonical Ltd.


import imp
import logging
import os
import random
import signal
import sys
from twisted.application import service
from twisted.internet import defer
from twisted.internet import error
from twisted.internet import task
from twisted.python import reflect

from rmake.lib import logger
from rmake.lib.proc_pool import connector

log = logging.getLogger(__name__)


class ProcessPool(service.Service):

    childFactory = None
    parentFactory = None
    minIdleProcs = 1
    maxIdleTime = 15
    recycleAfter = 500

    pool = None

    def __init__(self, starter=None, args=(), debug=False):
        if starter is None:
            # Current package might be rmake or rmake3, so use __name__.
            packages = ['twisted', __name__.split('.')[0]]
            starter = ProcessStarter(packages=packages, debug=debug)
        self.starter = starter
        self.args = dict(args)

        self.finished = False
        self.started = False
        self.processes = set()
        self.ready = set()
        self.busy = set()
        self.maint = task.LoopingCall(self.rebalance)
        self.maint.start(self.maxIdleTime, now=False)
        self.calls = {}

    def startService(self):
        """Start the process pool and spawn the first set of workers."""
        from twisted.internet import reactor
        def _start():
            self.finished = False
            self.started = True
            self.rebalance()
        reactor.callLater(0, _start)

    def stopService(self):
        self.finished = True
        l = [self.stopAWorker(x) for x in self.processes]
        def cb_stopped(_):
            if self.maint.running:
                self.maint.stop()
        return defer.DeferredList(l).addCallback(cb_stopped)

    def rebalance(self):
        """Start or stop workers to match the configured pool size."""
        if self.finished:
            return
        while len(self.ready) < self.minIdleProcs:
            self.startAWorker()
        while len(self.ready) > self.minIdleProcs:
            self.stopAWorker()

    def startAWorker(self):
        """Start one worker and place it into the idle pool."""
        if self.finished:
            return
        child = self.starter.startProcess(self.childFactory,
                self.parentFactory)
        self.processes.add(child)
        self.ready.add(child)
        self.calls[child] = 0
        log.debug("Starting worker %r", child)
        child.callRemote('startup', **self.args
                ).addErrback(logger.logFailure,
                        "Error starting worker subprocess:")
        child.finished.addBoth(self._pruneProcess, child)

    def stopAWorker(self, child=None):
        """Stop one worker, preferring idle workers if there are any."""
        from twisted.internet import reactor
        if child is None:
            if self.ready:
                child = self.ready.pop()
            else:
                child = random.choice(list(self.processes))
        log.debug("Stopping worker %r", child)
        # First instruct the worker to shut down gracefully.
        child.callRemote('shutdown'
                ).addErrback(lambda reason: reason.trap(
                    error.ProcessTerminated, error.ProcessDone))

        # Schedule the process to be killed if it doesn't exit on its own.
        signals = [signal.SIGTERM] * 3 + [signal.SIGKILL]
        def _killProcess():
            signum = signals.pop(0)
            log.info("Terminating worker %r with signal %d", child, signum)
            child.signalProcess(signum)
            if signals:
                delayCall[0] = reactor.callLater(3, _killProcess)
            else:
                delayCall[0] = None
        delayCall = [reactor.callLater(3, _killProcess)]

        # Stop the kill cycle once the process has exited.
        onExit = child.finished
        def _exited(result):
            if delayCall[0] and delayCall[0].active():
                delayCall[0].cancel()
            delayCall[0] = None
            return result
        onExit.addBoth(_exited)
        return onExit

    def _pruneProcess(self, _, child):
        log.debug("Removing worker %r", child)
        self.processes.discard(child)
        self.ready.discard(child)
        self.busy.discard(child)
        self.calls.pop(child, None)

    def doWork(self, command, **kwargs):
        if not self.ready:
            self.startAWorker()
        child = self.ready.pop()
        self.rebalance()
        self.busy.add(child)
        self.calls[child] += 1

        logBase = kwargs.pop('logBase', None)
        child.setLogBase(logBase)

        die = False
        if self.recycleAfter and self.calls[child] >= self.recycleAfter:
            die = True

        def cb_returned(result, child, is_error=False):
            child.setLogBase(None)
            self.busy.discard(child)
            if die:
                self.stopAWorker(child).addCallback(lambda _: self.rebalance())
            else:
                self.ready.add(child)
            return result

        return child.callRemote(command, **kwargs
                ).addCallback(cb_returned, child
                ).addErrback(cb_returned, child, is_error=True)


class ProcessStarter(object):

    connectorFactory = connector.ProcessConnector

    def __init__(self, packages=(), debug=False):
        self.packages = packages
        self.debug = debug

    @staticmethod
    def _checkRoundTrip(obj):
        """Make sure that C{obj} will be resolvable through C{qual} and
        C{namedAny}.
        """
        path = reflect.qual(obj)
        tripped = reflect.namedAny(path)
        if tripped is not obj:
            raise RuntimeError("importing %r is not the same as %r" %
                    (path, obj))
        return path

    def startProcess(self, childClass, parentClass):
        from twisted.internet import reactor
        childClassPath = self._checkRoundTrip(childClass)
        prot = self.connectorFactory(parentClass())

        bootstrapPath = os.path.join(os.path.dirname(__file__), 'bootstrap.py')

        # Insert required modules into PYTHONPATH if they lie outside the
        # system import locations.
        env = os.environ.copy()
        pythonPath = []
        for pkg in self.packages:
            p = os.path.dirname(imp.find_module(pkg)[1])
            if (p.startswith(os.path.join(sys.prefix, 'lib'))
                    or p.startswith(os.path.join(sys.prefix, 'lib64'))):
                continue
            pythonPath.append(p)
        pythonPath.extend(env.get('PYTHONPATH', '').split(os.pathsep))
        env['PYTHONPATH'] = os.pathsep.join(pythonPath)

        args = (sys.executable, bootstrapPath, childClassPath)
        fds = {connector.TO_CHILD: 'w', connector.FROM_CHILD: 'r'}
        if self.debug:
            fds.update({0: 0, 1: 1, 2: 2})
        else:
            fds.update({0: 'w', 1: 'r', 2: 'r'})
        reactor.spawnProcess(prot, sys.executable, args, env, childFDs=fds)
        return prot
