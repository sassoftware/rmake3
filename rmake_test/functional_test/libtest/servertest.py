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
