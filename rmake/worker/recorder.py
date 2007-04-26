#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import asyncore
import os
import socket

from conary.lib import util

from rmake.lib import server

class BuildLogRecorder(asyncore.dispatcher, server.Server):
    def __init__(self, key=None):
        server.Server.__init__(self)
        self.port = None
        self.logPath = None
        self.logFd = None
        self.key = key

    def _exit(self, rc=0):
        return os._exit(rc)

    def attach(self, trove, map=None):
        asyncore.dispatcher.__init__(self, None, map)
        self.trove = trove
        self.openSocket()
        self.openLogFile()

    def handleRequestIfReady(self, sleepTime=0.1):
        asyncore.poll2(timeout=sleepTime, map=self._map)

    def getPort(self):
        return self.port

    def getHost(self):
        return socket.getfqdn()

    def getLogPath(self):
        return self.logPath

    def openLogFile(self):
        util.mkdirChain(os.path.dirname(self.trove.logPath))
        fd = os.open(self.trove.logPath, os.W_OK | os.O_CREAT)
        self.logPath = self.trove.logPath
        self.logFd = fd

    def openSocket(self):
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.bind(('', 0))
        self.listen(1)
        self.port = self.socket.getsockname()[1]

    def handle_accept(self):
        csock, caddr = self.accept()
        if self.key:
            key = csock.recv(len(self.key) + 1)
            if key != (self.key + '\n'):
                csock.close()
            csock.send('OK\n')
        # we only need to accept one request.
        self.del_channel()
        self.set_socket(csock)
        self.accepting = False
        self.connected = True

    def close(self):
        asyncore.dispatcher.close(self)
        if self.logFd:
            os.close(self.logFd)
            self.logFd = None
        self._halt = True

    def handle_read(self):
        rv = self.socket.recv(4096)
        if not rv:
            self.connected = False
            self.close()
        else:
            os.write(self.logFd, rv)

    def _signalHandler(self, sigNum, frame):
        server.Server._signalHandler(self, sigNum, frame)
        # we got a signal, but have not finished reading yet.
        if self.connected and self.logFd:
            # keep reading until the socket is closed
            # or until we're killed again.
            self._halt = False

    def writable(self):
        return False
