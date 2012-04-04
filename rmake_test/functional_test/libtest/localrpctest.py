#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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

