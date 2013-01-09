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


"""
Write and read logs that can be re-parsed back into mostly intact records,
regardless of the contents of the log message.
"""


import logging
import os
import time
from collections import namedtuple
from conary.lib import util


class StructuredLogFormatter(logging.Formatter):

    def __init__(self):
        logging.Formatter.__init__(self,
                '[%(asctime)s] %(levelno)s %(name)s %(message)s',
                None)

    def formatTime(self, record, datefmt=None):
        # ISO 8601 timestamp, UTC only
        timetup = time.gmtime(record.created)
        timestampPart = time.strftime('%FT%T', timetup)
        return '%s.%06dZ' % (timestampPart, int(round(record.msecs * 1000)))

    def format(self, record):
        # Prefix each record with its size, this way newlines or binary garbage
        # in the message don't prevent the log from being parsed.
        payload = logging.Formatter.format(self, record)
        if isinstance(payload, unicode):
            payload = payload.encode('utf8')
        size = len(payload) + 1  # add trailing newline
        return '%x %s' % (size, payload)


_LogLine = namedtuple('_LogLine',
        'timestamp level name message startPos endPos raw')


class StructuredLogParser(object):

    def __init__(self, stream, asRecords=True):
        self.stream = stream
        self.asRecords = asRecords

    def __iter__(self):
        return self

    def next(self):
        startPos = self.stream.tell()
        buf = ''
        while True:
            d = self.stream.read(1)
            if not d:
                self.stream.seek(startPos)
                raise StopIteration
            buf += d
            if d == ' ':
                break
            if not (('0' <= d <= '9') or ('a' <= d <= 'f')):
                raise ValueError("malformed logfile")
        size = int(buf, 16)
        payload = self.stream.read(size)
        if len(payload) < size:
            self.stream.seek(startPos)
            raise StopIteration
        endPos = startPos + len(buf) + size
        timestamp, level, name, message = payload.split(' ', 3)
        level = int(level)
        message = message[:-1]  # remove newline
        logLine = _LogLine(timestamp, level, name, message, startPos, endPos,
                buf + payload)

        if self.asRecords:
            # Trick strptime into parsing UTC timestamps
            # [1970-01-01T00:00:00.000000Z] -> 1970-01-01T00:00:00 UTC
            parseable = timestamp[1:-9] + ' UTC'
            timetup = time.strptime(parseable, '%Y-%m-%dT%H:%M:%S %Z')
            microseconds = int(timestamp[-8:-2])

            # Trick mktime into epoch-izing UTC timestamps
            timetup = timetup[:8] + (0,)  # Set DST off
            epoch = time.mktime(timetup) - time.timezone
            epoch += microseconds / 1e6  # Add microseconds

            record = logging.LogRecord(
                    name=name,
                    level=int(level),
                    pathname=None,
                    lineno=-1,
                    msg=message,
                    args=None,
                    exc_info=None,
                    )
            record.created = epoch
            record.msecs = (epoch - long(epoch)) * 1000
            record.relativeCreated = 0
            return record
        else:
            return logLine


class BulkHandler(object):

    formatter = StructuredLogFormatter()
    level = logging.NOTSET

    def __init__(self, path, mode='a'):
        self.path = path
        self.mode = mode
        self.stream = None
        self.lastUsed = 0

    def _open(self):
        dirpath = os.path.dirname(self.path)
        if not os.path.isdir(dirpath):
            os.makedirs(dirpath)
        return open(self.path, self.mode)

    def emit(self, record):
        self.emitMany([record])
    handle = emit

    def emitMany(self, records):
        self.lastUsed = time.time()
        if self.stream is None:
            self.stream = self._open()
        for record in records:
            self.stream.write(self.formatter.format(record) + '\n')
        self.stream.flush()

    def close(self):
        if self.stream:
            self.stream.close()
            self.stream = None


class JobLogManager(object):

    handlerClass = BulkHandler
    timeout = 60

    def __init__(self, basePath):
        self.basePath = basePath
        self.handlers = {}

    def _get(self, task_uuid):
        handler = self.handlers.get(task_uuid)
        if handler:
            return handler
        path = self.getPath(task_uuid)
        self.handlers[task_uuid] = handler = self.handlerClass(path, 'ab')
        return handler

    def getPath(self, task_uuid=None):
        if task_uuid:
            return os.path.join(self.basePath, 'task-%s.log' % task_uuid)
        else:
            return os.path.join(self.basePath, 'job.log')

    def getAllPaths(self):
        out = []
        for name in self.handlers:
            out.append(self.getPath(name))
        return out

    def emitMany(self, records, task_uuid=None):
        self._get(task_uuid).emitMany(records)

    def getLogger(self, task_uuid=None, name='dispatcher'):
        handler = self._get(task_uuid)
        logger = logging.Logger(name, level=logging.DEBUG)
        logger.handlers = [handler]
        return logger

    def prune(self):
        cutoff = time.time() - self.timeout
        for subpath, handler in self.handlers.items():
            if handler.lastUsed < cutoff:
                handler.close()

    def close(self):
        for handler in self.handlers.values():
            handler.close()
        self.handlers = {}


def _softIter(iterable):
    try:
        return iterable.next()
    except StopIteration:
        return None


def _splitLog(inFile):
    """
    Split a logfile into a series of subfiles at each boundary where the
    timestamp goes backwards
    """
    firstByte = 0
    lastByte = 0
    lastStamp = None
    regions = []
    for record in StructuredLogParser(inFile, asRecords=False):
        timestamp = record.timestamp
        if timestamp <= lastStamp:
            # Timestamp went backwards, start a new segment
            regions.append((firstByte, lastByte))
            firstByte = lastByte
        lastByte = inFile.tell()
        lastStamp = timestamp
    if firstByte != lastByte:
        regions.append((firstByte, lastByte))
    return [util.SeekableNestedFile(inFile, end - start, start)
            for (start, end) in regions]


def mergeLogs(inFiles, sort=True):
    if not inFiles:
        return
    if sort:
        # Sort records within an invididual log by breaking them apart wherever
        # a discontinuity exists
        splitFiles = []
        for inFile in inFiles:
            splitFiles.extend(_splitLog(inFile))
        inFiles = splitFiles
    # Get the first record from each file
    parsers = [StructuredLogParser(fobj, asRecords=True) for fobj in inFiles]
    nextRecord = [_softIter(x) for x in parsers]
    while True:
        if not any(nextRecord):
            break
        # Find which record from all files that has the lowest timestamp
        n = min((x.created, n) for (n, x) in enumerate(nextRecord) if x)[1]
        yield nextRecord[n]
        # Grab the next one from the same file
        nextRecord[n] = _softIter(parsers[n])
