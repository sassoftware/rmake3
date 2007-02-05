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
import grp
import os
import pwd
import signal
import sys
import time

from optparse import OptionParser

from conary.conarycfg import ConfigFile, CfgList, CfgString, CfgBool, CfgInt
from conary.lib import options, util

from rmake.lib import logfile
from rmake.lib import logger

(NO_PARAM,  ONE_PARAM)  = (options.NO_PARAM, options.ONE_PARAM)
(OPT_PARAM, MULT_PARAM) = (options.OPT_PARAM, options.MULT_PARAM)

class DaemonConfig(ConfigFile):
    logDir         = '/var/log/'
    lockDir        = '/var/run/'
    verbose        = (CfgBool, False)

_commands = []
def _register(cmd):
    _commands.append(cmd)

class DaemonCommand(options.AbstractCommand):
    docs = {'config'             : ("Set config KEY to VALUE", "'KEY VALUE'"),
            'config-file'        : ("Read PATH config file", "PATH"),
            'verbose'            : ("Increase verobsity in output"),
            'debug-all'          : "Debug exceptions"}

    def addParameters(self, argDef):
        d = {}
        d["config"] = MULT_PARAM
        d["config-file"] = '-c', MULT_PARAM
        d["debug-all"] = '-d', NO_PARAM
        d["skip-default-config"] = NO_PARAM

        argDef[self.defaultGroup] = d

    def addConfigOptions(self, cfgMap, argDef):
        cfgMap['verbose'] = 'verbose', NO_PARAM, '-v'
        options.AbstractCommand.addConfigOptions(self, cfgMap, argDef)

    def processConfigOptions(self, cfg, cfgMap, argSet):
        for file in argSet.pop('config-file', []):
            cfg.read(file)
        options.AbstractCommand.processConfigOptions(self, cfg, cfgMap, argSet)


class ConfigCommand(DaemonCommand):
    commands = ['config']

    help = 'Display configuration for this service'

    def runCommand(self, daemon, cfg, argSet, args):
        return cfg.display()
_register(ConfigCommand)

class StopCommand(DaemonCommand):
    commands = ['stop', 'kill']

    help = 'Stop the service'

    def runCommand(self, daemon, cfg, argSet, args):
        return daemon.kill()
_register(StopCommand)

class StartCommand(DaemonCommand):
    commands = ['start']

    help = 'Start the service'

    docs = {'no-daemon': "Do not run as a daemon"}

    def addParameters(self, argDef):
        DaemonCommand.addParameters(self, argDef)
        argDef["no-daemon"] = '-n', NO_PARAM

    def runCommand(self, daemon, cfg, argSet, args):
        return daemon.start(fork=not argSet.pop('no-daemon', False))
_register(StartCommand)

