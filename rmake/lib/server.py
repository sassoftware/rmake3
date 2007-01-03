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
        self._halt = False
        self._haltSignal = None
        if logger is None:
            logger = logger_.Logger()
        self._logger = logger

    def getLogger(self):
        return self._logger

    def serve_forever(self):
        self._halt = False
        self._haltSignal = None
        try:
            self._try('loop hook', self._serveLoopHook)
            while True:
                if self._halt:
                    try:
                        self.info('Shutting down server')
                        self._try('halt', self._shutDown)
                    finally:
                        os._exit(1)
                    assert(0)
                self._try('request handling', self.handleRequestIfReady, .1)
                self._try('loop hook', self._serveLoopHook)
        finally:
            coveragehook.save()

    def handleRequestIfReady(self, sleepTime):
        raise NotImplmentedError

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

    def _shutDown(self):
        sys.exit(0)

    def _signalHandler(self, sigNum, frame):
        # if they rekill, we just exit
        if sigNum == signal.SIGINT:
            signal.signal(sigNum, signal.default_int_handler)
        else:
            signal.signal(sigNum, signal.SIG_DFL)
        self._halt = True
        self._haltSignal = sigNum
        return

    def _collectChildren(self):
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except OSError, err:
            if err.errno != errno.ECHILD:
                raise
            else:
                pid = None
        if pid:
            self._pidDied(pid, status)

    def _pidDied(self, pid, status):
        # We may want to check for failure here, but that is really
        # an odd case, the child process should have handled its own
        # logging.
        exitRc = os.WEXITSTATUS(status)
        signalRc = os.WTERMSIG(status)
        if exitRc or signalRc:
            if exitRc:
                self.warning('pid %s exited with exit status %s' % (pid, exitRc))
            else:
                self.warning('pid %s killed with signal %s' % (pid, signalRc))

    def _killPid(self, pid, name, sig=signal.SIGTERM):
        if not pid:
            return
        try:
            os.kill(pid, sig)
        except OSError, err:
            if err.errno in (errno.ESRCH,):
                # the process is already dead!
                return
            raise
        timeSlept = 0
        while timeSlept < 20:
            found, status = os.waitpid(pid, os.WNOHANG)
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
        if os.WIFEXITED(status):
            exitRc = os.WEXITSTATUS(status)
            if exitRc:
                self.warning('%s (pid %s) exited with'
                            ' exit status %s' % (name, pid, exitRc))
        else:
            sigNum = os.WTERMSIG(status)
            if sigNum != sig:
                self.warning('%s (pid %s) exited with'
                            ' signal %s' % (name, pid, sigNum))

    def info(self, *args, **kw):
        self._logger.info(*args, **kw)

    def error(self, *args, **kw):
        self._logger.error(*args, **kw)

    def warning(self, *args, **kw):
        self._logger.warning(*args, **kw)

    def debug(self, *args, **kw):
        self._logger.debug(*args, **kw)

