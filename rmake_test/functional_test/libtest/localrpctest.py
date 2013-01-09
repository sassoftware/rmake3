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
