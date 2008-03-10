#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import sys
import time

from conary.build import recipe
from conary.conaryclient import cmdline
from conary.deps import deps
from conary.repository import changeset
from conary import trove

from rmake import failure
from rmake.build import publisher
from rmake.lib import apiutils
from rmake.lib.apiutils import freeze, thaw
from rmake.lib import flavorutil

troveStates = {
    'TROVE_STATE_INIT'        : 0,
    'TROVE_STATE_FAILED'      : 1,
    'TROVE_STATE_RESOLVING'   : 2,
    'TROVE_STATE_BUILDABLE'   : 3,
    'TROVE_STATE_WAITING'     : 4,
    'TROVE_STATE_PREPARING'   : 5,
    'TROVE_STATE_BUILDING'    : 6,
    'TROVE_STATE_BUILT'       : 7,
    'TROVE_STATE_UNBUILDABLE' : 8,
    'TROVE_STATE_PREBUILT'    : 9,
    'TROVE_STATE_DUPLICATE'   : 10,
    'TROVE_STATE_PREPARED'    : 11,
}

recipeTypes = {
    'RECIPE_TYPE_UNKNOWN'      : 0,
    'RECIPE_TYPE_PACKAGE'      : 1,
    'RECIPE_TYPE_FILESET'      : 2,
    'RECIPE_TYPE_GROUP'        : 3,
    'RECIPE_TYPE_INFO'         : 4,
    'RECIPE_TYPE_REDIRECT'     : 5,
}

buildTypes = {
    'TROVE_BUILD_TYPE_NORMAL'        : 0,
    'TROVE_BUILD_TYPE_PREP'          : 1,
}


# assign troveStates to this module's dict so that they can be referenced with
# module 'getattribute' notation (eg; buildtrove.TROVE_STATE_INIT)
sys.modules[__name__].__dict__.update(troveStates)
sys.modules[__name__].__dict__.update(recipeTypes)
sys.modules[__name__].__dict__.update(buildTypes)

stateNames = dict([(x[1], x[0].rsplit('_', 1)[-1].capitalize()) \
                   for x in troveStates.iteritems()])
recipeTypeNames = dict([(x[1], x[0].rsplit('_', 1)[-1].capitalize()) \
                       for x in recipeTypes.iteritems()])


stateNames.update({
    TROVE_STATE_INIT      : 'Initialized',
    TROVE_STATE_PREPARING : 'Creating Chroot',
    TROVE_STATE_WAITING   : 'Queued',
})

def _getStateName(state):
    return stateNames[state]

def _getRecipeTypeName(recipeType):
    return recipeTypeNames[recipeType]

def getRecipeType(recipeClass):
    if recipe.isPackageRecipe(recipeClass):
        return RECIPE_TYPE_PACKAGE
    if recipe.isGroupRecipe(recipeClass):
        return RECIPE_TYPE_GROUP
    if recipe.isInfoRecipe(recipeClass):
        return RECIPE_TYPE_INFO
    if recipe.isRedirectRecipe(recipeClass):
        return RECIPE_TYPE_REDIRECT
    if recipe.isFileSetRecipe(recipeClass):
        return RECIPE_TYPE_FILESET
    return RECIPE_TYPE_UNKNOWN

TROVE_STATE_LIST = sorted(troveStates.values())


