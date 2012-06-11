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


import itertools
import sys
import time

from rmake import failure
from rmake.build import buildtrove
from rmake.lib import uuid

jobStates = {
    'JOB_STATE_INIT'        : 0,
    'JOB_STATE_LOADING'     : 100,
    'JOB_STATE_BUILD'       : 101,
    'JOB_STATE_BUILT'       : 200,
    'JOB_STATE_FAILED'      : 400,
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

ACTIVE_STATES = [ JOB_STATE_INIT, JOB_STATE_BUILD, JOB_STATE_LOADING ]

def _getStateName(state):
    return stateNames[state]


class _AbstractBuildJob(object):
    """
        Abstract BuildJob.

        Contains basic data for a build job and methods for accessing that
        data.  Most setting of this data (after creation) should be through 
        methods that are defined in BuildJob subclass.
    """
    def __init__(self, jobUUID=None, jobId=None, jobName=None, troveList=(),
            state=JOB_STATE_INIT, status='', owner=None, failure=None,
            configs=(), timeStarted=None, timeUpdated=None, timeFinished=None):
        self.jobUUID = jobUUID or uuid.uuid4()
        self.jobId = jobId
        self.jobName = jobName

        self.state = state
        self.status = status
        self.owner = owner
        self.failure = failure

        self.timeStarted = timeStarted
        self.timeUpdated = timeUpdated
        self.timeFinished = timeFinished

        self.troveContexts = {}
        self.troves = {}
        self.configs = dict(configs)
        for troveTup in troveList:
            self.addTrove(*troveTup)

    def hasTrove(self, name, version, flavor, context=''):
        return (name, version, flavor, context) in self.troves

    def findTrovesWithContext(self, labelPath, troveSpecList, *args, **kw):
        contextLists = {}
        for n,v,f,c in troveSpecList:
            contextLists.setdefault((n,v,f), []).append(c)
        results = self.findTroves(labelPath, contextLists, *args, **kw)
        finalResults = {}
        for troveSpec, troveList in results.iteritems():
            for context in contextLists[troveSpec]:
                l = []
                finalResults[troveSpec + (context,)] = l
                for troveTup in troveList:
                    if context is None:
                        for c in self.troveContexts[troveTup]:
                            l.append(troveTup + (c,))
                    elif context in self.troveContexts[troveTup]:
                        l.append(troveTup + (context,))
        return finalResults

    def addTrove(self, name, version, flavor, context='', buildTrove=None):
        if buildTrove:
            assert(buildTrove.getContext() == context)
        else:
            buildTrove = buildtrove.BuildTrove(None, name, version, flavor,
                                               context=context)
        buildTrove.setPublisher(self.getPublisher())
        self.troves[name, version, flavor, context] = buildTrove
        self.troveContexts.setdefault((name, version, flavor), []).append(context)
        if buildTrove.getConfig():
            self.setTroveConfig(buildTrove, buildTrove.getConfig())

    def removeTrove(self, name, version, flavor, context=''):
        del self.troves[name,version,flavor,context]
        l = self.troveContexts[name,version,flavor]
        l.remove(context)
        if not l:
            del self.troveContexts[name, version, flavor]

    def addBuildTrove(self, buildTrove):
        self.addTrove(buildTrove=buildTrove,
                      *buildTrove.getNameVersionFlavor(withContext=True))

    def setBuildTroves(self, buildTroves):
        self.troves = {}
        self.troveContexts = {}
        for trove in buildTroves:
            trove.jobId = self.jobId
            self.troves[trove.getNameVersionFlavor(withContext=True)] = trove
            self.troveContexts.setdefault(trove.getNameVersionFlavor(), 
                                          []).append(trove.getContext())

    def iterTroveList(self, withContexts=False):
        if withContexts:
            return self.troves.iterkeys()
        else:
            return self.troveContexts.iterkeys()

    def iterLoadableTroveList(self):
        return (x[0] for x in self.troves.iteritems())

    def iterLoadableTroves(self):
        return (x for x in self.troves.itervalues())

    def getTrove(self, name, version, flavor, context=''):
        return self.troves[name, version, flavor, context]

    def iterTroves(self):
        return self.troves.itervalues()


    def getStateName(self):
        """
            Returns human-readable name for current state
        """
        return _getStateName(self.state)

    def getFailureReason(self):
        return self.failureReason

    def isBuilding(self):
        return self.state == JOB_STATE_BUILD

    def isBuilt(self):
        return self.state == JOB_STATE_BUILT

    def isFailed(self):
        return self.state == JOB_STATE_FAILED

    def isFinished(self):
        return self.state in (JOB_STATE_FAILED, JOB_STATE_BUILT)

    def isRunning(self):
        return self.state in ACTIVE_STATES

    def isLoading(self):
        return self.state == JOB_STATE_LOADING

    def trovesInProgress(self):
        for trove in self.iterTroves():
            if trove.isBuilding() or trove.isBuildable():
                return True
        return False

    def iterTrovesByState(self, state):
        return (x for x in self.iterTroves() if x.state == state)

    def getBuiltTroveList(self):
        return list(itertools.chain(*[ x.getBinaryTroves() for x in 
                                    self.iterTroves()]))

    def getTrovesByName(self, name):
        name = name.split(':')[0] + ':source'
        return [ x for x in self.troveContexts if x[0] == name ]

    def iterFailedTroves(self):
        return (x for x in self.iterTroves() if x.isFailed())

    def iterPrimaryFailureTroves(self):
        return (x for x in self.iterTroves() if x.isPrimaryFailure())

    def iterBuiltTroves(self):
        return (x for x in self.iterTroves() if x.isBuilt())

    def iterUnbuiltTroves(self):
        return (x for x in self.iterTroves() if x.isUnbuilt())

    def iterBuildingTroves(self):
        return (x for x in self.iterTroves() if x.isBuilding())

    def iterWaitingTroves(self):
        return (x for x in self.iterTroves() if x.isWaiting())

    def iterPreparingTroves(self):
        return (x for x in self.iterTroves() if x.isPreparing())

    def hasBuildingTroves(self):
        return self._hasTrovesByCheck('isBuilding')

    def iterBuildableTroves(self):
        return (x for x in self.iterTroves() if x.isBuildable())

    def hasBuildableTroves(self):
        return self._hasTrovesByCheck('isBuildable')

    def _hasTrovesByCheck(self, check):
        for trove in self.iterTroves():
            if getattr(trove, check)():
                return True
        return False

    def getMainConfig(self):
        if '' in self.configs:
            return self.configs['']

    def setMainConfig(self, config):
        self.configs[''] = config
        for trove in self.iterTroves():
            if not trove.getContext():
                trove.cfg = config

    def getConfigDict(self):
        return dict(self.configs)

    def setConfigs(self, configDict):
        self.configs = configDict
        for trove in self.iterTroves():
            trove.setConfig(configDict[trove.getContext()])

    def iterConfigList(self):
        return self.configs.itervalues()

    def setTroveConfig(self, buildTrove, configObj):
        if buildTrove.getContext() not in self.configs:
            self.configs[buildTrove.context] = configObj
        buildTrove.setConfig(configObj)

    def getTroveConfig(self, buildTrove):
        return self.configs[buildTrove.getContext()]


class BuildJob(_AbstractBuildJob):
    """
        Buildjob object with "publisher" methods.  The methods below
        are used to make state changes to the job and then publish 
        those changes to the job to subscribers.
    """

    def __init__(self, *args, **kwargs):
        _AbstractBuildJob.__init__(self, *args, **kwargs)
        self._publisher = None
        self._log = None

    def getPublisher(self):
        return self._publisher

    def setPublisher(self, publisher):
        self._publisher = publisher

    def log(self, format, *args, **kwargs):
        if self._log:
            self._log.info(format, *args, **kwargs)
        else:
            raise RuntimeError("Build job has no logger set")

    def setBuildTroves(self, buildTroves):
        """
            Sets the give 
        """
        _AbstractBuildJob.setBuildTroves(self, buildTroves)
        publisher = self.getPublisher()
        for trove in buildTroves:
            trove.setPublisher(publisher)

    def jobQueued(self, message=''):
        if not message:
            message = 'Job Queued'
        self._setState(JOB_STATE_QUEUED, message)

    def jobStarted(self, message, pid=0):
        self.start = time.time()
        self.pid = pid
        self._setState(JOB_STATE_STARTED, message)

    def jobBuilding(self, message):
        self._setState(JOB_STATE_BUILD, message)

    def jobPassed(self, message):
        self.finish = time.time()
        self._setState(JOB_STATE_BUILT, message)

    def jobLoading(self, message):
        self._setState(JOB_STATE_LOADING, message)

    def jobLoaded(self, loadResults):
        for trove in self.iterLoadableTroves():
            troveTup = trove.getNameVersionFlavor(True)
            if troveTup in loadResults:
                trove.troveLoaded(loadResults[troveTup])

        self._setState(JOB_STATE_LOADED, '', loadResults)

    def jobFailed(self, failureReason=''):
        self.finish = time.time()
        if isinstance(failureReason, str):
            failureReason = failure.BuildFailed(failureReason)
        self.failureReason = failureReason

        self._setState(JOB_STATE_FAILED, str(failureReason), failureReason)
        for trove in self.iterTroves():
            if trove.isStarted():
                trove.troveFailed(failureReason)

    def jobStopped(self, failureReason=''):
        # right now jobStopped is an alias for job failed.
        # but I think we may wish to give it its own state
        # at some point so I'm distinguishing it here.
        self.jobFailed(failure.Stopped(failureReason))

    def jobCommitting(self):
        self._setState(JOB_STATE_COMMITTING, '')

    def jobCommitFailed(self, message=''):
        if self.failureReason:
            # this job was previously failed, so revert to its failed state.
            self._setState(JOB_STATE_FAILED, str(self.failureReason))
        self._setState(JOB_STATE_BUILT, 'Commit failed: %s' % message)

    def jobCommitted(self, troveMap):
        self._setState(JOB_STATE_COMMITTED, '')
        publisher = self.getPublisher()
        publisher.jobCommitted(self, troveMap)

    def exceptionOccurred(self, err, tb):
        self.jobFailed(failure.InternalError(str(err), tb))

    def _setState(self, state, status='', *args):
        self.state = state
        self.status = status
