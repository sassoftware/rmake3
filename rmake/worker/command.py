#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import errno
import os
import shutil
import socket
import sys
import time
import traceback

from conary import conaryclient
from conary.lib import util
from conary.repository import changeset
from conary.repository.errors import CommitError

from rmake import errors

from rmake import failure
from rmake.build import subscriber
from rmake.worker import resolver

from rmake.lib import logfile
from rmake.lib import logger
from rmake.lib import repocache
from rmake.lib import recipeutil
from rmake.lib import server

from rmake.lib.apiutils import thaw, freeze


class Command(server.Server):
    """
        Superclass for commands.  Expects information to run one operation
        which it will perform and report about.

        The command is set up to handle forked operation:
            The main action occurs inside the pipe and any information
            processed is set via pipe.  The readPipe, if it exists,
            will parse data sent over that pipe.
    """
    name = 'command' # command name is used for logging purposes.

    def __init__(self, cfg, commandId, jobId):
        server.Server.__init__(self)
        self.cfg = cfg
        self.commandId = commandId
        self.jobId = jobId
        self.logData = None
        self._isErrored = False
        self._errorMessage = ''
        self._output = [] # default location for information read in 
                          # from the readPipe.
        self.failureReason = None
        self.readPipe = None
        self.writePipe = None

    def _exit(self, exitRc):
        sys.exit(exitRc)

    def isReady(self):
        return True

    def shouldFork(self):
        return True

    def setWritePipe(self, writePipe):
        """
            Sets the pipe to read data in.  This should match a readPipe
            set on the other side of a fork.
            @type readPipe: instance of lib.pipereader.PipeWriter
        """
        self.writePipe = writePipe

    def setReadPipe(self, readPipe):
        """
            Sets the pipe to read data in.  This should match a writePipe
            set on the other side of a fork.
            @type readPipe: instance of lib.pipereader.PipeReader
        """
        self.readPipe = readPipe

    def fileno(self):
        """
            Enables calling select() on a command.
        """
        return self.readPipe.fileno()

    def handleRead(self):
        # depending on the class of readPipe, this may not return data
        # until full objects have been read in.
        data = self.readPipe.handle_read()
        if data:
            self._handleData(data)

    def flushInputBuffer(self):
        if not self.readPipe:
            return
        for data in self.readPipe.readUntilClosed(timeout=20):
            self._handleData(data)

    def handleWrite(self):
        self.writePipe.handle_write()

    def _handleData(self, data):
        """ 
            Default behavior for handling incoming data on the readPipe.
        """
        self._output.append(data)

    def getCommandId(self):
        return self.commandId

    def getChrootFactory(self):
        return None

    def getLogPath(self):
        """
            All commands log their activities to a file based on their command
            it.  Returns the path for that logFile.
        """
        commandId = (self.getCommandId().replace('/', '_')
                                                    .replace('~', '')
                                                    .replace(' ', ''))
        base =  self.cfg.getBuildLogDir(self.jobId)
        return '%s/%s.log' % (base, commandId)

    def runCommandAndExit(self):
        # we actually want to die when the command is killed.
        # We want our entire process group to be killed.
        # Remove signal handlers and set us to be the leader of our
        # process group.
        os.setpgrp()
        self._resetSignalHandlers()
        try:
            self._try('Command', self._runCommand)
            os._exit(0)
        except SystemExit, err:
            os._exit(err.args[0])
        except:
            # error occurred, but we'll let our parent node send out the
            # "errored" message.
            os._exit(1)

    def _serveLoopHook(self):
        """
            Called inside the forked command process until the command is done.
        """
        self.writePipe.handleWriteIfReady()
        self._collectChildren()

    def runCommandNoExit(self):
        try:
            self._try('Command', self._runCommand)
        except SystemExit, err:
            return err.args[0]
        return 0

    def _runCommand(self):
        self.commandStarted()
        self.logger = logger.Logger(self.name) # output to stdout so logging
                                               # is all covered by logFile
        self.logFile = logfile.LogFile(self.getLogPath())
        if self.logData:
            self.logFile.logToPort(*self.logData)
        else:
            self.logFile.redirectOutput()
        try:
            self.logger.info('Running Command... (pid %s)' % os.getpid())
            try:
                self.runCommand()
            except SystemExit, err:
                raise
            except Exception, err:
                if isinstance(err, SystemExit) and not err.args[0]:
                    self.commandFinished()
                else:
                    self.logger.error(traceback.format_exc())
                    self.commandErrored(err, traceback.format_exc())
                raise
            else:
                self.commandFinished()
        finally:
            self.logFile.restoreOutput()

    def isErrored(self):
        return self._isErrored

    def getFailureReason(self):
        return self.failureReason

    def setError(self, msg, tb=''):
        self._isErrored = True
        self.failureReason = failure.CommandFailed(self.commandId, str(msg), tb)

    def commandDied(self, status):
        self.flushInputBuffer()
        exitRc = os.WEXITSTATUS(status)
        signalRc = os.WTERMSIG(status)
        commandId = self.getCommandId()
        if exitRc or signalRc:
            if exitRc:
                msg = 'unexpectedly died with exit code %s'
                msg = msg % (exitRc)
            else:
                msg = 'unexpectedly killed with signal %s'
                msg = msg % (signalRc)
            self.setError(msg)
        self.commandFinished()

    def commandStarted(self):
        pass

    def commandFinished(self):
        pass

    def commandErrored(self, msg, tb=''):
        self.setError(msg, tb)


