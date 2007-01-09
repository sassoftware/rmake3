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
    def __init__(self, jobId, baseDir, chrootHelperPath, buildCfg, serverCfg,
                 logger=None):
        self.jobId = jobId
        self.cfg = buildCfg
        self.serverCfg = serverCfg
        self.cfg = copy.deepcopy(self.cfg)
        self.cfg.threaded = False
        self.baseDir = baseDir
        self.chrootHelperPath = chrootHelperPath
        cacheDir = self.baseDir + '/cscache'
        util.mkdirChain(cacheDir)
        self.csCache = repocache.RepositoryCache(cacheDir)
        self.chroots = {}
        if logger is None:
            logger = logger_.Logger()
        self.logger = logger


    def createRoot(self, jobList, buildTrove):
        self.cfg.logFile = '/var/log/conary'
        self.cfg.dbPath = '/var/lib/conarydb'

        setArch, targetArch = flavorutil.getTargetArch(buildTrove.flavor)
        if not setArch:
            targetArch = None

        if self.cfg.strictMode or (buildTrove.isPackageRecipe()
                                   or buildTrove.isInfoRecipe()):
            rootDir = self.baseDir + '/chroot'
            chrootClass = rootfactory.FullRmakeChroot
        elif (buildTrove.isRedirectRecipe() or buildTrove.isGroupRecipe()
              or buildTrove.isFilesetRecipe()):
            # we don't need to actually instantiate a root to cook
            # these packages - if we're not worried about using the 
            # "correct" conary, conary-policy, etc.
            rootDir = self.baseDir + '/chroot'
            jobList = []
            os.chdir(self.baseDir)
            chrootClass = rootfactory.FakeRmakeRoot
        else:
            raise errors.OpenError('Chroot could not be created - unknown recipe type for %s' % buildTrove.getName())

        self.cfg.root = rootDir
        copyInConary = not targetArch and not self.cfg.strictMode

        chroot = chrootClass(buildTrove,
                             self.chrootHelperPath,
                             self.cfg, self.serverCfg, jobList, self.logger,
                             csCache=self.csCache,
                             copyInConary=copyInConary)

        if self.cfg.reuseRoots and not self.cfg.strictMode:
            # we're going to keep the old contents of the root and perform
            # as few updates as possible.  However, that still means
            # unmounting those things owned by root so that the rmake process
            # can make any necessary modifications.
            chroot.unmount()
        else:
            chroot.clean()
        chroot.create(rootDir)
        buildLogPath = self.serverCfg.getBuildLogPath(self.jobId)
        chrootServer = rMakeChrootServer(chroot, self.cfg, targetArch,
                                         useTmpfs=self.serverCfg.useTmpfs,
                                         buildLogPath=buildLogPath)

        buildTrove.log('Chroot Created')
        client = chrootServer.start()
        self.chroots[client.getPid()] = (chroot, client)
        return client

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def cleanRoot(self, pid):
        root, client = self.chroots[pid]
        self.killRoot(pid)
        root.clean()

    def __del__(self):
        self.killAllRoots()

    def killAllRoots(self):
        for pid in list(self.chroots): # make copy since is modified
            self.killRoot(pid)

    def killRoot(self, pid):
        root, client = self.chroots[pid]
        try:
            client.stop()
        except OSError, err:
            if err.errno != errno.ESRCH:
                raise
            else:
                return
        except errors.OpenError, err:
            pass
        died = False
        for i in xrange(400):
            try:
                foundPid, status = os.waitpid(pid, os.WNOHANG)
            except OSError, err:
                if err.errno in (errno.ESRCH, errno.ECHILD):
                    foundPid = True
                else:
                    raise
            if not foundPid:
                time.sleep(.1)
            else:
                died = True
                break
        if not died:
            self.warning('child process %s did not shut down' % pid)
        else:
            del self.chroots[pid]


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