class Daemon(options.MainHandler):
    '''This class contains basic daemon functions, useful for creating your own
       daemon.
    '''
    abstractCommand = DaemonCommand
    name = 'daemon'
    commandName = 'daemon'
    commandList = _commands
    user   = None
    groups = None
    loggerClass = logger.Logger
    useConaryOptions = False

    def __init__(self):
        self._logFile = None
        self.logger = self.loggerClass(self.name)
        options.MainHandler.__init__(self)

    def getLockFilePath(self):
        return os.path.join(self.cfg.lockDir, "%s.pid" % self.name)

    def removeLockFile(self):
        lockFile = self.getLockFilePath()
        try:
            os.unlink(lockFile)
        except OSError, e:
            if e.errno == errno.ENOENT:
                pass
            else:
                raise

    def getPidFromLockFile(self, warnOnError=False):
        lockFile = self.getLockFilePath()
        try:
            lock = open(lockFile, "r")
            pid = int(lock.read())
            lock.close()
            return pid
        except Exception, e:
            if warnOnError:
                self.warning("unable to open lockfile for reading: %s (%s)" % (lockFile, str(e)))
            return None

    def writePidToLockFile(self):
        lockFile = self.getLockFilePath()
        try:
            lock = open(lockFile, "w")
            lock.write("%d" % os.getpid())
            lock.close()
            return True
            lockFile = self.getLockFilePath()
        except Exception, e:
            self.warning("unable to open lockfile: %s (%s)", lockFile, str(e))
            return False

    def kill(self):
        if not os.getuid():
            if self.user:
                pwent = pwd.getpwnam(self.user)
                os.setgroups([])
                os.setgid(pwent.pw_gid)
                os.setuid(pwent.pw_uid)

        pid = self.getPidFromLockFile(warnOnError=True)
        if not pid:
            self.error("could not kill %s: no pid found." % self.name)
            sys.exit(1)

        pipeFD = os.popen("ps -p %d -o comm=" %pid)
        procName = pipeFD.readline().strip()
        pipeFD.close()
        if not procName:
            return

        if procName not in sys.argv[0]:
            self.error("pid: %d does not seem to be a valid %s." % (pid,
                                                                   self.name))
            sys.exit(1)
        self.info("killing %s pid %d" % (self.name, pid))
        try:
            os.kill(pid, signal.SIGINT)
            while True:
                # loop waiting for the process to die
                pipeFD = os.popen("ps -p %d -o comm=" %pid)
                procName = pipeFD.readline().strip()
                pipeFD.close()
                if not procName:
                    break
                time.sleep(.5)
        except OSError, e:
            if e.errno != errno.ESRCH:
                raise
            else:
                self.info("process not found; removing lock file")
                self.removeLockfile()
        else:
            #Do we really want to remove the PID?  Shouldn't we
            #let the daemon process do it?
            self.removeLockFile()

    def getLogFile(self):
        if self._logFile is not None:
            return self._logFile
        try:
            logPath = os.path.join(self.cfg.logDir, "%s.log" % self.name)
            self._logFile = logfile.LogFile(logPath)
            return self._logFile
        except OSError, err:
            self.error('error opening logfile "%s" for writing: %s',
                              logPath, err.strerror)
            sys.exit(1)

    def info(self, msg, *args):
        self.logger.info(msg, *args)

    def error(self, msg, *args):
        self.logger.error(msg, *args)

    def warning(self, msg, *args):
        self.logger.warning(msg, *args)

    def start(self, fork=True):
        if not os.getuid():
            if self.user:
                pwent = pwd.getpwnam(self.user)
                if self.groups:
                    groupIds = []
                    for group in self.groups:
                        grpent = grp.getgrnam(group)
                        groupIds.append(grpent.gr_gid)
                    os.setgroups(groupIds)
                else:
                    os.setgroups([])
                os.setgid(pwent.pw_gid)
                os.setuid(pwent.pw_uid)
        logPath = os.path.join(self.cfg.logDir, "%s.log" % self.name)
        self.logger.logToFile(logPath)

        pid = self.getPidFromLockFile()
        if pid:
            # check if the pid is actually valid...
            pipeFD = os.popen("ps -p %s -o pid="% pid)
            pidLine = pipeFD.readline()
            pipeFD.close()

            if str(pid) in pidLine:
                self.error("Daemon already running as pid %s", pid)
                sys.exit(1)
            else:
                self.info("Old %s pid seems to be invalid. killing." % self.name)
                self.kill()

        self.info("using Conary in %s",
                  os.path.dirname(sys.modules['conary'].__file__))
        if fork:
            pid = os.fork()

            if pid == 0:
                # redirect stdout and stderr to <name>.log
                logFile = self.getLogFile()
                logFile.redirectOutput(close=True)
                null = os.open("/dev/null", os.O_RDONLY)
                os.dup2(null, sys.stdin.fileno())
                os.close(null)

                pid = os.fork()
                if pid == 0:
                    # abandon the controlling tty by resetting session id
                    os.setsid()

                    sys.stdout.flush()
                    sys.stderr.flush()
                    self.daemonize()
                else:
                    timeSlept = 0
                    while timeSlept < 60:
                        lockFilePid = self.getPidFromLockFile()
                        if not lockFilePid or lockFilePid != pid:
                            foundPid, status = os.waitpid(pid, os.WNOHANG)
                            if foundPid:
                                os._exit(1)
                            else:
                                time.sleep(.5)
                                timeSlept += 1
                        else:
                            os._exit(0)
                    os._exit(1)
            else:
                pid, status = os.waitpid(pid, 0)
                if os.WIFEXITED(status):
                    rc = os.WEXITSTATUS(status)
                    return rc
                else:
                    self.error('process killed with signal %s' % os.WTERMSIG(status))
                    return 1
        else:
            sys.excepthook = util.genExcepthook()
            self.daemonize()
            return 0


    def daemonize(self):
        '''Call this to execute the daemon'''
        self.writePidToLockFile()
        try:
            try:
                self.doWork()
            except KeyboardInterrupt:
                self.info("interrupt caught; exiting")
        finally:
            self.removeLockFile()

    def doWork(self):
        raise NotImplementedError

    def runCommand(self, thisCommand, cfg, argSet, otherArgs, **kw):
        self.cfg = cfg
        return options.MainHandler.runCommand(self, thisCommand, self, cfg, 
                                             argSet, otherArgs, **kw)

    def usage(self, rc=1, showAll=False):
        print '%s: back end to rMake build tool' % self.commandName
        if not showAll:
            print
            print 'Common Commands (use "%s help" for the full list)' % self.commandName
        return options.MainHandler.usage(self, rc, showAll=showAll)

    def mainWithExceptionHandling(self, argv):
        from rmake import errors
        try:
            argv = list(argv)
            debugAll = '--debug-all' in argv
            if debugAll:
                debuggerException = Exception
                argv.remove('--debug-all')
            else:
                debuggerException = errors.RmakeInternalError
            sys.excepthook = errors.genExcepthook(debug=debugAll,
                                                  debugCtrlC=debugAll)
            self.main(argv)
        except debuggerException, err:
            raise
        except errors.RmakeError, err:
            self.logger.error(err)
            return 1
        except KeyboardInterrupt:
            pass
        return 0
