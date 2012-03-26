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


import errno
import copy
import os
import stat
import sys
import tempfile
import time
import traceback

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

    def reset(self):
        self.chroots = {}
        self.toRemove = {}
        self.badChroots = {}

    def listChroots(self):
        chroots = set(self.chroots)
        if os.path.exists(self.root):
            for name in os.listdir(self.root):
                path = self.root + '/' + name
                if os.path.isdir(path):
                    chroots.add(path)
        chroots = [ x for x in chroots if x not in self.badChroots ]
        return self._shortenChrootPaths(chroots)


    def _shortenChrootPaths(self, chrootPaths):
        finalChroots = []
        for chroot in chrootPaths:
            if chroot.startswith(self.root):
                chroot = chroot[len(self.root)+1:]
                finalChroots.append(chroot)
        return finalChroots

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

    def _getBestOldChroot(self, buildReqs, reuseRoot, goodRootsOnly=False):
        """
            If the chroot is being reused, pick by contents of the chroot.
            Otherwise, pick oldest

            If goodRootsOnly is True, be more discerning about which chroot
            to use - only use ones that have more than half matching packages.
        """
        if not reuseRoot:
            for chroot in self.listOldChroots():
                # return oldest directory
                return sorted(self.listOldChroots(),
                              key=lambda x: os.stat(x)[stat.ST_MTIME])[0]
        buildReqsByNLF = set([(x[0], x[1].trailingLabel(), x[2]) 
                             for x in buildReqs])
        matches = {}
        for chrootPath in self.listOldChroots():
            db = database.Database(chrootPath, '/var/lib/conarydb')
            chrootContents = db.iterAllTroves()
            trovesByNLF = set([(x[0], x[1].trailingLabel(), x[2]) for x in chrootContents])
            # matches = 2*matches - extras - so an empty chroot is better than 
            # a chroot with lots of wrong troves.
            matches[chrootPath] = 2 * len(trovesByNLF.intersection(buildReqsByNLF)) - len(trovesByNLF.difference(buildReqsByNLF))
        if matches:
            rank, best = sorted((x[1], x[0]) for x in matches.iteritems())[-1]
            if rank >= len(buildReqsByNLF) or not goodRootsOnly:
                return best

    def requestSlot(self, troveName, buildReqs, reuseChroots):
        if self.slots > 0 and len(self.chroots) >= self.slots:
            return None
        allChroots = self.listChroots()
        newPath = self._createRootPath(troveName)
        if self.slots <= 0:
            return (None, newPath)
        if len(allChroots) < self.slots:
            if reuseChroots:
                # we've got more slots, but maybe we'll get a really
                # good match from an existing chroot and we should
                # reuse it.
                oldPath = self._getBestOldChroot(buildReqs,
                                                 reuseChroots,
                                                 goodRootsOnly=True)
            else:
                # we haven't reached the chroot limit so keep going
                oldPath = None
        else:
            oldPath = self._getBestOldChroot(buildReqs, reuseChroots)
        if oldPath:
            self.toRemove[oldPath] = True
        return (oldPath, newPath)

    def useSlot(self, root):
        self.chroots[root] = None

