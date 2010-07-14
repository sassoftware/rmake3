#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

import errno
import logging
import os


class FileStore(object):

    def __init__(self, cfg):
        self.cfg = cfg

    def _path(self, relpath):
        return os.path.join(self.cfg.dataDir, relpath)

    def _mkparent(self, abspath):
        dirpath = os.path.dirname(abspath)
        if not os.path.exists(dirpath):
            os.makedirs(dirpath)

    def open(self, relpath, mode='rb', create=False, missingOK=False):
        abspath = self._path(relpath)
        if create:
            self._mkparent(abspath)
        try:
            return open(abspath, mode)
        except IOError, err:
            if missingOK and err.errno == errno.ENOENT:
                return None
            raise

    def append(self, relpath, data):
        fObj = self._open(relpath, 'ab', create=True)
        fObj.write(data)
        fObj.close()


class FileStoreLogHandler(logging.Handler):

    def __init__(self, store, prefix):
        logging.Handler.__init__(self)
        self.store = store
        if prefix[-1] != '.':
            prefix += '.'
        self.prefix = prefix
        self.formatter = logging.Formatter(
                "%(created)s\t%(levelno)s\t%(name)s\t%(message)s\n")

    def emit(self, record):
        self.emitMany([record])

    def emitMany(self, records):
        fdcache = {}
        for record in records:
            if not record.name.startswith(self.prefix):
                continue
            fObj = fdcache.get(record.name)
            if fObj is None:
                name = record.name[len(self.prefix):]
                parts = name.split('.')
                job = parts[0]
                if len(parts) == 1:
                    filename = 'job.log'
                elif len(parts) >= 3 and parts[1] == 'tasks':
                    filename = 'task-%s.log' % parts[2]
                else:
                    filename = '.'.join(parts[1:])

                relpath = os.path.join('logs', job, filename)
                fObj = fdcache[record.name] = self.store.open(relpath, 'ab',
                        create=True)

            data = self.format(record)
            if not isinstance(data, unicode):
                # Malformed log records will not be tolerated.
                data = data.decode('utf8', 'replace')
            fObj.write(data.encode('utf8'))

        for fObj in fdcache.values():
            fObj.close()


def openJobLogger(store, prefix='rmake.jobs'):
    handler = FileStoreLogHandler(store, prefix)
    logger = logging.getLogger(prefix)
    logger.propagate = False
    logger.handlers = [handler]
    return handler
