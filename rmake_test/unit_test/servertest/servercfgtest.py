#!/usr/bin/python
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


import pwd

from testutils import mock
from rmake_test import rmakehelp
from rmake.server import servercfg
from rmake.lib import chrootcache
from rmake import errors, constants
from conary.lib import cfgtypes

class CfgChrootCacheTest(rmakehelp.RmakeHelper):
    def testCfgChrootCache(self):
        c = servercfg.CfgChrootCache()
        self.failUnlessEqual(c.parseString('local /path/to/cache'),
                             ('local', '/path/to/cache'))
        self.failUnlessRaises(cfgtypes.ParseError, c.parseString, 'foo')
        self.failUnlessRaises(cfgtypes.ParseError, c.parseString, 'foo bar baz')

        self.failUnlessEqual(c.format(('local', '/path/to/cache')),
                             'local /path/to/cache')

class rMakeBuilderConfigurationTest(rmakehelp.RmakeHelper):
    def testGetChrootCache(self):
        c = servercfg.rMakeBuilderConfiguration()

        # test no setting
        self.failUnlessEqual(c.getChrootCache(), None)
        self.failUnlessEqual(c._getChrootCacheDir(), None)

        # test a valid setting
        c.configLine('chrootcache local /path/to/cache')
        chrootCache = c.getChrootCache()
        self.failUnless(isinstance(chrootCache, chrootcache.LocalChrootCache))
        self.failUnlessEqual(c._getChrootCacheDir(), '/path/to/cache')

        # test checkBuildSanity - need to mock out some bits for that
        def getpwuid(*args):
            class struct_passwd:
                pass
            p = struct_passwd()
            p.pw_name = constants.rmakeUser
            return p
        mock.replaceFunctionOnce(pwd, 'getpwuid', getpwuid)
        mock.mockMethod(c._checkDir, True)
        c.checkBuildSanity()
        self.failUnlessEqual(c._checkDir._mock.calls,
                             [
            (('buildDir', '/var/rmake'), ()),
            (('chroot dir (subdirectory of buildDir)', '/var/rmake/chroots', 'rmake', 448), ()),
            (('chroot archive dir (subdirectory of buildDir)', '/var/rmake/archive', 'rmake', 448), ()),
            (('chroot cache dir (subdirectory of buildDir)', '/path/to/cache', 'rmake', 448), ())
            ])

        # test an invalid setting
        c.configLine('chrootcache unknown /path/to/cache')
        try:
            c.getChrootCache()
            self.fail('exception expected was not raised')
        except Exception, e:
            self.failUnless(isinstance(e, errors.RmakeError))
            self.failUnlessEqual(str(e), 'unknown chroot cache type of "unknown" specified')
        self.failUnlessEqual(c._getChrootCacheDir(), None)

    def testLocalRepoMap(self):
        """
        Test that single-node servers are configured to use 'localhost' for
        contacting the repository.
        """
        cfg = servercfg.rMakeConfiguration()
        self.assertEquals(cfg.hostName, 'localhost')
