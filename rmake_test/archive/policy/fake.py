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
