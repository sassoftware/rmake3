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
Tracks compatibility with versions of integrated software for backwards
compatibility checks.
"""
from conary import constants
from rmake import errors

try:
    from conary.cmds import cvccmd
except ImportError:
    # pyflakes=ignore
    from conary import cvc as cvccmd

minimumSupportedConaryVersion = '2.1.12'
minimumBuildVersion = '1.1.19'


def parseVersion(ver):
    bits = []
    for bit in ver.split('.'):
        try:
            bits.append(int(bit))
        except ValueError:
            bits.append(9999)
            break
    return tuple(bits)


class ConaryVersion(object):

    def __init__(self, conaryVersion=None):
        if conaryVersion is None:
            conaryVersion = constants.version
            # first, remove any changeset id (RMK-1077)
            conaryVersion = conaryVersion.split('_', 1)[0]
            # then convert to integers
            conaryVersion = parseVersion(conaryVersion)
        self.conaryVersion = conaryVersion

        self.majorVersion = self.conaryVersion[0:2]
        if len(self.conaryVersion) < 3:
            self.minorVersion = 0
        else:
            self.minorVersion = self.conaryVersion[2]

    def checkRequiredVersion(self, minVer=minimumSupportedConaryVersion):
        if not self.checkVersion(minVer):
            raise errors.RmakeError("rMake requires Conary version %s or "
                    "later (found version %s)" % (minVer, constants.version))

    def checkVersion(self, minVer=None, maxVer=None):
        if minVer:
            if isinstance(minVer, basestring):
                minVer = parseVersion(minVer)
            if self.conaryVersion < minVer:
                return False

        if maxVer:
            if isinstance(maxVer, basestring):
                maxVer = parseVersion(maxVer)
            if self.conaryVersion > maxVer:
                return False

        return True

    # Individual compatibility checks

    def getObjectsToCook(self, loaders, recipeClasses):
        if hasattr(loaders[0], 'getLoadedTroves'):
            return loaders
        return recipeClasses

    def requireFactoryRecipeGeneration(self):
        '''
        Checks to see if the FactoryRecipe generator exists, added pre conary
        2.0.26
        '''
        if not self.checkVersion(minVer='2.0.26'):
            raise errors.RmakeError('rMake requires a conary version 2.0.26 or '
                                    'greater to build factories')
        return True


def checkRequiredVersions():
    ConaryVersion().checkRequiredVersion()
