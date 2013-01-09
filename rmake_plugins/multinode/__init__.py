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


import os
import socket
import traceback

from conary.lib import cfgtypes, log, util

from rmake import errors
from rmake.plugins import plugin


# 
from rmake.multinode.server import dispatcher
from rmake.multinode.server import messagebus
from rmake_plugins.multinode.build.builder import WorkerClient
from rmake_plugins.multinode.server.server import ServerExtension
from rmake_plugins.multinode.server import servercfg
from rmake_plugins.multinode.cmdline import admin_command

# load our messages so that they are understood by the messagebus
import rmake.multinode.messages


class MultinodePlugin(plugin.ServerPlugin, plugin.ClientPlugin):
    types = [plugin.TYPE_SERVER, plugin.TYPE_CLIENT]

    def server_preInit(self, main, argv):
        servercfg.updateConfig()
        admin_command.addCommands(main)

    def startMessageBus(self, server):
        messageBusLog = server.cfg.logDir + '/messagebus.log'
        messageLog = server.cfg.logDir + '/messages/messagebus.log'
        util.mkdirChain(os.path.dirname(messageLog))
        m = messagebus.MessageBus('', server.cfg.messageBusPort, messageBusLog, 
                                  messageLog)
        port = m.getPort()
        pid = server._fork('Message Bus')
        if pid:
            m._close()
            server._messageBusPid = pid
        else:
            try:
                try:
                    m._installSignalHandlers()
                    server._close()
                    self._runServer(m, m.serve_forever, 'Message Bus')
                except Exception, err:
                    m.error('Startup failed: %s: %s' % (err,
                                                        traceback.format_exc()))
            finally:
                os._exit(3)

    def startDispatcher(self, server):
        pid = server._fork('Dispatcher')
        if pid:
            server._dispatcherPid = pid
            return
        try:
            d = dispatcher.DispatcherServer(server.cfg, server.db)
            try:
                d._installSignalHandlers()
                server._close()
                server.db.reopen()
                self._runServer(d, d.serve, 'Dispatcher')
            except Exception, err:
                d.error('Startup failed: %s: %s' % (err,
                                                    traceback.format_exc()))
        finally:
            os._exit(3)

    def _runServer(self, server, fn, name, *args, **kw):
        try:
            fn()
            os._exit(0)
        except SystemExit, err:
            os._exit(err.args[0])
        except errors.uncatchableExceptions, err:
            # Keyboard Interrupt, etc.
            os._exit(1)
        except socket.error, err:
            err = '%s Died: %s\n' % (name, err)
        except Exception, err:
            try:
                err = '%s Died: %s\n%s' % (name, err, traceback.format_exc())
                server.error(err)
                os._exit(1)
            except:
                os._exit(2)

    def server_postInit(self, server):
        if server.cfg.messageBusHost is None:
            self.startMessageBus(server)
        self.startDispatcher(server)

        extension = ServerExtension(server)
        extension.attach()

    def server_loop(self, server):
        if hasattr(server, '_nodeClient'):
            server._nodeClient.poll()

    def server_shutDown(self, server):
        if getattr(server, '_dispatcherPid', None):
            pid = server._dispatcherPid
            server._dispatcherPid = None
            server._killPid(pid)
        if getattr(server, '_messageBusPid', None):
            pid = server._messageBusPid
            server._messageBusPid = None
            server._killPid(pid)

    def server_pidDied(self, server, pid, status):
        if server._halt:
            return
        if pid == getattr(server, '_messageBusPid', None):
            server._halt = True
            server._messageBusPid = None
            server.error('Message bus died - shutting down rMake')
        elif pid == getattr(server, '_dispatcherPid', None):
            server._halt = True
            server._dispatcherPid = None
            server.error('Dispatcher died - shutting down rMake')

    def server_builderInit(self, server, builder):
        builder.setWorker(WorkerClient(server.cfg, builder.getJob(), server.db))
