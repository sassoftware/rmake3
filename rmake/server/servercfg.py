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
import subprocess
import urllib

from conary.lib import log, cfg, util
from conary.lib.cfgtypes import CfgPath, CfgList, CfgString, CfgInt, CfgType
from conary.lib.cfgtypes import CfgBool, CfgPathList, CfgDict
from conary.conarycfg import CfgLabel, CfgUserInfo

from rmake import constants
from rmake import errors
from rmake.lib import daemon

class rMakeBuilderConfiguration(daemon.DaemonConfig):
    buildDir          = (CfgPath, '/var/rmake')
    helperDir         = (CfgPath, "/usr/libexec/rmake")
    slots             = (CfgInt, 1)
    useCache          = (CfgBool, False)
    useTmpfs          = (CfgBool, False)
    pluginDirs        = (CfgPathList, ['/usr/share/rmake/plugins'])
    usePlugins        = (CfgBool, True)
    usePlugin         = CfgDict(CfgBool)
    chrootLimit       = (CfgInt, 4)
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

    def getChrootHelper(self):
        return self.helperDir + '/chroothelper'

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
    proxyUrl          = (CfgString, 'http://LOCAL:7778') # local here means
                                                         # managed by rMake
    reposUrl          = (CfgString, 'http://LOCAL:7777')
    reposName         = socket.gethostname()
    sslCertPath       = (CfgPath, '/srv/rmake/certs/rmake-server-cert.pem')
    reposUser         = CfgUserInfo

    def __init__(self, readConfigFiles = False, ignoreErrors=False):
        daemon.DaemonConfig.__init__(self)
        self.setIgnoreErrors(ignoreErrors)
        self.addAlias('proxy', 'proxyUrl')
        self.addAlias('serverUrl', 'reposUrl')
        self.addAlias('serverName', 'reposName')
        self.addAlias('user',  'reposUser')
        if readConfigFiles:
            self.readFiles()


    def setServerName(self, serverName):
        for x in list(self.reposUser):
            if x[0] == self.reposName:
                self.reposUser.remove(x)
        if not self.reposUser.find(serverName):
            self.reposUser.addServerGlob(serverName, 'rmake', 'rmake')
        self.reposName = serverName

    def readFiles(self):
        for path in ['/etc/rmake/serverrc', 'serverrc']:
            self.read(path, False)

    def getServerUri(self):
        if not hasattr(self, 'rmakeUrl'):
            rmakeUrl = 'unix:///var/lib/rmake/socket'
        else:
            rmakeUrl = self.rmakeUrl
        if '://' in rmakeUrl:
            return rmakeUrl
        else:
            return 'unix://' + rmakeUrl

    def getSocketPath(self):
        rmakeUrl = self.getServerUri()
        type, rest = urllib.splittype(rmakeUrl)
        if type != 'unix':
            return None
        return os.path.normpath(rest)

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

    def getReposDbPath(self):
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
        url = self.translateUrl(self.reposUrl)
        return { self.reposName : url }

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

    def getUrlInfo(self, url):
        host = urllib.splithost(urllib.splittype(url)[1])[0]
        host, port = urllib.splitport(host)
        if port:
            port = int(port)
        return host, port

    def getProxyInfo(self):
        if not self.proxyUrl:
            return None
        return self.getUrlInfo(self.proxyUrl)

    def getReposInfo(self):
        if not self.reposUrl:
            return None
        return self.getUrlInfo(self.reposUrl)

    def isExternalProxy(self):
        return self.proxyUrl and self.getProxyInfo()[0] != 'LOCAL'

    def isExternalRepos(self):
        return self.getReposInfo()[0] != 'LOCAL'

    def getProxyUrl(self):
        if not self.proxyUrl:
            return None
        if self.isExternalProxy():
            return self.proxyUrl
        else:
            # need to have the proxy url be a fqdn so that it can
            # be used by rmake nodes
            return self.translateUrl(self.proxyUrl)

    def getUserGlobs(self):
        return self.reposUser

    def sanityCheck(self):
        currUser = pwd.getpwuid(os.getuid()).pw_name

    def getSslCertificatePath(self):
        return self.sslCertPath

    def getSslCertificateGenerator(self):
        return self.helperDir + '/gen-cert.sh'

    def sanityCheckForStart(self):
        cfgPaths = ['buildDir', 'logDir', 'lockDir', 'serverDir']
        socketPath = self.getSocketPath()
        if socketPath:
            if not os.access(os.path.dirname(socketPath), os.W_OK):
                log.error('cannot write to socketPath directory at %s - cannot start server' % os.path.dirname(socketPath))
                sys.exit(1)

        ret = self._sanityCheckForSSL()
        if ret:
            sys.exit(ret)

        cfgPaths = ['buildDir', 'logDir', 'lockDir', 'serverDir']
        for path in cfgPaths:
            if not os.path.exists(self[path]):
                log.error('%s does not exist, expected at %s - cannot start server' % (path, self[path]))
                sys.exit(1)
            if not os.access(self[path], os.W_OK):
                log.error('user "%s" cannot write to %s at %s - cannot start server' % (currUser, path, self[path]))
                sys.exit(1)

    def reposRequiresSsl(self):
        return urllib.splittype(self.reposUrl)[0] == 'https'

    def proxyRequiresSsl(self):
        return (self.proxyUrl
                and urllib.splittype(self.proxyUrl)[0] == 'https')

    def requiresSsl(self):
        """
            Return True if any service run by rMake requires ssl certificates
        """
        return ((not self.isExternalRepos() and self.reposRequiresSsl())
                or (not self.isExternalProxy() and self.proxyRequiresSsl())
                or urllib.splittype(self.getServerUri())[0] == 'https')

    def _sanityCheckForSSL(self):
        """Check SSL settings, create SSL certificate if missing.
        Returns 0 if everything is OK, or an exit code otherwise"""
        if not self.requiresSsl():
            return 0

        if not self.sslCertPath:
            log.error("sslCertPath to be set - cannot start server")
            return 1
        try:
            util.mkdirChain(os.path.dirname(self.sslCertPath))
        except OSError, err:
            log.error("Could not access sslCerti dir %s: %s" % os.path.dirname(self.sslCertPath), err)

        return self.makeCertificate()

    def makeCertificate(self):
        certfiles = set([self.getSslCertificatePath()])
        missing = [ x for x in certfiles if not os.access(x, os.R_OK) ]
        if not missing:
            return 0

        # At least one of the certificates doesn't exist, let's recreate them
        # both
        if not self.getSslCertificateGenerator():
            log.error("sslGenCertPath is not set - "
                      "cannot start server")
            return 1
        if not os.access(self.getSslCertificateGenerator(), os.X_OK):
            log.error("Unable to run %s to generate SSL certificate - "
                      "cannot start server" % self.sslGenCertPath)
            return 1

        genCertPath = self.getSslCertificateGenerator()
        cmd = [ genCertPath ]
        certfname = certfiles.pop()
        util.mkdirChain(os.path.dirname(certfname))
        certf = open(certfname, "w+")
        p = subprocess.Popen(cmd, stdout=certf)
        p.communicate()
        if p.returncode:
            log.error("Error executing %s - cannot start server" % genCertPath)
            return p.returncode
        # Sanity check
        certf.seek(0)
        data = certf.read()
        certf.close()
        if not data:
            log.error("Invalid certificate produced - cannot start server")
            return 1
        if certfiles:
            certfname = certfiles.pop()
            open(certfname, "w+").write(data)
        return 0
