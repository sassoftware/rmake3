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
import os
import resource
import signal
import sys
import tempfile
import time
import traceback

from conary.build import cook,use
from conary.deps import deps
from conary.lib import epdb
from conary.lib import log,util
from conary import conaryclient
from conary import versions
from conary.deps.deps import ThawFlavor

from rmake.build.failure import BuildFailed, FailureReason
from rmake.lib import flavorutil
from rmake.lib import logfile
from rmake.lib import recipeutil
from rmake.lib.apiutils import thaw, freeze

class CookResults(object):
    def __init__(self, name, version, flavor):
        self.name = name
        self.version = version
        self.flavor = flavor
        self.status = ''
        self.csFile = ''
        self.pid = 0
        self.failureReason = None
        self.signal = ''

    def exitedNormally(self):
        return not self.signal

    def setExitStatus(self, status):
        self.status = status

    def setExitSignal(self, signal):
        self.signal = signal

    def getExitSignal(self):
        return self.signal

    def getExitStatus(self):
        return self.status

    def setChangeSetFile(self, csFile):
        self.csFile = csFile

    def getChangeSetFile(self):
        return self.csFile

    def setFailureReason(self, reason):
        self.failureReason = reason

    def getFailureReason(self):
        return self.failureReason

    def isBuildSuccess(self):
        return self.exitedNormally() and not self.status

    def __freeze__(self):
        d = self.__dict__.copy()
        d['pid'] = self.pid
        d['version'] = str(self.version)
        d['flavor'] = self.flavor.freeze()
        d['failureReason'] = freeze('FailureReason', self.failureReason)
        return d

    @staticmethod
    def __thaw__(d):
        d = d.copy()
        new = CookResults(d.pop('name'),
                          versions.VersionFromString(d.pop('version')),
                          ThawFlavor(d.pop('flavor')))
        new.__dict__.update(d)
        new.failureReason = thaw('FailureReason', new.failureReason)
        return new


def cookTrove(cfg, name, version, flavor, targetLabel):
    util.mkdirChain(cfg.root + '/tmp')
    fd, csFile = tempfile.mkstemp(dir=cfg.root + '/tmp',
                                  prefix='rmake-%s-' % name,
                                  suffix='.ccs')
    os.close(fd)
    os.chmod(csFile, 0644) # we need to be able to read this file 
                           # from the rmake server

    logPath = cfg.root + '/tmp/%s-%s.log' % (name, version.trailingRevision())
    logFile = logfile.LogFile(logPath)

    results = CookResults(name, version, flavor)

    # ignore child output problems
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)

    inF, outF = os.pipe()
    pid = os.fork()
    if not pid:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        os.close(inF)
        try:
            try:
                os.setpgrp()
                # don't accidentally make world writable files
                os.umask(0022)
                # don't allow us to create core dumps
                resource.setrlimit(resource.RLIMIT_CORE, (0,0))
                logFile.redirectOutput()

                _cookTrove(cfg, name, version, flavor, targetLabel, csFile,
                           failureFd=outF)
            except Exception, msg:
                errMsg = 'Error cooking %s=%s[%s]: %s' % \
                                        (name, version, flavor, str(msg))
                _buildFailed(outF, errMsg, traceback.format_exc())
                os._exit(1)
            else:
                os._exit(0)
        finally:
            # some kind of error occurred if we get here.
            os._exit(1)
    else:
        os.close(outF)
        return logPath, pid, (results, pid, inF, csFile)


def getResults(results, pid, inF, csFile):
    (gotResult, status) = os.waitpid(pid, os.WNOHANG)
    if not gotResult:
        return None

    if os.WIFSIGNALED(status):
        results.setExitSignal(os.WTERMSIG(status))
    else:
        assert(os.WIFEXITED(status))
        results.setExitStatus(os.WEXITSTATUS(status))

    if results.isBuildSuccess():
        results.setChangeSetFile(csFile)
    elif results.getExitSignal():
        results.setFailureReason(BuildFailed('Build exited with signal %s' % results.getExitSignal()))
    else:
        errReason = []
        buffer = os.read(inF, 1024)
        while buffer:
            errReason.append(buffer)
            buffer = os.read(inF, 1024)
        errReason = ''.join(errReason)
        errTag, data = errReason.split('\002', 1)
        results.setFailureReason(thaw('FailureReason', (errTag, data)))
    os.close(inF)
    return results

