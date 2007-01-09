import logging
import os

from conary.lib import util

class Logger(object):

    name = ''
    consoleDateFormat = '%X'
    consoleFormat = '%(asctime)s - [%(name)s] - %(message)s'
    isCopy = False

    formatterClass = logging.Formatter
    dateFormat = '%x %X %Z'
    fileFormat = '%(asctime)s - [%(name)s] - %(message)s'

    def __init__(self, name=None, logPath=None):
        # do some borg magic to ensure there's only one Logger instance per
        # class + name
        if not hasattr(self.__class__, '_dict'):
            self.__class__._dict = {}
        if name is not None:
            self.name = name

        self._loggers = []
        if self.name in self.__class__._dict:
            self.__dict__ = self.__class__._dict[self.name]
            self.isCopy = True
            return
        else:
            self.__class__._dict[self.name] = self.__dict__

        self.fileHandler = None


        # set up for output to the console - everything above debug
        self.console = logging.StreamHandler()
        self.console.setFormatter(self.formatterClass(self.consoleFormat,
                                                      self.consoleDateFormat))
        self.console.setLevel(logging.INFO)
        logger = logging.getLogger(self.name)
        logger.parent = None
        for handler in logger.handlers:
            logger.removeHandler(x)
        logger.setLevel(logging.DEBUG)
        self.logger = logger
        if logPath:
            self.logToFile(logPath)
        else:
            self.enableConsole()
        self._loggers.append(logger)

    def setQuietMode(self):
        for logger in self._loggers:
            logger.setLevel(logging.ERROR)

    def logToFile(self, logPath):
        if not self.fileHandler:
            util.mkdirChain(os.path.dirname(logPath))
            fileHandler = logging.FileHandler(logPath)
            fileHandler.setFormatter(self.formatterClass(self.fileFormat,
                                                         self.dateFormat))
            self.fileHandler = fileHandler
        self.logger.addHandler(self.fileHandler)

    def info(self, message, *args, **kw):
        self.logger.info(message, *args, **kw)

    def error(self, message, *args, **kw):
        self.logger.error('error: ' + message, *args, **kw)

    def warning(self, message, *args, **kw):
        self.logger.warning('warning: ' + message, *args, **kw)

    def debug(self, message, *args, **kw):
        self.logger.debug('debug: ' + message, *args, **kw)

    def enableConsole(self, level=logging.INFO):
        self.logger.addHandler(self.console)
        self.console.setLevel(level)

    def disableConsole(self):
        self.logger.removeHandler(self.console)

class ServerLogger(Logger):

    rpcConsoleFormat = '%(asctime)s %(message)s'
    rpcFormat = '%(asctime)s - %(message)s'
    maxParamLength = 300

    def __init__(self, name=None, logPath=None):
        Logger.__init__(self, name=name, logPath=logPath)
        if self.isCopy:
            return
        self.xmlrpcLogger = logging.getLogger(self.name + '-rpc')
        self.xmlrpcLogger.setLevel(logging.DEBUG)
        self._loggers.append(self.xmlrpcLogger)
        self.xmlrpcConsole = logging.StreamHandler()
        self.xmlrpcConsole.setFormatter(
                                     self.formatterClass(self.rpcConsoleFormat,
                                                         self.consoleDateFormat))
        self.xmlrpcConsole.setLevel(logging.INFO)
        self.rpcFileHandler = None
        self.enableRPCConsole()

    def enableRPCConsole(self):
        self.xmlrpcLogger.addHandler(self.xmlrpcConsole)

    def disableRPCConsole(self):
        self.xmlrpcLogger.removeHandler(self.xmlrpcConsole)

    def logRPCToFile(self, rpcPath):
        if not self.rpcFileHandler:
            fileHandler = logging.FileHandler(rpcPath)
            fileHandler.setFormatter(self.formatterClass(self.rpcFormat,
                                                       self.dateFormat))
            self.rpcFileHandler = fileHandler
        self.xmlrpcLogger.addHandler(self.rpcFileHandler)

    def logRPCCall(self, callData, methodname, args):
        self.xmlrpcLogger.info('%-15s - %s' % (methodname, callData.getAuth()))

    def logRPCDetails(self, methodname, **kw):
        params = []
        for param, value in kw.items():
            value = str(value)
            if len(value) > self.maxParamLength:
                value = value[:self.maxParamLength] + '<truncated>'
            params.append('='.join((param, value)))
        params = ', '.join(sorted(params))
        self.xmlrpcLogger.info(' ->  %s(%s)' % (methodname, params))
