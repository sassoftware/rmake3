#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import time

from conary.build import recipe
from conary.conaryclient import cmdline
from conary.deps import deps
from conary.repository import changeset

from rmake import failure
from rmake.lib import flavorutil
from rmake.lib.ninamori.types import constants


TroveState = constants('TroveState',
        'INIT '         # = 0
        'FAILED '       # = 1
        'RESOLVING '    # = 2
        'BUILDABLE '    # = 3
        'WAITING '      # = 4
        'PREPARING '    # = 5
        'BUILDING '     # = 6
        'BUILT '        # = 7
        'UNBUILDABLE '  # = 8
        'PREBUILT '     # = 9
        'DUPLICATE '    # = 10
        'PREPARED '     # = 11
        )


RecipeType = constants('RecipeType',
        'UNKNOWN '      # = 0
        'PACKAGE '      # = 1
        'FILESET '      # = 2
        'GROUP '        # = 3
        'INFO '         # = 4
        'REDIRECT '     # = 5
        )


BuildType = constants('BuildType',
        'NORMAL '       # = 0
        'PREP '         # = 1
        'SPECIAL '      # = 2 (DEPRECATED)
        )


stateNames = dict([(val, str(name).capitalize())
    for (val, name) in TroveState.by_value.items()])
stateNames.update({
    TroveState.INIT: 'Initialized',
    TroveState.PREPARING: 'Creating Chroot',
    TroveState.WAITING: 'Queued',
})


def getRecipeType(recipeClass):
    if recipe.isPackageRecipe(recipeClass):
        return RecipeType.PACKAGE
    if recipe.isGroupRecipe(recipeClass):
        return RecipeType.GROUP
    if recipe.isInfoRecipe(recipeClass):
        return RecipeType.INFO
    if recipe.isRedirectRecipe(recipeClass):
        return RecipeType.REDIRECT
    if recipe.isFileSetRecipe(recipeClass):
        return RecipeType.FILESET
    return RecipeType.UNKNOWN


class _AbstractBuildTrove(object):
    """
        Base class for the trove object.
    """

    def __init__(self, jobUUID, name, version, flavor,
                 state=TroveState.INIT, status='',
                 failureReason=None, logPath='', start=0, finish=0,
                 pid=0, recipeType=RecipeType.PACKAGE,
                 chrootHost='', chrootPath='', 
                 preBuiltRequirements=None, preBuiltBinaries=None,
                 context='', flavorList=None, 
                 buildType=BuildType.NORMAL):
        # These five fields uniquely identify the build trove.
        self.jobUUID = jobUUID
        self.name = name
        self.version = version
        self.flavor = flavor
        self.context = context
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
        self.cfg = None
        if flavorList is None:
            self.flavorList = [flavor]
        else:
            self.flavorList = flavorList

    def __repr__(self):
        if self.getContext():
            context = '{%s}' % self.getContext()
        else:
            context = ''
        return "<%s('%s=%s[%s]%s')>" % (self.__class__.__name__.split('.')[-1],
                                        self.getName(),
                                        self.getVersion().trailingLabel(),
                                        self.getFlavor(), context)

    def getName(self):
        return self.name

    def getVersion(self):
        return self.version

    def getLabel(self):
        return self.version.trailingLabel()

    def getHost(self):
        return self.version.trailingLabel().getHost()

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

    def getTroveString(self, withContext=True):
        return '%s=%s[%s]%s' % (self.name, self.version, self.flavor,
                self.getContextStr())

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
        return self.state == TroveState.FAILED

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
        return self.state in (TroveState.FAILED, TroveState.UNBUILDABLE)

    def isPrebuilt(self):
        return self.state == TroveState.PREBUILT

    def isDuplicate(self):
        return self.state == TroveState.DUPLICATE

    def isBuilt(self):
        return self.state == TroveState.BUILT


    def isFinished(self):
        return (self.isFailed() or self.isBuilt()
                or self.isDuplicate() or self.isPrepared())

    def isPrepOnly(self):
        return self.buildType == BuildType.PREP

    def isPrepared(self):
        return self.state == TroveState.PREPARED

    def isBuildable(self):
        return self.state == TroveState.BUILDABLE

    def isResolving(self):
        return self.state == TroveState.RESOLVING

    def isBuilding(self):
        return self.state == TroveState.BUILDING

    def isPreparing(self):
        return self.state == TroveState.PREPARING

    def isWaiting(self):
        return self.state == TroveState.WAITING

    def isStarted(self):
        return (not self.isFinished()
                and not self.state == TroveState.INIT)

    def isUnbuilt(self):
        return self.state in (TroveState.INIT, TroveState.BUILDABLE,
                              TroveState.WAITING, TroveState.RESOLVING,
                              TroveState.PREPARING)

    def needsBuildreqs(self):
        return self.state in (TroveState.INIT, TroveState.PREBUILT)

    def isPackageRecipe(self):
        return self.recipeType == RecipeType.PACKAGE

    def isInfoRecipe(self):
        return self.recipeType == RecipeType.INFO

    def isGroupRecipe(self):
        return self.recipeType == RecipeType.GROUP

    def isFilesetRecipe(self):
        return self.recipeType == RecipeType.FILESET

    def isRedirectRecipe(self):
        return self.recipeType == RecipeType.REDIRECT

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
        return stateNames[self.state]

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