class AttachedCommand(Command):

    def __init__(self, serverCfg, commandId, jobId, eventHandler,
      job=None, trove=None):
        assert job or trove
        super(AttachedCommand, self).__init__(serverCfg, commandId, jobId)
        self.eventHandler = eventHandler
        self.job = job
        self.trove = trove
        if trove:
            self.parent = trove
        else:
            self.parent = job
        self.publisher = None

    def _handleData(self, (jobId, eventList)):
        self.eventHandler._receiveEvents(*thaw('EventList', eventList))

    def getTrove(self):
        return self.trove

    def setFailure(self, failure):
        if self.trove:
            self.trove.troveFailed(failure)
        else:
            self.job.jobFailed(failure)

    def runCommand(self):
        try:
            self.parent.getPublisher().reset()
            self.publisher = PipePublisher(self.writePipe)
            self.publisher.attach(self.parent)
            self.runAttachedCommand()
        except SystemExit, err:
            self.writePipe.flush()
            raise
        except Exception, err:
            self.logger.error(traceback.format_exc())
            # even if there's an exception in here, we don't really
            # want to retry the build.
            reason = failure.InternalError(str(err), traceback.format_exc())
            self.setFailure(reason)
            self.writePipe.flush()
            self._shutDownAndExit()

    def handleRequestIfReady(self, sleep):
        time.sleep(sleep)

    def _serveLoopHook(self):
        try:
            self.writePipe.handleWriteIfReady()
            self._attachedServeLoopHook()
        except SystemExit, err:
            raise
        except Exception, err:
            self.logger.error(traceback.format_exc())
            reason = failure.InternalError(str(err), traceback.format_exc())
            self.setFailure(reason)
            self._shutDownAndExit()


