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

import logging
import sys
from twisted.python import log as twlog


FORMATS = {
        'apache': ('[%(asctime)s] [%(levelname)s] (%(name)s) %(message)s',
            '%a %b %d %T %Y'),
        'console': ('%(levelname)s: %(message)s', None),
        'file': ('%(asctime)s %(levelname)s %(name)s : %(message)s', None),
        }


def setupLogging(logPath=None, consoleLevel=logging.WARNING,
        consoleFormat='console', fileLevel=logging.INFO, fileFormat='file',
        logger='', withTwisted=False):

    logger = logging.getLogger(logger)
    logger.handlers = []
    logger.propagate = False
    level = 100

    # Console handler
    if consoleLevel is not None:
        if consoleFormat in FORMATS:
            consoleFormat = FORMATS[consoleFormat]
        consoleFormatter = logging.Formatter(*consoleFormat)
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(consoleFormatter)
        consoleHandler.setLevel(consoleLevel)
        logger.addHandler(consoleHandler)
        level = min(level, consoleLevel)

    # File handler
    if logPath and fileLevel is not None:
        if fileFormat in FORMATS:
            fileFormat = FORMATS[fileFormat]
        logfileFormatter = logging.Formatter(*fileFormat)
        logfileHandler = logging.FileHandler(logPath)
        logfileHandler.setFormatter(logfileFormatter)
        logfileHandler.setLevel(fileLevel)
        logger.addHandler(logfileHandler)
        level = min(level, fileLevel)

    if withTwisted:
        twlog.startLoggingWithObserver(twistedLogObserver, setStdout=False)

    logger.setLevel(level)
    return logger


def twistedLogObserver(eventDict):
    """Forward twisted logs to the python stdlib logger.

    Primary differences from t.p.log.PythonLoggingObserver:
     * Default level of DEBUG for non-error messages
     * Picks a logger based on the module of the caller. This way the output
       shows which part of twisted generated the message.
    """
    n = 2
    module = 'twisted'
    while True:
        try:
            caller = sys._getframe(n)
        except ValueError:
            break
        name = caller.f_globals.get('__name__')
        if name not in (None, 'twisted.python.log'):
            module = name
            break
        n += 1
    logger = logging.getLogger(module)
    if 'logLevel' in eventDict:
        level = eventDict['logLevel']
    elif eventDict['isError']:
        level = logging.ERROR
    else:
        level = logging.DEBUG
    text = twlog.textFromEventDict(eventDict)
    if text is None:
        return
    logger.log(level, text)


def logFailure(failure, msg='Unhandled exception in deferred:'):
    """Log a Twisted Failure object with traceback.

    Suitable for use as an errback.
    """
    logging.error('%s\n%s', msg, failure.getTraceback())
