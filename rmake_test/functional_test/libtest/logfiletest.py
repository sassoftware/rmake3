# -*- mode: python -*-
#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

import asyncore
import os
import signal
import socket
import sys
import time
import tempfile

#test
from rmake_test import rmakehelp

#rmake
from rmake.lib import logfile

class PortLogger(asyncore.dispatcher):
    def __init__(self, path):
        asyncore.dispatcher.__init__(self, None, {})
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.bind(('', 0))
        self.listen(1)
        self.path = path
        self.port = self.socket.getsockname()[1]

    def serveThenDie(self):
        try:
            while True:
                asyncore.poll(map=self._map)
        finally:
            os._exit(0)

    def handle_accept(self):
        csock, caddr = self.accept()
        # we only need to accept one request.
        self.del_channel()
        self.set_socket(csock)
        self.accepting = False
        self.connected = True
        self.logFile = open(self.path, 'w', 0) # no buffer

    def handle_read(self):
        rv = self.socket.recv(4096)
        if not rv:
            self.handle_close()
        os.write(self.logFile.fileno(), rv)

    def handle_close(self):
        os._exit(0)

    def writable(self):
        return False


class LogFileTest(rmakehelp.RmakeHelper):
    def testLogFile(self):
        # test logging to fd
        path = self.workDir + '/logfile'
        fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY)
        logFile = logfile.LogFile(fd)
        logFile.redirectOutput()
        print 'foo!'
        logFile.close()
        assert(open(path).read() == 'foo!\n')
        assert(self.captureOutput(sys.stdout.write, 'bar\n')[1] == 'bar\n')

    def testTee(self):
        def _redirect(logFile):
            logFile.teeOutput()
            print 'foo'
            logFile.close()

        path = self.workDir + '/logfile'
        logFile = logfile.LogFile(path)
        assert(self.captureOutput(_redirect, logFile)[1] == 'foo\n')
        assert(open(path).read() == 'foo\n')
        assert(self.captureOutput(sys.stdout.write, 'bar\n')[1] == 'bar\n')
        assert(open(path).read() == 'foo\n')

    def testRedirectToPort(self):
        path = self.workDir + '/logfile'
        outpath = self.workDir + '/logfile2'
        p = PortLogger(outpath)
        pid = os.fork()
        if not pid:
            p.serveThenDie()
        try:
            logFile = logfile.LogFile(path)
            logFile.logToPort('localhost', p.port)
            print "foo",
        finally:
            logFile.close()
            pid, status = self.waitThenKill(pid)
            assert(pid)
        assert(open(path).read() == 'foo')
        assert(open(outpath).read() == 'foo')

