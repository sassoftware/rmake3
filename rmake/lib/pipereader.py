#
# Copyright (c) 2007 rPath, Inc.
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
"""
Simple class for reading marshalled data through a pipe.
"""
import marshal
import os
import select
import struct

class PipeReader(object):
    def __init__(self, fd):
        self.fd = fd
        self.length = None
        self.buf = []
        self.sizeLength = 4 
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
        if self.length is not None:
            # handle length = 0
            if self.length:
                newStr = os.read(self.fd, self.length)
                newLen = len(newStr)
                self.length -= newLen
                self.buf.append(newStr)
                if self.length:
                    return
            self.length = None
            text = ''.join(self.buf)
            self.buf = []
            return text
        sizeChars = os.read(self.fd, self.sizeLength)
        self.sizeBuf.append(sizeChars)
        if len(sizeChars) == 0:
            os.close(self.fd)
            self.fd = None
            return

        if len(sizeChars) < self.sizeLength:
            self.sizeLength -= len(sizeChars)
            return
        else:
            sizeChars = ''.join(self.sizeBuf)
            self.sizeBuf = []
            self.sizeLength = 4
            self.length = struct.unpack('L', sizeChars)[0]
            return

    def handleReadIfReady(self, sleep=0.1):
        if self.fd is None:
            return
        ready = select.select([self], [], [], sleep)[0]
        if ready:
            return self.handle_read()

    def readUntilClosed(self):
        while self.fd is not None:
            data = self.handleReadIfReady()
            if data is not None:
                yield data


class PipeWriter(object):
    def __init__(self, fd):
        self.fd = fd
        self.length = None
        self.buf = []
        self.sizeLength = 4
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
        length = struct.pack('L', length)
        self.buf.extend((length + text))

    def handle_write(self):
        if self.buf:
            rc = os.write(self.fd, self.buf[0])
            if rc < len(self.buf[0]):
                self.buf[0] = self.buf[0][rc:]
            else:
                self.buf.pop(0)

    def handleWriteIfReady(self, sleep=0.1):
        if self.buf:
            ready = select.select([], [self], [], sleep)[1]
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

def makeMarshalPipes():
    inF, outF = os.pipe()
    return MarshalPipeReader(inF), MarshalPipeWriter(outF)