class BuildCommand(AttachedCommand):

    name = 'build-command'

    def __init__(self, serverCfg, commandId, jobId, eventHandler, buildCfg,
                 chrootFactory, trove, builtTroves, targetLabel, logData=None,
                 logPath=None, uri=None):
        super(BuildCommand, self).__init__(serverCfg, commandId, jobId,
            eventHandler, trove=trove)
        self.buildCfg = buildCfg
        self.chrootFactory = chrootFactory
        self.builtTroves = builtTroves
        self.targetLabel = targetLabel
        self.logData = logData
        self.logPath = logPath
        self.uri = None

    def isReady(self):
        return self.chrootFactory.reserveRoot()

    def getChrootFactory(self):
        return self.chrootFactory

    def runAttachedCommand(self):
        try:
            trove = self.trove
            trove.creatingChroot(self.cfg.getName(),
                                 self.chrootFactory.getChrootName())
            self.chrootFactory.create()
            self.chroot = self.chrootFactory.start(
                                        lambda: self._fork('Chroot server'))
        except Exception, err:
            # sends off messages to all listeners that this trove failed.
            self.logger.error(traceback.format_exc())
            trove.chrootFailed(str(err), traceback.format_exc())
            return

        # this will grab the actual conary configuration used and write
        # it out to disk at /etc/conaryrc.
        self.chroot.storeConfig(self.buildCfg)
        oldPath = '%s/tmp/conaryrc' % self.chrootFactory.root
        if os.path.exists(oldPath):
            newPath = '%s/etc/conaryrc' % self.chrootFactory.root
            util.mkdirChain(os.path.dirname(newPath))
            if os.path.exists(newPath):
                os.remove(newPath)
            shutil.copy(oldPath, newPath)

        n,v = trove.getName(), trove.getVersion()
        self.chroot.checkoutPackage(self.buildCfg, n, v)

        if trove.isPrepOnly():
            # we start the chroot in prepare mode to make sure that
            # tagscripts are run, and that the chroot is valid.
            self.chroot.stop()
            trove.trovePrepared()
            return
        flavorList = trove.getFlavorList()
        buildReqs = self.chrootFactory.getInstalledTroves()
        crossReqs = self.chrootFactory.getInstalledCrossTroves()
        logPath, pid = self.chroot.buildTrove(self.buildCfg,
                                              self.targetLabel,
                                              n, v, flavorList,
                                              trove.getLoadedSpecsList(),
                                              self.builtTroves,
                                              self.logData,
                                              buildReqs=buildReqs,
                                              crossReqs=crossReqs)
        # sends off message that this trove is building.
        self.chroot.subscribeToBuild(n,v, flavorList)
        trove.troveBuilding(pid)
        self.serve_forever()

    def _attachedServeLoopHook(self):
        if self.chroot.checkSubscription():
            self.getResults()
            self._halt = True
            return

    def getResults(self):
        try:
            trove = self.trove
            repos = conaryclient.ConaryClient(self.buildCfg).getRepos()
            buildResult = self.chroot.checkResults(self.trove.getName(),
                                                   self.trove.getVersion(),
                                                   self.trove.getFlavorList())
            if buildResult.isBuildSuccess():
                csFile = buildResult.getChangeSetFile()
                cs = changeset.ChangeSetFromFile(csFile)
                troveList = [x.getNewNameVersionFlavor() for
                             x in cs.iterNewTroveList() ]
                try:
                    repos.commitChangeSet(cs)
                except CommitError, err:
                    # someone else committed this package between 
                    # our building and committing
                    if 'already exists' in str(err):
                        trove.troveDuplicate(troveList)
                    else:
                        raise
                else:
                    # sends off message that this trove built successfully
                    trove.troveBuilt(troveList)
                del cs # this makes sure the changeset closes the fd.
            else:
                reason = buildResult.getFailureReason()
                trove.troveFailed(reason)
                # passes through to killRoot at the bottom.
        except Exception, e:
            self.logger.error(traceback.format_exc())
            reason = failure.InternalError(str(e), traceback.format_exc())
            trove.troveFailed(reason)
        self.chroot.stop()

    def _shutDown(self):
        try:
            self.chroot.stop()
        except OSError, err:
            if err.errno != errno.ESRCH:
                raise
            else:
                return
        except errors.OpenError, err:
            pass
        self._killAllPids()
        if self.buildCfg.cleanAfterCook and self.trove.isBuilt():
            self.chrootFactory.clean()
        else:
            self.chrootFactory.unmount()
        Command._shutDown(self)