class _AbstractBuildTrove:
    """
        Base class for the trove object.
    """

    def __init__(self, jobId, name, version, flavor,
                 state=TROVE_STATE_INIT, status='',
                 failureReason=None, logPath='', start=0, finish=0,
                 pid=0, recipeType=RECIPE_TYPE_PACKAGE,
                 chrootHost='', chrootPath='', 
                 preBuiltRequirements=None, preBuiltBinaries=None,
                 context='', flavorList=None, 
                 buildType=TROVE_BUILD_TYPE_NORMAL):
        assert(name.endswith(':source'))
        self.jobId = jobId
        self.name = name
        self.version = version
        self.flavor = flavor
        assert(isinstance(flavor, deps.Flavor))
        self.buildRequirements = set()
        self.delayedRequirements = set()
        self.crossRequirements = set()
        self.builtTroves = set()
        self.loadedTroves = []
        self.loadedSpecsList = [{}]
        self.packages = set([name.split(':')[0]])
        self.state = state
        self.status = status
        self.logPath = logPath
        self.start = start
        self.finish = finish
        self.failureReason = failureReason
        self.pid = pid
        self.buildType = buildType
        self.chrootHost = chrootHost
        self.chrootPath = chrootPath
        self.recipeType = recipeType
        self.preBuiltRequirements = None
        self.preBuiltBinaries = preBuiltBinaries
        self.preBuiltTime = 0
        self.preBuildFast = 0
        self.preBuiltLog = ''
        self.isPrimary = False
        self.context = context
        self.cfg = None
        if flavorList is None:
            self.flavorList = [flavor]

    def __repr__(self):
        if self.getContext():
            context = '{%s}' % self.getContext()
        else:
            context = ''
        return "<BuildTrove('%s=%s[%s]%s')>" % (self.getName(),
                                          self.getVersion().trailingLabel(),
                                          self.getFlavor(), context)

    def getName(self):
        return self.name

    def getVersion(self):
        return self.version

    def getLabel(self):
        return self.version.trailingLabel()

    def getFlavor(self):
        return self.flavor

    def getFullFlavor(self):
        return deps.overrideFlavor(self.cfg.buildFlavor, self.flavor)

    def getFlavorList(self):
        return self.flavorList

    def getLoadedSpecsList(self):
        return self.loadedSpecsList

    def getLoadedTroves(self):
        return self.loadedTroves

    def setPrimaryTrove(self):
        self.isPrimary = True

    def isPrimaryTrove(self):
        return self.isPrimary

    def setLoadedTroves(self, loadedTroves):
        self.loadedTroves = loadedTroves

    def setLoadedSpecsList(self, loadedSpecsList):
        self.loadedSpecsList = [dict(x) for x in loadedSpecsList]

    def setFlavorList(self, flavorList):
        self.flavorList = flavorList

    def getNameVersionFlavor(self, withContext=False):
        if withContext:
            return (self.name, self.version, self.flavor, self.context)
        return (self.name, self.version, self.flavor)

    def getContext(self):
        return self.context

    def getContextStr(self):
        if self.context:
            return '{%s}' % self.context
        else:
            return ''

    def setFlavor(self, flavor):
        self.flavor = flavor
        self.flavorList = [flavor]

    def setRecipeType(self, recipeType):
        self.recipeType = recipeType


    def setConfig(self, configObj):
        self.cfg = configObj

    def setState(self, newState):
        self.state = newState

    def getPrebuiltRequirements(self):
        return self.preBuiltRequirements

    def getPrebuiltBinaries(self):
        return self.preBuiltBinaries

    def getState(self):
        return self.state

    def isPrimaryFailure(self):
        return self.state == TROVE_STATE_FAILED

    def hasTargetArch(self):
        return flavorutil.hasTarget(self.flavor)

    def isCrossCompiled(self):
        # cross compiler tool chain tools are not cross compiled.
        # At least, in our simplified world they're not.
        if not self.hasTargetArch():
            return False
        isCrossTool = flavorutil.getCrossCompile(self.flavor)[2]
        return not isCrossTool

    def isFailed(self):
        return self.state in (TROVE_STATE_FAILED, TROVE_STATE_UNBUILDABLE)

    def isPrebuilt(self):
        return self.state == TROVE_STATE_PREBUILT

    def isDuplicate(self):
        return self.state == TROVE_STATE_DUPLICATE

    def isBuilt(self):
        return self.state == TROVE_STATE_BUILT


    def isFinished(self):
        return (self.isFailed() or self.isBuilt()
                or self.isDuplicate() or self.isPrepared())

    def isPrepOnly(self):
        return self.buildType == TROVE_BUILD_TYPE_PREP

    def isPrepared(self):
        return self.state == TROVE_STATE_PREPARED

    def isBuildable(self):
        return self.state == TROVE_STATE_BUILDABLE

    def isResolving(self):
        return self.state == TROVE_STATE_RESOLVING

    def isBuilding(self):
        return self.state == TROVE_STATE_BUILDING

    def isPreparing(self):
        return self.state == TROVE_STATE_PREPARING

    def isWaiting(self):
        return self.state == TROVE_STATE_WAITING

    def isStarted(self):
        return (not self.isFinished()
                and not self.state == TROVE_STATE_INIT)

    def isUnbuilt(self):
        return self.state in (TROVE_STATE_INIT, TROVE_STATE_BUILDABLE,
                              TROVE_STATE_WAITING, TROVE_STATE_RESOLVING,
                              TROVE_STATE_PREPARING)

    def needsBuildreqs(self):
        return self.state in (TROVE_STATE_INIT, TROVE_STATE_PREBUILT)

    def isPackageRecipe(self):
        return self.recipeType == RECIPE_TYPE_PACKAGE

    def isInfoRecipe(self):
        return self.recipeType == RECIPE_TYPE_INFO

    def isGroupRecipe(self):
        return self.recipeType == RECIPE_TYPE_GROUP

    def isFilesetRecipe(self):
        return self.recipeType == RECIPE_TYPE_FILESET

    def isRedirectRecipe(self):
        return self.recipeType == RECIPE_TYPE_REDIRECT

    def setBuiltTroves(self, troveList):
        self.builtTroves = set(troveList)

    def iterBuiltTroves(self):
        return iter(self.builtTroves)

    def setDelayedRequirements(self, delayedReqs):
        self.delayedRequirements = delayedReqs

    def getDelayedRequirements(self):
        return self.delayedRequirements

    def isDelayed(self):
        return bool(self.delayedRequirements)

    def setBuildRequirements(self, buildReqs):
        self.buildRequirements = set(buildReqs)

    def setCrossRequirements(self, crossReqs):
        self.crossRequirements = set(crossReqs)

    def setLoadedSpecs(self, loadedSpecs):
        self.loadedSpecsList = [dict(loadedSpecs)]

    def addBuildRequirements(self, buildReqs):
        self.buildRequirements.update(buildReqs)

    def iterBuildRequirements(self):
        return iter(self.buildRequirements)


    def getBuildRequirements(self):
        return list(self.buildRequirements)

    def getBuildRequirementSpecs(self):
        return [ cmdline.parseTroveSpec(x) 
                 for x in self.iterBuildRequirements() ]

    def getCrossRequirements(self):
        return list(self.crossRequirements)

    def getCrossRequirementSpecs(self):
        return [ cmdline.parseTroveSpec(x)
                 for x in self.getCrossRequirements() ]

    def getLoadedSpecs(self):
        return dict(self.loadedSpecsList[0])

    def iterAllLoadedSpecs(self):
        stack = [self.getLoadedSpecs()]
        while stack:
            specDict = stack.pop()
            for troveSpec, (troveTup, subLoadDict) in specDict.iteritems():
                yield cmdline.parseTroveSpec(troveSpec), troveTup
                stack.append(subLoadDict)

    def setDerivedPackages(self, packages):
        self.packages = set(packages)

    def getDerivedPackages(self):
        return self.packages

    def setBinaryTroves(self, troves):
        self.builtTroves = set(troves)

    def getBinaryTroves(self):
        return self.builtTroves

    def getFailureReason(self):
        return self.failureReason

    def setFailureReason(self, failureReason):
        self.failureReason = failureReason

    def getStateName(self):
        return _getStateName(self.state)

    def getChrootHost(self):
        return self.chrootHost

    def getChrootPath(self):
        return self.chrootPath

    def getConfig(self):
        return self.cfg

    def __hash__(self):
        return hash(self.getNameVersionFlavor(True))

    def __eq__(self, other):
        return self.getNameVersionFlavor(True) == other.getNameVersionFlavor(True)

    def __cmp__(self, other):
        return cmp(self.getNameVersionFlavor(), other.getNameVersionFlavor())

