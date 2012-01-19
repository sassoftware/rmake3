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


import os
from cStringIO import StringIO

from conary import streams

_L_PROTO    = 0
_L_HDRSZ    = 5
_L_PLDSZ    = 6

class InsufficientData(Exception):
    pass

class BadMagicError(Exception):
    pass

class BaseStreamSet(streams.StreamSet):
    streamDict = {}

    # Default frozen size
    frozenSize = 0

    def __init__(self):
        streams.StreamSet.__init__(self)

        # Incomplete reads will get appended here
        self._incomplete = None

    def thawString(self, data):
        """
        Thaw this StreamSet from the supplied string
        """
        if len(data) < self.frozenSize:
            raise InsufficientData()

        # Enough data available
        self._incomplete = None
        self.thaw(data)

    def thawFromStream(self, streamReader, maxRead=None):
        """
        Read the StreamSet from the stream
        Returns False if not enough data was available
        """

        # If a previous read returned false, try to append the data
        if self._incomplete:
            dn = self.frozenSize - len(self._incomplete)
            assert(dn > 0)
            data = self._incomplete
        else:
            dn = self.frozenSize
            data = ''

        if maxRead is not None:
            db = min(dn, maxRead)
        data += streamReader(dn)

        if len(data) != self.frozenSize:
            # Incomplete read
            self._incomplete = data
            return False

        # Enough data available
        self.thawString(data)
        return True


class PLead(BaseStreamSet):
    streamDict = {
        _L_PROTO : (streams.SMALL, streams.ShortStream, "msgProtocol"),
        _L_HDRSZ : (streams.SMALL, streams.IntStream,   "msgHeaderSize"),
        _L_PLDSZ : (streams.SMALL, streams.IntStream,   "msgPayloadSize"),
    }
    # Size of a frozen lead
    frozenSize = 32

    # Magic
    magic = '\xbe\xeb\xab\xba\x04\x00\x00\x00\00\00\00\00\00'

    def __init__(self):
        BaseStreamSet.__init__(self)
        self.msgProtocol.set(1)
        self.msgHeaderSize.set(0)
        self.msgPayloadSize.set(0)

    def freeze(self):
        rv = self.magic + BaseStreamSet.freeze(self)
        assert(len(rv) == 32)
        return rv

    def thawString(self, data):
        if len(data) < self.frozenSize:
            raise InsufficientData()

        # Enough data available
        self._incomplete = None

        magiclen = len(self.magic)
        if data[:magiclen] != self.magic:
            raise BadMagicError()

        self.thaw(data[magiclen:])

class PHeader(object):
    def __init__(self):
        self.headers = {}
        self.buf = None

    def freeze(self):
        return str(self)

    def __getitem__(self, key):
        return self.headers[key]

    def __setitem__(self, key, value):
        if isinstance(value, (list, tuple)):
            for item in value:
                if '\n' in str(item):
                    raise ValueError, 'Cannot have newlines in headers.'
        elif '\n' in str(value):
                raise ValueError, 'Cannot have newlines in headers.'
        self.headers[key] = value

    def __contains__(self, key):
        return key in self.headers

    def add_header(self, key, value):
        self[key] = value

    def append_header(self, key, value):
        if key in self:
            if isinstance(self[key], list):
                self[key].append(value)
            else:
                self[key] = [self[key], value]
        else:
            self[key] = value

    def __str__(self):
        keyOrder = ('messageType', 'messageId', 'sessionId', 'timeStamp', None)
        keyOrder = dict((x[1], x[0]) for x in enumerate(keyOrder))

        def keySort(header):
            if header in keyOrder:
                return (keyOrder[header], header)
            else:
                return (keyOrder[None], header)
        lines = []
        for key in sorted(self.headers, key=keySort):
            value = self.headers[key]
            if not isinstance(value, list):
                value = [value]
            for item in sorted(value):
                lines.append('%s: %s\n' % (key, item))
        return ''.join(lines)

    def readLine(self, ln):
        item = ln.split(None, 1)
        if len(item) == 1:
            key, value = item[0], ''
        else:
            key, value = item
        if key[-1] != ':':
            raise RuntimeError, 'bad header line %s' % ln
        key = key[:-1]
        self.append_header(key, value)

    def thawString(self, data):
        self.frozenSize = len(data)
        finished = self.thawFromStream(StringIO(data).read)
        assert(finished)

    def thawFromStream(self, streamReader):
        if self.frozenSize == 0:
            return True
        if self.buf is None:
            self.buf = []
            self.bytesRead = 0
            self.headers = {}

        buf = streamReader(self.frozenSize - self.bytesRead)
        self.bytesRead += len(buf)
        idx = buf.find('\n')
        while idx != -1:
            line = ''.join(self.buf + [buf[:idx]])
            self.buf = []
            self.readLine(line)
            buf = buf[idx+1:]
            idx = buf.find('\n')
        if buf:
            self.buf.append(buf)

        if self.bytesRead == self.frozenSize:
            assert(self.buf == [])
            self.buf = None
            self.bytesRead = 0
            return True

        else:
            return False

