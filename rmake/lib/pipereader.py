#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


"""
Simple class for reading marshalled data through a pipe.
"""
import fcntl
import marshal
import os
import select
import struct
import time

def getStructSize(char):
    # NOTE:  This could change depending on architecture - so you can't
    # use this method when reading from sockets!
    return len(struct.pack(char, 0))

LENGTH_STRUCT = 'L'

class PipeReader(object):
    def __init__(self, fd):
        self.fd = fd
        self.length = None
        self.buf = []
        self.sizeLength = getStructSize(LENGTH_STRUCT) 
        self.sizeNeeded = self.sizeLength 
        self.sizeBuf = []

    def __del__(self):
        self.close()

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def fileno(self):
        if self.fd is None:
            raise IOError('Pipe is closed')
        return self.fd

    def handle_read(self):
        if self.fd is None:
            return
        if self.length is not None:
            # handle length = 0
            if self.length:
                newStr = os.read(self.fd, self.length)
                if not newStr:
                    self.close()
                    return
                newLen = len(newStr)
                self.length -= newLen
                self.buf.append(newStr)
                if self.length:
                    return
            self.length = None
            text = ''.join(self.buf)
            self.buf = []
            return text
        sizeChars = os.read(self.fd, self.sizeNeeded)
        if not sizeChars:
            self.close()
            return
        self.sizeBuf.append(sizeChars)
        if len(sizeChars) == 0:
            os.close(self.fd)
            self.fd = None
            return

        if len(sizeChars) < self.sizeNeeded:
            self.sizeNeeded -= len(sizeChars)
            return
        else:
            sizeChars = ''.join(self.sizeBuf)
            self.sizeBuf = []
            self.sizeNeeded = self.sizeLength
            self.length = struct.unpack(LENGTH_STRUCT, sizeChars)[0]
            return

    def handleReadIfReady(self, sleep=0.1):
        if self.fd is None:
            return
        ready = None
        try:
            ready = select.select([self], [], [], sleep)[0]
        except select.error, e:
            pass
        if ready:
            return self.handle_read()

    def readUntilClosed(self, timeout=None):
        start = time.time()
        while self.fd is not None:
            data = self.handleReadIfReady()
            if data is not None:
                start = time.time()
                yield data
            if timeout and (time.time() - start > timeout):
                self.close()
                break

class PipeWriter(object):
    def __init__(self, fd):
        self.fd = fd
        self.length = None
        self.buf = []
        self.sizeBuf = []

    def __del__(self):
        self.close()

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def fileno(self):
        return self.fd

    def send(self, text):
        length = len(text)
        length = struct.pack(LENGTH_STRUCT, length)
        self.buf.extend((length + text))

    def handle_write(self):
        if self.buf:
            rc = os.write(self.fd, self.buf[0])
            if rc < len(self.buf[0]):
                self.buf[0] = self.buf[0][rc:]
            else:
                self.buf.pop(0)

    def hasData(self):
        return bool(self.buf)

    def handleWriteIfReady(self, sleep=0.1):
        if self.buf:
            try:
                ready = select.select([], [self], [], sleep)[1]
            except select.error, err:
                ready = False
            if ready:
                self.handle_write()
                return True
        return False

    def flush(self):
        while self.buf:
            self.handleWriteIfReady(sleep=5)

class MarshalPipeReader(PipeReader):
    def handle_read(self):
        txt = PipeReader.handle_read(self)
        if txt is None:
            return
        return marshal.loads(txt)

class MarshalPipeWriter(PipeWriter):
    def send(self, object):
        txt = marshal.dumps(object)
        return PipeWriter.send(self, txt)


def makePipes():
    inF, outF = os.pipe()
    fcntl.fcntl(inF, fcntl.F_SETFD,
                fcntl.fcntl(inF, fcntl.F_GETFD) | fcntl.FD_CLOEXEC)
    fcntl.fcntl(outF, fcntl.F_SETFD,
                fcntl.fcntl(outF, fcntl.F_GETFD) | fcntl.FD_CLOEXEC)
    return inF, outF


def makeMarshalPipes():
    inF, outF = makePipes()
    return MarshalPipeReader(inF), MarshalPipeWriter(outF)