class _FreezableBuildTrove(_AbstractBuildTrove):
    """
        "Freezable" build trove can be frozen and unfrozen into a dictionary
        of low-level objects in order to be sent via xmlrpc.
    """
    attrTypes = {'jobId'             : 'int',
                 'name'              : 'str',
                 'version'           : 'version',
                 'flavor'            : 'flavor',
                 'context'           : 'str',
                 'crossRequirements' : 'set',
                 'buildRequirements' : 'set',
                 'builtTroves'       : 'troveTupleList',
                 'failureReason'     : 'FailureReason',
                 'packages'          : None,
                 'pid'               : 'int',
                 'state'             : 'int',
                 'status'            : 'str',
                 'logPath'           : 'str',
                 'start'             : 'float',
                 'finish'            : 'float',
                 'chrootHost'        : 'str',
                 'chrootPath'        : 'str',
                 'loadedSpecsList'   : 'LoadSpecsList',
                 'flavorList'        : 'flavorList',
                 'buildType'         : 'int',
                 }

    def __freeze__(self):
        d = {}
        for attr, attrType in self.attrTypes.iteritems():
            d[attr] = freeze(attrType, getattr(self, attr))
        d['packages'] = list(d['packages'])
        if self.jobId is None:
            d['jobId'] = ''
        return d

    @classmethod
    def __thaw__(class_, d):
        types = class_.attrTypes
        new = class_(thaw(types['jobId'], d.pop('jobId')),
                     thaw(types['name'], d.pop('name')),
                     thaw(types['version'], d.pop('version')),
                     thaw(types['flavor'], d.pop('flavor')),
                     thaw(types['state'], d.pop('state')))
        d['packages'] = set(d['packages'])
        if new.jobId == '':
            new.jobId = None

        for attr, value in d.iteritems():
            setattr(new, attr, thaw(types[attr], value))
        return new


