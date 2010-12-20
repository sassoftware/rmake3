#
# Copyright (c) 2010 rPath, Inc.
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
Local configuration for rMake.

The information held in this configuration object should be all the required 
local setup needed to use rMake.
"""
import os
import pwd
import socket
import sys
import subprocess
import urllib

from conary import dbstore
from conary.lib import log, cfg, util
from conary.lib.cfgtypes import CfgPath, CfgString, CfgInt
from conary.lib.cfgtypes import CfgBool, CfgPathList, CfgDict, ParseError
from conary.conarycfg import CfgUserInfo

from rmake import constants
from rmake import errors
from rmake.lib import daemon, chrootcache


class CfgChrootCache(cfg.CfgType):
    def parseString(self, str):
        s = str.split()
        if len(s) != 2:
            raise ParseError("chroot cache type and path expected")
        return tuple(s)

    def format(self, val, displayOptions = None):
        return "%s %s" % val


class CfgPortRange(cfg.CfgType):

    def parseString(self, val):
        parts = val.replace('-', ' ').split()
        if len(parts) == 1:
            raise ParseError("Expected two port numbers for range")
        start, end = parts
        try:
            start = int(start)
            end = int(end)
        except ValueError:
            raise ParseError("Port is not a number")
        if not 1024 < start < 65535:
            raise ParseError("Starting port is out of range 1024-65535")
        if not 1024 < end < 65535:
            raise ParseError("Ending port is out of range 1024-65535")
        if end < start:
            start, end = end, start
        return (start, end)

    def format(self, val, displayOptions=None):
        return "%s %s" % val


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
    chrootCache       = CfgChrootCache
    chrootCaps        = (CfgBool, False,
            "Set capability masks as directed by chroot contents. "
            "This has the potential to be unsafe.")
    chrootServerPorts = (CfgPortRange, (63000, 64000),
            "Port range to be used for 'rmake chroot' sessions.")
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

class rMakeConfiguration(rMakeBuilderConfiguration):
    logDir            = (CfgPath, '/var/log/rmake')
    lockDir           = (CfgPath, '/var/run/rmake')
    serverDir         = (CfgPath, '/srv/rmake')
    proxyUrl          = (CfgString, 'http://LOCAL:7778') # local here means
                                                         # managed by rMake
    reposUrl          = (CfgString, 'http://LOCAL:7777')
    reposName         = socket.gethostname()
    sslCertPath       = (CfgPath, '/srv/rmake/certs/rmake-server-cert.pem')
    caCertPath        = CfgPath
    reposUser         = CfgUserInfo

    dbPath            = dbstore.CfgDriver

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
        if not self.dbPath:
            return ('sqlite', self.serverDir + '/jobs.db')
        else:
            return self.dbPath

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

    def getRepositoryUrl(self):
        return self.translateUrl(self.reposUrl)

    def translateUrl(self, url):
        type, host = urllib.splittype(url)
        host, rest = urllib.splithost(host)
        host, port = urllib.splitport(host)
        if host in ('LOCAL', 'localhost', ''):
            host = self.hostName
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

    def getSslCertificatePath(self):
        return self.sslCertPath

    def getCACertificatePath(self):
        return self.caCertPath

    def getSslCertificateGenerator(self):
        return self.helperDir + '/gen-cert.sh'

    def sanityCheck(self):
        pass

    def sanityCheckForStart(self):
        currUser = pwd.getpwuid(os.getuid()).pw_name
        cfgPaths = ['logDir', 'lockDir', 'serverDir']
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
            log.error("Could not access sslCert dir %s: %s" % os.path.dirname(self.sslCertPath), err)

        if self.caCertPath and not os.access(self.caCertPath, os.R_OK):
            log.error("Could not access client CA certificate file: %s",
                self.caCertPath)
            return 1

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
        genCertPath = self.getSslCertificateGenerator()
        if not os.access(genCertPath, os.X_OK):
            log.error("Unable to run %s to generate SSL certificate - "
                      "cannot start server" % genCertPath)
            return 1

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
