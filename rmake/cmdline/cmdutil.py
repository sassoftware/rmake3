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
