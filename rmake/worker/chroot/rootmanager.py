#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import errno
import copy
import os
import sys
import tempfile
import time

#conary
from conary.lib import util

#rmake
from rmake import constants
from rmake import errors
from rmake.worker.chroot import rootserver
from rmake.worker.chroot import rootfactory
from rmake.lib import flavorutil
from rmake.lib import logger as logger_
from rmake.lib import repocache

class ChrootManager(object):
    def __init__(self, serverCfg, logger=None):
        self.serverCfg = serverCfg
        self.baseDir =  os.path.realpath(serverCfg.getChrootDir())
        self.archiveDir =  os.path.realpath(serverCfg.getChrootArchiveDir())
        self.chrootHelperPath = serverCfg.chrootHelperPath
        cacheDir = serverCfg.getCacheDir()
        util.mkdirChain(cacheDir)
        if self.serverCfg.useCache:
            self.csCache = repocache.RepositoryCache(cacheDir)
        else:
            self.csCache = None
        self.chroots = {}
        if logger is None:
            logger = logger_.Logger()
        self.logger = logger

    def listChroots(self):
        chroots = []
        if os.path.exists(self.baseDir):
            for name in os.listdir(self.baseDir):
                path = self.baseDir + '/' + name
                if os.path.isdir(path):
                    chroots.append(name)
        if os.path.exists(self.archiveDir):
            for name in os.listdir(self.archiveDir):
                chroots.append('archive/' + name)
        return chroots

    def createRootPath(self, buildTrove):
        name = buildTrove.getName().rsplit(':', 1)[0]
        path =  self.baseDir + '/%s' % name
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

        rootDir = self.createRootPath(buildTrove)
        if (not cfg.strictMode and
              (buildTrove.isRedirectRecipe() or buildTrove.isGroupRecipe()
               or buildTrove.isFilesetRecipe())):
            # we don't need to actually instantiate a root to cook
            # these packages - if we're not worried about using the 
            # "correct" conary, conary-policy, etc.
            jobList = []
            util.mkdirChain(self.baseDir)
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
        chrootServer = rMakeChrootServer(chroot, targetArch,
                                         useTmpfs=self.serverCfg.useTmpfs,
                                         buildLogPath=buildLogPath,
                                         reuseRoots=cfg.reuseRoots,
                                         strictMode=cfg.strictMode, 
                                         logger=self.logger)

        self.chroots[rootDir] = chrootServer
        return chrootServer

    def useExistingChroot(self, chrootPath, useChrootUser=True):
        if not chrootPath.startswith(self.baseDir):
            chrootPath = self.baseDir + '/' +  chrootPath
        assert(os.path.exists(chrootPath))
        chroot = rootfactory.ExistingChroot(chrootPath, self.logger,
                                             self.chrootHelperPath)
        chrootServer = rMakeChrootServer(chroot, targetArch=None,
                                         useTmpfs=self.serverCfg.useTmpfs,
                                         buildLogPath=None, reuseRoots=True,
                                         useChrootUser=useChrootUser,
                                         logger=self.logger,
                                         runTagScripts=False)
        self.chroots[chrootPath] = chrootServer
        return chrootServer

    def archiveChroot(self, chrootPath, newPath):
        chrootPath = os.path.realpath(self.baseDir + '/' + chrootPath)
        newPath = os.path.realpath(self.archiveDir + '/' + newPath)
        assert(os.path.dirname(chrootPath) == self.baseDir)
        assert(os.path.dirname(newPath) == self.archiveDir)
        util.mkdirChain(self.archiveDir)
        util.execute('/bin/mv %s %s' % (chrootPath, newPath))
        return 'archive/' + os.path.basename(newPath)

    def deleteChroot(self, chrootPath):
        if chrootPath.startswith('archive/'):
            chrootPath = self.archiveDir + '/' + chrootPath[len('archive/'):]
            chrootPath = os.path.realpath(chrootPath)
            assert(os.path.dirname(chrootPath) == self.archiveDir)
        else:
            chrootPath = os.path.realpath(self.baseDir +'/' +  chrootPath)
            assert(os.path.dirname(chrootPath) == self.baseDir)
        chroot = rootfactory.ExistingChroot(chrootPath, self.logger,
                                             self.chrootHelperPath)
        chroot.clean()

