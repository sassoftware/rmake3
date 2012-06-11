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
