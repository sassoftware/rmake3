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
