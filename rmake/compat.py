#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Tracks compatibility with versions of integrated software for backwards 
compatibility checks.
"""
from conary import constants
from conary import state
from conary.lib import log

from rmake import errors

testing = False

class ConaryVersion(object):
    maxKnownVersion = "2.0"
    _warnedUser = False

    def __init__(self, conaryVersion=None):
        global testing
        if conaryVersion is None:
            if not testing:
                conaryVersion = constants.version
            else:
                conaryVersion = self.maxKnownVersion

        try:
            self.conaryVersion = [int(x) for x in conaryVersion.split('.')]
        except ValueError, err:
            if not self._warnedUser:
                log.warning('nonstandard conary version "%s".  Assuming latest "%s".' % (conaryVersion, self.maxKnownVersion))
                ConaryVersion._warnedUser = True
            self.conaryVersion = [ int(x)
                                    for x in self.maxKnownVersion.split('.') ]

        self.majorVersion = self.conaryVersion[0:2]
        if len(self.conaryVersion) < 3:
            self.minorVersion = 0
        else:
            self.minorVersion = self.conaryVersion[2]
        self.isOneOne = self.majorVersion == (1,1)
        self.isOneTwo = self.majorVersion == (1,2)
        self.isTwoZero = self.majorVersion == (2,0)

    def checkRequiredVersion(self):
        oneZeroVersion = None
        oneOneVersion = 19
        oneTwoVersion = 0
        twoZeroVersion = 0
        if not self.checkVersion(oneZeroVersion, oneOneVersion,
                                 oneTwoVersion, twoZeroVersion):
            versions = []
            if oneOneVersion:
                versions.append('1.1.%s' % oneOneVersion)
            if oneTwoVersion:
                versions.append('1.2.%s' % oneTwoVersion)
            if twoZeroVersion:
                versions.append('2.0.%s' % twoZeroVersion)
            versions = ' or '.join(versions)
            raise errors.RmakeError('rMake requires conary'
                                    ' version %s or greater' % versions)

    def requireVersion(self, oneZeroVersion, oneOneVersion, twoZeroVersion,
                       msg):
        if not self.checkVersion(oneZeroVersion, oneOneVersion, twoZeroVersion):
            version = ''
            if oneZeroVersion:
                version = '1.0.%s or ' % oneZeroVersion
            version += '1.1.%s' % oneOneVersion
            raise errors.RmakeError('rMake requires a conary version %s or greater for %' % (version, msg))
        return True

    def stateFileVersion(self):
        if not hasattr(state.ConaryState, 'stateVersion'):
            return 0
        return state.ConaryState.stateVersion

    def supportsForceCommit(self):
        return self.checkVersion(False, False, 7)

    def signAfterPromote(self):
        return self.checkVersion(True, True, True, False)

    def acceptsPartialBuildReqCloning(self):
        return self.checkVersion(False, 95)

    def supportsFindGroupSources(self):
        return self.checkVersion(False, 21)

    def supportsNewPkgBranch(self):
        return self.checkVersion(False, 25)

    def updateSrcTakesMultipleVersions(self):
        return self.checkVersion(False, 90)

    def requireFindGroupSources(self):
        return self.requireVersion(False, 21, None, 'building group sources')

    def ConaryStateFromFile(self, path, repos=None, parseSource=True):
        if self.stateFileVersion() == 0: 
            return state.ConaryStateFromFile(path)
        else: # support added in 1.0.31 and 1.1.4
            return state.ConaryStateFromFile(path, repos=repos,
                                             parseSource=parseSource)

    def supportsCloneCallback(self):
        # support added in 1.0.30 and 1.1.3
        return self.checkVersion(30, 3)

    def supportsCloneNoTracking(self):
        # support added in 1.1.17
        return self.checkVersion(False, 17)

    def supportsConfigIsDefault(self):
        # support added in 1.0.33 and 1.1.6
        return self.checkVersion(33, 6)

    def supportsCloneNonRecursive(self):
        # support added in 1.0.30 and 1.1.3
        return self.checkVersion(30, 3)

    def checkVersion(self, oneZeroVersion, oneOneVersion, oneTwoVersion=None,
                     twoZeroVersion=None):
        if self.majorVersion == [1,0]:
            if isinstance(oneZeroVersion, bool):
                return oneZeroVersion
            if not oneZeroVersion:
                return False
            return self.minorVersion >= oneZeroVersion
        elif self.majorVersion == [1,1]:
            if isinstance(oneOneVersion, bool): return oneOneVersion
            if not oneOneVersion:
                return False
            return self.minorVersion >= oneOneVersion
        elif self.majorVersion == [1,2]:
            if isinstance(oneTwoVersion, bool): return oneTwoVersion
            if oneTwoVersion is None:
                return True
            return self.minorVersion >= oneTwoVersion
        elif self.majorVersion == [2,0]:
            if isinstance(twoZeroVersion, bool): return twoZeroVersion
            if twoZeroVersion is None:
                return True
            return self.minorVersion >= twoZeroVersion
        # default to supporting everything - we're running something really new!
        return True

def checkRequiredVersions():
    ConaryVersion().checkRequiredVersion()
