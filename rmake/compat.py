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
from conary import state
from conary.lib import log

from rmake import errors

try:
    from conary.cmds import cvccmd
except ImportError:
    # pyflakes=ignore
    from conary import cvc as cvccmd

minimumSupportedConaryVersion = '1.1.19'
testing = False

class ConaryVersion(object):
    _warnedUser = False

    def __init__(self, conaryVersion=None):
        global testing
        if conaryVersion is None:
            if not testing:
                conaryVersion = constants.version
            else:
                conaryVersion = [9999,9999,9999]

        try:
            # first, remove any changeset id (RMK-1077)
            conaryVersion = conaryVersion.split('_', 1)[0]
            # then convert to integers
            self.conaryVersion = [int(x) for x in conaryVersion.split('.')]
        except ValueError, err:
            if not self._warnedUser:
                log.warning('nonstandard conary version "%s". '
                            'Assuming latest.'
                            % (conaryVersion))
                ConaryVersion._warnedUser = True
            self.conaryVersion = [9999]

        self.majorVersion = self.conaryVersion[0:2]
        if len(self.conaryVersion) < 3:
            self.minorVersion = 0
        else:
            self.minorVersion = self.conaryVersion[2]

    def checkRequiredVersion(self):
        if not self.checkVersion():
            raise errors.RmakeError('rMake requires conary'
                                    ' version %s or greater' %
                                    minimumSupportedConaryVersion)

    def stateFileVersion(self):
        if not hasattr(state.ConaryState, 'stateVersion'):
            return 0
        return state.ConaryState.stateVersion

    def supportsForceCommit(self):
        return self.checkVersion(minVer="1.2.7")

    def signAfterPromote(self):
        if self.checkVersion(maxVer="1.2.99"):
            return True
        return False

    def acceptsPartialBuildReqCloning(self):
        return self.checkVersion(minVer="1.1.95")

    def supportsFindGroupSources(self):
        return self.checkVersion(minVer="1.1.21")

    def supportsNewPkgBranch(self):
        return self.checkVersion(minVer="1.1.25")

    def updateSrcTakesMultipleVersions(self):
        return self.checkVersion(minVer="1.1.90")

    def requireFindGroupSources(self):
        if not self.checkVersion(minVer='1.1.21'):
            raise errors.RmakeError('rMake requires a conary version 1.1.21 or '
                                    'greater to build group sources'
                                    % (version, msg))
        return True

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

    def ConaryStateFromFile(self, path, repos=None, parseSource=True):
        if self.stateFileVersion() == 0: 
            return state.ConaryStateFromFile(path)
        else: # support added in 1.0.31 and 1.1.4
            return state.ConaryStateFromFile(path, repos=repos,
                                             parseSource=parseSource)

    def loadServerSchema(self, db):
        from conary.server import schema
        if self.checkVersion(minVer='1.2.6'):
            schema.loadSchema(db, doMigrate=True)
        else:
            schema.loadSchema(db, migrate=True)

    def supportsCloneCallback(self):
        # support added in 1.0.30 and 1.1.3
        return self.checkVersion(minVer=('1.0.30','1.1.3'))

    def supportsCloneNoTracking(self):
        # support added in 1.1.17
        return self.checkVersion(minVer='1.1.17')

    def supportsConfigIsDefault(self):
        # support added in 1.0.33 and 1.1.6
        return self.checkVersion(minVer=('1.0.33','1.1.6'))

    def supportsCloneNonRecursive(self):
        # support added in 1.0.30 and 1.1.3
        return self.checkVersion(minVer=('1.0.30','1.1.3'))

    def getObjectsToCook(self, loaders, recipeClasses):
        if hasattr(loaders[0], 'getLoadedTroves'):
            return loaders
        return recipeClasses

    def supportsDefaultBuildReqs(self):
        # Support added in 2.0.28
        return self.checkVersion(minVer='1.0.28')

    def checkVersion(self, minVer=minimumSupportedConaryVersion, maxVer=None):
        if minVer:
            if isinstance(minVer, str):
                minVer = [int(x) for x in minVer.split(".")]
                if not minVer <= self.conaryVersion:
                    return False
            else:
                lowVer = [9999,9999,9999]
                for v in minVer:
                    v = [int(x) for x in v.split(".")]
                    if self.conaryVersion[:2] == v[:2] and \
                            not v <= self.conaryVersion:
                        return False
                    lowVer = min(lowVer,v)
                if not lowVer <= self.conaryVersion:
                    return False
        if maxVer:
            if isinstance(maxVer, str):
                maxVer = [int(x) for x in maxVer.split(".")]
                if not self.conaryVersion <= maxVer:
                    return False
            else:
                highVer = mimumSupportedConaryVersion
                for v in maxVer:
                    v = [int(x) for x in v.split(".")]
                    if self.conaryVersion[:2] == v[:2] and \
                            not self.conaryVersion <= v:
                        return False
                    highVer = max(highVer,v)
                if not self.conaryVersion <= highVer:
                    return False
        return True

def checkRequiredVersions():
    ConaryVersion().checkRequiredVersion()
