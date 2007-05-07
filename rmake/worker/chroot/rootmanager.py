#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import errno
import copy
import os
import stat
import sys
import tempfile
import time

#conary
from conary.lib import util
from conary.local import database

#rmake
from rmake import constants
from rmake import errors
from rmake.worker.chroot import rootserver
from rmake.worker.chroot import rootfactory
from rmake.lib import flavorutil
from rmake.lib import logger as logger_
from rmake.lib import repocache

class ChrootQueue(object):
    def __init__(self, root, slots):
        self.root = root
        self.slots = slots
        self.chroots = {}
        self.toRemove = {}  # chroots that are scheduled for removal
        self.badChroots = {}

    def listChroots(self):
        chroots = set(self.chroots)
        if os.path.exists(self.root):
            for name in os.listdir(self.root):
                path = self.root + '/' + name
                if os.path.isdir(path):
                    chroots.add(path)
        return [ x for x in chroots if x not in self.badChroots ]

    def listOldChroots(self):
        chroots = []
        if os.path.exists(self.root):
            for name in os.listdir(self.root):
                path = self.root + '/' + name
                if (not os.path.isdir(path)
                    or path in self.chroots
                    or path in self.toRemove
                    or path in self.badChroots):
                    continue
                chroots.append(path)
        return [ x for x in chroots if x not in self.badChroots ]

    def _createRootPath(self, troveName):
        name = troveName.rsplit(':', 1)[0]
        path =  self.root + '/%s' % name
        count = 1
        if not os.path.exists(path) and not path in self.chroots:
            self.chroots[path] = None
            return path
        path = path + '-%s'
        while True:
            fullPath = path % count
            if not os.path.exists(fullPath) and not fullPath in self.chroots:
                self.chroots[fullPath] = None
                return fullPath
            else:
                count += 1

    def addChroot(self, path, chroot):
        self.chroots[path] = chroot

    def chrootFinished(self, chrootPath):
        self.chroots.pop(chrootPath, False)

    def deleteChroot(self, chrootPath):
        self.chroots.pop(chrootPath, False)
        self.toRemove.pop(chrootPath, False)
        self.badChroots.pop(chrootPath, False)

    def markBadChroot(self, chrootPath):
        # we tried to remove this chroot but it failed.
        # Never use this chroot again.
        self.deleteChroot(chrootPath)
        self.badChroots[chrootPath] = True

    def _getBestOldChroot(self, buildReqs, reuseRoot):
        """
            If the chroot is being reused, pick by contents of the chroot.
            Otherwise, pick oldest
        """
        if not reuseRoot:
            for chroot in self.listOldChroots():
                # return oldest directory
                return sorted(self.listOldChroots(),
                              key=lambda x: os.stat(x)[stat.ST_MTIME])[0]
        buildReqsByNBF = set([(x[0], x[1].branch(), x[2]) for x in buildReqs])
        matches = {}
        for chrootPath in self.listOldChroots():
            db = database.Database(chrootPath, '/var/lib/conarydb')
            chrootContents = db.iterAllTroves()
            trovesByNBF = set([(x[0], x[1].branch(), x[2]) for x in chrootContents])
            # matches = 2*matches - extras - so an empty chroot is better than 
            # a chroot with lots of wrong troves.
            matches[chrootPath] = 2 * len(trovesByNBF.intersection(buildReqsByNBF)) - len(trovesByNBF.difference(buildReqsByNBF))
        return sorted((x[1], x[0]) for x in matches.iteritems())[-1][1]

    def requestSlot(self, troveName, buildReqs, reuseChroots):
        if self.slots > 0 and len(self.chroots) >= self.slots:
            return None
        allChroots = self.listChroots()
        newPath = self._createRootPath(troveName)
        if self.slots <= 0:
            return (None, newPath)
        if len(allChroots) < self.slots:
            # we haven't reached the chroot limit so keep going
            return (None, newPath)
        oldPath = self._getBestOldChroot(buildReqs, reuseChroots)
        return (oldPath, newPath)

    def useSlot(self, root):
        self.chroots[root] = None

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
        if logger is None:
            logger = logger_.Logger()
        self.logger = logger
        self.queue = ChrootQueue(self.baseDir, self.serverCfg.chrootLimit)

    def listChroots(self):
        chroots = self.queue.listChroots()
        if os.path.exists(self.archiveDir):
            for name in os.listdir(self.archiveDir):
                chroots.append('archive/' + name)
        return chroots

    def chrootFinished(self, chrootPath):
        self.queue.chrootFinished(chrootPath)

    def getRootFactory(self, cfg, buildReqList, crossReqList, buildTrove):
        cfg = copy.deepcopy(cfg)
        cfg.threaded = False

        cfg.logFile = '/var/log/conary'
        cfg.dbPath = '/var/lib/conarydb'

        setArch, targetArch = flavorutil.getTargetArch(buildTrove.flavor)

        if not setArch:
            targetArch = None

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
            util.mkdirChain(self.baseDir)
        copyInConary = (not targetArch
                        and not cfg.strictMode
                        and cfg.copyInConary)

        chroot = chrootClass(buildTrove,
                             self.chrootHelperPath,
                             cfg, self.serverCfg, buildReqList, crossReqList,
                             self.logger,
                             csCache=self.csCache,
                             copyInConary=copyInConary)
        buildLogPath = self.serverCfg.getBuildLogPath(buildTrove.jobId)
        chrootServer = rMakeChrootServer(chroot, targetArch, 
                                         chrootQueue=self.queue,
                                         useTmpfs=self.serverCfg.useTmpfs,
                                         buildLogPath=buildLogPath,
                                         reuseRoots=cfg.reuseRoots,
                                         strictMode=cfg.strictMode,
                                         logger=self.logger,
                                         buildTrove=buildTrove)

        return chrootServer

    def useExistingChroot(self, chrootPath, useChrootUser=True):
        if not chrootPath.startswith(self.baseDir):
            chrootPath = self.baseDir + '/' +  chrootPath
        if not os.path.exists(chrootPath):
            raise errors.OpenError("No such chroot exists")
        chroot = rootfactory.ExistingChroot(chrootPath, self.logger,
                                            self.chrootHelperPath)
        chrootServer = rMakeChrootServer(chroot, targetArch=None,
                                         chrootQueue=self.queue,
                                         useTmpfs=self.serverCfg.useTmpfs,
                                         buildLogPath=None, reuseRoots=True,
                                         useChrootUser=useChrootUser,
                                         logger=self.logger,
                                         runTagScripts=False,
                                         root=chrootPath)
        return chrootServer

    def archiveChroot(self, chrootPath, newPath):
        chrootPath = os.path.realpath(self.baseDir + '/' + chrootPath)
        newPath = os.path.realpath(self.archiveDir + '/' + newPath)
        assert(os.path.dirname(chrootPath) == self.baseDir)
        assert(os.path.dirname(newPath) == self.archiveDir)
        util.mkdirChain(self.archiveDir)
        util.execute('/bin/mv %s %s' % (chrootPath, newPath))
        self.queue.deleteChroot(chrootPath)
        return 'archive/' + os.path.basename(newPath)

    def deleteChroot(self, chrootPath):
        if (chrootPath.startswith(self.archiveDir) 
            or chrootPath.startswith('archive/')):
            if chrootPath.startswith('archive/'):
                chrootPath = self.archiveDir + '/' + chrootPath[len('archive/'):]
            chrootPath = os.path.realpath(chrootPath)
            assert(os.path.dirname(chrootPath) == self.archiveDir)
        else:
            if not chrootPath.startswith(self.baseDir):
                chrootPath = self.baseDir + '/' +  chrootPath
            chrootPath = os.path.realpath(chrootPath)
            assert(os.path.dirname(chrootPath) == self.baseDir)
        chroot = rootfactory.ExistingChroot(chrootPath, self.logger,
                                             self.chrootHelperPath)
        chroot.clean(chrootPath)
        self.queue.deleteChroot(chrootPath)

