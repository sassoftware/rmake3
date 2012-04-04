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


"""
Tests rmake.node.nodecfg
"""

import os
import sys
import time

from testutils import mock
from rmake_test import rmakehelp
from conary_test import recipes

from conary.deps import deps
from conary.deps import arch

from rmake import failure
from rmake.worker import command

class NodeTest(rmakehelp.RmakeHelper):

    def testNodeConfig(self):
        from rmake.node import nodecfg
        oldArch = arch.baseArch
        try:
            arch.baseArch = 'x86_64'
            arch.initializeArch()
            cfg = nodecfg.NodeConfiguration()
            assert(cfg.buildFlavors == set([deps.parseFlavor('is:x86_64 x86')]))
        finally:
            arch.baseArch = oldArch
            arch.initializeArch()
