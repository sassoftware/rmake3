#
# Copyright (c) 2009 rPath, Inc.
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
