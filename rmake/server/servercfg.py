#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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
import urllib

from conary.lib import log, cfg
from conary.lib.cfgtypes import CfgPath, CfgList, CfgString, CfgInt, CfgType
from conary.lib.cfgtypes import CfgBool, CfgPathList, CfgDict
from conary.conarycfg import CfgLabel, CfgUserInfo

from rmake import constants
from rmake import errors
from rmake.lib import daemon

class rMakeBuilderConfiguration(daemon.DaemonConfig):
    buildDir          = (CfgPath, '/var/rmake')
    chrootHelperPath  = (CfgPath, "/usr/libexec/rmake/chroothelper")
    slots             = (CfgInt, 1)
    useCache          = (CfgBool, False)
    useTmpfs          = (CfgBool, False)
    pluginDirs        = (CfgPathList, ['/usr/share/rmake/plugins'])
    usePlugins        = (CfgBool, True)
    usePlugin         = CfgDict(CfgBool)
    verbose           = False

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
        rmakeUser = constants.rmakeuser
        if pwd.getpwuid(os.getuid()).pw_name == rmakeUser:
            self._checkDir('buildDir', self.buildDir)
            self._checkDir('chroot dir (subdirectory of buildDir)',
                            self.getChrootDir(),
                            rmakeUser, 0700)
            self._checkDir('chroot archive dir (subdirectory of buildDir)',
                            self.getChrootArchiveDir(),
                            rmakeUser, 0700)

class rMakeConfiguration(rMakeBuilderConfiguration):
    logDir            = (CfgPath, '/var/log/rmake')
    lockDir           = (CfgPath, '/var/run/rmake')
    serverDir         = (CfgPath, '/srv/rmake')
    serverUrl         = (CfgString, None)
    proxy             = (CfgString, 'http://LOCAL:7778') # local here means 
                                                         # managed by rMake
    serverPort        = (CfgInt, 7777)
    serverName        = socket.gethostname()
    socketPath        = (CfgPath, '/var/lib/rmake/socket')
    user              = CfgUserInfo

    def __init__(self, readConfigFiles = False, ignoreErrors=False):
        daemon.DaemonConfig.__init__(self)
        self.setIgnoreErrors(ignoreErrors)
        if readConfigFiles:
            self.readFiles()

        if not self.user and not self.isExternalRepos():
            self.user.addServerGlob(self.serverName, 'rmake', 'rmake')

    def setServerName(self, serverName):
        for x in list(self.user):
            if x[0] == self.serverName:
                self.user.remove(x)
        if not self.user.find(serverName):
            self.user.addServerGlob(serverName, 'rmake', 'rmake')
        self.serverName = serverName

    def readFiles(self):
        for path in ['/etc/rmake/serverrc', 'serverrc']:
            self.read(path, False)

    def isExternalRepos(self):
        return bool(self.serverUrl)

    def getServerUri(self):
        if '://' in self.socketPath:
            return self.socketPath
        else:
            return 'unix://' + self.socketPath

    def getDbPath(self):
        return self.serverDir + '/jobs.db'

    def getDbContentsPath(self):
        return self.serverDir + '/jobcontents'

    def getContentsPath(self):
        return self.serverDir + '/repos/contents'

    def getProxyDir(self):
        return self.serverDir + '/proxy'

    def getProxyContentsPath(self):
        return self.getProxyDir() + '/contents'

    def getProxyChangesetPath(self):
        return self.getProxyDir() + '/changesets'

    def getProxyPath(self):
        return self.getProxyDir() + '/sqldb'

    def getProxyConfigPath(self):
        return self.getProxyDir() + '/serverrc'

    def getProxyLogPath(self):
        return self.logDir + '/proxy.log'

    def getReposDir(self):
        return self.serverDir + '/repos'

    def getReposPath(self):
        return self.serverDir + '/repos/sqldb'

    def getReposConfigPath(self):
        return self.serverDir + '/repos/serverrc'

    def getReposCachePath(self):
        return self.serverDir + '/repos/cachedb'

    def getReposLogPath(self):
        return self.logDir + '/repos.log'

    def getProxyLogPath(self):
        return self.logDir + '/proxy.log'

    def getSubscriberLogPath(self):
        return self.logDir + '/subscriber.log'

    def getRepositoryMap(self):
        if self.isExternalRepos():
            url = self.translateUrl(self.serverUrl)
        else:
            url = 'http://%s:%s/conary/' % (socket.gethostname(),
                                            self.serverPort)
        return { self.serverName : url }

    def translateUrl(self, url):
        type, host = urllib.splittype(url)
        host, rest = urllib.splithost(host)
        host, port = urllib.splitport(host)
        if host in ('LOCAL', 'localhost', ''):
            host = socket.gethostname()
            if port:
                host = '%s:%s' % (host, port)
            return '%s://%s%s' % (type, host, rest)
        else:
            return url

    def getReposInfo(self):
        if not self.serverUrl:
            return None
        host = urllib.splithost(urllib.splittype(self.proxy)[1])[0]
        host, port = urllib.splitport(host)
        return host, port


    def getProxyInfo(self):
        if not self.proxy:
            return None
        host = urllib.splithost(urllib.splittype(self.proxy)[1])[0]
        host, port = urllib.splitport(host)
        return host, port

    def isExternalProxy(self):
        return self.proxy and self.getProxyInfo()[0] != 'LOCAL'

    def getProxyUrl(self):
        if not self.proxy:
            return None
        if self.isExternalProxy():
            return self.proxy
        else:
            # need to have the proxy url be a fqdn so that it can
            # be used by rmake nodes
            return self.translateUrl(self.proxy)

    def getUserGlobs(self):
        return self.user

    def sanityCheck(self):
        currUser = pwd.getpwuid(os.getuid()).pw_name

        if self.serverPort != self.getDefaultValue('serverPort'):
            if self.serverUrl:
                log.error('Cannot specify both serverPort and serverUrl')
                sys.exit(1)

    def sanityCheckForStart(self):
        cfgPaths = ['buildDir', 'logDir', 'lockDir', 'serverDir']
        if self.getServerUri().startswith('unix://'):
            if os.path.exists(self.socketPath):
                cfgPaths.append('socketPath')
            elif not os.access(os.path.dirname(self.socketPath), os.W_OK):
                log.error('cannot write to socketPath directory at %s - cannot start server' % os.path.dirname(self.socketPath))
                sys.exit(1)

        cfgPaths = ['buildDir', 'logDir', 'lockDir', 'serverDir']
        for path in cfgPaths:
            if not os.path.exists(self[path]):
                log.error('%s does not exist, expected at %s - cannot start server' % (path, self[path]))
                sys.exit(1)
            if not os.access(self[path], os.W_OK):
                log.error('user "%s" cannot write to %s at %s - cannot start server' % (currUser, path, self[path]))
                sys.exit(1)
