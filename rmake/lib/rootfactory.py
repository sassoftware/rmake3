#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import os
import shutil

#conary
from conary.lib import util, log

#rmake
from rmake import errors

class AbstractChroot(object):
    """
        Abstract Chroot.  A Chroot instance manages the creation and removal
        of a chroot on the file system by copying in and installing files.

        The AbstractChroot records a set of commands to be used to create
        that chroot.
    """

    def __init__(self):
        self.mounts = {}
        self.filesToCopy = []
        self.dirsToCopy = []
        self.dirsToAdd = []
        self.usersToSupport = []
        self.groupsToSupport = []
        self.devNodes = []

    def create(self, root):
        """
            Actually instantiate this root on the file system.
        """
        raise NotImplementedError

    def clean(self, root, raiseError=True):
        """
            Removes this root or any files in teh way of this root.
        """
        raise NotImplementedError

    def addMount(self, fromDir, toDir, type):
        """
            Creates a mount point.  Other versions may actually
            run a mount command for this mount point.
        """
        # NOTE: we don't actually manage mount points any more.
        # This funtion is left in place to help document what the chroothelper
        # does.
        self.addDir(toDir, mode=0755)

    def addDir(self, directory, mode=0755, uid=0, gid=0):
        """
            Adds directory to be created when root is instantiated
        """
        self.dirsToAdd.append((directory, mode, uid, gid))

    def copyDir(self, sourceDir, targetDir=None):
        """
            Adds directory to be copied in when root is instantiated
        """
        if targetDir is None:
            targetDir = sourceDir
        self.dirsToCopy.append((sourceDir, targetDir))

    def copyFile(self, sourceFile, targetFile=None, mode=None):
        """
            Adds file to be copied in when root is instantiated
        """
        if targetFile is None:
            targetFile = sourceFile
        self.filesToCopy.append((sourceFile, targetFile, mode))

    def addUser(self, name, uid, gid=None, home=None, shell='/bin/bash'):
        """
            Adds user that must be in /etc/passwd when root is instantiated
        """
        if gid is None:
            gid = uid
        if gid == uid:
            self.groupsToSupport.append((name, gid, []))
        if home is None:
            home = '/home/%s' % name
        log.debug("adding user %s (%s,%s) home=%s", name, uid, gid, home)
        self.usersToSupport.append((name, uid, gid, home, shell))

    def addDeviceNode(self, path):
        """
            Adds device node that should be created when root is instantiated
        """
        self.devNodes.append(path)


class BasicChroot(AbstractChroot):
    """
        The root instance manages a root environment, creating and installing
        the necessary files for the root to be usuable, and cleaning up
        after itself as much as possible.

        The BasicChroot has an implementation of the create and clean 
        commands which actually manipulate the chroot.

        However, the main means of installing packages into the chroot is
        left blank - the install method.
    """
    def create(self, root):
        assert(root and root[0] == '/' and root != "/")
        self.root = root
        self.install()
        self._createDirs()
        self._copyFiles()
        self._copyDirs()
        self._supportGroups()
        self._supportUsers()
        self._addDeviceNodes()
        self._postInstall()

    def clean(self, root, raiseError=True):
        pass

    def install(self):
        """
            Hook for actually creating the chroot.
        """
        pass

    def _createDirs(self):
        for dir, mode, uid, gid in self.dirsToAdd:
            dir = self.root + dir
            log.debug("creating chroot:%s", dir)
            util.mkdirChain(dir)
            if mode:
                os.chmod(dir, mode)
            if (uid or gid) and not os.getuid():
                os.chown(dir, uid, gid)

    def _copyFiles(self):
        for (sourceFile, targetFile, mode) in self.filesToCopy:
            log.debug("copying file %s into chroot:%s", sourceFile, targetFile)
            try:
                target = self.root + targetFile
                target = os.path.realpath(target)
                util.mkdirChain(os.path.dirname(target))
                shutil.copy(sourceFile, target)
                if mode is not None:
                    os.chmod(target, mode)
            except (IOError, OSError), e:
                raise errors.OpenError(
                    'Could not copy in file %s to %s: %s' % (sourceFile, 
                                                             targetFile, e))


    def _copyDirs(self):
        for (sourceDir, targetDir) in self.dirsToCopy:
            targetDir = self.root + targetDir
            if os.path.exists(targetDir):
                if os.path.islink(targetDir):
                    os.unlink(targetDir)
                else:
                    util.rmtree(targetDir)

            util.mkdirChain(os.path.realpath(os.path.dirname(targetDir)))
            log.debug("copying dir %s into chroot:%s", sourceDir, targetDir)
            try:
                shutil.copytree(sourceDir, targetDir)
            except shutil.Error, e:
                errorList = '\n'.join('cannot copy %s to %s: %s' % x 
                                    for x in e.args[0])
                raise errors.OpenError(
                'Could not copy in directory %s:\n%s' % (sourceDir, errorList))

    def _supportGroups(self):
        if not self.groupsToSupport:
            return

        groupFile = self.root + '/etc/group'
        assert(os.path.exists(groupFile))
        names = []
        newGroupLines = []

        for (name, gid, users) in self.groupsToSupport:
            newLine = ':'.join((name, 'x', str(gid), ','.join(users) + '\n'))
            names.append(name)
            newGroupLines.append(newLine)

        groupLines = [ x for x in open(groupFile).readlines() 
                       if x.split(':', 1) not in names ] 
        groupLines.extend(newGroupLines)
        open(groupFile, 'w').write(''.join(groupLines))

    def _supportUsers(self):
        if not self.usersToSupport:
            return

        passwdFile = self.root + '/etc/passwd'
        assert(os.path.exists(passwdFile))

        names = []
        newPasswdLines = []
        newShadowLines = []

        for (name, uid, gid, home, shell) in self.usersToSupport:
            newLine = ':'.join((name, 'x', str(uid), str(gid), '', home, shell + '\n'))
            newShadow = ':'.join((name, '*', str(uid), '0', '99999', '7', '', '', '\n'))
            newShadowLines.append(':'.join(newShadow))
            newPasswdLines.append(newLine)

        passwdLines = [ x for x in open(passwdFile).readlines()
                        if x.split(':', 1) not in names ]
        passwdLines.extend(x + '\n' for x in newPasswdLines)
        open(passwdFile, 'w').write(''.join(passwdLines))

        shadowFile = self.root + '/etc/shadow'
        if os.path.exists(shadowFile) and not os.getuid():
            shadowLines = [ x for x in open(shadowFile).readlines() 
                            if x.split(':', 1) not in names ] 
            shadowLines.extend(newShadowLines)
            open(shadowFile, 'w').write(''.join(shadowLines))

    def _addDeviceNodes(self):
        if os.getuid(): # can only make device nodes as root
            util.mkdirChain('%s/dev' % self.root)
            return

        for devNode in self.devNodes:
            os.system("/sbin/MAKEDEV -d %s/dev/ -D /dev -x %s" % (self.root, devNode))


