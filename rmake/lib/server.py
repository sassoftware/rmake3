#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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
        self._serving = False

    def _closeLog(self):
        self._logger.close()

    def _close(self):
        self._closeLog()

    def getLogger(self):
        return self._logger

    def _exit(self, exitRc):
        sys.exit(exitRc)

    def serve_forever(self):
        self._serving = True
        startedShutdown = False
        try:
            while True:
                if self._halt:
                    self.info('Shutting down server')
                    coveragehook.save()
                    startedShutdown = True
                    self._shutDownAndExit()
                self._try('loop hook', self._serveLoopHook)
                self._try('request handling', self.handleRequestIfReady, .1)
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
                self._shutDownAndExit()
            raise

    def serve_once(self):
        self._serving = True
        startedShutdown = False
        self._try('loop hook', self._serveLoopHook)
        try:
            self._try('request handling', self.handleRequestIfReady, .1)
            self._try('loop hook', self._serveLoopHook)
            if self._halt:
                self.info('Shutting down server')
                coveragehook.save()
                startedShutdown = True
                self._shutDownAndExit()
        except SystemExit, err:
            self._serving = False
            try:
                coveragehook.save()
            except:
                pass
            self._exit(err.args[0])
        except:
            self._serving = False
            try:
                coveragehook.save()
            except:
                pass
            if not startedShutdown:
                self._shutDownAndExit()
            raise

    def handleRequestIfReady(self, sleepTime=0.1):
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

    def isKnownPid(self, pid):
        return pid in self._pids

    def _shutDown(self):
        self._killAllPids()
        self._exit(0)

    def _shutDownAndExit(self):
        try:
            self._try('halt', self._shutDown)
            self._exit(0)
        except:
            self._exit(1)

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

    def _collectChild(self, pid):
        try:
            pid, status = os.waitpid(pid, 0)
        except OSError, err:
            if err.errno in (errno.ESRCH, errno.ECHILD):
                pid = None
        if pid:
            self._try('pidDied', self._pidDied, pid, status)


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

    def _getPidName(self, pid, name=None):
        if not name:
            name = self._pids.get(pid, 'Unknown')
        return name

    def _killPid(self, pid, name=None, sig=signal.SIGTERM, timeout=20, 
                 hook=None, hookArgs=None, killGroup=False):
        if not pid:
            return
        if not hookArgs:
            hookArgs = []
        name = self._getPidName(pid, name)
        try:
            if killGroup:
                os.kill(-os.getpgid(pid), sig)
            else:
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
            if hook:
                hook(*hookArgs)

        if not found:
            if sig != signal.SIGKILL:
                self.warning('%s (pid %s) would not die, killing harder...' % (name, pid))
                self._killPid(pid, name, signal.SIGKILL, hook=hook,
                              hookArgs=hookArgs)
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

