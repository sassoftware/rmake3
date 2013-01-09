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

from testrunner import testhelp
from conary_test import rephelp

import re
import signal
import time

#rmake
from rmake.lib import server

#test

class ServerTest(rephelp.RepositoryHelper):

    def _signalHandler(self, signalNum, frame):
        pass

    def _signalHandlerKill(self, signalNum, frame):
        os.kill(os.getpid(), signal.SIGKILL)

    def testKillPid(self):
        s = server.Server()
        pid = os.fork()
        signal.signal(signal.SIGTERM, self._signalHandler)
        if pid:
            time.sleep(1)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            rc, txt = self.captureOutput(s._killPid, pid, 'Frobnicator',
                                         timeout=2)

            assert(re.match('[0-9:]+ - \[root\] - warning: pid [0-9]+ \(Frobnicator\) exited with exit status 1', txt))
        else:
            try:
                time.sleep(10000)
            finally:
                os._exit(1)


    def testKillPidHarder(self):
        s = server.Server()
        pid = os.fork()
        signal.signal(signal.SIGTERM, self._signalHandler)
        if pid:
            time.sleep(1)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            rc, txt = self.captureOutput(s._killPid, pid, 'Frobnicator', 
                                         timeout=.5)
            assert(re.match('[0-9:]+ - \[root\] - warning: Frobnicator \(pid [0-9]+\) would not die, killing harder...', txt))
        else:
            try:
                time.sleep(10000)
                time.sleep(10000)
            finally:
                os._exit(1)

    def testKillPidSignal(self):
        raise testhelp.SkipTestException("Test is unreliable")
        s = server.Server()
        pid = os.fork()
        signal.signal(signal.SIGTERM, self._signalHandlerKill)
        if pid:
            time.sleep(.1)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            rc, txt = self.captureOutput(s._killPid, pid, 'Frobnicator',
                                         timeout=2)
            assert(re.match('[0-9:]+ - \[root\] - warning: pid [0-9]+ \(Frobnicator\) killed with signal 9', txt))
        else:
            try:
                time.sleep(10000)
            finally:
                os._exit(1)

    def testCollectChildren(self):
        s = server.Server()
        s._collectChildren()
        pid = os.fork()
        if not pid:
            time.sleep(10000)
        os.kill(pid, signal.SIGKILL)
        time.sleep(.1)
        rc, txt = self.captureOutput(s._collectChildren)
        assert(re.match('[0-9:]+ - \[root\] - warning: pid [0-9]+ \(Unknown\) killed with signal 9', txt))
        pid = os.fork()
        if not pid:
            os._exit(13)
        time.sleep(.5)
        rc, txt = self.captureOutput(s._collectChildren)
        assert(re.match('[0-9:]+ - \[root\] - warning: pid [0-9]+ \(Unknown\) exited with exit status 13', txt))

    def testTry(self):
        def raiseSystemExit():
            raise SystemExit(1)

        def raiseException():
            raise RuntimeError('foo')

        def passMe():
            pass

        s = server.Server()
        rc, txt = self.captureOutput(s._try, 'Frobinator', raiseException,
                                     _returnException=True)
        assert(isinstance(rc, RuntimeError))
        assert('Error in Frobinator' in txt)
        assert('RuntimeError: foo' in txt)
        rc, txt = self.captureOutput(s._try, 'Frobinator', passMe)
        assert(not txt)
        self.assertRaises(SystemExit,
                          self.captureOutput, s._try, 'Frobinator',
                          raiseSystemExit)
