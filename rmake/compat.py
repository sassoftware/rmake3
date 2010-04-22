#
# Copyright (c) 2006-2010 rPath, Inc.
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
#
"""
Tracks compatibility with versions of integrated software for backwards
compatibility checks.
"""
from conary import constants
from rmake import errors

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
            conaryVersion = parseVersion(constants.version)
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
                                    'greater to build factories'
                                    % (version, msg))
        return True


def checkRequiredVersions():
    ConaryVersion().checkRequiredVersion()