def stopBuild(results, pid, inF, csFile):
    log.info('killing %s' % pid)
    try:
        os.kill(-pid, signal.SIGTERM)
    except OSError, err:
        if err.errno != err.ENOENT:
            raise
        else:
            log.warning('cooking pid %s did not exit' % pid)

    timeSlept = 0
    while timeSlept < 10:
        gotResult, status = os.waitpid(pid, os.WNOHANG)
        if gotResult:
            break
        else:
            time.sleep(.5)
            timeSlept += .5
    os.close(inF)

    if not gotResult:
        log.warning('pid %s did not respond to kill, trying SIGKILL' % pid)
        try:
            os.kill(-pid, signal.SIGKILL)
        except OSError, err:
            if err.errno != err.ESRCH:
                raise
            else:
                return

        # just hang waiting
        gotResult, status = os.waitpid(pid, 0)
    log.info('pid %s killed' % pid)

def _buildFailed(failureFd, errMsg, traceBack):
    #if sys.stdin.isatty():
    #    epdb.post_mortem(sys.exc_info()[2])
    log.error(errMsg)
    frz = '\002'.join(str(x) for x in freeze('FailureReason',
                                BuildFailed(errMsg, traceBack)))
    if failureFd is not None:
        os.write(failureFd, frz)
        os.close(failureFd)
    os._exit(1)

def _cookTrove(cfg, name, version, flavor, targetLabel, csFile, failureFd):
    try:
        log.debug('Cooking %s=%s[%s] to %s (stored in %s)' % \
                  (name, version, flavor, targetLabel, csFile))
        repos = conaryclient.ConaryClient(cfg).getRepos()

        (loader, recipeClass, localFlags, usedFlags)  = \
            recipeutil.loadRecipeClass(repos, name, version, flavor)
    except Exception, msg:
        errMsg = 'Error loading recipe %s=%s[%s]: %s' % \
                                        (name, version, flavor, str(msg))
        _buildFailed(failureFd, errMsg, traceback.format_exc())


    try:
        # get the correct environment variables from this root
        # some packages depend on environment variables e.g. $QTDIR that 
        # are set by other packages.  
        setupEnvironment()

        # now override flags set in flavor
        # don't need to reset this flavor ever, because
        # we are in a fork
        flavorutil.setLocalFlags(localFlags)
        packageName = name.split(':')[0]
        cfg.buildFlavor = deps.overrideFlavor(cfg.buildFlavor, flavor)
        use.setBuildFlagsFromFlavor(packageName, cfg.buildFlavor)

        use.resetUsed()
        use.setUsed(usedFlags)

        # we don't want to sign packages here, if necessary, we can sign
        # them at a higher level.
        cfg.signatureKeyMap = {}
        cfg.signatureKey = None

        # if we're already on the target label, we'll assume no targeting 
        # is necessary
        if targetLabel == version.trailingLabel():
            targetLabel = None
    except Exception, msg:
        errMsg = 'Error initializing cook environment %s=%s[%s]: %s' % \
                                            (name, version, flavor, str(msg))
        _buildFailed(failureFd, errMsg, traceback.format_exc())

    try:
        os.chdir('/tmp') # make sure we're in a directory
                         # that we can write to.  Although
                         # this _shouldn't_ be an issue,
                         # conary 1.0.{19,20} require it.
        # finally actually cook the recipe!
        built = cook.cookObject(repos, cfg, recipeClass, version,
                                prep=False, macros={},
                                targetLabel=targetLabel,
                                changeSetFile=csFile,
                                alwaysBumpCount=False,
                                ignoreDeps=False,
                                logBuild=True, crossCompile=None,
                                requireCleanSources=True)
    except Exception, msg:
        errMsg = 'Error building recipe %s=%s[%s]: %s' % (name, version,
                                                          flavor, str(msg))
        _buildFailed(failureFd, errMsg, traceback.format_exc())


def setupEnvironment():
    """
    Grab a fresh copy of the environment, based on the currently installed
    troves.
    """
    skipenv = set(['DISPLAY', 'STY', 'COVERAGE_DIR'])
    for key in os.environ.keys():
        if key not in skipenv:
            del os.environ[key]
    for line in os.popen('/bin/bash -l -c env'):
        key, val = line.split('=', 1)
        if key not in skipenv:
            os.environ[key] = val[:-1]
    os.environ['LANG'] = 'C'
    os.environ['HOME'] = '/tmp/rmake'
