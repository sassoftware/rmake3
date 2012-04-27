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
    Creates chroots to be used for building.

    Uses the chroothelper program to do final processing and chrooting.
"""

import grp
import itertools
import os
import pwd
import shutil
import sys
import stat

#conary
from conary import conarycfg
from conary import conaryclient
from conary import callbacks
from conary.deps import deps
from conary.lib import util, openpgpkey, sha1helper

#rmake
from rmake import errors
from rmake import compat
from rmake import constants
from rmake.lib import flavorutil
from rmake.lib import rootfactory

def _addModeBits(path, bits):
    s = os.lstat(path)
    if not stat.S_ISLNK(s.st_mode) and not (s.st_mode & bits == bits):
        os.chmod(path, stat.S_IMODE(s.st_mode) | bits)

class ConaryBasedChroot(rootfactory.BasicChroot):
    """ 
        The root manages a root environment, creating and installing
        the necessary files for the root to be usuable, and cleaning up
        after itself as much as possible.
    """
    def __init__(self, jobList, crossJobList, bootstrapJobList, logger, cfg,
            csCache=None, chrootCache=None, targetFlavor=None, oldRoot=None):
        rootfactory.BasicChroot.__init__(self)
        self.cfg = cfg
        self.jobList = jobList
        self.crossJobList = crossJobList
        self.bootstrapJobList = bootstrapJobList
        self.callback = None
        self.logger = logger
        self.csCache = csCache
        self.chrootCache = chrootCache
        self.chrootFingerprint = None
        self.oldRoot = oldRoot
        if targetFlavor is not None:
            cfg.initializeFlavors()
            self.sysroot = flavorutil.getSysRootPath(targetFlavor)
        self.rpmRoot = None

        self.addDir('/tmp', mode=01777)
        self.addDir('/var/tmp', mode=01777)
        self.addDir('/etc')
        self.addDir('/etc/rmake')
        self.addDir('/etc/conary')

        self.addDir(self.cfg.tmpDir, mode=01777)
        if self.crossJobList:
            self.addDir('%s/lib' % self.sysroot)
            self.addDir('%s/usr/lib' % self.sysroot)

    def moveOldRoot(self, oldRoot, newRoot):
        self.logger.info('Moving root from %s to %s for reuse' % (oldRoot,
                                                                  newRoot))
        if os.path.exists(newRoot):
            self.logger.warning('Root already exists at %s - cannot move old root to that spot')
            return False

        try:
            os.rename(oldRoot, newRoot)
        except OSError, err:
            self.logger.warning('Could not rename old root %s to %s: %s' % (oldRoot, newRoot, err))
            return False

        self.cfg.root = newRoot
        client = conaryclient.ConaryClient(self.cfg)
        try:
            assert(client.db.db.schemaVersion)
        except Exception, err:
            self.logger.warning('Could not access database in old root %s: %s.  Removing old root' % (oldRoot, err))
            os.rename(newRoot, oldRoot)
            return False
        return True

    def create(self, root):
        self.cfg.root = root
        rootfactory.BasicChroot.create(self, root)

    def install(self):
        self.cfg.root = self.root
        if self.oldRoot:
            if self.serverCfg.reuseChroots:
                self._moveOldRoot(self.oldRoot, self.root)
        if not self.jobList and not self.crossJobList:
            # should only be true in debugging situations
            return

        client = conaryclient.ConaryClient(self.cfg)
        repos = client.getRepos()
        if self.chrootCache and hasattr(repos, 'getChangeSetFingerprints'):
            self.chrootFingerprint = self._getChrootFingerprint(client)
            if self.chrootCache.hasChroot(self.chrootFingerprint):
                strFingerprint = sha1helper.sha1ToString(
                        self.chrootFingerprint)
                self.logger.info('restoring cached chroot with '
                        'fingerprint %s', strFingerprint)
                self.chrootCache.restore(self.chrootFingerprint, self.cfg.root)
                self.logger.info('chroot fingerprint %s '
                         'restore done', strFingerprint)
                return

        def _install(jobList):
            self.cfg.flavor = []
            openpgpkey.getKeyCache().setPublicPath(
                                     self.cfg.root + '/root/.gnupg/pubring.gpg')
            openpgpkey.getKeyCache().setPrivatePath(
                                self.cfg.root + '/root/.gnupg/secring.gpg')
            self.cfg.pubRing = [self.cfg.root + '/root/.gnupg/pubring.gpg']
            client = conaryclient.ConaryClient(self.cfg)
            client.setUpdateCallback(self.callback)
            if self.csCache:
                changeSetList = self.csCache.getChangeSets(client.getRepos(),
                                                           jobList,
                                                           callback=self.callback)
            else:
                changeSetList = []

            try:
                updJob, suggMap = client.updateChangeSet(
                    jobList, keepExisting=False, resolveDeps=False,
                    recurse=False, checkPathConflicts=False,
                    fromChangesets=changeSetList,
                    migrate=True)
            except conaryclient.update.NoNewTrovesError:
                # since we're migrating, this simply means there were no
                # operations to be performed
                pass
            else:
                util.mkdirChain(self.cfg.root + '/root')
                client.applyUpdate(updJob, replaceFiles=True,
                                   tagScript=self.cfg.root + '/root/tagscripts')

        self._installRPM()
        self._touchShadow()

        if self.bootstrapJobList:
            self.logger.info("Installing initial chroot bootstrap requirements")
            oldRoot = self.cfg.dbPath
            try:
                # Bootstrap troves are installed outside the system DB,
                # although it doesn't matter as much in trove builds as it does
                # in image builds.
                self.cfg.dbPath += '.bootstrap'
                _install(self.bootstrapJobList)
            finally:
                self.cfg.dbPath = oldRoot

        if self.jobList:
            self.logger.info("Installing chroot requirements")
            _install(self.jobList)

        if self.crossJobList:
            self.logger.info("Installing chroot cross-compile requirements")
            oldRoot = self.cfg.root
            try:
                self.cfg.root += self.sysroot
                _install(self.crossJobList)
            finally:
                self.cfg.root = oldRoot

        self._uninstallRPM()

        # directories must be traversable and files readable (RMK-1006)
        for root, dirs, files in os.walk(self.cfg.root, topdown=True):
            for directory in dirs:
                _addModeBits(os.sep.join((root, directory)), 05)
            for filename in files:
                _addModeBits(os.sep.join((root, filename)), 04)

        if self.chrootFingerprint:
            strFingerprint = sha1helper.sha1ToString(self.chrootFingerprint)
            self.logger.info('caching chroot with fingerprint %s',
                    strFingerprint)
            self.chrootCache.store(self.chrootFingerprint, self.cfg.root)
            self.logger.info('caching chroot %s done',
                    strFingerprint)

    def _copyInConary(self):
        conaryDir = os.path.dirname(sys.modules['conary'].__file__)
        self.copyDir(conaryDir)
        #self.copyDir(conaryDir,
        #             '/usr/lib/python2.4/site-packages/conary')
        #self.copyDir(conaryDir,
        #             '/usr/lib64/python2.4/site-packages/conary')
        self.copyDir(conaryDir,
                     '/usr/share/rmake/conary')
        if conaryDir.endswith('site-packages/conary'):
            self.copyFile('/usr/bin/conary')
            self.copyFile('/usr/bin/cvc')
        elif os.path.exists(os.path.join(conaryDir, '../commands')):
            commandDir = os.path.realpath(os.path.join(conaryDir,'../commands'))
            for fname in ['cvc', 'conary']:
                self.copyFile(os.path.join(commandDir, fname),
                              os.path.join('/usr/bin', fname))
            # Need to copy perlreqs.pl too
            scriptsDir = os.path.realpath(os.path.join(conaryDir,'../scripts'))
            if os.path.exists(scriptsDir):
                self.copyDir(scriptsDir)
                self.copyFile(os.path.join(scriptsDir, 'perlreqs.pl'),
                    '/usr/libexec/conary/perlreqs.pl')

    def _installRPM(self):
        """If needed, choose a version of RPM to use to install the chroot."""
        self._uninstallRPM()
        if not self.cfg.rpmRequirements:
            return

        ccfg = conarycfg.ConaryConfiguration(False)
        cli = conaryclient.ConaryClient(ccfg)

        # Find troves that provide the necessary RPM dep.
        found = cli.db.getTrovesWithProvides(self.cfg.rpmRequirements)
        tups = list(itertools.chain(*found.values()))
        if not tups:
            raise errors.ServerError("Could not locate a RPM trove meeting "
                    "one of these requirements:\n  %s"
                    % ("\n  ".join(str(x) for x in self.cfg.rpmRequirements)))

        # Search those troves for the python import root.
        targetRoot = '/python%s.%s/site-packages' % sys.version_info[:2]
        targetPaths = [ targetRoot + '/rpm/__init__.py',
                        targetRoot + '/rpmmodule.so' ]
        roots = set()
        for trove in cli.db.getTroves(tups, pristine=False):
            for pathId, path, fileId, fileVer in trove.iterFileList():
                for targetPath in targetPaths:
                    if path.endswith(targetPath):
                        root = path[:-len(targetPath)] + targetRoot
                        roots.add(root)

        # Insert into the search path and do a test import.
        if not roots:
            raise errors.ServerError("A required RPM trove was found but "
                    "did not contain a suitable python module "
                    "(expected python%s.%s)" % sys.version_info[:2])

        self.rpmRoot = sorted(roots)[0]
        self.logger.info("Using RPM in root %s", self.rpmRoot)
        sys.path.insert(0, self.rpmRoot)
        __import__('rpm')


    def _uninstallRPM(self):
        """Remove a previously-installed RPM from the python path and clear the
        module cache."""
        if self.rpmRoot:
            assert sys.path[0] == self.rpmRoot
            del sys.path[0]
            self.rpmRoot = None
        for name in sys.modules.keys():
            if name.split('.')[0] == 'rpm':
                del sys.modules[name]

    def _touchShadow(self):
        # Create shadow files with owner-writable permissions before RPM can
        # create them with no permissions. (RMK-1079)
        etc = os.path.join(self.root, 'etc')
        util.mkdirChain(etc)
        for name in (etc + '/shadow', etc + '/gshadow'):
            open(name, 'a').close()
            os.chmod(name, 0600)

    def _getChrootFingerprint(self, client):
        job = (sorted(self.jobList) + sorted(self.crossJobList) +
                sorted(self.bootstrapJobList))
        fingerprints = client.repos.getChangeSetFingerprints(job,
                recurse=False, withFiles=True, withFileContents=True,
                excludeAutoSource=True, mirrorMode=False)

        a = len(self.jobList)
        b = a + len(self.crossJobList)

        # Make backwards-compatible chroot fingerprints by only appending more
        # info if it is set.

        # version 1 or later fingerprint
        blob = ''.join(fingerprints[:a])  # jobList
        if (self.crossJobList or self.bootstrapJobList or
                self.cfg.rpmRequirements):
            # version 2 or later fingerprint
            blob += '\n'
            blob += ''.join(fingerprints[a:b]) + '\n'  # crossJobList
            blob += ''.join(fingerprints[b:]) + '\n'  # bootstrapJobList
            blob += '\t'.join(str(x) for x in self.cfg.rpmRequirements) + '\n'
        return sha1helper.sha1String(blob)

    def invalidateCachedChroot(self):
        """Destroy a cached chroot archive associated with this chroot."""
        if self.chrootFingerprint:
            self.logger.warning("Removing cached chroot with fingerprint %s",
                    sha1helper.sha1ToString(self.chrootFingerprint))
            self.chrootCache.remove(self.chrootFingerprint)


class rMakeChroot(ConaryBasedChroot):

    def __init__(self,
            buildTrove,
            chrootHelperPath,
            cfg,
            serverCfg,
            jobList,
            crossJobList,
            bootstrapJobList,
            logger,
            uid=None,
            gid=None,
            csCache=None,
            chrootCache=None,
            copyInConary=True,
            oldRoot=None,
            ):
        """ 
            uid/gid:  the uid/gid which special files in the chroot should be 
                      owned by
        """
        ConaryBasedChroot.__init__(self,
                jobList,
                crossJobList,
                bootstrapJobList,
                logger,
                cfg,
                csCache,
                chrootCache,
                buildTrove.getFlavor(),
                oldRoot=None,
                )
        self.jobId = buildTrove.jobId
        self.buildTrove = buildTrove
        self.chrootHelperPath = chrootHelperPath
        self.serverCfg = serverCfg
        self.callback = ChrootCallback(self.buildTrove, logger,
                                       caching=bool(csCache))
        self.copyInConary = copyInConary

        if copyInConary:
            self._copyInConary()
            for dir in self.cfg.policyDirs:
                if os.path.exists(dir):
                    self.copyDir(dir)
        self._copyInRmake()

    def getRoot(self):
        return self.cfg.root

    def checkSanity(self):
        if self.copyInConary:
            # we're just overriding the version of conary used
            # as long as that't the only sanity check we can return 
            # immediately
            return
        for job in self.jobList:
            if job[0] == 'conary:python':
                version = job[2][0].trailingRevision().getVersion()
                try:
                    compat.ConaryVersion(version).checkRequiredVersion()
                except errors.RmakeError, error:
                    errorMsg = str(error) + (' - tried to install version %s in chroot' % version)
                    raise error.__class__(errorMsg)

    def useStandardRoot(self):
        return True

    def install(self):
        self.logger.info('Creating chroot')
        ConaryBasedChroot.install(self)
        # copy in the tarball files needed for building this package from
        # the cache.
        self._cacheBuildFiles()

    def _cacheBuildFiles(self):
        if not self.csCache:
            return
        client = conaryclient.ConaryClient(self.cfg)
        sourceTup = self.buildTrove.getNameVersionFlavor()
        sourceTup = (sourceTup[0], sourceTup[1], deps.parseFlavor(''))
        trv = self.csCache.getTroves(client.getRepos(), [sourceTup],
                                     withFiles=True)[0]
        allFiles = list(trv.iterFileList())
        fileContents = [(x[2], x[3]) for x in allFiles]
        oldRootLen = len(self.csCache.root)
        if fileContents:
            self.logger.info('Caching %s files' % len(fileContents))
            for path in self.csCache.getFileContentsPaths(client.getRepos(),
                                                          fileContents):
                newPath = path[oldRootLen:]
                self.copyFile(path, '/tmp/cscache/' + newPath,
                              mode=0755)


    def _copyInRmake(self):
        # should this be controlled by strict mode too?
        rmakeDir = os.path.dirname(sys.modules['rmake'].__file__)
        # don't copy in rmake into /usr/lib/python2.4/site-packages
        # as its important that we don't muck with the standard file 
        # system location for some test runs of rmake inside of rmake
        #self.copyDir(rmakeDir)
        # just copy to a standard path
        self.copyDir(rmakeDir, '/usr/share/rmake/rmake')

    def _postInstall(self):
        self.createConaryRc()
        self.createRmakeUsers()

    def createConaryRc(self):
        conaryrc = None
        try:
            if self.canChroot(): # then we will be chrooting into this dir
                conaryrc = open('%s/etc/conaryrc.prechroot' % self.cfg.root, 'w')
                oldroot = self.cfg.root
                self.cfg.root = '/'
                try:
                    self.cfg.storeConaryCfg(conaryrc)
                finally:
                    self.cfg.root = oldroot
            else:
                conaryrc = open('%s/etc/conaryrc.rmake' % self.cfg.root, 'w')
                self.cfg.storeConaryCfg(conaryrc)
        except Exception, msg:
            self.logger.error("Error writing conaryrc: %s", msg)
        conaryrc.close()

    def createRmakeUsers(self):
        """Copy passwd/group entries for rmake and rmake-chroot into the chroot.
        """
        passwd = open(os.path.join(self.cfg.root, 'etc/passwd'), 'a')
        group = open(os.path.join(self.cfg.root, 'etc/group'), 'a')
        for name in (constants.rmakeUser, constants.chrootUser):
            pwdata = pwd.getpwnam(name)
            print >> passwd, ":".join(str(x) for x in pwdata)
            grpdata = grp.getgrgid(pwdata.pw_gid)
            print >> group, ":".join(str(x) for x in grpdata)

    def canChroot(self):
        return (pwd.getpwnam(constants.rmakeUser).pw_uid == os.getuid())


    def unmount(self, root, raiseError=True):
        if not os.path.exists(root):
            return True
        if self.canChroot():
            self.logger.info('Running chroot helper to unmount...')
            util.mkdirChain(root + '/sbin')
            rc = os.system('%s --unmount %s' % (self.chrootHelperPath, root))
            if rc:
                if raiseError:
                    raise errors.ServerError('Could not unmount old chroot')
                return False
        return True


    def clean(self, root, raiseError=True):
        if self.canChroot():
            self.logger.info('Running chroot helper to clean/unmount...')
            util.mkdirChain(root + '/sbin')
            shutil.copy('/sbin/busybox', root + '/sbin/busybox')
            rc = os.system('%s %s --clean' % (self.chrootHelperPath, root))
            if rc:
                if raiseError:
                    raise errors.ServerError(
                            'Cannot create chroot - chroot helper failed'
                            ' to clean old chroot')
                else:
                    return False
        self.logger.debug("removing old chroot tree: %s", root)
        # First, remove the conary database
        try:
            os.unlink(util.joinPaths(root, '/var/lib/conarydb/conarydb'))
        except OSError:
            pass
        # attempt to remove just the /tmp dir first.
        # that's where the chroot process should have had all
        # of its files.  Doing this makes sure we don't remove
        # /bin/rm while it might still be needed the next time around.
        os.system('rm -rf %s/tmp' % root)
        removeFailed = False
        if os.path.exists(root + '/tmp'):
            removeFailed = True
        else:
            os.system('rm -rf %s' % root)
            if os.path.exists(root):
                removeFailed = True
        if removeFailed and raiseError:
            raise errors.ServerError(
                'Cannot create chroot - old root at %s could not be removed.'
                '  This may happen due to permissions problems such as root'
                ' owned files, or earlier build processes that have not'
                ' completely died.  Please shut down rmake, kill any remaining'
                ' rmake processes, and then retry.  If that does not work,'
                ' please remove the old root by hand.' % root)
        return not removeFailed


class ExistingChroot(rMakeChroot):
    def __init__(self, rootPath, logger, chrootHelperPath):
        self.root = rootPath
        self.logger = logger
        self.chrootHelperPath = chrootHelperPath
        self.chrootFingerprint = None
        rootfactory.BasicChroot.__init__(self)
        self._copyInRmake()

    def create(self, root):
        rootfactory.BasicChroot.create(self, root)

    def install(self):
        pass

    def getRoot(self):
        return self.root

    def _postInstall(self):
        pass

    def checkSanity(self):
        pass

class FullRmakeChroot(rMakeChroot):
    """
        This chroot contains everything needed to start the rMake chroot.
    """

    def __init__(self, *args, **kw):
        rMakeChroot.__init__(self, *args, **kw)
        self.addMount('/proc', '/proc', type='proc')
        self.addMount('/dev/pts', '/dev/pts', type='devpts')
        self.addMount('tmpfs', '/dev/shm', type='tmpfs')
        self.addDeviceNode('urandom') # needed for ssl and signing
        self.addDeviceNode('ptmx') # needed for pty use

        self.copyFile('/etc/hosts')
        self.copyFile('/etc/resolv.conf')

        # make time outputs accurate
        if os.path.exists('/etc/localtime'):
            self.copyFile('/etc/localtime')
        # glibc:runtime should provide a good default nsswitch
        if os.path.exists('/etc/nsswitch.conf'):
            self.copyFile('/etc/nsswitch.conf')

        if self.cfg.copyInConfig:
            for option in ['archDirs', 'mirrorDirs',
                           'siteConfigPath', 'useDirs', 'componentDirs']:
                for dir in self.cfg[option]:
                    if os.path.exists(dir):
                        self.copyDir(dir)
            for option in ['defaultMacros']:
                for path in self.cfg[option]:
                    if os.path.exists(path):
                        self.copyFile(path)

class ChrootCallback(callbacks.UpdateCallback):
    """
        Callback to update trove log as the chroot is created.
        @param buildTrove: trove we're creating a chroot for
        @type: build.buildtrove.BuildTrove
    """
    def __init__(self, buildTrove, logger, caching=True):
        callbacks.UpdateCallback.__init__(self)
        self.hunk = (0,0)
        self.buildTrove = buildTrove
        self.logger = logger
        self.showedHunk = False
        self.caching = caching

    def _message(self, text):
        self.buildTrove.log(text)

    def setChangesetHunk(self, num, total):
        self.showedHunk = False
        self.hunk = (num, total)

    def setUpdateHunk(self, num, total):
        self.hunk = (num, total)

    def setUpdateJob(self, jobs):
        descriptions = []
        jobs.sort()
        for job in jobs:
            if job[2][0]:
                n,v,f = job[0], job[2][0], job[2][1]
            else:
                n,v,f = job[0], job[1][0], job[1][1]
            
            v = '%s/%s' % (v.trailingLabel(), v.trailingRevision())
            archDeps = [x.name for x in f.iterDepsByClass(deps.InstructionSetDependency)]
            if archDeps:
                f = '[is: %s]' % ' '.join(archDeps)
            else:
                f = ''
            if job[2][0]:
                action = ''
            else:
                action = 'Erase '
            descriptions.append('%s%s=%s%s' % (action, n,v,f))
        if self.hunk[1] > 1:
            self._message("installing %d of %d:\n    %s" % \
                            (self.hunk[0], self.hunk[1],
                             '\n    '.join(descriptions)))
        else:
            self._message("installing: \n    %s" % \
                          ('\n    '.join(descriptions),))

    def downloadingChangeSet(self, got, need):
        if self.caching and not self.showedHunk:
            # we display our message here because here we have the size...
            # but we only want to display the message once per changeset
            self._message("Caching changeset %s of %s (%sKb)" % (
                                            self.hunk + (need/1024 or 1,)))
            self.showedHunk = True