class BuildTrove(_AbstractBuildTrove):
    """
        BuildTrove object with "publisher" methods.  The methods below
        are used to make state changes to the trove and then publish 
        those changes to the trove to subscribers. 
    """

    def __init__(self, *args, **kwargs):
        _AbstractBuildTrove.__init__(self, *args, **kwargs)
        self._publisher = None

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

    def troveLoaded(self, results):
        self.setFlavor(results.flavor)
        self.setRecipeType(results.recipeType)
        self.setLoadedSpecsList(results.loadedSpecsList)
        self.setLoadedTroves(results.loadedTroves)
        self.setDerivedPackages(results.packages)
        self.setDelayedRequirements(results.delayedRequirements)
        self.setBuildRequirements(results.buildRequirements)
        self.setCrossRequirements(results.crossRequirements)

    def troveBuildable(self):
        """
            Set trove as buildable.

            Publishes state change.
        """
        self._setState(TroveState.BUILDABLE, status='')

    def troveResolvingBuildReqs(self, host='_local_', pid=0):
        """
            Log step in dep resolution.

            Publishes log message.
        """
        self.finish = 0
        self.start = time.time()
        self.pid = pid
        self._setState(TroveState.RESOLVING,
                       'Resolving build requirements', host, pid)

    def trovePrebuilt(self, buildReqs, binaryTroves, preBuiltTime=0,
                      fastRebuild=False, logPath='', superClassesMatch=True,
                      sourceMatches=True):
        self.finish = time.time()
        self.pid = 0
        self._setState(TroveState.PREBUILT, '', buildReqs, binaryTroves)
        self.preBuiltRequirements = buildReqs
        self.preBuiltBinaries = binaryTroves
        if preBuiltTime is None:
            preBuiltTime = 0
        self.preBuiltTime = preBuiltTime
        self.fastRebuild = fastRebuild
        self.preBuiltLog = logPath
        self.superClassesMatch = superClassesMatch
        self.prebuiltSourceMatches = sourceMatches

    def prebuiltIsSourceMatch(self):
        return self.prebuiltSourceMatches

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
        self._setState(TroveState.INIT,
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
        self._setState(TroveState.INIT, '\n'.join(errMsg))

    def troveUnresolvableDepsReset(self, missingDeps):
        self.finish = time.time()
        self.pid = 0
        self._setState(TroveState.INIT,
           'Trove could not resolve dependencies, waiting until troves are built: %s' % (
                                                                missingDeps,))

    def troveQueued(self, message):
        self._setState(TroveState.WAITING, message)

    def creatingChroot(self, hostname, path):
        """
            Log step in building.

            Publishes log message.
        """
        self.chrootHost = hostname
        self.chrootPath = path
        self._setState(TroveState.PREPARING, '', hostname, path)

    def chrootFailed(self, err, traceback=''):
        f = failure.ChrootFailed(str(err), traceback)
        self.hostname = ''
        self.path = ''
        self.troveFailed(f)

    def troveBuilding(self, pid=0, settings=[]):
        """
            Set state to BUILDING.

            Publishes state change.

            @param logPath: path to build log on the filesystem.
            @param pid: pid of build process.
        """
        self.pid = pid
        self.finish = 0
        self.start = time.time()
        self._setState(TroveState.BUILDING, '', pid, settings)

    def troveAlreadyCommitted(self, troveList):
        self.setBuiltTroves(troveList)
        self.finish = time.time()
        self.setBuiltTroves(troveList)
        self._setState(TroveState.BUILT, '', troveList)

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
        self._setState(TroveState.BUILT, '', troveList)
        if prebuilt and self.preBuiltLog:
            self.logPath = self.preBuiltLog

    def trovePrepared(self):
        self.finish = time.time()
        self.pid = 0
        self._setState(TroveState.PREPARED, '')

    def troveDuplicate(self, troveList):
        self._setState(TroveState.DUPLICATE, '', troveList)

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
            state = TroveState.FAILED
        else:
            # primary failures are those failures that are directly caused
            # by something wrong.  Secondary failures are those that are due
            # to another trove failing.
            # E.g. a trove missing build reqs that are not part of the job
            # would be a primary failure.  A trove that could not build
            # because of another trove missing build reqs would be secondary.
            state = TroveState.UNBUILDABLE
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
