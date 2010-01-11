#
# Copyright (c) 2006-2009 rPath, Inc.
#
# All rights reserved.
#
"""
Very basic message bus.

Nodes register, are given session ids, and subscribe to different message
topics.  Currently, no guarantee of delivery is made (other than TCP 
guarantees), no backup is made, no data stored to disk.

All message types are the same - there are no queues, simply messages broadcast
to all listeners on that topic.  Listeners are able to filter topics by
attributes of the message using a uri format:

A subscribe request of /foo?a=b will listen to foo messages if attribute
a of the message has value "b".
"""
import asyncore
import errno
import optparse
import os
import resource
import signal
import socket
import sys
import time
import traceback
import urllib

from rmake import errors
from rmake.lib import apirpc
from rmake.lib.apiutils import api, api_parameters, api_return, freeze, thaw
from rmake.lib.daemon import daemonize, setDebugHook

from rmake.messagebus import logger
from rmake.messagebus import messageprocessor
from rmake.messagebus import messages
from rmake.messagebus import rpclib
from rmake.messagebus.busclient import ConnectionClosed


class MessageBus(apirpc.ApiServer):
    """
        Main message bus.  Receives connections from the
        MessageBusListener, and farms them out to the various sessions
        that are subscribed.

        MessageBus(host, port):
            host - host to listen for connections at, generally ''
            port - port to listen to connections at.  If 0, will be an open
                   port assigned by operating system.
    """
    def __init__(self, host, port, logPath, messagePath=None):
        l = logger.MessageBusLogger('messagebus', logPath)
        apirpc.ApiServer.__init__(self, l)
        self._map = {}
        self._sessionCount = {}
        self._messageCount = 0
        self._pendingSessions = []
        self._sessions = {}
        if messagePath:
            self._logger.logMessagesToFile(messagePath)
        self._logger.info('Message bus started, listening on port %s (pid %s)' % (port, os.getpid()))
        # instantiating this class stores this connection handler in self._map.
        # (ala asyncore)
        self._server = MessageBusListener(self, host, port, logger=self._logger,
                                          map=self._map)
        self._subscribers = SubscriptionManager()
        self._dispatcher = MessageBusDispatcher(self)

    def _close(self):
        apirpc.ApiServer._close(self)
        self._server.close()
        for session in self._pendingSessions:
            session.close()
        for session in self._sessions.itervalues():
            session.close()

    def listSessions(self):
        return [ x for x in self._sessions.values() if x is not None ]

    def _callLocalMethod(self, m, fromSession):
        m.thawPayloadStream()
        methodName = m.getMethodName()
        params = m.getParams()
        handler = rpclib.MessageBusXMLRPCResponseHandler(m, fromSession)
        self._dispatcher._dispatch(methodName,
                                   (m.getMessageId(), handler, params))

    def newSession(self, session, sessionId=None):
        """
            Listen/Sends for messages to this session.
        """
        session.setSessionId(
            '%s:[Unregistered, port %s]' % (session.hostname, session.port))
        self._pendingSessions.append(session)

    def completeConnection(self, session, m):
        if session.sessionId and session.sessionId in self._sessions:
            # We're already connected.  Don't resend ACK.
            return
        count = self._sessionCount.setdefault(session.hostname, 1)
        status = None
        if m.headers.requestedSessionId:
            sessionId = m.headers.requestedSessionId
            if sessionId in self._sessions and not self._sessions[sessionId]:
                status = 'RECONNECTED'
                self._logger.info('session %s reconnected' % sessionId)
        if m.getSessionClass():
            session.setSessionClass(m.getSessionClass())
        else:
            session.setSessionClass('Anonymous')
        if not status:
            status = 'CONNECTED'
            sessionId = '%s-%s:%s' % (session.getSessionClass(),
                                      session.hostname, count)
            self._logger.info('registering new host as session %s' % sessionId)
            self._sessionCount[session.hostname] += 1

        session.setSessionId(sessionId)
        self._sessions[sessionId] = session
        self._pendingSessions.remove(session)

        for destination in m.getSubscriptions():
            self._subscribers.addSubscriber(destination, session)
        m = messages.NodeStatus()
        m.set(session.sessionId, status)
        self.sendMessage('/internal/nodes', m)
        m = messages.ConnectedResponse()
        m.set(session.sessionId)
        session.sendMessage(m)

    def closeSession(self, session):
        m = messages.NodeStatus()
        m.set(session.sessionId, 'DISCONNECTED')
        self.sendMessage('/internal/nodes', m)
        self._sessions[session.sessionId] = None
        self._subscribers.deleteSubscriber(session)

    def getSession(self, sessionId):
        return self._sessions.get(sessionId, None)

    def getPort(self):
        return self._server.getPort()

    def hasMessages(self):
        return bool([ x for x in self._sessions.itervalues() 
                      if x and x.writable()])

    def handleRequestIfReady(self, sleepTime):
        asyncore.poll2(timeout=sleepTime, map=self._map)

    def serve_once(self):
        asyncore.poll2(map=self._map)

    def sendMessage(self, destination, m):
        messageId = '%s:%s' % ('messagebus', self._messageCount)
        self._messageCount += 1
        m.direct(destination)
        m.stamp(messageId, 'messagebus', time.time())
        for session in self._subscribers.iterSubscribers(m):
            if session.sessionId != m.headers.sessionId:
                session.sendMessage(m)

    def _signalHandler(self, sigNum, frame):
        if sigNum == signal.SIGINT:
            self.error('SIGINT caught and ignored')
        else:
            apirpc.ApiServer._signalHandler(self, sigNum, frame)

    def sendError(self, session, responseTo, errorMessage):
        err = errors.RmakeError(errorMessage)
        err = ('RmakeError', freeze('RmakeError', err))
        session.sendMessage(messages.MethodError(responseTo, err))

    def receivedMessage(self, fromSession, m):
        """
            Handles a message, internal or otherwise,
            received from a particular session.
        """
        # internal messages first:
        # ConnectionRequest -> ConnectedResponse - completes registration.
        # Subscribe request -> no response, but listening to that 
        #                      subscription
        try:
            self._logger.logMessage(m, fromSession)
            if isinstance(m, messages.ConnectionRequest):
                self.completeConnection(fromSession, m)
            elif not fromSession.isRegistered():
                self.sendError(fromSession, m, 'Bad request')

            elif isinstance(m, messages.SubscribeRequest):
                self._subscribers.addSubscriber(m.headers.destination, fromSession)
            elif isinstance(m, (messages.MethodCall, messages.MethodResponse)):
                if not m.getTargetId():
                    response = self._callLocalMethod(m, fromSession)
                else:
                    session = self.getSession(m.getTargetId())
                    if session is None:
                        self.sendError(fromSession, m,
                                       'Unknown session %s' % m.getTargetId())
                    else:
                        self._logger.info('Sent %r to %s' % (m, session))
                        session.sendMessage(m)
            elif isinstance(m, messages.Message):
                # normal messages, sent around to all subscribers
                sent = False
                for session in self._subscribers.iterSubscribers(m):
                    if session.sessionId != m.getSessionId():
                        sent = True
                        self._logger.info('Sent %r to %s' % (m, session))
                        session.sendMessage(m)
                if not sent:
                    self._logger.info('Message %s %s dropped.',
                            m.getMessageId(), m.headers.messageType)
        except Exception, err:
            self._logger.error('Error handling message %s: %s\n%s' % (
                               m.getMessageId(), err, traceback.format_exc()))
            # we couldn't handle this message, we couldn't even send them
            # an error message about it.  Close their session so they have
            # some idea that they did something wrong.
            raise ConnectionClosed