class rMakeChrootServer(object):
    """
        Manages starting the rmake chroot server.
    """
    def __init__(self, chroot, targetArch, buildLogPath, logger,
                 chrootQueue, useTmpfs=False, reuseRoots=False, 
                 strictMode=False, useChrootUser=True, runTagScripts=True, 
                 root=None, buildTrove=None):
        self.chroot = chroot
        self.targetArch = targetArch
        self.queue = chrootQueue
        self.useTmpfs = useTmpfs
        self.reuseRoots = reuseRoots
        self.strictMode = strictMode
        self.buildLogPath = buildLogPath
        self.useChrootUser = useChrootUser
        self.logger = logger
        self.runTagScripts = runTagScripts
        self.root = root
        self.buildTrove = buildTrove
        self.oldRoot = None

    def reserveRoot(self):
        if self.root is None:
            jobList = [ (x[0],) + x[2] for x in self.chroot.jobList ]
            data = self.queue.requestSlot(self.buildTrove.getName(),
                                          jobList,
                                          self.reuseRoots)
            if not data:
                return None
            oldRoot, newRoot = data
            self.oldRoot = oldRoot
            self.root = newRoot
        else:
            self.queue.useChroot(self.root)
        return True

    def getRoot(self):
        return self.root

    def getChrootName(self):
        return self.getRoot().rsplit('/', 1)[-1]

    def clean(self):
        ok = self.chroot.clean(self.getRoot())
        if ok:
            self.queue.deleteChroot(self.getRoot())
        else:
            self.queue.markBadChroot(self.getRoot())

    def unmount(self):
        return self.chroot.unmount(self.getRoot())

    def create(self):
        if not self.root:
            self.reserveRoot()
        if self.reuseRoots:
            if self.oldRoot:
                self.chroot.moveOldRoot(self.oldRoot, self.getRoot())
            # we're going to keep the old contents of the root and perform
            # as few updates as possible.  However, that still means
            # unmounting those things owned by root so that the rmake process
            # can make any necessary modifications.
            self.chroot.unmount(self.getRoot())
        else:
            if self.oldRoot:
                self.chroot.clean(self.oldRoot, raiseError=False)
            self.chroot.clean(self.getRoot())
        self.queue.chrootFinished(self.oldRoot)
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


