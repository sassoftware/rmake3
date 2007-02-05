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
    Creates chroots to be used for building.

    Uses the chroothelper program to do final processing and chrooting.
"""
import os
import pwd
import shutil
import sys

#conary
from conary import conarycfg
from conary import conaryclient
from conary import callbacks
from conary.deps import deps
from conary.lib import util, log

#rmake
from rmake import constants
from rmake import errors
from rmake.lib import rootfactory

class ConaryBasedChroot(rootfactory.BasicChroot):
    """ 
        The root manages a root environment, creating and installing
        the necessary files for the root to be usuable, and cleaning up
        after itself as much as possible.
    """
    def __init__(self, jobList, logger, cfg, csCache=None):
        rootfactory.BasicChroot.__init__(self)
        self.cfg = cfg
        self.jobList = jobList
        self.callback = None
        self.logger = logger
        self.csCache = csCache

        self.addDir('/tmp', mode=01777)
        self.addDir('/var/tmp', mode=01777)
        self.addDir('/etc')
        self.addDir('/etc/rmake')
        self.addDir('/etc/conary')
        self.addDir(self.cfg.tmpDir, mode=01777)

    def install(self):
        if not self.jobList:
            # should only be true in debugging situations
            return
        assert(self.cfg.root == self.root)
        client = conaryclient.ConaryClient(self.cfg)
        client.setUpdateCallback(self.callback)

        if self.csCache:
            changeSetList = self.csCache.getChangeSets(client.getRepos(),
                                                       self.jobList,
                                                       callback=self.callback)
        else:
            changeSetList = []

        self.logger.info('Troves To Install:')
        self.logger.info('\n    '.join('%s=%s[%s]' % (x[0], x[2][0], x[2][1])
                               for x in sorted(self.jobList)))

        updJob, suggMap = client.updateChangeSet(
            self.jobList, keepExisting=False, resolveDeps=False,
            recurse=False, checkPathConflicts=False,
            fromChangesets=changeSetList,
            migrate=True)
        util.mkdirChain(self.cfg.root + '/root')
        client.applyUpdate(updJob, replaceFiles=True,
                           tagScript=self.cfg.root + '/root/tagscripts')


    def _copyInConary(self):
        conaryDir = os.path.dirname(sys.modules['conary'].__file__)
        self.copyDir(conaryDir)
        self.copyDir(conaryDir,
                     '/usr/lib/python2.4/site-packages/conary')
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

class rMakeChroot(ConaryBasedChroot):

    def __init__(self, buildTrove, chrootHelperPath, cfg, serverCfg,
                 jobList, logger, uid=None, gid=None, csCache=None,
                 copyInConary=True):
        """ 
            uid/gid:  the uid/gid which special files in the chroot should be 
                      owned by
        """
        ConaryBasedChroot.__init__(self, jobList, logger, cfg, csCache)

        self.jobId = buildTrove.jobId
        self.buildTrove = buildTrove
        self.chrootHelperPath = chrootHelperPath
        self.serverCfg = serverCfg
        self.callback = ChrootCallback(self.buildTrove, logger)

        if copyInConary:
            self._copyInConary()
        self._copyInRmake()
        self._cacheBuildFiles()

    def getRoot(self):
        return self.cfg.root

    def install(self):
        self.logger.info('Creating chroot')
        ConaryBasedChroot.install(self)
        # copy in the tarball files needed for building this package from
        # the cache.
        self._cacheBuildFiles()

    def _cacheBuildFiles(self):
        client = conaryclient.ConaryClient(self.cfg)
        sourceTup = self.buildTrove.getNameVersionFlavor()
        sourceTup = (sourceTup[0], sourceTup[1], deps.parseFlavor(''))
        trv = self.csCache.getTroves(client.getRepos(), [sourceTup],
                                     withFiles=True)[0]
        allFiles = list(trv.iterFileList())
        fileContents = [(x[2], x[3]) for x in allFiles]
        oldRootLen = len(self.csCache.root)
        for path in self.csCache.getFileContentsPaths(client.getRepos(),
                                                      fileContents):
            newPath = path[oldRootLen:]
            self.copyFile(path, '/var/rmake/cscache/' + newPath,
                          mode=0755)


    def _copyInRmake(self):
        # should this be controlled by strict mode too?
        rmakeDir = os.path.dirname(sys.modules['rmake'].__file__)
        self.copyDir(rmakeDir)
        # just copy to a standard path
        self.copyDir(rmakeDir, '/usr/share/rmake/rmake')
        self.copyDir(rmakeDir, '/usr/lib/python2.4/site-packages/rmake')

    def _postInstall(self):
        self.createConaryRc()

    def createConaryRc(self):
        conaryCfg = conarycfg.ConaryConfiguration(False)
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

    def canChroot(self):
        return (pwd.getpwnam(constants.rmakeuser).pw_uid == os.getuid())


    def unmount(self):
        if not os.path.exists(self.getRoot()):
            return
        if self.canChroot():
            self.logger.info('Running chroot helper to unmount...')
            util.mkdirChain(self.getRoot() + '/sbin')
            rc = os.system('%s --unmount %s' % (self.chrootHelperPath, 
                            self.getRoot()))
            if rc:
                raise errors.OpenError('Could not unmount old chroot')


    def clean(self):
        if self.canChroot():
            self.logger.info('Running chroot helper to clean/unmount...')
            util.mkdirChain(self.getRoot() + '/sbin')
            shutil.copy('/sbin/busybox', self.getRoot() + '/sbin/busybox')
            rc = os.system('%s %s --clean' % (self.chrootHelperPath,
                            self.getRoot()))
            if rc:
                raise errors.OpenError(
                        'Cannot create chroot - chroot helper failed'
                        ' to clean old chroot')

        self.logger.debug("removing old chroot tree: %s", self.getRoot())
        os.system('rm -rf %s/tmp' % self.getRoot())
        removeFailed = False
        if os.path.exists(self.getRoot() + '/tmp'):
            # attempt to remove just the /tmp dir first.
            # that's where the chroot process should have had all
            # of its files.  Doing this makes sure we don't remove
            # /bin/rm while it might still be needed the next time around.
            removeFailed = True
        else:
            os.system('rm -rf %s' % self.getRoot())
            if os.path.exists(self.getRoot()):
                removeFailed = True
        if removeFailed:
            raise errors.OpenError(
                'Cannot create chroot - old root at %s could not be removed.'
                '  This may happen due to permissions problems such as root'
                ' owned files, or earlier build processes that have not'
                ' completely died.  Please shut down rmake, kill any remaining'
                ' rmake processes, and then retry.  If that does not work,'
                ' please remove the old root by hand.' % self.getRoot())

class FakeRmakeRoot(rMakeChroot):
    def canChroot(self):
        return False

    def clean(self):
        pass

class ExistingChroot(rMakeChroot):
    def __init__(self, rootPath, logger, chrootHelperPath):
        self.root = rootPath
        self.logger = logger
        self.chrootHelperPath = chrootHelperPath
        rootfactory.BasicChroot.__init__(self)
        self._copyInRmake()

    def create(self, root):
        rootfactory.BasicChroot.create(self, root)

    def install(self):
        pass

    def getRoot(self):
        return self.root

    def clean(self):
        pass

    def _postInstall(self):
        pass

class FullRmakeChroot(rMakeChroot):
    """
        This chroot contains everything needed to start the rMake chroot.
    """

    def __init__(self, *args, **kw):
        rMakeChroot.__init__(self, *args, **kw)
        self.addMount('/proc', '/proc', type='proc')
        self.addMount('/dev/pts', '/dev/pts', type='devpts')
        self.addDeviceNode('urandom') # needed for ssl and signing
        self.addDeviceNode('ptmx') # needed for pty use

        self.copyFile('/etc/hosts')
        self.copyFile('/etc/resolv.conf')

        # make time outputs accurate
        if os.path.exists('/etc/localtime'):
            self.copyFile('/etc/localtime')
        if os.path.exists('/etc/nsswitch.conf'):
            self.copyFile('/etc/nsswitch.conf')

        # ********
        # NOTE:
        # We copy in local system files, including policy and use dirs,
        # in order to make the use of rmake as easy as possible.  If rMake
        # ever gets to the point where its use is distributed, we should 
        # no longer copy anything but required networking/system info 
        # from the host system, and instead generate or pass in this
        # information from the host system
        self.copyFile('/etc/passwd')
        self.copyFile('/etc/group')


        if not self.cfg.strictMode:
            for option in ['archDirs', 'mirrorDirs', 'policyDirs',
                           'siteConfigPath', 'useDirs']:
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
    def __init__(self, buildTrove, logger):
        callbacks.UpdateCallback.__init__(self)
        self.hunk = (0,0)
        self.buildTrove = buildTrove
        self.logger = logger

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
            n,v,f = job[0], job[2][0], job[2][1]
            v = '%s/%s' % (v.trailingLabel(), v.trailingRevision())
            archDeps = [x.name for x in f.iterDepsByClass(deps.InstructionSetDependency)]
            if archDeps:
                f = '[is: %s]' % ' '.join(archDeps)
            else:
                f = ''
            descriptions.append('%s=%s%s' % (n,v,f))
        if self.hunk[1] > 1:
            self._message("installing %d of %d:\n    %s" % \
                            (self.hunk[0], self.hunk[1],
                             '\n    '.join(descriptions)))
        else:
            self._message("installing: \n    %s" % \
                          ('\n    '.join(descriptions),))

    def downloadingChangeSet(self, got, need):
        if not self.showedHunk:
            # we display our message here because here we have the size...
            # but we only want to display the message once per changeset
            self._message("Caching changeset %s of %s (%sKb)" % (
                                            self.hunk + (need/1024 or 1,)))
            self.showedHunk = True

