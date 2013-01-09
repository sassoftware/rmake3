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
