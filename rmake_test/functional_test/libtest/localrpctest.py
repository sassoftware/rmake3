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


import sys
import signal
import tempfile
import os

from testrunner import testhelp
from rmake.lib import localrpc

class Server:
    def hello(self):
        return 'hello, world'

class LocalRpcTest(testhelp.TestCase):

    def testLocalRPC(self):
        fd, path = tempfile.mkstemp()
        os.unlink(path)

        server = localrpc.UnixDomainXMLRPCServer(path, logRequests=False)
        server.register_instance(Server())

        pid = os.fork()
        if pid == 0:
            server.serve_forever()

        proxy = localrpc.ServerProxy('unix://' + path)
        assert(proxy.hello() == 'hello, world')

        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        os.unlink(path)