class EnvelopeWriter(object):
    def __init__(self, envelope):
        self._envelope = envelope
        self._leadWritten = False
        self._headerWritten = False
        self._lead = None
        self._header = None
        self._buf = None
        self._bytesWritten = 0

    def __call__(self, streamWriter):
        envelope = self._envelope
        if self._header is None:
            # Freeze header first to set message size
            self._header = envelope._header.freeze()
            envelope._lead.msgHeaderSize.set(len(self._header))
            self._lead = envelope._lead.freeze()

        if not self._leadWritten:
            rc = streamWriter(self._lead)
            if rc is None:
                rc = len(self._lead)

            self._lead = self._lead[rc:]
            if not self._lead:
                self._leadWritten = True
            else:
                return False
        if not self._headerWritten:
            rc = streamWriter(self._header)
            if rc is None:
                rc = len(self._header)
            self._header = self._header[rc:]
            if not self._header:
                self._headerWritten = True
            else:
                return False

        # Write payload
        if envelope._payloadStream is None:
            # No payload
            return True

        # Rewind payload stream
        envelope._payloadStream.seek(0)

        payloadSize = envelope._lead.msgPayloadSize()
        if payloadSize > 0 and envelope._payloadStream is None:
            raise ValueError

        if self._buf is None:
            self._bytesRead = 0
            self._bytesWritten = 0
            self._buf = ''
        if self._bytesWritten < payloadSize:
            if not self._buf:
                envelope._payloadStream.seek(self._bytesRead)
                toRead = payloadSize - self._bytesRead
                self._buf = envelope._payloadStream.read(toRead)
                self._bytesRead += len(self._buf)
                if not self._buf:
                    return False
            rc = streamWriter(self._buf)
            if rc is None:
                rc = len(self._buf)
            self._bytesWritten += rc
            self._buf = self._buf[rc:]
        if self._bytesWritten == payloadSize:
            self._buf = None
            return True

