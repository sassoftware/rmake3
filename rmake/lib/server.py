#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
"""
Utility server that manages child processes.
"""
import errno
import os
import signal
import sys
import time
import traceback

from conary.lib import coveragehook

from rmake import errors
from rmake.lib import logger as logger_

class Server(object):
    def __init__(self, logger=None):
        if logger is None:
            logger = logger_.Logger()
        self._logger = logger
        self._halt = False
        self._haltSignal = None
        self._pids = {}

    def _closeLog(self):
        self._logger.close()

    def _close(self):
        self._closeLog()

    def getLogger(self):
        return self._logger

    def _exit(self, exitRc):
        os._exit(exitRc)

    def serve_forever(self):
        self._halt = False
        self._haltSignal = None
        startedShutdown = False
        try:
            self._try('loop hook', self._serveLoopHook)
            while True:
                if self._halt:
                    self.info('Shutting down server')
                    coveragehook.save()
                    startedShutdown = True
                    self._try('halt', self._shutDown)
                    sys.exit(0)
                self._try('request handling', self.handleRequestIfReady, .1)
                self._try('loop hook', self._serveLoopHook)
        except SystemExit, err:
            try:
                coveragehook.save()
            except:
                pass
            self._exit(err.args[0])
        except:
            try:
                coveragehook.save()
            except:
                pass
            if not startedShutdown:
                self._try('halt', self._shutDown)
            raise

    def handleRequestIfReady(self, sleepTime):
        time.sleep(sleepTime)

    def _serveLoopHook(self):
        pass

    def _try(self, name, fn, *args, **kw):
        try:
            return fn(*args, **kw)
        except errors.uncatchableExceptions, err:
            raise
        except Exception, err:
            self.error('Error in %s: %s\n%s', name, err,
                      traceback.format_exc())
            raise
        assert(0)

    def _fork(self, name):
        pid = os.fork()
        if not pid:
            self._resetSignalHandlers()
            return
        self._pids[pid] = name
        return pid

    def _shutDown(self):
        self._killAllPids()
        sys.exit(0)

    def _killAllPids(self):
        for pid, name in self._pids.items():
            self._killPid(pid, name)

    def _resetSignalHandlers(self):
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.default_int_handler)

    def _signalHandler(self, sigNum, frame):
        # if they rekill, we just exit
        if sigNum == signal.SIGINT:
            signal.signal(sigNum, signal.default_int_handler)
        else:
            signal.signal(sigNum, signal.SIG_DFL)
        try:
            coveragehook.save()
        except:
            pass
        self._halt = True
        self._haltSignal = sigNum
        return

    def _installSignalHandlers(self):
        signal.signal(signal.SIGTERM, self._signalHandler)
        signal.signal(signal.SIGINT, self._signalHandler)

    def _collectChildren(self):
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except OSError, err:
            if err.errno != errno.ECHILD:
                raise
            else:
                pid = None
        if pid:
            self._try('pidDied', self._pidDied, pid, status)

    def _getExitMessage(self, pid, status, name=None):
        if name is None:
            name = self._pids.get(pid, 'Unknown')

        exitRc = os.WEXITSTATUS(status)
        signalRc = os.WTERMSIG(status)
        if not status:
            return
        if exitRc:
            return 'pid %s (%s) exited with exit status %s' % (pid, name, exitRc)
        else:
            return 'pid %s (%s) killed with signal %s' % (pid, name, signalRc)

    def _pidDied(self, pid, status, name=None):
        # We may want to check for failure here, but that is really
        # an odd case, the child process should have handled its own
        # logging.
        exitRc = os.WEXITSTATUS(status)
        signalRc = os.WTERMSIG(status)
        if status:
            self.warning(self._getExitMessage(pid, status, name))
        self._pids.pop(pid, None)

    def _killPid(self, pid, name=None, sig=signal.SIGTERM, timeout=20):
        if not pid:
            return
        if not name:
            name = self._pids.get(pid, 'Unknown')
        try:
            os.kill(pid, sig)
        except OSError, err:
            if err.errno in (errno.ESRCH,):
                # the process is already dead!
                return
            raise
        timeSlept = 0
        while timeSlept < timeout:
            try:
                found, status = os.waitpid(pid, os.WNOHANG)
            except OSError, err:
                if err.errno == errno.ECHILD:
                    # it's not our child process, so we can't 
                    # wait for it
                    return
                raise
            if found:
                break
            else:
                time.sleep(.5)
                timeSlept += .5

        if not found:
            if sig != signal.SIGKILL:
                self.warning('%s (pid %s) would not die, killing harder...' % (name, pid))
                self._killPid(pid, name, signal.SIGKILL)
            else:
                self.error('%s (pid %s) would not die.' % (name, pid))
            return
        # yay, our kill worked.
        self._pidDied(pid, status, name)

    def info(self, *args, **kw):
        self._logger.info(*args, **kw)

    def error(self, *args, **kw):
        self._logger.error(*args, **kw)

    def warning(self, *args, **kw):
        self._logger.warning(*args, **kw)

    def debug(self, *args, **kw):
        self._logger.debug(*args, **kw)