class SessionManager(asyncore.dispatcher):
    """
        SessionManager - manages one connection to the message bus.
    """
    def __init__(self, messageBus, sock, client_address, map, logger):
        self.messageProcessor = messageprocessor.MessageProcessor()
        self.messageBus = messageBus
        self.logger = logger
        self.bufferSize = 4096
        self.hostname = client_address[0]
        if self.hostname.startswith('::ffff:'):
            self.hostname = self.hostname[7:]
        self.port = client_address[1]
        self.socket = sock
        self.sessionId = None
        self.sessionClass = None
        self._map = map


    def setSessionClass(self, sessionClass):
        self.sessionClass = sessionClass

    def getSessionClass(self):
        return self.sessionClass

    def __str__(self):
        return 'Session(%s)' % self.sessionId

    def connect(self):
        asyncore.dispatcher.__init__(self, self.socket, self._map)

    def disconnect(self):
        self.close()

    def setSessionId(self, sessionId):
        self.sessionId = sessionId

    def getSessionId(self):
        return self.sessionId

    def isRegistered(self):
        return self.sessionId

    def close(self):
        self.messageBus.closeSession(self)
        # Copied from python2.6's asyncore
        self.connected = False
        self.accepting = False
        self.del_channel()
        try:
            self.socket.close()
        except socket.error, why:
            if why.args[0] not in (errno.ENOTCONN, errno.EBADF):
                raise

    def handle_read(self):
        try:
            m = self.messageProcessor.processData(self.recv, self.bufferSize)
        except errors.uncatchableExceptions:
            raise
        except ConnectionClosed:
            raise
        except:
            self.logger.readFailed(self)
            raise ConnectionClosed

        if m:
            self.messageBus.receivedMessage(self, m)
        if not self.connected:
            # If the connection died during the read, make sure processing of
            # this socket stops.
            raise ConnectionClosed

    def handle_error(self):
        error = sys.exc_info()[1]
        if isinstance(error, ConnectionClosed):
            self.close()
        else:
            # Errors that escape from our try/excepts around read and write
            # are fatal.
            raise

    def handle_expt(self):
        if self._fileno in self._map:
            err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            self.logger.error("Closing connection due to asynchronous "
                    "error: %d %s", err, os.strerror(err))
        raise ConnectionClosed

    def handle_close(self):
        raise ConnectionClosed

    def sendMessage(self, m):
        """
            Queue a message to be sent to this session (non-blocking)
        """
        self.messageProcessor.sendMessage(m)

    def getQueuedMessages(self):
        return self.messageProcessor.getQueuedMessages()

    def writable(self):
        """
            Asyncore checks this to see if it should call handle_write.
            Only do so if we have data to sent to this node.
        """
        return self.messageProcessor.hasData()

    def handle_write(self):
        """
            Actually send the response.
        """
        try:
            self.messageProcessor.sendData(self)
        except socket.error, err:
            if err.args[0] in (errno.EBADF, errno.EPIPE, errno.ECONNRESET):
                self.logger.error('Socket closed when write attempted to %s.  Disconnecting' % self.sessionId)
            else:
                self.logger.error('Unknown socket exception when write attempted to %s, disconnecting: %s' % (self.sessionId, err))
            self.handle_close()
        except Exception:
            self.logger.writeFailed(self)
            self.handle_close()


