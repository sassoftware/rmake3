#
# Copyright (c) 2008 rPath, Inc.  All Rights Reserved.
#
"""
Cache of chroots.
"""

import os
import subprocess

from conary.lib import sha1helper, util
sha1ToString = sha1helper.sha1ToString

class ChrootCacheInterface(object):
    """
    ChrootCacheInterface defines the standard interface for a chroot
    cache.  It should never be instantiated.
    """
    def store(self, chrootFingerprint, root):
        """
        Store the chroot currently located at C{root} in the
        filesystem using the given chroot fingerprint.

        @param chrootFingerprint: The fingerprint (a SHA1 sum) to use
        when storing the chroot
        @type chrootFingerprint: str of length 20
        @param root: The location of the chroot in the filesystem
        @type root: str
        @return: None
        """
        raise NotImplementedError

    def restore(self, chrootFingerprint, root):
        """
        Return the cached chroot with the given chroot fingerprint to
        the directory specified by C{root}

        @param chrootFingerprint: The fingerprint (a SHA1 sum) to use
        when restoring the chroot
        @type chrootFingerprint: str of length 20
        @param root: The location to restore the chroot in the filesystem
        @type root: str
        @return: None
        """
        raise NotImplementedError

    def hasChroot(self, chrootFingerprint):
        """
        Check to see if the chroot cache contains an entry for the given
        chroot fingerprint

        @param chrootFingerprint: The fingerprint (a SHA1 sum) to check
        @type chrootFingerprint: str of length 20
        @return: bool
        """
        raise NotImplementedError

class LocalChrootCache(ChrootCacheInterface):
    """
    The LocalChrootCache class implements a chroot cache that uses the
    local file system to store tar archive of chroots.
    """
    def __init__(self, cacheDir):
        """
        Instanciate a LocalChrootCache object
        @param cacheDir: The base directory for the chroot cache files
        @type cacheDir: str
        """
        self.cacheDir = cacheDir

    def store(self, chrootFingerprint, root):
        path = self._fingerPrintToPath(chrootFingerprint)
        util.mkdirChain(self.cacheDir)
        subprocess.call('tar cSpf - -C %s . | gzip -9 - > %s' %(root, path),
                        shell=True)

    def restore(self, chrootFingerprint, root):
        path = self._fingerPrintToPath(chrootFingerprint)
        subprocess.call('zcat %s | tar xSpf - -C %s' %(path, root),
                        shell=True)

    def hasChroot(self, chrootFingerprint):
        path = self._fingerPrintToPath(chrootFingerprint)
        return os.path.isfile(path)

    def _fingerPrintToPath(self, chrootFingerprint):
        tar = sha1ToString(chrootFingerprint) + '.tar.gz'
        return os.path.join(self.cacheDir, tar)
