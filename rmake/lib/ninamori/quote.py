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


import re


_QID_CACHE = {}
SAFE_IDENTIFIER = re.compile('^[a-z_][a-z0-9_]*$')


def quoteIdentifier(name):
    if name in _QID_CACHE:
        return _QID_CACHE[name]

    if '"' in name:
        raise ValueError("Double quotes cannot appear in SQL identifiers.")

    if SAFE_IDENTIFIER.search(name):
        quoted = name
    else:
        quoted = '"%s"' % (name,)

    _QID_CACHE[name] = quoted
    return quoted


def quoteString(val):
    # TODO: implement this!
    return repr(val)
