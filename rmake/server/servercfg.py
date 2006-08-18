#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
"""
Local configuration for rMake.

The information held in this configuration object should be all the required 
local setup needed to use rMake.
"""
import os
import pwd
import socket
import stat
import sys

from conary.lib import log, cfg
from conary.lib.cfgtypes import CfgPath, CfgList, CfgString, CfgInt, CfgType
from conary.conarycfg import CfgLabel
from rmake.lib import daemon

class rMakeConfiguration(daemon.DaemonConfig):
    buildDir          = (CfgPath, '/var/rmake')
    chrootHelperPath  = (CfgPath, "/usr/libexec/rmake/chroothelper")
    logDir            = (CfgPath, '/var/log/rmake')
    lockDir           = (CfgPath, '/var/run/rmake')
    reposPassword     = 'rmake' # FIXME: we should not be storing this 
                                # information here!
    serverDir         = (CfgPath, '/srv/rmake')
    serverPort        = (CfgInt, 7777)
    serverName        = socket.getfqdn()
    socketPath        = (CfgPath, '/var/lib/rmake/socket')

    def __init__(self, readConfigFiles = True):
        daemon.DaemonConfig.__init__(self)
        self.readFiles()

    def readFiles(self):
        for path in ['/etc/rmake/serverrc', 'serverrc']:
            self.read(path, False)

    def getDbPath(self):
        return self.serverDir + '/jobs.db'

    def getDbContentsPath(self):
        return self.serverDir + '/jobcontents'

    def getContentsPath(self):
        return self.serverDir + '/repos/contents'

    def getReposDir(self):
        return self.serverDir + '/repos'

    def getReposPath(self):
        return self.serverDir + '/repos/sqldb'

    def getReposConfigPath(self):
        return self.serverDir + '/repos/serverrc'

    def getCachePath(self):
        return self.serverDir + '/repos/cachedb'

    def getReposLogPath(self):
        return self.logDir + '/repos.log'

    def getRepositoryMap(self):
        return { self.serverName :
                 'http://localhost:%s/conary/' % (self.serverPort) }

    def getBuildLogDir(self):
        return self.logDir + '/buildlogs/'

    def getBuildLogPath(self, jobId):
        return self.logDir + '/buildlogs/%d.log' % jobId

    def sanityCheck(self):
        currUser = pwd.getpwuid(os.getuid()).pw_name

        cfgPaths = ['buildDir', 'logDir', 'lockDir', 'serverDir']

        if os.path.exists(self.socketPath):
            cfgPaths.append('socketPath')
        elif not os.access(os.path.dirname(self.socketPath), os.W_OK):
            log.error('cannot write to socketPath directory at %s - cannot start server' % os.path.dirname(self.socketPath))
            sys.exit(1)
        for path in cfgPaths:
            if not os.path.exists(self[path]):
                log.error('%s does not exist, expected at %s - cannot start server' % (path, self[path]))
                sys.exit(1)
            if not os.access(self[path], os.W_OK):
                log.error('user "%s" cannot write to %s at %s - cannot start server' % (currUser, path, self[path]))
                sys.exit(1)
        if not (os.stat(self.buildDir)[stat.ST_MODE] & 07777) == 0700:
            log.error('buildDir at %s must be mode 0700 and owned by rmake.' % (self.buildDir))
            sys.exit(1)

