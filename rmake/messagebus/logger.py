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


import logging
from logging import handlers
import os
import traceback

from conary.lib import util

from rmake.lib import logger

LOGSIZE = 10 * 1024 * 1024
BACKUPS = 3

class MessageBusLogger(logger.ServerLogger):
    name = 'messagebus'
    messageFormat = '%(asctime)s - %(message)s'

    def __init__(self, name=None, logPath=None):
        logger.ServerLogger.__init__(self, name, logPath)
        self.messageLogger = logging.getLogger(self.name + '-transcript')
        self.messageLogger.setLevel(logging.WARNING)
        self.messageLogger.parent = None
        self._loggers.append(self.messageLogger)
        self.messageFileHandler = None
        self.messageConsole = logging.StreamHandler()
        self.messageConsole.setFormatter(
                                     self.formatterClass(self.messageFormat,
                                                      self.consoleDateFormat))
        self.messageConsole.setLevel(logging.INFO)
        self.messageHandler = None

    def _getTraceback(self):
        return traceback.format_exc()

    def logMessagesToFile(self, logPath):
        if self.messageHandler:
            self.messageLogger.removeHandler(self.messageHandler)
        util.mkdirChain(os.path.dirname(logPath))
        fileHandler = handlers.RotatingFileHandler(logPath, 
                                                  maxBytes=LOGSIZE,
                                                  backupCount=BACKUPS)
        fileHandler.setFormatter(self.formatterClass(self.messageFormat,
                                                     self.dateFormat))
        self.messageHandler = fileHandler
        self.messageLogger.addHandler(self.messageHandler)
        self.messageLogger.setLevel(logging.INFO)

    def enableMessageConsole(self):
        self.messageLogger.setLevel(logging.INFO)
        self.messageLogger.addHandler(self.messageConsole)

    def disableMessageConsole(self):
        if not self.messageHandler:
            self.messageLogger.setLevel(logging.WARNING)
        self.messageLogger.removeHandler(self.messageConsole)

    def connectionFailed(self, caddr):
        self.error("Connection failed from address %s:%s - %s" % 
                   (caddr[0], caddr[1], self._getTraceback()))

    def readFailed(self, session):
        self.error("Reading from sessionId %s failed: %s" %
                   (session.sessionId, self._getTraceback()))

    def writeFailed(self, session):
        self.error("Writing to sessionId %s failed: %s" %
                   (session.sessionId, self._getTraceback()))

    def logMessage(self, m, fromSession=None):
        if fromSession:
            m.headers.sessionId = fromSession.sessionId
        txt = ' '*4 + '\n    '.join(str(m).split('\n'))
        txt += ' '*4 + '\n    '.join(m.getPayloadStream().read().split('\n'))
        txt = 'Received Message:\n' + txt
        self.messageLogger.info(txt)
