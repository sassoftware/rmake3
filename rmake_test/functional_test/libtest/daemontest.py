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
import re
import sys
import time

from conary_test import rephelp

# conary
from conary.lib import util

#rmake
from rmake.lib import daemon

#test
from testutils import mock

class DaemonTest(rephelp.RepositoryHelper):
    def generateDaemonClass(self):


        class MyConfig(daemon.DaemonConfig):
            logDir = self.workDir + '/var/log'
            lockDir = self.workDir + '/var/lock'

        class MyTestDaemon(daemon.Daemon):
            configClass = MyConfig
            name = 'foobar'

            def getConfigFile(self, argv):
                return MyConfig()

            def doWork(self):
                try:
                    while True:
                        time.sleep(.1)
                finally:
                    os._exit(2)
        return MyTestDaemon

    def testGetDaemon(self):
        raise testsuite.SkipTestException('Fails in bamboo')
        daemonClass = self.generateDaemonClass()
        util.mkdirChain(self.workDir + '/var/log')
        util.mkdirChain(self.workDir + '/var/lock')
        d = daemonClass()
        rv, txt = self.captureOutput(d.main, ['./daemontest', 'start'])
        assert(not rv)
        err, txt = self.captureOutput(d.main, ['./daemontest', 'start'],
                                     _returnException=True)
        assert(isinstance(err, SystemExit))
        assert(err.code == 1)
        assert(re.match('[0-9:]+ - \[foobar\] - error: Daemon already running as pid [0-9]+', txt))
        pid = d.getPidFromLockFile()
        rv, txt = self.captureOutput(d.main, ['./daemontest', 'stop'])
        err, txt = self.captureOutput(d.main, ['./daemontest', 'stop'],
                                     _returnException=True)
        txt = open(self.workDir + '/var/log/foobar.log').read()
        assert(re.search("[0-9/]+ [0-9:]+ [A-Z]* - \[foobar\] - warning: unable to open lockfile for reading: %s/var/lock/foobar.pid \(\[Errno 2\] No such file or directory: '%s/var/lock/foobar.pid'\)\n"
                 "[0-9/]+ [0-9:]+ [A-Z]* - \[foobar\] - error: could not kill foobar: no pid found.\n" % (self.workDir, self.workDir), txt))
        assert(isinstance(err, SystemExit))
        assert(err.code == 1)

    def testStopDaemon(self):
        raise testsuite.SkipTestException('Fails in bamboo')
        daemonClass = self.generateDaemonClass()
        util.mkdirChain(self.workDir + '/var/log')
        util.mkdirChain(self.workDir + '/var/lock')
        d = daemonClass()
        rv, txt = self.captureOutput(d.main, ['./daemontest', 'start'])
        assert(not rv)
        mock.mock(os, 'kill')
        mock.mock(time, 'sleep')
        mock.mockMethod(d.error)
        err, txt = self.captureOutput(d.main, ['./daemontest', 'stop'], 
                                     _returnException=True)
        msg = d.error._mock.popCall()[0][0]
        assert('Failed to kill foobar (pid ' in msg)
        mock.unmockAll()
        self.captureOutput(d.main, ['./daemontest', 'stop'])
