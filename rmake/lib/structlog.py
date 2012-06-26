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
Write and read logs that can be re-parsed back into mostly intact records,
regardless of the contents of the log message.
"""


import datetime
import logging
import os
import time


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


class StructuredLogParser(object):

    def __init__(self, stream, asRecords=False):
        self.stream = stream
        self.asRecords = asRecords

    def __iter__(self):
        return self

    def next(self):
        buf = ''
        while True:
            d = self.stream.read(1)
            if not d:
                raise StopIteration
            if d == ' ':
                break
            if not (('0' <= d <= '9') or ('a' <= d <= 'f')):
                raise ValueError("malformed logfile")
            buf += d
        size = int(buf, 16)
        payload = self.stream.read(size)
        if len(payload) < size:
            raise StopIteration
        timestamp, level, name, message = payload.split(' ', 3)
        level = int(level)
        message = message[:-1]  # remove newline

        # Trick strptime into parsing UTC timestamps
        # [1970-01-01T00:00:00.000000Z] -> 1970-01-01T00:00:00 UTC
        parseable = timestamp[1:-9] + ' UTC'
        timetup = time.strptime(parseable, '%Y-%m-%dT%H:%M:%S %Z')
        microseconds = int(timestamp[-8:-2])

        if self.asRecords:
            # Trick mktime into epoch-izing UTC timestamps
            timetup = timetup[:8] + (0,)  # Set DST off
            epoch = time.mktime(timetup) - time.timezone
            epoch += int(timestamp[-8:-2]) / 1e6  # Add microseconds

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
            timetup = timetup[:6] + (microseconds,)
            timestamp = datetime.datetime(*timetup)
            return timestamp, level, name, message


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
