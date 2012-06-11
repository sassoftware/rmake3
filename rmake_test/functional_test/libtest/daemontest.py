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
