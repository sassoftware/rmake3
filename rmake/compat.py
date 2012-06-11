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
