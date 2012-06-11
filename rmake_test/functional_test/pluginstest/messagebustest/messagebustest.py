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


from rmake_test import rmakehelp


class Poller(object):
    def __init__(self, bus, *clients):
        self.bus = bus
        self.clients = clients

    def writable(self):
        return self.bus.hasMessages() or [ x for x in self.clients if x.getSession().writable() ]

    def poll(self):
        found = self.writable()
        self.bus.serve_once()
        for client in self.clients:
            if client.poll():
                found = True
        self.bus.serve_once()
        return found

    def add(self, client):
        self.clients.append(client)

class MessageBusTest(rmakehelp.RmakeHelper):

    def importPlugins(self):
        global messages
        global messagebus
        global busclient
        from rmake.messagebus import messages
        from rmake.messagebus import busclient
        from rmake.multinode.server import messagebus

    def testMessageBus(self):
        class MyMessage(messages.Message):
            messageType = 'MINE'

            def set(self, **params):
                self.updateHeaders(params)
        logPath = self.workDir + '/messagebus.log'
        messagePath = self.workDir + '/messagebus.messages'
        clientLog = self.workDir + '/client-log'
        mgr = messagebus.MessageBus('', 0, logPath, messagePath)
        mgr.getLogger().disableConsole()
        port = mgr.getPort()
        client = busclient.MessageBusClient('localhost', port, None, logPath=clientLog)
        client.logger.disableConsole()
        client.connect()
        client2 = busclient.MessageBusClient('localhost', port, None, logPath=clientLog)
        client2.logger.disableConsole()
        client2.connect()
        client3 = busclient.MessageBusClient('localhost', port, None, logPath=clientLog)
        client3.logger.disableConsole()
        client3.connect()
        p = Poller(mgr, client, client2, client3)
        while (p.writable() or not client.isRegistered() or not
                client2.isRegistered() or not client3.isRegistered()):
            p.poll()
        client.popMessages()
        client2.popMessages()
        client3.popMessages()

        client2.subscribe('/foo')
        client3.subscribe('/foo')
        client.subscribe('/foo?a=b')
        msg = MyMessage()
        msg.set(a='b')
        msg2 = MyMessage()
        msg2.set(c='d')
        msg3 = MyMessage()
        msg3.set(e='f')
        client2.sendMessage('/foo', msg)
        client2.sendMessage('/foo', msg2)
        client.sendMessage('/foo', msg2)
        client.sendMessage('/foo', msg3, client2.getSessionId())

        while p.poll() or not client.hasMessages() or not client2.hasMessages():
            pass
        msg, = client.popMessages()
        assert(msg.headers.a == 'b')
        assert(msg.getSessionId() == client2.getSessionId())
        assert(msg.getMessageId() == '%s:2' % client2.getSessionId())
        assert(msg.getDestination() == '/foo')
        assert(msg.getTimestamp())

        msg, two = client2.popMessages()
        assert(msg.headers.c == 'd')
        assert(msg.getSessionId() == client.getSessionId())
        assert(msg.getMessageId() == '%s:2' % client.getSessionId())
        assert(msg.getDestination() == '/foo')
        assert(msg.getTargetId() is None)
        assert(msg.getTimestamp())
        assert(two.headers.e == 'f')
        assert(two.getSessionId() == client.getSessionId())
        assert(two.getMessageId() == '%s:3' % client.getSessionId())
        assert(two.getDestination() == '/foo')
        assert(two.getTargetId() == client2.getSessionId())
        assert(two.getTimestamp())

        msgs = client3.popMessages()
        assert msg3.getMessageId() not in [x.getMessageId() for x in msgs]

    def testDisconnect(self):
        messageBusLog = self.workDir + '/messagebus.log'
        messageBusMessages = self.workDir + '/messagebus.messages'
        clientLog = self.workDir + '/client-log'
        mgr = messagebus.MessageBus('', 0, logPath=messageBusLog, messagePath=messageBusMessages)
        mgr._logger.disableConsole()
        port = mgr.getPort()
        client = busclient.MessageBusClient('localhost', port, None, logPath=clientLog)
        client.logger.disableConsole()
        client.connect()
        client2 = busclient.MessageBusClient('localhost', port, None, logPath=clientLog)
        client2.logger.disableConsole()
        client2.connect()
        p = Poller(mgr, client, client2)
        while (p.writable() or not client.isRegistered()
               or not client2.isRegistered()):
            p.poll()
        client2.popMessages()

        client2.subscribe('/internal/nodes')
        while p.poll():
            pass
        client.disconnect()
        while not client2.hasMessages():
            p.poll()
        m, = client2.popMessages()
        assert(isinstance(m, messages.NodeStatus))
        assert(m.getStatus() == 'DISCONNECTED')

        client.connect()
        while not client2.hasMessages():
            p.poll()
        m, = client2.popMessages()
        assert(isinstance(m, messages.NodeStatus))
        assert(m.getStatus() == 'RECONNECTED')
        assert(m.getStatusId() == client.getSessionId())