class rMakeChrootServer(object):
    """
        Manages starting the rmake chroot server.
    """
    def __init__(self, chroot, targetArch, buildLogPath, logger,
                 useTmpfs=False, reuseRoots=False, strictMode=False,
                 useChrootUser=True, runTagScripts=True):
        self.chroot = chroot
        self.targetArch = targetArch
        self.useTmpfs = useTmpfs
        self.reuseRoots = reuseRoots
        self.strictMode = strictMode
        self.buildLogPath = buildLogPath
        self.useChrootUser = useChrootUser
        self.logger = logger
        self.runTagScripts = runTagScripts

    def getRoot(self):
        return self.chroot.getRoot()

    def getChrootName(self):
        return self.getRoot().rsplit('/', 1)[-1]

    def clean(self):
        return self.chroot.clean()

    def unmount(self):
        return self.chroot.unmount()

    def create(self):
        if self.reuseRoots and not self.strictMode:
            # we're going to keep the old contents of the root and perform
            # as few updates as possible.  However, that still means
            # unmounting those things owned by root so that the rmake process
            # can make any necessary modifications.
            self.chroot.unmount()
        else:
            self.chroot.clean()
        self.chroot.create(self.getRoot())

    def start(self, forkCommand=os.fork):
        self.socketPath = self.getRoot() + '/tmp/chroot-socket-%s'
        pid = forkCommand()
        if pid:
            self.logger.info("Chroot server starting (pid %s)" % pid)
            self.socketPath = self.socketPath % pid
            return self._waitForChrootServer(pid)
        else:
            self.socketPath = self.socketPath % os.getpid()
            try:
                self._startChrootServer()
            finally:
                os._exit(1)

    def _startChrootServer(self):
        socketPath = self.socketPath[len(self.getRoot()):]
        if self.chroot.canChroot():
            prog = self.chroot.chrootHelperPath
            args = [prog, self.getRoot(), socketPath]
            if self.targetArch:
                args.extend(['--arch', self.targetArch])
            if self.useTmpfs:
                args.append('--tmpfs')
            if not self.useChrootUser:
                args.append('--no-chroot-user')
            if not self.runTagScripts:
                args.append('--no-tag-scripts')
            os.execv(prog, args)
        else:
            # testsuite and FakeRoot path
            rmakeDir = os.path.dirname(sys.modules['rmake'].__file__)
            conaryDir = os.path.dirname(sys.modules['conary'].__file__)
            prog = (self.getRoot() + constants.chrootRmakePath
                    + constants.chrootServerPath)
            util.mkdirChain(self.getRoot() + '/tmp/rmake/lib')
            args = [prog, 'start', '-n', '--config',
                    'root %s' % self.getRoot(), '--socket', socketPath]
            env = {'PYTHONPATH' : '%s:%s' % (os.path.dirname(rmakeDir),
                                             os.path.dirname(conaryDir))}
            if 'COVERAGE_DIR' in os.environ:
                import shutil
                chrootRmakePath = self.getRoot() + constants.chrootRmakePath
                realRmakePath = os.path.dirname(sys.modules['rmake'].__file__)
                shutil.rmtree(chrootRmakePath)
                util.mkdirChain(chrootRmakePath)
                os.symlink(realRmakePath, chrootRmakePath + '/rmake')
                env.update(x for x in os.environ.items() if x[0].startswith('COVERAGE'))
            os.execve(prog, args, env)

    def _waitForChrootServer(self, pid):
        # paths passed back from the server will be relative to the chroot
        # if we chroot into it, otherwise they'll be relative to /
        uri = 'unix:%s' % (self.socketPath)

        if self.chroot.canChroot():
            clientRoot = self.getRoot()
        else:
            clientRoot = '/'
        client = rootserver.ChrootClient(clientRoot, uri, pid)

        def checkPid():
            checkedPid, status = os.waitpid(pid, os.WNOHANG)
            if checkedPid:
                msg = ('Chroot server failed to start - please check'
                       ' logs for chroot process %s' % pid)
                if self.buildLogPath:
                    msg += ' and build log %s' % self.buildLogPath
                raise errors.OpenError(msg)
            return True


        timeSlept = 0    # fail after an hour of the chroot process running
                         # if tag scripts takes longer than that then there's
                         # a problem.
        while timeSlept < 7200:
            if os.path.exists(self.socketPath):
                break
            checkPid()
            time.sleep(.1)
            timeSlept += .1

        client.ping(hook=checkPid, seconds=60)
        return client