class SubscriptionManager(object):
    """
        Sessions "subscribe" to different channels, on which they get
        their messages.  This manages those subscribers.
    """
    def __init__(self):
        self._subscribers = {}

    def iterSubscribers(self, m):
        lst = self._subscribers.get(m.headers.destination, [])
        for subscriber, pattern in lst:
            if m.getTargetId() and m.getTargetId() != subscriber.sessionId:
                continue
            found = True
            for key, value in pattern.iteritems():
                if getattr(m.headers, key, None) != value:
                    found = False
            if found:
                yield subscriber

    def addSubscriber(self, channel, session):
        """
            Subscribe to a channel. 
            A subscribe request of /foo?a=b will listen to foo messages 
            if attribute a of the message has value "b".
        """
        channel, attrs = urllib.splitquery(channel)
        pattern = {}
        if attrs:
            attr, rest = urllib.splitattr(attrs)
            for attr in [attr] + rest:
                key, value = urllib.splitvalue(attr)
                pattern[key] = value
        self._subscribers.setdefault(channel, []).append((session, pattern))

    def deleteSubscriber(self, session):
        """
        Delete all subscriptions by a particular C{session}.
        """
        for channel, subscribers in self._subscribers.items():
            self._subscribers[channel] = [x for x in subscribers
                    if x[0] is not session]