class Envelope(object):
    def __init__(self):
        self._lead = PLead()
        self._header = PHeader()
        self._payloadStream = None

        self.bufSize = 16384

        self._incLead = None
        self._incHeader = None
        self._incPayload = None
        self._writer = None

    def thawLead(self, streamReader):
        """Read the lead from the stream"""
        return self._lead.thawFromStream(streamReader)

    def thawHeader(self, streamReader):
        headerSize = self._lead.msgHeaderSize()
        self._header.frozenSize = headerSize
        return self._header.thawFromStream(streamReader)

    def setPayloadSize(self, size):
        self._lead.msgPayloadSize.set(size)

    def getPayloadSize(self):
        return self._lead.msgPayloadSize()

    def setPayloadStream(self, stream):
        self._payloadStream = stream

    def setHeaderSize(self, size):
        return self._lead.msgHeaderSize.set(size)

    def getHeaderSize(self):
        return self._lead.msgHeaderSize()

    def getHeaders(self):
        return self._header.headers

    def setHeaders(self, headers):
        self._header.headers = headers

    def getPayloadStream(self):
        return self._payloadStream

    def getContentType(self):
        return self._header['content-type']

    def setContentType(self, contentType):
        self._header['content-type'] = contentType

    def getWriter(self):
        return EnvelopeWriter(self)

    def freezeToStream(self, streamWriter):
        """
            Note - with this you can't write this message out to 
            multiple places at once
        """
        if not self._writer:
            self._writer = EnvelopeWriter(self)
        finished = self._writer(streamWriter)
        if finished:
            del self._writer
            self._writer = None
        return finished

    def freeze(self, streamWriter=None):
        if streamWriter is None:
            s = StringIO()
            streamWriter = s.write
        else:
            s = None

        self.freezeToStream(streamWriter)
        if s is not None:
            return s.getvalue()

    def thawFromStream(self, streamReader, blocking=False):
        """
        If blocking is True, the read from the stream is blocking.
        Returns True if thawing the message succeded, False if a short read
        happened (and the lead + header could not be completely read). False
        cannot be returned if blocking is True.
        """
        if (self._incLead, self._incHeader, self._incPayload) == \
                (None, None, None):
            self._incLead, self._incHeader = True, True
            self._incPayload = True

            self._payloadStream = StringIO()

        while 1:
            if self._incLead:
                self._incLead = not self.thawLead(streamReader)
                if not blocking:
                    # Lead is still incomplete
                    return False
                continue

            if self._incHeader:
                self._incHeader = not self.thawHeader(streamReader)
                if not blocking:
                    # Header is stil incomplete
                    return False
                continue

            if self._incPayload:
                payloadSize = self._lead.msgPayloadSize()
                toRead = payloadSize - self._payloadStream.tell()
                assert toRead > 0, toRead

                data = streamReader(toRead)
                assert data, "Should have read something"
                self._payloadStream.write(data)

                self._incPayload = (len(data) < toRead)

                if self._incPayload:
                    # Payload still incomplete
                    if not blocking:
                        return False
                    # Go back thorugh the loop to continue reading the payload
                    continue

                # Payload is now complete, we will get out of the loop at the
                # next break

            break

        # Message is no longer incomplete
        self._incLead, self._incHeader, self._incPayload = None, None, None

        self._payloadStream.seek(0)
        return True

    def hasCompleteLead(self):
        """Returns True if he lead was read"""
        return not self._incLead

    def hasCompleteHeader(self):
        """Returns True if the header was read"""
        return not (self._incLead or self._incHeader)

    def hasCompletePayload(self):
        """Returns True if the payload was read"""
        return not (self._incLead or self._incHeader or self._incPayload)

    def readPayload(self, size=None):
        """
        Reads data from the payload stream.
        If the optional size is specified, read no more than size bytes.
        Otherwise, read to the end of the stream.
        """
        if size is not None:
            return self._payloadStream.read(size)
        dataToRead = self._lead.msgPayloadSize()
        data = []
        dataRead = 0
        while dataRead < dataToRead:
            d = self._payloadStream.read(dataToRead - dataRead)
            if not d:
                break
            data.append(d)
            dataRead += len(d)
        return "".join(data)

    def reset(self):
        """Resets the state of the message"""
        self.__init__()

    def write(self, data):
        """Writes the data into the message"""
        if self._payloadStream is None:
            self._payloadStream = StringIO()

        self._payloadStream.write(data)

        # Set payload size
        self._lead.msgPayloadSize.set(self._payloadStream.tell())

    def seek(self, offset, whence=0):
        return self._payloadStream.seek(offset, whence)
    
    def tell(self):
        return self._payloadStream.tell()

    def truncate(self, size=None):
        if size:
            self._payloadStream.truncate(size)
        else:
            self._payloadStream.truncate()
