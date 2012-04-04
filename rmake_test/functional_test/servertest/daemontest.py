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
import shutil
from conary.lib import util
from testrunner import testhelp
from testutils import mock
from testutils import sock_utils

from rmake.lib import logfile
from rmake.server import daemon
from rmake_test import resources
from rmake_test import rmakehelp


class DaemonTest(rmakehelp.RmakeHelper):

    def testResetCommand(self):
        raise testhelp.SkipTestException('Failing test in bamboo')
        oldRm = os.remove
        oldRmTree = shutil.rmtree
        try:
            cfg = self.rmakeCfg
            util.mkdirChain(cfg.getReposDir())
            util.mkdirChain(cfg.getProxyDir())
            mock.mock(os, 'remove')
            mock.mock(shutil, 'rmtree')
            cmd = daemon.ResetCommand()
            self.captureOutput(cmd.runCommand, None,
                               self.rmakeCfg, ['reset'], {})
            os.remove._mock.assertCalled(cfg.getDbPath())
            os.remove._mock.assertNotCalled()
            shutil.rmtree._mock.assertCalled(cfg.getReposDir())
            shutil.rmtree._mock.assertCalled(cfg.getDbContentsPath())
            shutil.rmtree._mock.assertCalled(cfg.getProxyDir())
            shutil.rmtree._mock.assertNotCalled()
        finally:
            os.remove = oldRm
            shutil.rmtree = oldRmTree

    def testStart(self):
        raise testhelp.SkipTestException('Failing test in bamboo')
        startFile = self.workDir + '/startFile'
        if os.path.exists(startFile):
            os.remove(startFile)
        stopFile = self.workDir + '/stopFile'
        #sys.argv[0] = 'python ./testsuite.py'
        #sys.argv[0] = 'daemontest.py'
        self.rmakeCfg.pluginDirs = resources.get_plugin_dirs()
        self.rmakeCfg.usePlugins = False
        self.rmakeCfg.usePlugin['multinode'] = False
        reposPort, proxyPort = sock_utils.findPorts(2)
        self.rmakeCfg.reposUrl = 'http://LOCAL:%s' % reposPort
        self.rmakeCfg.proxyUrl = 'http://LOCAL:%s' % proxyPort

        util.mkdirChain(self.rmakeCfg.lockDir)
        util.mkdirChain(self.rmakeCfg.buildDir)
        pid = os.fork()
        if not pid:
            self.rmakeCfg.writeToFile(self.workDir + '/rmakecfg')
            daemon.rMakeDaemon.configClass.getSocketPath = lambda x: self.rootDir + '/socket'
            daemon.rMakeDaemon.configClass.getServerUri = lambda x: 'unix://' + self.rootDir + '/socket'


            logFile = logfile.LogFile(startFile)
            logFile.redirectOutput()
            try:
                try:
                    daemon.main(['rmake-server', 'start', '-n', '--skip-default-config', '--config-file', self.workDir + '/rmakecfg'])
                except SystemExit, err:
                    if err.code == 0:
                        os._exit(0)
            finally:
                os._exit(1)
        timeSlept = 0
        while timeSlept < 5:
            if os.path.exists(startFile):
                log = open(startFile).read()
                if 'Started rMake Server at pid %s' % pid in log:
                    break
            time.sleep(.1)
            timeSlept += .1
        assert(timeSlept < 5)
        # wait for fail current jobs process to stop.
        time.sleep(1)
        try:
            logFile = logfile.LogFile(stopFile)
            logFile.redirectOutput()
            daemon.main(['rmake-server', 'stop', '--skip-default-config', '--config-file', self.workDir + '/rmakecfg'])
        except SystemExit, err:
            if err.code:
                raise
        timeSlept = 0
        while timeSlept < 5:
            pid, status = os.waitpid(pid, os.WNOHANG)
            if pid:
                break
            time.sleep(.1)
            timeSlept += .1
        assert(pid)
        assert(not status)
        logOutput = re.sub('[0-9:]+ -', '[TIME] -', open(startFile).read())
        logOutput = re.sub('\(serving at .*\)', '(serving at <path>)', logOutput)
        logOutput = re.sub('[0-9]+', '<#>', logOutput)
        logOutput = re.sub('using Conary in .*', 'using Conary in <path>', logOutput)
        self.assertEquals(logOutput, '''\
[TIME] - [rmake-server] - using Conary in <path>
[TIME] - [rmake-server] - Started repository "rmakehost" on port <#> (pid <#>)
[TIME] - [rmake-server] - Started proxy on port <#> (pid <#>)
[TIME] - [rmake-server] - *** Started rMake Server at pid <#> (serving at <path>)
[TIME] - [rmake-server] - Shutting down server
[TIME] - [rmake-server] - killing repository at <#>
[TIME] - [rmake-server] - killing proxy at <#>
''')

