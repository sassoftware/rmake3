#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import bz2
import itertools
import sys
import time

from conary.lib import log
from conary.repository import trovesource

from rmake import errors
from rmake import failure
from rmake.lib import apiutils
from rmake.lib.apiutils import thaw, freeze
from rmake.build import buildtrove
from rmake.build import publisher

from xmlrpclib import dumps, loads

jobStates = {
    'JOB_STATE_INIT'        : 0,
    'JOB_STATE_FAILED'      : 1,
    'JOB_STATE_QUEUED'      : 2,
    'JOB_STATE_STARTED'     : 3,
    'JOB_STATE_BUILD'       : 4,
    'JOB_STATE_BUILT'       : 5,
    'JOB_STATE_COMMITTING'  : 6,
    'JOB_STATE_COMMITTED'   : 7,
    'JOB_STATE_LOADING'     : 8,
    'JOB_STATE_LOADED'      : 9,
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

ACTIVE_STATES = [ JOB_STATE_BUILD, JOB_STATE_QUEUED, JOB_STATE_STARTED,
                  JOB_STATE_LOADING, JOB_STATE_LOADED ]

def _getStateName(state):
    return stateNames[state]

class _AbstractBuildJob(trovesource.SearchableTroveSource):
    """
        Abstract BuildJob.

        Contains basic data for a build job and methods for accessing that
        data.  Most setting of this data (after creation) should be through 
        methods that are defined in BuildJob subclass.
    """
    def __init__(self, jobId=None, troveList=[], state=JOB_STATE_INIT,
                 start=0, status='', finish=0, failureReason=None,
                 uuid='', pid=0, configs=None, owner=''):
        trovesource.SearchableTroveSource.__init__(self)
        self.jobId = jobId
        self.uuid = uuid
        self.pid = pid
        self.owner = owner
        self.state = state
        self.status = status
        self.troveContexts = {}
        self.troves = {}
        self.start = start
        self.finish = finish
        self.failureReason = failureReason
        self.searchAsDatabase()
        if not configs:
            configs = {}
        self.configs = configs
        for troveTup in troveList:
            self.addTrove(*troveTup)

    def trovesByName(self, name):
        """
            Method required for Searchable trovesource.

            Takes a name and returns sources or binaries associated
            with this job.
        """
        if name.endswith(':source'):
            return [ x for x in self.troveContexts if x[0] == name ]
        else:
            troveTups = []
            for trove in self.iterTroves():
                for troveTup in trove.getBinaryTroves():
                    if troveTup[0] == name:
                        troveTups.append(troveTup)
            return troveTups

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
        return (x[0] for x in self.troves.iteritems() if not x[1].isSpecial())

    def iterLoadableTroves(self):
        return (x for x in self.troves.itervalues() if not x.isSpecial())

    def getSpecialTroves(self):
        return [ x for x in self.troves.itervalues() if x.isSpecial() ]

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
        return self.state in (JOB_STATE_LOADING, JOB_STATE_LOADED,
            JOB_STATE_STARTED, JOB_STATE_BUILD)

    def isCommitted(self):
        return self.state == JOB_STATE_COMMITTED

    def isCommitting(self):
        return self.state == JOB_STATE_COMMITTING

    def isLoading(self):
        return self.state == JOB_STATE_LOADING

    def isLoaded(self):
        return self.state == JOB_STATE_LOADED

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

class _FreezableBuildJob(_AbstractBuildJob):
    """
        Adds freeze methods to build job.  Allows the build job
        to be sent over xmlrpc.
    """

    attrTypes = {'jobId'          : 'int',
                 'pid'            : 'int',
                 'uuid'           : 'str',
                 'state'          : 'int',
                 'status'         : 'str',
                 'start'          : 'float',
                 'finish'         : 'float',
                 'failureReason'  : 'FailureReason',
                 'troves'         : 'manual',
                 'configs'        : 'manual'}


    def __freeze__(self, sanitize=False):
        d = {}
        for attr, attrType in self.attrTypes.iteritems():
            d[attr] = freeze(attrType, getattr(self, attr))
        if self.jobId is None:
            d['jobId'] = ''

        d['troves'] = [ (freeze('troveContextTuple', x[0]),
                         x[1] and freeze('BuildTrove', x[1]) or '')
                        for x in self.troves.iteritems() ]
        if sanitize:
            freezeClass = 'SanitizedBuildConfiguration'
        else:
            freezeClass = 'BuildConfiguration'
        d['configs'] = [ (x[0], freeze(freezeClass, x[1]))
                              for x in self.configs.items() ]
        return d

    def writeToFile(self, path, sanitize=False):
        jobStr = dumps((self.__freeze__(sanitize=sanitize),))
        outFile = bz2.BZ2File(path, 'w')
        outFile.write(jobStr)
        outFile.close()

    @classmethod
    def loadFromFile(class_, path):
        jobStr = bz2.BZ2File(path).read()
        jobDict, = loads(jobStr)[0]
        return class_.__thaw__(jobDict)

    @classmethod
    def __thaw__(class_, d):
        types = class_.attrTypes

        new = class_(thaw(types['jobId'], d.pop('jobId')), [],
                     thaw(types['state'], d.pop('state')))
        if new.jobId is '':
            new.jobId = None

        for attr, value in d.iteritems():
            setattr(new, attr, thaw(types[attr], value))

        new.troves = dict((thaw('troveContextTuple', x[0]),
                           x[1] and thaw('BuildTrove', x[1] or None))
                            for x in new.troves)
        for (n,v,f,c) in new.troves:
            new.troveContexts.setdefault((n,v,f), []).append(c)
        configs = dict((x[0], thaw('BuildConfiguration', x[1]))
                       for x in d['configs'])
        if configs:
            new.setConfigs(configs)
        else:
            new.configs = {}
        return new


class BuildJob(_FreezableBuildJob):
    """
        Buildjob object with "publisher" methods.  The methods below
        are used to make state changes to the job and then publish 
        those changes to the job to subscribers.
    """

    def __init__(self, *args, **kwargs):
        self._publisher = publisher.JobStatusPublisher()
        _FreezableBuildJob.__init__(self, *args, **kwargs)
        self._amOwner = False

    def amOwner(self):
        """
            Returns True if this process owns this job, otherwise
            returns False.  Processes that don't own jobs are not allowed
            to update other processes about the job's status (this avoids
            message loops).
        """
        return self._amOwner

    def own(self):
        self._amOwner = True

    def disown(self):
        self._amOwner = False

    def getPublisher(self):
        return self._publisher

    def log(self, message):
        """
            Publish log message "message" to trove subscribers.
        """
        self._publisher.jobLogUpdated(self, message)

    def setBuildTroves(self, buildTroves):
        """
            Sets the give 
        """
        _FreezableBuildJob.setBuildTroves(self, buildTroves)
        publisher = self.getPublisher()
        for trove in buildTroves:
            trove.setPublisher(publisher)
            trove.own()
        self._publisher.buildTrovesSet(self)

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
        self.getPublisher().cork()

        self._setState(JOB_STATE_FAILED, str(failureReason), failureReason)
        for trove in self.iterTroves():
            if trove.isStarted():
                trove.troveFailed(failureReason)
        self.getPublisher().uncork()

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
        self._publisher.jobStateUpdated(self, state, status, *args)

apiutils.register(apiutils.api_freezable(BuildJob))

def NewBuildJob(db, troveTups, jobConfig=None, state=JOB_STATE_INIT, uuid=''):
    """
        Create a new build job that is attached to the database - i.e.
        that will send notifications to the database when it is updated.

        Note this is the preferred way to create a BuildJob, since it gives
        the job a jobId.
    """
    job = BuildJob(None, troveTups, state=state, uuid=uuid)
    if jobConfig:
        job.setMainConfig(jobConfig)
    db.addJob(job)
    return job
