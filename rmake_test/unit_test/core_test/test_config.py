#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#


from twisted.trial import unittest

from rmake.core import config


class ConfigTest(unittest.TestCase):

    def test_calculatedPaths(self):
        cfg = config.DispatcherConfig()
        cfg.dataDir = '/tmp/data'
        self.assertEquals(cfg.lockDir, '/tmp/data/lock')
        cfg.dataDir = '/tmp/data2'
        self.assertEquals(cfg.lockDir, '/tmp/data2/lock')
        cfg.logDir = '/tmp/logs'
        self.assertEquals(cfg.logPath_http, '/tmp/logs/access.log')
        self.assertEquals(cfg.logPath_server, '/tmp/logs/server.log')

    def test_fails(self):
        self.fail("oh nooo")
