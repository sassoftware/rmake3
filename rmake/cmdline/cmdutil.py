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
Command line utilities.  Should never be needed outside of the command line parsing, and thus should never need to be imported by anyone.
"""
import re

from conary.conaryclient import cmdline

def parseTroveSpec(troveSpec, allowEmptyName=False):
    troveSpec, context = re.match('^(.*?)(?:{(.*)})?$', troveSpec).groups()
    troveSpec = cmdline.parseTroveSpec(troveSpec, allowEmptyName=allowEmptyName)
    return troveSpec + (context,)

def parseTroveSpecContext(troveSpec, allowEmptyName=False):
    troveSpec, context = re.match('^(.*?)(?:{(.*)})?$', troveSpec).groups()
    return troveSpec, context

def getSpecStringFromTuple(spec):
    troveSpec = ''
    if len(spec) == 4:
        context = spec[3]
    else:
        context = None
    if spec[0] is not None:
        troveSpec = spec[0]
    if spec[1] is not None:
        troveSpec += '=%s' % spec[1]
    if spec[2] is not None:
        troveSpec += '[%s]' % spec[2]
    return troveSpec, context
