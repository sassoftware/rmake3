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
import errno
import copy
import os
import sys
import time

#conary
from conary.lib import util

#rmake
from rmake import constants
from rmake import errors
from rmake.build.chroot import server as chrootserver
from rmake.build import rootfactory
from rmake.lib import flavorutil
from rmake.lib import logger as logger_
from rmake.lib import repocache

class ChrootManager(object):
    def __init__(self, baseDir, chrootHelperPath, serverCfg, logger=None):
        self.baseDir = baseDir
        self.chrootHelperPath = chrootHelperPath
        self.serverCfg = serverCfg
        cacheDir = self.baseDir + '/cscache'
        util.mkdirChain(cacheDir)
        self.csCache = repocache.RepositoryCache(cacheDir)
        self.chroots = {}
        if logger is None:
            logger = logger_.Logger()
        self.logger = logger

    def getRootPath(self, buildTrove):
        name = buildTrove.getName().rsplit(':', 1)[0]
        path =  self.baseDir + '/chroot-%s' % name
        count = 1
        if path not in self.chroots:
            return path
        path = path + '-%s'
        while True:
            if path % count in self.chroots:
                count += 1
            else:
                return path % count

    def rootFinished(self, chroot):
        root = chroot.getRoot()
        if root in self.chroots:
            del self.chroots[root]

    def getRootFactory(self, cfg, jobList, buildTrove):
        cfg = copy.deepcopy(cfg)
        cfg.threaded = False

        cfg.logFile = '/var/log/conary'
        cfg.dbPath = '/var/lib/conarydb'

        setArch, targetArch = flavorutil.getTargetArch(buildTrove.flavor)

        if not setArch:
            targetArch = None

        rootDir = self.getRootPath(buildTrove)
        if (not cfg.strictMode and
              (buildTrove.isRedirectRecipe() or buildTrove.isGroupRecipe()
               or buildTrove.isFilesetRecipe())):
            # we don't need to actually instantiate a root to cook
            # these packages - if we're not worried about using the 
            # "correct" conary, conary-policy, etc.
            jobList = []
            os.chdir(self.baseDir)
            chrootClass = rootfactory.FakeRmakeRoot
        else:
            chrootClass = rootfactory.FullRmakeChroot
        cfg.root = rootDir
        copyInConary = not targetArch and not cfg.strictMode

        chroot = chrootClass(buildTrove,
                             self.chrootHelperPath,
                             cfg, self.serverCfg, jobList, self.logger,
                             csCache=self.csCache,
                             copyInConary=copyInConary)
        buildLogPath = self.serverCfg.getBuildLogPath(buildTrove.jobId)
        chrootServer = rMakeChrootServer(chroot, cfg, targetArch,
                                         useTmpfs=self.serverCfg.useTmpfs,
                                         buildLogPath=buildLogPath)

        self.chroots[rootDir] = chrootServer
        return chrootServer


class rMakeChrootServer(object):
    """
        Manages starting the rmake chroot server.
    """
    def __init__(self, chroot, cfg, targetArch, buildLogPath,
                 useTmpfs=False):
        self.chroot = chroot
        self.cfg = cfg
        self.targetArch = targetArch
        self.useTmpfs = useTmpfs
        self.buildLogPath = buildLogPath

    def getRoot(self):
        return self.chroot.cfg.root

    def clean(self):
        return self.chroot.clean()

    def create(self):
        if self.cfg.reuseRoots and not self.cfg.strictMode:
            # we're going to keep the old contents of the root and perform
            # as few updates as possible.  However, that still means
            # unmounting those things owned by root so that the rmake process
            # can make any necessary modifications.
            self.chroot.unmount()
        else:
            self.chroot.clean()
        self.chroot.create(self.getRoot())

    def start(self):
        pid = os.fork()
        if pid:
            return self._waitForChrootServer(pid)
        else:
            try:
                self._startChrootServer()
            finally:
                os._exit(1)

    def _startChrootServer(self):
        if self.chroot.canChroot():
            prog = self.chroot.chrootHelperPath
            args = [prog, self.cfg.root]
            if self.targetArch:
                args.extend(['--arch', self.targetArch])
            if self.useTmpfs:
                args.append('--tmpfs')
            os.execv(prog, args)
        else:
            # testsuite and FakeRoot path
            rmakeDir = os.path.dirname(sys.modules['rmake'].__file__)
            conaryDir = os.path.dirname(sys.modules['conary'].__file__)
            prog = (self.cfg.root + constants.chrootRmakePath
                    + constants.chrootServerPath)
            util.mkdirChain(self.cfg.root + '/tmp/rmake/lib')
            args = [prog, 'start', '-n', '--config',
                    'root %s' % self.cfg.root]
            os.execve(prog, args,
                  {'PYTHONPATH' : '%s:%s' % (os.path.dirname(rmakeDir),
                                             os.path.dirname(conaryDir))})

    def _waitForChrootServer(self, pid):
        # paths passed back from the server will be relative to the chroot
        # if we chroot into it, otherwise they'll be relative to /
        socketPath = '/tmp/rmake/lib/chrootsocket'
        uri = 'unix:%s%s' % (self.cfg.root, socketPath)

        if self.chroot.canChroot():
            clientRoot = self.cfg.root
        else:
            clientRoot = '/'
        client = chrootserver.ChrootClient(clientRoot, uri, pid)

        def checkPid():
            checkedPid, status = os.waitpid(pid, os.WNOHANG)
            if checkedPid:
                raise errors.OpenError(
                    'Chroot server failed to start - please check'
                    ' %s' % self.buildLogPath)


        timeSlept = 0
        while timeSlept < 180:
            if os.path.exists('%s%s' % (self.cfg.root, socketPath)):
                break
            checkPid()
            time.sleep(.1)
            timeSlept += .1

        client.ping(hook=checkPid, seconds=60)
        return client


