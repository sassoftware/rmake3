# -*- mode: python -*-
#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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

