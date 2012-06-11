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


from testutils import mock

from rmake_test import rmakehelp
from rmake.lib import chrootcache
from conary.lib import util
import subprocess
import re
import os
import tempfile

class LocalChrootCacheTest(rmakehelp.RmakeHelper):
    def setUp(self):
        rmakehelp.RmakeHelper.setUp(self)
        self.cacheDir = self.workDir + '/chrootcache'
        self.chrootCache = chrootcache.LocalChrootCache(self.cacheDir)

    def _mkdirChain(self, *args, **kw):
        self.failUnless(len(args) == 1)
        self.failUnless(args[0].endswith('/work/chrootcache'))

    def testStore(self):
        def call(*args, **kw):
            expected = 'tar cSpf - -C /some/dir . | gzip -1 - > %s/6861736868617368686173686861736868617368.ABC123.tar.gz' %self.cacheDir
            self.failUnlessEqual(args, (expected,))
            self.failUnless(kw == dict(shell=True))

        def mkstemp(*args, **kw):
            return (
                os.open('/dev/null', os.O_WRONLY),
                '%s/6861736868617368686173686861736868617368.ABC123.tar.gz' %
                    self.cacheDir)

        def rename(*args, **kw):
            pass

        mock.replaceFunctionOnce(subprocess, 'call', call)
        mock.replaceFunctionOnce(util, 'mkdirChain', self._mkdirChain)
        mock.replaceFunctionOnce(tempfile, 'mkstemp', mkstemp)
        mock.replaceFunctionOnce(os, 'rename', rename)
        self.chrootCache.store('hash' * 5, '/some/dir')

    def testRestore(self):
        def call(*args, **kw):
            expected = 'zcat %s/6861736868617368686173686861736868617368.tar.gz | tar xSpf - -C /some/dir' %self.cacheDir
            self.failUnlessEqual(args, (expected,))
            self.failUnless(kw == dict(shell=True))

        mock.replaceFunctionOnce(subprocess, 'call', call)
        self.chrootCache.restore('hash' * 5, '/some/dir')

    def testHasChroot(self):
        def isfile(*args, **kw):
            self.failUnless(kw == {})
            expected = '%s/6861736868617368686173686861736868617368.tar.gz' %self.cacheDir
            self.failUnlessEqual(args, (expected,))
            return True

        mock.replaceFunctionOnce(os.path, 'isfile', isfile)
        self.failUnless(self.chrootCache.hasChroot('hash' * 5))

        def isfile(*args, **kw):
            self.failUnless(len(args) == 1)
            self.failUnless(kw == {})
            self.failUnless(args[0].endswith('/work/chrootcache/6861736868617368686173686861736868617368.tar.gz'))
            return False

        mock.replaceFunctionOnce(os.path, 'isfile', isfile)
        self.failUnless(not self.chrootCache.hasChroot('hash' * 5))

    def test_fingerPrintToPath(self):
        path = self.chrootCache._fingerPrintToPath('hash' * 5)
        self.failUnlessEqual(path, self.cacheDir + '/6861736868617368686173686861736868617368.tar.gz')


class ChrootCacheInterfaceTest(rmakehelp.RmakeHelper):
    def testChrootCacheInterface(self):
        intf = chrootcache.ChrootCacheInterface()
        self.failUnlessRaises(NotImplementedError, intf.store, 'foo', 'dir')
        self.failUnlessRaises(NotImplementedError, intf.restore, 'foo', 'dir')
        self.failUnlessRaises(NotImplementedError, intf.hasChroot, 'foo')
