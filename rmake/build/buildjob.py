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
import sys
import time

from conary.lib import log
from conary.repository import trovesource

from rmake.lib import apiutils
from rmake.lib.apiutils import thaw, freeze

from rmake.build import failure
from rmake.build import subscribe

jobStates = {
    'JOB_STATE_INIT'        : 0,
    'JOB_STATE_FAILED'      : 1,
    'JOB_STATE_QUEUED'      : 2,
    'JOB_STATE_STARTED'     : 3,
    'JOB_STATE_BUILD'       : 4,
    'JOB_STATE_BUILT'       : 5,
    'JOB_STATE_COMMITTING'  : 6,
    'JOB_STATE_COMMITTED'   : 7,
    }

# assign jobStates to this module's dict so that they can be referenced with
# module 'getattribute' notation (eg; buildjob.JOB_STATE_INIT)
sys.modules[__name__].__dict__.update(jobStates)

stateNames = dict([(x[1], x[0].split('_')[-1].capitalize()) \
                   for x in jobStates.iteritems()])

# only need to specify names that differ from their variable name
stateNames.update({
    JOB_STATE_INIT       : 'Initialized',
    JOB_STATE_BUILD      : 'Building',
})

def _getStateName(state):
    return stateNames[state]

class _AbstractBuildJob(object):
    def __init__(self):
        self.status = ''
        self.state = None
        self.failureReason = None
        self._statusLogger = subscribe.JobStatusPublisher()

    def getStatusLogger(self):
        return self._statusLogger

    def jobQueued(self):
        self._setStatus(JOB_STATE_QUEUED, 'Job Queued')

    def jobStarted(self, message, pid=0):
        self.start = time.time()
        self.pid = pid
        self._setStatus(JOB_STATE_STARTED, message)

    def jobBuilding(self, message):
        self._setStatus(JOB_STATE_BUILD, message)

    def jobPassed(self, message):
        self.finish = time.time()
        self._setStatus(JOB_STATE_BUILT, message)

    def jobFailed(self, failureReason=''):
        self.finish = time.time()
        if isinstance(failureReason, str):
            failureReason = failure.BuildFailed(failureReason)
        self.failureReason = failureReason
        self.getStatusLogger().cork()

        self._setStatus(JOB_STATE_FAILED, str(failureReason))
        for trove in self.iterTroves():
            if trove.isUnbuilt() or trove.isBuilding():
                trove.troveFailed(failureReason)
        self.getStatusLogger().uncork()

    def jobStopped(self, failureReason=''):
        # right now jobStopped is an alias for job failed.
        # but I think we may wish to give it its own state
        # at some point so I'm distinguishing it here.
        self.jobFailed(failure.JobStopped(failureReason))

    def jobCommitting(self):
        self._setStatus(JOB_STATE_COMMITTING, '')

    def jobCommitFailed(self, message=''):
        if self.failureReason:
            # this job was previously failed, so revert to its failed state.
            self._setStatus(JOB_STATE_FAILED, str(self.failureReason))
        self._setStatus(JOB_STATE_BUILT, 'Commit failed: %s' % message)

    def jobCommitted(self, troveTupleList):
        self._setStatus(JOB_STATE_COMMITTED, '')
        logger = self.getStatusLogger()
        logger.jobCommitted(self, troveTupleList)

    def exceptionOccurred(self, err, tb):
        failureReason = failure.InternalError(str(err), tb)
        self.finish = time.time()
        self.failureReason = failureReason
        self._setStatus(JOB_STATE_FAILED, str(failureReason))

    def log(self, message):
        self.status = message
        self._statusLogger.jobLogUpdated(self, message)

    def _setStatus(self, state, status, *args):
        self.state = state
        self.status = status
        self._statusLogger.jobStateUpdated(self, state, status, args)

