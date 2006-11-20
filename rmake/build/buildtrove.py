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

from conary.build import recipe
from conary.conaryclient import cmdline
from conary.deps import deps
from conary import trove

from rmake.build import failure
from rmake.lib import apiutils
from rmake.lib.apiutils import freeze, thaw

troveStates = {
    'TROVE_STATE_INIT'      : 0,
    'TROVE_STATE_FAILED'    : 1,
    'TROVE_STATE_BUILDABLE' : 2,
    'TROVE_STATE_BUILDING'  : 4,
    'TROVE_STATE_BUILT'     : 5,
    }

recipeTypes = {
    'RECIPE_TYPE_UNKNOWN'      : 0,
    'RECIPE_TYPE_PACKAGE'      : 1,
    'RECIPE_TYPE_FILESET'      : 2,
    'RECIPE_TYPE_GROUP'        : 3,
    'RECIPE_TYPE_INFO'         : 4,
    'RECIPE_TYPE_REDIRECT'     : 5,
}


# assign troveStates to this module's dict so that they can be referenced with
# module 'getattribute' notation (eg; buildtrove.TROVE_STATE_INIT)
sys.modules[__name__].__dict__.update(troveStates)
sys.modules[__name__].__dict__.update(recipeTypes)

stateNames = dict([(x[1], x[0].rsplit('_', 1)[-1].capitalize()) \
                   for x in troveStates.iteritems()])
recipeTypeNames = dict([(x[1], x[0].rsplit('_', 1)[-1].capitalize()) \
                       for x in recipeTypes.iteritems()])


stateNames.update({
    TROVE_STATE_INIT      : 'Initialized',
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
    if recipe.isFilesetRecipe(recipeClass):
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
                 pid=0, recipeType=RECIPE_TYPE_PACKAGE):
        assert(name.endswith(':source'))
        self.jobId = jobId
        self.name = name
        self.version = version
        self.flavor = flavor
        self.buildRequirements = set()
        self.builtTroves = set()
        self.packages = set([name.split(':')[0]])
        self.state = state
        self.status = status
        self.logPath = logPath
        self.start = start
        self.finish = finish
        self.failureReason = failureReason
        self.pid = pid
        self.recipeType = recipeType

    def __repr__(self):
        return "<BuildTrove('%s=%s[%s]')>" % (self.getName(),
                                          self.getVersion().trailingLabel(),
                                          self.getFlavor())

    def getName(self):
        return self.name

    def getVersion(self):
        return self.version

    def getFlavor(self):
        return self.flavor

    def getNameVersionFlavor(self):
        return (self.name, self.version, self.flavor)

    def setState(self, newState):
        self.state = newState

    def getState(self):
        return self.state

    def isFailed(self):
        return self.state == TROVE_STATE_FAILED

    def isBuilt(self):
        return self.state == TROVE_STATE_BUILT

    def isBuildable(self):
        return self.state == TROVE_STATE_BUILDABLE

    def isBuilding(self):
        return self.state == TROVE_STATE_BUILDING

    def isUnbuilt(self):
        return self.state in (TROVE_STATE_INIT, TROVE_STATE_BUILDABLE)

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

    def setBuildRequirements(self, buildReqs):
        self.buildRequirements = set(buildReqs)

    def addBuildRequirements(self, buildReqs):
        self.buildRequirements.update(buildReqs)

    def iterBuildRequirements(self):
        return iter(self.buildRequirements)

    def getBuildRequirements(self):
        return list(self.buildRequirements)

    def getBuildRequirementSpecs(self):
        return [ cmdline.parseTroveSpec(x) 
                 for x in self.iterBuildRequirements() ]

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

    def __hash__(self):
        return hash(self.getNameVersionFlavor())

    def __eq__(self, other):
        return self.getNameVersionFlavor() == other.getNameVersionFlavor()

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
                 'buildRequirements' : 'troveSpecList',
                 'builtTroves'       : 'troveTupleList',
                 'failureReason'     : 'FailureReason',
                 'packages'          : None,
                 'pid'               : 'int',
                 'state'             : 'int',
                 'status'            : 'str',
                 'logPath'           : 'str',
                 'start'             : 'float',
                 'finish'            : 'float',
                 }

    def __freeze__(self):
        d = {}
        for attr, attrType in self.attrTypes.iteritems():
            d[attr] = freeze(attrType, getattr(self, attr))
        d['packages'] = list(d['packages'])
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
        self._publisher = None
        _FreezableBuildTrove.__init__(self, *args, **kwargs)
 
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

    def troveResolvingBuildReqs(self):
        """
            Log step in dep resolution.

            Publishes log message.
        """
        self.log('Resolving build requirements')

    def troveResolvedButDelayed(self, newDeps):
        """
            Log step in dep resolution.

            Publishes log message.
        """
        self.log('Resolved buildreqs include %s other troves scheduled to be built - delaying' % (len(newDeps),))

    def prepChroot(self):
        """
            Log step in building.

            Publishes log message.
        """
        self.log('Preparing Chroot')

    def troveBuilding(self, logPath='', pid=0):
        """
            Set state to BUILDING.

            Publishes state change.

            @param logPath: path to build log on the filesystem.
            @param pid: pid of build process.
        """

        self.pid = pid
        self.start = time.time()
        self.logPath = logPath
        self._setState(TROVE_STATE_BUILDING, status='')

    def troveBuilt(self, changeSet):
        """
            Sets the trove state to built.

            Publishes this change.

            @param changeSet: changeset created for this trove.
        """
        self.finish = time.time()
        self.pid = 0
        self.setBuiltTroves([x.getNewNameVersionFlavor() for
                             x in changeSet.iterNewTroveList() ])
        self._setState(TROVE_STATE_BUILT, '', changeSet)

    def troveFailed(self, failureReason):
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
        self._setState(TROVE_STATE_FAILED, status=str(self.getFailureReason()))

    def troveMissingBuildReqs(self, buildReqs):
        """
            Sets the trove state to failed, sets failure reason to missing 
            buildreqs.

            Publishes this change.

            @param buildReqs: missing build reqs
            @type buildReqs: list of strings that are the missing buildreqs.
        """
        self.troveFailed(failure.MissingBuildreqs(buildReqs))

    def troveMissingDependencies(self, troveAndDepSets):
        """
            Sets the trove state to failed, sets failure reason to missing 
            dependencies.

            Publishes this change.

            @param troveAndDepSets: missing dependencies
            @type troveAndDepSets: (trove, depSet) list.
        """
        self.troveFailed(failure.MissingDependencies(troveAndDepSets))

    def _setState(self, state, status=None, *args):
        oldState = self.state
        self.state = state
        if status is not None:
            self.status = status
        if self._publisher:
            self._publisher.troveStateUpdated(self, state, oldState, *args)

apiutils.register(apiutils.api_freezable(BuildTrove))
