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


import os
import pwd
import socket
import sys

from conary.deps import arch
from conary.deps import deps
from conary.lib.cfg import ConfigFile
from conary.lib.cfgtypes import CfgType, ParseError
from conary.lib.cfgtypes import CfgBool, CfgPath, CfgInt, CfgString

from rmake import constants
from rmake import errors
from rmake.lib import chrootcache


class CfgChrootCache(CfgType):
    def parseString(self, str):
        s = str.split()
        if len(s) != 2:
            raise ParseError("chroot cache type and path expected")
        return tuple(s)

    def format(self, val, displayOptions = None):
        return "%s %s" % val


class rMakeBuilderConfiguration(ConfigFile):
    buildDir          = (CfgPath, '/var/rmake')
    helperDir         = (CfgPath, "/usr/libexec/rmake")
    slots             = (CfgInt, 1)
    useCache          = (CfgBool, False)
    useTmpfs          = (CfgBool, False)
    chrootLimit       = (CfgInt, 4)
    chrootCache       = CfgChrootCache
    chrootCaps        = (CfgBool, False,
            "Set capability masks as directed by chroot contents. "
            "This has the potential to be unsafe.")
    hostName          = (CfgString, 'localhost')
    verbose           = False

    def getAuthUrl(self):
        return None

    def getCommandSocketDir(self):
        return self.buildDir + '/tmp/'

    def getName(self):
        return '_local_'

    def getCacheDir(self):
        return self.buildDir + '/cscache'

    def getChrootDir(self):
        return self.buildDir + '/chroots'

    def getChrootArchiveDir(self):
        return self.buildDir + '/archive'

    def getBuildLogDir(self, jobId=None):
        if jobId:
            return self.logDir + '/buildlogs/%d/' % jobId
        return self.logDir + '/buildlogs/'

    def getBuildLogPath(self, jobId):
        return self.logDir + '/buildlogs/%d.log' % jobId

    def getChrootHelper(self):
        return self.helperDir + '/chroothelper'

    def getChrootCache(self):
        if not self.chrootCache:
            return None
        elif self.chrootCache[0] == 'local':
            return chrootcache.LocalChrootCache(self.chrootCache[1])
        else:
            raise errors.RmakeError('unknown chroot cache type of "%s" specified' %self.chrootCache[0])

    def _getChrootCacheDir(self):
        if not self.chrootCache:
            return None
        elif self.chrootCache[0] == 'local':
            return self.chrootCache[1]
        return None

    def _checkDir(self, name, path, requiredOwner=None,
                   requiredMode=None):
        if not os.path.exists(path):
            raise errors.RmakeError('%s does not exist, expected at %s - cannot start server' % (name, path))
            sys.exit(1)
        if not (requiredOwner or requiredMode):
            return
        statInfo = os.stat(path)
        if requiredMode and statInfo.st_mode & 0777 != requiredMode:
            raise errors.RmakeError('%s (%s) must have mode %o' % (path, name, requiredMode))
        if requiredOwner:
            ownerName = pwd.getpwuid(statInfo.st_uid).pw_name
            if ownerName != requiredOwner:
                raise errors.RmakeError('%s (%s) must have owner %s' % (
                                            path, name, requiredOwner))


    def checkBuildSanity(self):
        rmakeUser = constants.rmakeUser
        if pwd.getpwuid(os.getuid()).pw_name == rmakeUser:
            self._checkDir('buildDir', self.buildDir)
            self._checkDir('chroot dir (subdirectory of buildDir)',
                            self.getChrootDir(),
                            rmakeUser, 0700)
            self._checkDir('chroot archive dir (subdirectory of buildDir)',
                            self.getChrootArchiveDir(),
                            rmakeUser, 0700)
            chrootCacheDir = self._getChrootCacheDir()
            if chrootCacheDir:
                self._checkDir('chroot cache dir (subdirectory of buildDir)',
                               chrootCacheDir, rmakeUser, 0700)

class NodeConfiguration(rMakeBuilderConfiguration):
    useTmpfs          = (CfgBool, False)

    def __init__(self, readConfigFiles = False, ignoreErrors = False):
        self.setIgnoreErrors(ignoreErrors)
        rMakeBuilderConfiguration.__init__(self)

        if readConfigFiles:
            self.readFiles()
        if not self.hostName:
            self.hostName = socket.getfqdn()

    def getName(self):
        return self.name

    def readFiles(self):
        # we often start the node in /etc/rmake, which makes it read its
        # default configuration file twice if we don't dedup.  This is
        # relatively harmless but does lead to duplicate entries in the 
        # buildFlavors list.
        readPaths = []
        for path in ['/etc/rmake/noderc', 'noderc']:
            if os.path.realpath(path) not in readPaths:
                self.read(path, False)
                readPaths.append(os.path.realpath(path))

    def sanityCheck(self):
        pass