class StopCommand(Command):

    name = 'stop-command'

    def __init__(self, cfg, commandId, targetCommand, killFn):
        Command.__init__(self, cfg, commandId, targetCommand.jobId)
        self.targetCommand = targetCommand
        self.killFn = killFn

    def runCommand(self):
        self.killFn(self.targetCommand.pid)

    def shouldFork(self):
        # Because this command runs kill, it must be the parent process 
        # that runs kill, not some other child.  You can't kill your sibling.
        return False

    def commandDied(self, status):
        Command.commandDied(self, status)
        try:
            pid, status = os.waitpid(self.targetCommand.pid, os.WNOHANG)
        except OSError, err:
            if err.errno == errno.ECHILD:
                pass
            elif err.errno == errno.ESRCH:
                pass
            else:
                raise
        else:
            self.setError('%s did not die!' % self.targetCommand.getCommandId())

class SessionCommand(Command):

    name = 'session-command'

    def __init__(self, serverCfg, commandId, chrootFactory, command):
        Command.__init__(self, serverCfg, commandId, 0)
        self.chrootFactory = chrootFactory
        self.command = command
        self.hostInfo = []

    def getTrove(self):
        return self.trove

    def getChrootFactory(self):
        return self.chrootFactory

    def runCommand(self):
        self.chrootFactory.logger = self.logger
        self.chrootFactory.create()
        self.chroot = self.chrootFactory.start(
                                        lambda: self._fork('Chroot Server'))
        port = self.chroot.startSession(self.command)
        self.writePipe.send((socket.gethostname(), port))
        self.writePipe.flush()
        self.serve_forever()

    def _pidDied(self, pid, status, name=None):
        if pid == self.chroot.pid:
            self.chrootFactory.unmount()
            self._halt = True

    def _handleData(self, output):
        self.hostInfo = output

    def getHostInfo(self):
        return self.hostInfo

class ResolveCommand(AttachedCommand):

    name = 'resolve-command'

    def __init__(self, cfg, commandId, jobId,  eventHandler, logData,
                 resolveJob):
        super(ResolveCommand, self).__init__(cfg, commandId, jobId,
            eventHandler, trove=resolveJob.getTrove())
        self.logData = logData
        self.resolveJob = resolveJob

    def runAttachedCommand(self):
        self.logger.debug('Resolving')
        self.trove.troveResolvingBuildReqs(self.cfg.getName(), os.getpid())
        client = conaryclient.ConaryClient(self.resolveJob.getConfig())
        repos = client.getRepos()
        if self.cfg.useCache:
            repos = repocache.CachingTroveSource(repos,
                                                 self.cfg.getCacheDir())
        self.resolver = resolver.DependencyResolver(self.logger, repos)
        resolveResult = self.resolver.resolve(self.resolveJob)
        self.logger.debug('Resolve finished, sending back result')
        self.trove.troveResolved(resolveResult)
        self.logger.debug('Result sent')


class LoadCommand(AttachedCommand):
    """
    Load all troves for a job.
    """
    name = 'load-command'

    def __init__(self, cfg, commandId, jobId, eventHandler, job, troveList,
      reposName):
        super(LoadCommand, self).__init__(cfg, commandId, jobId,
            eventHandler, job=job)
        self.troveList = troveList
        self.reposName = reposName

    def runAttachedCommand(self):
        repos = conaryclient.ConaryClient(self.job.getMainConfig()).getRepos()
        if self.cfg.useCache:
            repos = repocache.CachingTroveSource(repos, self.cfg.getCacheDir())

        troves = []
        for troveTup in self.troveList:
            trove = self.job.getTrove(*troveTup)
            self.publisher.attach(trove)
            troves.append(trove)

        result = recipeutil.getSourceTrovesFromJob(self.job, troves,
            repos, self.reposName)
        self.job.jobLoaded(result)


class PipePublisher(subscriber._RmakePublisherProxy):
    """
        Class that transmits events from internal build process -> rMake server.
    """

    # we override the _receiveEvents method to just pass these
    # events on, thus we just use listeners as a list of states we subscribe to

    def __init__(self, pipeWriter):
        self.pipeWriter = pipeWriter
        subscriber._RmakePublisherProxy.__init__(self)

    def _emitEvents(self, jobId, eventList):
        self.pipeWriter.send((jobId, freeze('EventList', eventList)))
        self.pipeWriter.flush()