class BuildJob(_AbstractBuildJob, trovesource.SearchableTroveSource):

    attrTypes = {'jobId'          : 'int',
                 'pid'            : 'int',
                 'uuid'           : 'str',
                 'state'          : 'int',
                 'status'         : 'str',
                 'start'          : 'float',
                 'finish'         : 'float',
                 'failureReason'  : 'FailureReason',
                 'troves'         : 'manual'}

    def __init__(self, jobId=None, troveList=[], state=JOB_STATE_INIT,
                 start=0, status='', finish=0, failureReason=None,
                 uuid='', pid=0):
        _AbstractBuildJob.__init__(self)
        trovesource.SearchableTroveSource.__init__(self)
        self.jobId = jobId
        self.uuid = uuid
        self.pid = pid
        self.state = state
        self.status = status
        self.troves = {}
        self.start = start
        self.finish = finish
        self.failureReason = failureReason
        self.searchAsDatabase()
        for troveTup in troveList:
            self.addTrove(*troveTup)

    def trovesByName(self, name):
        if name.endswith(':source'):
            return [ x for x in self.troves if x[0] == name ]
        else:
            troveTups = []
            for trove in self.troves.itervalues():
                for troveTup in trove.getBinaryTroves():
                    if troveTup[0] == name:
                        troveTups.append(troveTup)
            return troveTups

    def getStateName(self):
        return _getStateName(self.state)

    def getFailureReason(self):
        return self.failureReason

    def isQueued(self):
        return self.state == JOB_STATE_QUEUED

    def isBuilding(self):
        return self.state in (JOB_STATE_STARTED, JOB_STATE_BUILD)

    def isBuilt(self):
        return self.state in (JOB_STATE_BUILT,)

    def isFailed(self):
        return self.state in (JOB_STATE_FAILED,)

    def isFinished(self):
        return self.state in (JOB_STATE_FAILED, JOB_STATE_BUILT,
                              JOB_STATE_COMMITTED)

    def isRunning(self):
        return self.state in (JOB_STATE_STARTED, JOB_STATE_BUILD)

    def isCommitted(self):
        return self.state == JOB_STATE_COMMITTED

    def trovesInProgress(self):
        for trove in self.troves:
            if trove.isBuilding() or trove.isBuildable():
                return True
        return False

    def iterTroveList(self):
        return self.troves.iterkeys()

    def iterTrovesByState(self, state):
        return (x for x in self.iterTroves() if x.state == state)

    def iterTroves(self):
        return self.troves.itervalues()

    def getTrovesByName(self, name):
        name = name.split(':')[0] + ':source'
        return [ x for x in self.troves if x[0] == name ]

    def iterFailedTroves(self):
        return (x for x in self.troves.itervalues() if x.isFailed())

    def iterBuiltTroves(self):
        return (x for x in self.troves.itervalues() if x.isBuilt())

    def iterUnbuiltTroves(self):
        return (x for x in self.troves.itervalues() if x.isUnbuilt())

    def iterBuildingTroves(self):
        return (x for x in self.troves.itervalues() if x.isBuilding())

    def hasBuildingTroves(self):
        return self._hasTrovesByCheck('isBuilding')

    def iterBuildableTroves(self):
        return (x for x in self.troves.itervalues() if x.isBuildable())

    def hasBuildableTroves(self):
        return self._hasTrovesByCheck('isBuildable')

    def _hasTrovesByCheck(self, check):
        for trove in self.troves.itervalues():
            if getattr(trove, check)():
                return True
        return False

    def getTrove(self, name, version, flavor):
        return self.troves[name, version, flavor]

    def addTrove(self, name, version, flavor, buildTrove=None):
        if buildTrove:
            buildTrove.setStatusLogger(self.getStatusLogger())
        self.troves[name, version, flavor] = buildTrove

    def setBuildTroves(self, buildTroves):
        self.troves = {}
        for trove in buildTroves:
            trove.jobId = self.jobId
            trove.setStatusLogger(self.getStatusLogger())
            self.troves[trove.getNameVersionFlavor()] = trove
        self._statusLogger.buildTrovesSet(self)

    def __freeze__(self):
        d = {}
        for attr, attrType in self.attrTypes.iteritems():
            d[attr] = freeze(attrType, getattr(self, attr))

        d['troves'] = [ (freeze('troveTuple', x[0]),
                        x[1] and freeze('BuildTrove', x[1]) or '')
                        for x in self.troves.iteritems() ]
        return d

    @classmethod
    def __thaw__(class_, d):
        types = class_.attrTypes

        new = class_(thaw(types['jobId'], d.pop('jobId')), [],
                     thaw(types['state'], d.pop('state')))

        for attr, value in d.iteritems():
            setattr(new, attr, thaw(types[attr], value))

        new.troves = dict((thaw('troveTuple', x[0]),
                           x[1] and thaw('BuildTrove', x[1] or None))
                            for x in new.troves)
        return new

apiutils.register(apiutils.api_freezable(BuildJob))

def NewBuildJob(db, troveTups, jobConfig=None, state=JOB_STATE_INIT, uuid=''):
    job = BuildJob(None, troveTups, state=state, uuid=uuid)
    db.addJob(job, jobConfig)
    db.subscribeToJob(job)
    return job
