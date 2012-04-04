#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

import errno
import os
import shutil
import stat

from conary.lib import util
from conary.build import macros, policy
from conary.build.use import Use


class Foo(policy.DestdirPolicy):
    """
        Fake policy
    """
    invariantinclusions = [ '.*' ]

    def __init__(self, *args, **keywords):
        policy.DestdirPolicy.__init__(self, *args, **keywords)

    def doFile(self, path):
        raise RuntimeError('This fake policy always breaks.')