class MessageBusListener(asyncore.dispatcher):
    """
        Accepts connections for the message bus and converts them into
        Sessions which are managed by the message bus.
    """

    fd_limit = 65536

    def __init__(self, messageBus, host, port, logger, map=None):
        self.messageBus = messageBus
        self.logger = logger
        asyncore.dispatcher.__init__(self, None, map)
        self._set_rlimit()
        self.create_socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.bind( (host, port) )
        self.port = self.socket.getsockname()[1]
        self.listen(5)

    def _set_rlimit(self):
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft > self.fd_limit:
            return
        if hard < self.fd_limit:
            self.logger.warning("File descriptor hard limit (ulimit -Hn) is "
                    "only %d -- consider raising it to at least %d"
                    % (hard, self.fd_limit))
            soft = hard
        else:
            soft = self.fd_limit
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))

    def getPort(self):
        return self.port

    def handle_accept(self):
        c = None
        try:
            csock, caddr = self.accept()
        except socket.error, err:
            if err.args[0] == errno.EMFILE:
                # Too many open files
                self.logger.error("Could not accept connection: too many "
                        "open files.")
                return

        try:
            c = SessionManager(self.messageBus, csock, caddr, self._map,
                               self.logger)
            c.connect()
            self.messageBus.newSession(c)
        except errors.uncatchableExceptions:
            raise
        except ConnectionClosed:
            raise
        except:
            self.logger.connectionFailed(caddr)
            raise ConnectionClosed

    def handle_error(self):
        # errors outside of our try/except blocks are fatal.
        raise



class MessageBusDispatcher(apirpc.ApiServer):
    def __init__(self, messageBus):
        self.messageBus = messageBus
        apirpc.ApiServer.__init__(self)

    @api(version=1)
    @api_parameters(1)
    @api_return(1, None)
    def listSessions(self, callData):
        return dict((x.getSessionId(), x.getSessionClass())
                    for x in self.messageBus.listSessions())

    @api(version=1)
    @api_parameters(1)
    @api_return(1, None)
    def listQueueLengths(self, callData):
        return dict((x.getSessionId(), len(x.getQueuedMessages()))
                    for x in self.messageBus.listSessions())

class MessageBusRPCClient(object):
    def __init__(self, client):
        self.proxy = rpclib.SessionProxy(MessageBusDispatcher, client, '')

    def listSessions(self):
        return self.proxy.listSessions()

    def listSubscriptions(self):
        raise NotImplementedError

    def listQueueLengths(self):
        return self.proxy.listQueueLengths()


def main(args):
    parser = optparse.OptionParser()
    parser.add_option('-b', '--bind', default='::',
            help="Bind to this host")
    parser.add_option('-p', '--port', default=50900)
    parser.add_option('-P', '--pid-file')
    parser.add_option('-l', '--log-file')
    parser.add_option('-m', '--log-messages')
    options, args = parser.parse_args(args)
    if args:
        parser.error("No arguments expected")
    if not options.log_file:
        parser.error("You must specify a log file")

    bus = MessageBus(options.bind, int(options.port),
            options.log_file, options.log_messages)

    pidFile = None
    if options.pid_file:
        pidFile = open(options.pid_file, 'w')

    if daemonize():
        try:
            try:
                if pidFile:
                    pidFile.write(str(os.getpid()))
                    pidFile.close()
                signal.signal(signal.SIGTERM, bus._signalHandler)
                signal.signal(signal.SIGQUIT, bus._signalHandler)
                setDebugHook()
                bus.serve_forever()
            except:
                bus._logger.exception("Unhandled exception in message bus:")
        finally:
            os._exit(70)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