class BuildTrove(_FreezableBuildTrove):
    """
        BuildTrove object with "publisher" methods.  The methods below
        are used to make state changes to the trove and then publish 
        those changes to the trove to subscribers. 
    """

    def __init__(self, *args, **kwargs):
        self._publisher = publisher.JobStatusPublisher()
        self._amOwner = False
        _FreezableBuildTrove.__init__(self, *args, **kwargs)

    def amOwner(self):
        """
            Returns True if this process owns this trove, otherwise
            returns False.  Processes that don't own troves are not allowed
            to update other processes about the trove's status (this avoids
            message loops).
        """
        return self._amOwner

    def own(self):
        self._amOwner = True

    def disown(self):
        self._amOwner = False
 
    def setPublisher(self, publisher):
        """
            Set the publisher for all events emitted from this trove.
        """
        self._publisher = publisher

    def getPublisher(self):
        """
            Get the publisher for all events emitted from this trove.
        """
        return self._publisher

    def log(self, message):
        """
            Publish log message "message" to trove subscribers.
        """
        if self._publisher:
            self._publisher.troveLogUpdated(self, message)

    def troveBuildable(self):
        """
            Set trove as buildable.

            Publishes state change.
        """
        self._setState(TROVE_STATE_BUILDABLE, status='')

    def troveResolvingBuildReqs(self, host='_local_', pid=0):
        """
            Log step in dep resolution.

            Publishes log message.
        """
        self.finish = 0
        self.start = time.time()
        self.pid = pid
        self._setState(TROVE_STATE_RESOLVING,
                       'Resolving build requirements', host, pid)

    def trovePrebuilt(self, buildReqs, binaryTroves, preBuiltTime=0,
                      fastRebuild=False, logPath='', superClassesMatch=True):
        self.finish = time.time()
        self.pid = 0
        self._setState(TROVE_STATE_PREBUILT, '', buildReqs, binaryTroves)
        self.preBuiltRequirements = buildReqs
        self.preBuiltBinaries = binaryTroves
        if preBuiltTime is None:
            preBuiltTime = 0
        self.preBuiltTime = preBuiltTime
        self.fastRebuild = fastRebuild
        self.preBuiltLog = logPath
        self.superClassesMatch = superClassesMatch

    def prebuiltIsSourceMatch(self):
        if self.preBuiltBinaries[0][1].getSourceVersion() == self.version:
            return True
        if not self.version.hasParentVersion():
            return False
        parentVersion = self.version.getParentVersion()
        return self.preBuiltBinaries[0][1].getSourceVersion() == parentVersion


    def allowFastRebuild(self):
        return self.fastRebuild

    def getPrebuiltTime(self):
        return self.preBuiltTime

    def troveResolved(self, resolveResults):
        self.finish = time.time()
        self.pid = 0
        self._publisher.troveResolved(self, resolveResults)

    def troveResolvedButDelayed(self, newDeps):
        """
            Log step in dep resolution.

            Publishes log message.
        """
        # Move this trove back to initialized state so that dep resolution
        # will be attempted on it again.
        self.finish = time.time()
        self.pid = 0
        trovesToDelayFor = [ '%s=%s[%s]{%s}' % x.getNameVersionFlavor(True) for x in newDeps ]
        self._setState(TROVE_STATE_INIT,
                      'Resolved buildreqs include %s other troves scheduled to be built - delaying: \n%s' % (len(newDeps), '\n'.join(trovesToDelayFor)))

    def troveInCycleUnresolvableBuildReqs(self, missingBuildReqs):
        self.finish = time.time()
        self.pid = 0
        crossBuildReqs = [ x[1] for x in missingBuildReqs if x[0] ]
        buildReqs = [ x[1] for x in missingBuildReqs if not x[0] ]
        errMsg = []
        for type, missing in (('cross requirements', crossBuildReqs),
                              ('build requirements', buildReqs)):
            if not missing:
                continue
            strings = []
            for n,v,f in missing:
                if not v:
                    v = ''
                else:
                    v = '=%s' % v
                if f is None or f.isEmpty():
                    f = ''
                else:
                    f = '[%s]' % f
                strings.append('%s%s%s' % (n,v,f))
            errMsg.append('Trove in cycle could not resolve %s: %s' % (type, ', '.join(strings)))
        self._setState(TROVE_STATE_INIT, '\n'.join(errMsg))

    def troveUnresolvableDepsReset(self, missingDeps):
        self.finish = time.time()
        self.pid = 0
        self._setState(TROVE_STATE_INIT,
           'Trove could not resolve dependencies, waiting until troves are built: %s' % (
                                                                missingDeps,))

    def troveQueued(self, message):
        self._setState(TROVE_STATE_WAITING, message)

    def creatingChroot(self, hostname, path):
        """
            Log step in building.

            Publishes log message.
        """
        self.chrootHost = hostname
        self.chrootPath = path
        self._setState(TROVE_STATE_PREPARING, '', hostname, path)

    def chrootFailed(self, err, traceback=''):
        f = failure.ChrootFailed(str(err), traceback)
        self.hostname = ''
        self.path = ''
        self.troveFailed(f)

    def troveBuilding(self, pid=0):
        """
            Set state to BUILDING.

            Publishes state change.

            @param logPath: path to build log on the filesystem.
            @param pid: pid of build process.
        """
        self.pid = pid
        self.finish = 0
        self.start = time.time()
        self._setState(TROVE_STATE_BUILDING, '', pid)

    def troveAlreadyCommitted(self, troveList):
        self.setBuiltTroves(troveList)
        self.finish = time.time()
        self.setBuiltTroves(troveList)
        self._setState(TROVE_STATE_BUILT, '', troveList)

    def troveBuilt(self, troveList, prebuilt=False):
        """
            Sets the trove state to built.

            Publishes this change.

            @param changeSet: changeset created for this trove.
        """
        if isinstance(troveList, changeset.ChangeSet):
            troveList = [ x.getNewNameVersionFlavor()
                          for x in troveList.iterNewTroveList() ]
        self.finish = time.time()
        self.pid = 0
        self.setBuiltTroves(troveList)
        self._setState(TROVE_STATE_BUILT, '', troveList)
        if prebuilt and self.preBuiltLog:
            self.logPath = self.preBuiltLog

    def trovePrepared(self):
        self.finish = time.time()
        self.pid = 0
        self._setState(TROVE_STATE_PREPARED, '')

    def troveDuplicate(self, troveList):
        self._setState(TROVE_STATE_DUPLICATE, '', troveList)

    def troveFailed(self, failureReason, isPrimaryFailure=True):
        """
            Sets the trove state to failed.

            Publishes this change.

            @param failureReason: reason for failure.
            @type failureReason: build.failure.FailureReason or string.
        """
        self.finish = time.time()
        self.pid = 0
        if isinstance(failureReason, str):
            failureReason = failure.BuildFailed(failureReason)
        self.setFailureReason(failureReason)
        if isPrimaryFailure:
            state = TROVE_STATE_FAILED
        else:
            # primary failures are those failures that are directly caused
            # by something wrong.  Secondary failures are those that are due
            # to another trove failing.
            # E.g. a trove missing build reqs that are not part of the job
            # would be a primary failure.  A trove that could not build
            # because of another trove missing build reqs would be secondary.
            state = TROVE_STATE_UNBUILDABLE
        self._setState(state, str(failureReason), failureReason)

    def troveMissingBuildReqs(self, buildReqs, isPrimaryFailure=True):
        """
            Sets the trove state to failed, sets failure reason to missing 
            buildreqs.

            Publishes this change.

            @param buildReqs: missing build reqs
            @type buildReqs: list of strings that are the missing buildreqs.
        """
        self.troveFailed(failure.MissingBuildreqs(buildReqs),
                         isPrimaryFailure=isPrimaryFailure)

    def troveMissingDependencies(self, troveAndDepSets, isPrimaryFailure=True):
        """
            Sets the trove state to failed, sets failure reason to missing 
            dependencies.

            Publishes this change.

            @param troveAndDepSets: missing dependencies
            @type troveAndDepSets: (trove, depSet) list.
        """
        self.troveFailed(failure.MissingDependencies(troveAndDepSets),
                         isPrimaryFailure=isPrimaryFailure)

    def _setState(self, state, status=None, *args):
        oldState = self.state
        self.state = state
        if status is not None:
            self.status = status
        if self._publisher:
            self._publisher.troveStateUpdated(self, state, oldState, *args)

