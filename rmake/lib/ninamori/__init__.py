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


import inspect
import os
import sys
from rmake.lib.ninamori.connection import ConnectString, DatabaseConnection


def connect(connectString):
    if isinstance(connectString, basestring):
        connectString = ConnectString.parse(connectString)
    elif not isinstance(connectString, ConnectString):
        raise TypeError("Expected string or ConnectString object")
    driver = connectString.driver

    importRoot = os.path.dirname(__file__)
    moduleRoot = __name__
    addParts = ['drivers', driver]

    driverPath = os.path.join(importRoot, *addParts)
    for suffix in ('.py', '.pyc', '.so', 'module.so'):
        if os.path.exists(driverPath + suffix):
            break
    else:
        raise TypeError("Could not find database driver %r" % (driver,))

    moduleName = '.'.join([moduleRoot] + addParts)
    __import__(moduleName)

    for name, value in inspect.getmembers(sys.modules[moduleName]):
        if name.startswith('_') or not inspect.isclass(value):
            continue
        if issubclass(value, DatabaseConnection) and value.driver == driver:
            return value.connect(connectString)
    else:
        raise TypeError("Driver %r lacks a proper driver subclass" % (driver,))
