# -*- mode: python -*-
#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

import os
import signal
import sys
import time


#test
from rmake_test import rmakehelp

#conary
from conary.deps import deps
from conary.repository import errors as repoerrors

#rmake
from rmake import errors
from rmake.lib import apirpc
from rmake.lib import apiutils
from rmake.lib.apiutils import api, api_parameters, api_return, api_forking, api_nonforking
from rmake.lib.rpcproxy import ShimAddress

class TestServer(apirpc.XMLApiServer):
    def __init__(self, *args, **kw):
        apirpc.XMLApiServer.__init__(self, *args, **kw)
        self._delayed = []

    @api(version=1)
    @api_parameters(1, 'bool')
    @api_return(1, 'bool')
    def ping(self, callData, b):
        return b

    @api(version=1)
    @api_parameters(1, 'flavor')
    @api_return(1, 'flavor')
    def ping2(self, callData, flavor):
        return flavor

    @api(version=1)
    def getPid(self, callData):
        return os.getpid()

    @api_forking
    @api(version=1)
    def getPidForking(self, callData):
        return os.getpid()

    @api_nonforking
    @api(version=1)
    def getPidNoForking(self, callData):
        return os.getpid()

    @api(version=1)
    @api_parameters(1)
    @api_return(1, None)
    def getAuth(self, callData):
        auth = callData.getAuth()
        return (auth.pid, auth.uid, auth.gid)

    @api_nonforking
    @api(version=1)
    @api_parameters(1, 'int')
    def delayed(self, callData, val):
        self._delayed.append((callData, val))
        return callData.delay()

    @api_nonforking
    @api(version=1)
    def release(self, callData):
        delayed = self._delayed
        self._delayed = []
        for callData, delayedVal in delayed:
            if delayedVal < 0:
                callData.respondWithException(
                                errors.RmakeError('Cannot accept %s' % delayedVal))
            else:
                callData.respond(delayedVal)
        return len(delayed)

class TestClient(object):
    def __init__(self, uri):
        self.proxy = apirpc.XMLApiProxy(TestServer, uri)

    def ping(self, b):
        return self.proxy.ping(b)

    def ping2(self, flavor):
        return self.proxy.ping2(flavor)

    def getAuth(self):
        return self.proxy.getAuth()

    def getPid(self):
        return self.proxy.getPid()

    def getPidNoForking(self):
        return self.proxy.getPidNoForking()

    def getPidForking(self):
        return self.proxy.getPidForking()

    def delayed(self, val):
        return self.proxy.delayed(val)

    def release(self):
        return self.proxy.release()

class ApiRPCTest(rmakehelp.RmakeHelper):
    def testApiRpcServe(self):
        self._testApiRpcServe(False)

    def testApiRpcServeForking(self):
        self._testApiRpcServe(True)

    def _testApiRpcServe(self, forking):

        port = testsuite.findPorts(1)[0]
        uri = 'http://localhost:%s/conary/' % port
        server = TestServer(uri, forkByDefault=forking)
        client = TestClient(uri)

        pid = os.fork()
        if not pid:
            time.sleep(.1)
            client.ping(True)
            os._exit(0)
        else:
            server.server.handle_request()
            self.waitThenKill(pid)


        pid = os.fork()
        if not pid:
            try:
                server.server.handle_request()
                server.server.handle_request()
                server.server.handle_request()
            finally:
                os._exit(0)
        else:
            assert((client.getPid() == pid) == (not forking))
            assert(client.getPidForking() != pid)
            assert(client.getPidNoForking() == pid)
            self.waitThenKill(pid)

        uri = 'unix://%s/socket' % self.workDir
        server = TestServer(uri)
        client = TestClient(uri)
        pid = os.fork()
        if not pid:
            time.sleep(.1)
            client.ping2(deps.parseFlavor('foo'))
            os._exit(0)
        else:
            server.server.handle_request()
            self.waitThenKill(pid)

        # verify that the unix SO_PEERCRED authentication gets the client
        # side pid,uid,gid as the peer credentials
        uri = 'unix://%s/socket2' % self.workDir
        server = TestServer(uri, forkByDefault=forking)
        client = TestClient(uri)
        pid = os.fork()
        if not pid:
            time.sleep(.1)
            server.server.handle_request()
            os._exit(0)
        else:
            time.sleep(.1)
            auth = tuple(client.getAuth())
            self.failUnless(auth == (os.getpid(), os.getuid(), os.getgid()))
            self.waitThenKill(pid)

    def testApiRpcParams(self):
        server = TestServer()
        client = TestClient(ShimAddress(server))
        assert(client.ping(True))
        assert(client.ping2(deps.parseFlavor('foo')) == deps.parseFlavor('foo'))
        self.assertRaises(apirpc.ApiError, client.proxy.ping, True, False)

        self.assertRaises(apirpc.ApiError, client.proxy.foobar)

    def testApiMajorVersionMismatch(self):
        server = TestServer()
        client = TestClient(ShimAddress(server))
        client.proxy._apiMajorVersion = '123123'
        tgt = "while the client runs API version 123123"
        try:
            client.ping(True)
        except errors.RmakeError, e:
            self.failUnlessIn(tgt, str(e))
        else:
            raise Exeption("ApiError not raised")

    def testFreezeThaw(self):
        @api(version=1)
        @api_parameters(1, None)
        @api_return(1, None)
        def testFunc(self, foo):
            return 0

        assert(list(apirpc._freezeParams(testFunc, [0], 1)) == [0])
        assert(apirpc._thawReturn(testFunc, 0, 1) == 0)

    def testFreezeThawException(self):
        @api(version=1)
        @api_parameters(1, None)
        @api_return(1, None)
        def testFunc(self, foo):
            return 0

        sys.exc_clear()
        frz = apirpc._freezeException(repoerrors.OpenError('foo'))
        self.assertEquals(str(apiutils.thaw(*frz)),
        'Exception from server:\n'
        'conary.repository.errors.OpenError: foo\n'
        'None\n')
        # this is rmake's internal error
        frz = apirpc._freezeException(errors.OpenError('foo'))
        self.assertEquals(str(apiutils.thaw(*frz)), 'foo')


    def testApiDelayed(self):
        def _forkCall(client, val):
            pid = os.fork()
            if pid:
                return pid
            try:
                if val < 0:
                    self.assertRaises(errors.RmakeError, client.delayed, val)
                else:
                    assert(val == client.delayed(val))
                os._exit(0)
            finally:
                os._exit(1)

        port = testsuite.findPorts(1)[0]
        uri = 'http://localhost:%s/conary/' % port
        server = TestServer(uri)

        pid = os.fork()
        if not pid:
            try:
                server.serve_forever()
            finally:
                os._exit(0)
        try:
            serverPid = pid
            client = TestClient(uri)
            pids = []
            pids.append(_forkCall(client, 1))
            pids.append(_forkCall(client, 2))
            pids.append(_forkCall(client, -1))
            import time
            time.sleep(1)
            for pid in pids:
                assert(not os.waitpid(pid, os.WNOHANG)[0])
            assert(client.release() == 3)
            for pid in pids:
                pid, status  = self.waitThenKill(pid)
                assert(not status)
        finally:
            os.kill(serverPid, 9)
            self.waitThenKill(serverPid)