apiutils.register(apiutils.api_freezable(BuildTrove))

class LoadSpecs(object):

    @staticmethod
    def __freeze__(loadSpecs):
        d = {}
        stack = [(loadSpecs, d)]
        while stack:
            loadDict, frozenDict = stack.pop()
            for spec, (troveTup, subLoadDict) in loadDict.iteritems():
                newFrzDict = {}
                frozenDict[spec] = (freeze('troveTuple', troveTup), newFrzDict)
                if subLoadDict:
                    stack.append((subLoadDict, newFrzDict))
        return d

    @staticmethod
    def __thaw__(frzLoaded):
        d = {}
        stack = [(d, frzLoaded)]
        while stack:
            loadDict, frozenDict = stack.pop()
            for spec, (frzTroveTup, newFrzDict) in frozenDict.iteritems():
                subLoadDict = {}
                loadDict[spec] = (thaw('troveTuple', frzTroveTup), subLoadDict)
                if newFrzDict:
                    stack.append((subLoadDict, newFrzDict))
        return d

apiutils.register(LoadSpecs)
class LoadSpecsList(object):

    @staticmethod
    def __freeze__(loadSpecsList):
        return [ apiutils.freeze('LoadSpecs', x) for x in loadSpecsList]

    @staticmethod
    def __thaw__(frzLoadSpecsList):
        return [ apiutils.thaw('LoadSpecs', x) for x in frzLoadSpecsList ]
apiutils.register(LoadSpecsList)