class ChrootManager(object):
    def __init__(self, serverCfg, logger=None):
        self.serverCfg = serverCfg
        self.baseDir =  os.path.realpath(serverCfg.getChrootDir())
        self.archiveDir =  os.path.realpath(serverCfg.getChrootArchiveDir())
        self.chrootHelperPath = serverCfg.getChrootHelper()
        cacheDir = serverCfg.getCacheDir()
        util.mkdirChain(cacheDir)
        if self.serverCfg.useCache:
            self.csCache = repocache.RepositoryCache(cacheDir)
        else:
            self.csCache = None
        self.chrootCache = serverCfg.getChrootCache()
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

    def getRootFactory(self, cfg, buildReqList, crossReqList, bootstrapReqs,
            buildTrove):
        cfg = copy.deepcopy(cfg)
        cfg.threaded = False

        cfg.logFile = '/var/log/conary'
        cfg.dbPath = '/var/lib/conarydb'

        setArch, targetArch = flavorutil.getTargetArch(buildTrove.flavor)

        if not setArch:
            targetArch = None

        chrootClass = rootfactory.FullRmakeChroot
        util.mkdirChain(self.baseDir)
        copyInConary = (not targetArch
                        and not cfg.strictMode
                        and cfg.copyInConary)

        chroot = chrootClass(buildTrove,
                             self.chrootHelperPath,
                             cfg, self.serverCfg, buildReqList, crossReqList,
                             bootstrapReqs, self.logger,
                             csCache=self.csCache,
                             chrootCache=self.chrootCache,
                             copyInConary=copyInConary)
        buildLogPath = self.serverCfg.getBuildLogPath(buildTrove.jobId)
        chrootServer = rMakeChrootServer(chroot, targetArch,
                chrootQueue=self.queue, useTmpfs=self.serverCfg.useTmpfs,
                buildLogPath=buildLogPath, reuseRoots=cfg.reuseRoots,
                strictMode=cfg.strictMode, logger=self.logger,
                buildTrove=buildTrove, chrootCaps=self.serverCfg.chrootCaps)

        return chrootServer

    def useExistingChroot(self, chrootPath, useChrootUser=True, 
                          buildTrove = None):
        if chrootPath.startswith('archive/'):
            chrootPath = self.archiveDir + chrootPath[len('archive'):]
        elif not chrootPath.startswith(self.baseDir):
            chrootPath = self.baseDir + '/' +  chrootPath
        if not os.path.exists(chrootPath):
            raise errors.ServerError("No such chroot exists")
        chrootPath = os.path.realpath(chrootPath)
        assert(chrootPath.startswith(self.baseDir) or chrootPath.startswith(self.archiveDir))
        targetArch = None
        if buildTrove:
            setArch, targetArch = flavorutil.getTargetArch(buildTrove.flavor)

            if not setArch:
                targetArch = None

        chroot = rootfactory.ExistingChroot(chrootPath, self.logger,
                                            self.chrootHelperPath)
        chrootServer = rMakeChrootServer(chroot, targetArch=targetArch,
                chrootQueue=self.queue, useTmpfs=self.serverCfg.useTmpfs,
                buildLogPath=None, reuseRoots=True,
                useChrootUser=useChrootUser, logger=self.logger,
                runTagScripts=False, root=chrootPath,
                chrootCaps=self.serverCfg.chrootCaps)
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
                 root=None, buildTrove=None, chrootCaps=False):
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
        self.chrootCaps = chrootCaps
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

    def getInstalledTroves(self):
        return [(x[0], x[2][0], x[2][1]) for x in self.chroot.jobList]

    def getInstalledCrossTroves(self):
        return [(x[0], x[2][0], x[2][1]) for x in self.chroot.crossJobList]

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
        self.chroot.checkSanity()
        if not self.root:
            if not self.chroot.useStandardRoot():
                self.root = tempfile.mkdtemp(dir='/tmp',
                                      prefix='rmake-%s-root' % self.buildTrove.getName().split(':')[0])
            else:
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
            try:
                return self._waitForChrootServer(pid)
            except:
                self.chroot.invalidateCachedChroot()
                raise
        else:
            self.socketPath = self.socketPath % os.getpid()
            try:
                try:
                    self._startChrootServer()
                except:
                    print >> sys.stderr, "Error starting chroot helper:"
                    traceback.print_exc()
                    sys.stderr.flush()
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
            if self.chrootCaps:
                args.append('--chroot-caps')
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
                                             os.path.dirname(conaryDir)),
                   'RMAKE_ROOT' : self.getRoot()}
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
        uri = 'unix://%s' % (self.socketPath)

        if self.chroot.canChroot():
            clientRoot = self.getRoot()
        else:
            clientRoot = '/'
        client = rootserver.ChrootClient(clientRoot, uri, pid)

        def checkPid():
            checkedPid, status = os.waitpid(pid, os.WNOHANG)
            if checkedPid:
                msg = ('Chroot server failed to start - please check build log')
                raise errors.ServerError(msg)
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
