#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
    MessageBus Client.

    Aynchronous client to the mesage bus, handles the message bus protocol.
"""
import asyncore
import errno
import logging
import os
import socket
import sys
import time

from rmake import errors

from rmake.messagebus import logger
from rmake.messagebus import messages
from rmake.messagebus import messageprocessor
from rmake.messagebus import rpclib
from rmake.messagebus.rpclib import SessionProxy


def BusClientFormatterFactory(instance):
    class BusClientFormatter(logging.Formatter):
        def format(self, record):
            record.sessionId = instance.sessionId
            return logging.Formatter.format(self, record)
    return BusClientFormatter

class MessageBusClientLogger(logger.MessageBusLogger):

    fileFormat = '%(asctime)s - [%(sessionId)s] - %(message)s'
    consoleFormat = '%(asctime)s - [%(sessionId)s] - %(message)s'
    messageFormat = '%(asctime)s - [%(sessionId)s] - %(message)s'

    def __init__(self, logPath):
        self.formatterClass = BusClientFormatterFactory(self)
        self.sessionId = 'Not Registered (%s)' % socket.getfqdn()
        logger.MessageBusLogger.__init__(self, 'busclient', logPath=logPath)
        self.enableConsole()

    def setSessionId(self, sessionId):
        self.sessionId = sessionId
        self.info('Connected (pid %s).' % os.getpid())


class ConnectionClosed(Exception):
    "Exception used internally to moderate connection flow in asyncore."


class MessageBusClient(object):

    def __init__(self, host, port, dispatcher, sessionClass='',
                 logPath=None, messageLogPath=None,
                 connectionTimeout=0, subscriptions=None):
        self.logger = MessageBusClientLogger(logPath=logPath)
        self.dispatcher = dispatcher
        if messageLogPath:
            self.logger.logMessagesToFile(messageLogPath)
        self.session = _SessionClient(host, port, self._messageReceived,
                                      self.logger, sessionClass=sessionClass,
                                      connectionTimeout=connectionTimeout,
                                      subscriptions=subscriptions)
        self.callbacks = {}
        self.messages = []

    def setConnectionTimeout(self, timeout):
        self.session.connectionTimeout = timeout

    def __repr__(self):
        return 'BusClient(%r)' % (self.session)

    def connect(self):
        self.session.connect()

    def disconnect(self):
        self.session.disconnect()

    def isConnected(self):
        return self.session.connected

    def isRegistered(self):
        return self.session.sessionId

    def getSessionId(self):
        return self.session.sessionId

    def getSessionClass(self):
        return self.session.sessionClass

    def getSession(self):
        return self.session

    def serve(self):
        while True:
            self.session.poll()

    def poll(self, *args, **kw):
        return self.session.poll(*args, **kw)

    def flush(self):
        self.session.flush()

    def popMessages(self):
        messages = self.messages
        self.messages = []
        return messages

    def sendMessage(self, destination, m, targetId=None):
        m.direct(destination, targetId)
        self.session.sendMessage(m)

    def sendSynchronousMessage(self, destination, m):
        m.direct(destination)
        while not self.session.connected:
            self.session.connect()
        self.session.sendMessage(m)
        self.session.flush()

    def subscribe(self, dest):
        m = messages.SubscribeRequest()
        m.set(dest)
        self.session.sendMessage(m)

    def registerNode(self, nodeInstance):
        m = messages.RegisterNode()
        m.set(nodeInstance)
        self.session.sendMessage(m)

    def makeRemoteMethodMessage(self, sessionId, methodName, params=()):
        return messages.MethodCall(sessionId, methodName, params)

    def callRemoteMethod(self, sessionId, methodName, params=(), callback=None):
        m = self.makeRemoteMethodMessage(sessionId, methodName, params)
        if callback is None:
            callback = self._gotResultsCallback
        self.session.sendMessage(m)
        self.callbacks[m.getMessageId()] = callback

    def _gotResultsCallback(self, m):
        raise rpclib.ResultsReceived(m)

    def _callLocalMethod(self, m, handler=None):
        methodName = m.getMethodName()
        params = m.getParams()
        if not handler:
            handler = rpclib.MessageBusXMLRPCResponseHandler(m, self.session)
        self.dispatcher._dispatch(methodName,
                                  (m.getMessageId(), handler, params))

    def _messageReceived(self, m):
        # also send connected response to handler
        if isinstance(m, messages.MethodCall):
            self._callLocalMethod(m)
        elif (isinstance(m, messages.MethodResponse)
            and m.getResponseTo() in self.callbacks):
            responseTo = m.getResponseTo()
            self.callbacks[responseTo](m)
            if m.isFinal():
                del self.callbacks[responseTo]
        elif self.dispatcher:
            self.dispatcher.messageReceived(m)
        else:
            self.messages.append(m)

    def hasMessages(self):
        return self.messages


class _SessionClient(asyncore.dispatcher):
    def __init__(self, host, port, callback, logger,
                 user=None, password=None, sessionClass='', 
                 connectionTimeout=0, subscriptions=None):
        self.callback = callback
        self._map = {}
        self.messageProcessor = messageprocessor.MessageProcessor()

        asyncore.dispatcher.__init__(self, None, self._map)
        self.set_socket(socket.socket())
        self.sessionId = None
        self.count = 1
        self.host = host or 'localhost'
        self.port = port
        self.user = user
        self.password = password
        self.sessionClass = sessionClass
                                # used as a categorizer of this node.
        self.connectionTimeout = connectionTimeout
        self.connectionStart = None
        self.connected = False
        self.bufferSize = 4096
        self.logger = logger
        self.outMessages = []
        self.subscriptions = subscriptions

    def __repr__(self):
        return "SessionDispatcher(sessionId=%r)" % (self.sessionId)

    def connect(self):
        self.connected = False
        if not self._fileno:
            self.set_socket(socket.socket())
        self._connect()

    def _connect(self):
        if self.connectionStart is None:
            self.connectionStart = time.time()
        if self.socket is None:
            self.set_socket(socket.socket())
        try:
           asyncore.dispatcher.connect(self, (self.host, self.port))
           self.connected = True
           self.connectionStart = None
           return
        except socket.error, err:
            if err.args[0] != errno.ECONNREFUSED:
                raise
        if self.connectionTimeout == -1:
            time.sleep(1)
            return
        endTime = (self.connectionStart + self.connectionTimeout)
        timeLeft = endTime - time.time()
        if timeLeft <= 0:
            if self.connectionTimeout:
                self.logger.error('Could not connect.  Giving up.')
            raise
        else:
            self.logger.warning(
                'Could not connect.  Retrying for %s more seconds' % int(timeLeft))
            time.sleep(3)

    def disconnect(self):
        self.close()
        self.socket = None

    def handle_error(self):
        # any exception that makes its way outside of more discerning
        # try/excepts is fatal.
        raise

    def handle_expt(self):
        if not self.connected:
            self.del_channel() 
        else:
            self.logger.error("Error on socket.")
            raise RuntimeError('Socket errored out.')

    def writable(self):
        return self.messageProcessor.hasData()

    def handle_connect(self):
        if self.socket is None:
            return
        self.connected = True
        self.logger.info('Socket connected, sending connect request.')
        self.socket.setblocking(0)
        m = messages.ConnectionRequest()
        m.set(self.user, self.password, self.sessionClass, self.sessionId,
              self.subscriptions)
        self.sendMessage(m)

    def handle_write(self):
        self._movedData = True
        self.messageProcessor.sendData(self)

    def handle_read(self):
        self._movedData = True
        try:
            m = self.messageProcessor.processData(self.recv,
                                                  self.bufferSize)
        except socket.error, e:
            self.handle_error()
            return
        if m:
            m.thawPayloadStream()
            self._receivedMessages = True
            self.handle_message(m)

    def handle_message(self, m):
        self.logger.logMessage(m)
        if isinstance(m, messages.ConnectedResponse):
            self.logger.setSessionId(m.getSessionId())
            self.sessionId = m.headers.sessionId
            # send any queued messages that were waiting for 
            # connection to be confirmed
            for outM in self.outMessages:
                self.sendMessage(outM)
            self.outMessages = []
        self.callback(m)

    def handle_close(self):
        # asyncore will catch this and pass it to handle_error, bypassing any
        # event handlers queued to run after the current one.
        raise ConnectionClosed

    def handle_error(self):
        error = sys.exc_info()[1]
        if isinstance(error, ConnectionClosed):
            self.close()
        else:
            raise

    def close(self):
        self.logger.error('Lost connection to message bus.')
        self.accepting = False
        self.connected = False
        self.del_channel()
        try:
            self.socket.close()
        except socket.error, error:
            if error.args[0] not in (errno.ENOTCONN, errno.EBADF):
                raise
        if self.connectionTimeout:
            self.connect()

    def sendMessage(self, m):
        if not self.connected:
            self.connect()
        if not self.sessionId and not isinstance(m, messages.ConnectionRequest):
            self.outMessages.append(m)
            return
        elif self.sessionId:
            self.stamp(m)
        self.messageProcessor.sendMessage(m)

    def stamp(self, m):
        messageId = '%s:%s' % (self.sessionId , self.count)
        self.count += 1
        m.stamp(messageId, self.sessionId, time.time())

    def flush(self):
        while self.messageProcessor.hasData():
            self.poll()

    def poll(self, timeout=0.1, maxIterations=10):
        if not self.connected:
            self.connect()
        count = 0
        self._movedData = True
        while count < maxIterations:
            self._movedData = False
            asyncore.poll2(timeout=timeout, map=self._map)
            if not self._movedData:
                break
            count += 1
        if count:
            return True
        return False

    def getMap(self):
        return self._map


