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
"""
Dependency Handler and DependencyState classes
"""

import itertools
import time

from conary import conaryclient
from conary.conaryclient import cmdline, resolve
from conary.deps import deps
from conary.lib import graph, log
from conary.local import database, deptable
from conary.repository import trovesource

from rmake.build.buildstate import AbstractBuildState

FAILURE_REASON_FAILED = 0
FAILURE_REASON_BUILDREQ = 1
FAILURE_REASON_DEP = 2

class DependencyBasedBuildState(AbstractBuildState):
    """
        Dependency based build state.  Contains information about what troves
        are buildable and also, there dependency relationships.
    """

    def __init__(self, searchSource, sourceTroves, cfg):
        self.trovesByPackage = {}
        self.buildReqTroves = {}

        self.depGraph = graph.DirectedGraph()
        self.builtSource = BuiltTroveSource()

        self.searchSource = searchSource
        self._defaultBuildReqs = cfg.defaultBuildReqs

        AbstractBuildState.__init__(self, sourceTroves)

    def addTroves(self, sourceTroves):
        AbstractBuildState.addTroves(self, sourceTroves)
        sourceTroves = [ x for x in sourceTroves if not x.isFailed() ]
        [ self.depGraph.addNode(trove) for trove in sourceTroves ]
        for trove in sourceTroves:
            for package in trove.getDerivedPackages():
                self.trovesByPackage.setdefault(package, []).append(trove)

        for trove in sourceTroves:
            trove.addBuildRequirements(self._defaultBuildReqs)
            for buildReq in trove.getBuildRequirementSpecs():
                name, label, flavor = buildReq
                pkg = name.split(':')[0]
                providingTroves = self.trovesByPackage.get(pkg, [])
                for provTrove in providingTroves:
                    # this trove must be built after the providing trove,
                    # which means that provTrove should be a leaf first.
                    if (flavor is None or
                        provTrove.getFlavor().toStrongFlavor().satisfies(
                                                flavor.toStrongFlavor())):
                        # only add edges for nodes that are 
                        # likely to be on a satisfying branch or flavor,
                        # otherwise we'll create unnecessary cycles.
                        self.dependsOn(trove, provTrove, buildReq)

    def dependsOn(self, trove, provTrove, req):
        self.depGraph.addEdge(trove, provTrove, req)

    def troveBuilt(self, trove, binaryTroveList):
        binaryTroves = self.searchSource.getTroves(binaryTroveList)
        for binTrove in binaryTroves:
            self.builtSource.addTrove(binTrove.getNameVersionFlavor(),
                                      binTrove.getProvides(),
                                      binTrove.getRequires())
        self.buildReqTroves.pop(trove, False)
        self.depGraph.delete(trove)

    def troveFailed(self, trove):
        self.depGraph.delete(trove)
        self.buildReqTroves.pop(trove, False)

    def troveBuildable(self, trove, buildReqs):
        self.buildReqTroves[trove] = buildReqs

    def hasBuildableTroves(self):
        return bool(self.buildReqTroves)

    def getSolutionsForBuildReq(self, trove, buildReq):
        for childTrove, reason in self.depGraph.getChildren(trove,
                                                             withEdges=True):
            if reason == buildReq:
                yield childTrove

    def getTrovesRequiringTrove(self, trove):
        for parentTrove, reason in self.depGraph.getParents(trove,
                                                           withEdges=True):
            yield parentTrove, reason

    def getBuildReqTroves(self, trove):
        return self.buildReqTroves[trove]

    def popBuildableTrove(self):
        trove = self.buildReqTroves.keys()[0]
        return (trove, self.buildReqTroves.pop(trove))

    def getDependencyGraph(self):
        return self.depGraph

    def getTrovesByPackage(self, pkg):
        return self.trovesByPackage.get(pkg, [])

    def getBuiltTrovesSource(self):
        return self.builtSource

class DependencyHandler(object):
    """
        Updates what troves are buildable based on dependency information.
    """
    def __init__(self, statusLog, cfg, searchSource, logger, buildTroves):
        self.depState = DependencyBasedBuildState(searchSource, buildTroves,
                                                  cfg)
        self.client = conaryclient.ConaryClient(cfg)
        self.logger = logger
        if cfg.resolveTrovesOnly:
            self.installLabelPath = None
        else:
            self.installLabelPath = cfg.installLabelPath

        self.installFlavor = cfg.flavor

        statusLog.subscribe(statusLog.TROVE_BUILT, self.troveBuilt)
        statusLog.subscribe(statusLog.TROVE_BUILDING, self.troveBuilding)
        statusLog.subscribe(statusLog.TROVE_FAILED, self.troveFailed)
        statusLog.subscribe(statusLog.TROVE_STATE_UPDATED,
                            self.troveStateUpdated)

        if cfg.resolveTroveTups:
            resolveTroves = []
            searchSourceTroves = []
            allResolveTroveTups = list(itertools.chain(*cfg.resolveTroveTups))
            allResolveTroves = searchSource.getTroves(allResolveTroveTups,
                                                      withFiles=False)
            resolveTrovesByTup = dict((x.getNameVersionFlavor(), x)
                                      for x in allResolveTroves)

            for resolveTupList in cfg.resolveTroveTups:
                resolveTroves = [ resolveTrovesByTup[x] 
                                  for x in resolveTupList ]
                searchSourceTroves.append(resolveTroves)

            self.searchSource = DepHandlerSource(
                               self.depState.getBuiltTrovesSource(),
                               searchSourceTroves,
                               searchSource,
                               useInstallLabelPath=not cfg.resolveTrovesOnly)

            self.resolveSource = DepResolutionByTroveLists(cfg, None,
                                                           searchSourceTroves)
        else:
            self.resolveSource = DepResolutionByTroveLists(cfg, None, [])
            self.searchSource = DepHandlerSource(
                                           self.depState.getBuiltTrovesSource(),
                                           [], searchSource)

    def troveStateUpdated(self, trove, state, status):
        self.depState._setState(trove, trove.state)

    def hasBuildableTroves(self):
        return self.depState.hasBuildableTroves()

    def getBuildReqTroves(self, trove):
        return self.depState.getBuildReqTroves(trove)

    def troveFailed(self, trove, *args):
        publisher = trove.getPublisher()
        publisher.unsubscribe(publisher.TROVE_FAILED, self.troveFailed)
        publisher.cork()
        self._troveFailed(trove)
        publisher.subscribe(publisher.TROVE_FAILED, self.troveFailed)
        publisher.uncork()

    def _troveFailed(self, trove):
        depState = self.depState

        toFail = [(trove, None)]

        while toFail:
            trove, failReason = toFail.pop()
            for reqTrove, buildReq in depState.getTrovesRequiringTrove(trove):

                found = False
                for provTrove in depState.getSolutionsForBuildReq(reqTrove,
                                                                  buildReq):
                    if provTrove == trove:
                        continue
                    else:
                        found = True
                        break

                if not found:
                    toFail.append((reqTrove, buildReq))

            if failReason:
                if isinstance(failReason[0], str):
                    # FIXME: we _must_ figure out a better way to 
                    # determine whether the failure is due to a buildreq
                    # or dep
                    trove.troveMissingBuildReqs([failReason])
                else:
                    trove.troveMissingDependencies([failReason])
                depState.troveFailed(trove)
            else:
                depState.troveFailed(trove)

    def troveBuilding(self, trove, logPath='', pid=0):
        pass

    def popBuildableTrove(self):
        return self.depState.popBuildableTrove()

    def jobPassed(self):
        return self.depState.jobPassed()

    def troveBuilt(self, trove, troveList):
        self.depState.troveBuilt(trove, troveList)

    def updateBuildableTroves(self, limit=1, callback=None):
        """
            Update the set of troves that are buildable
            @param newlyAvail - troves that are newly available, and should
            therefore be considered for satisfying build requirements.
        """
        oldVerbosity = log.getVerbosity()
        log.setVerbosity(log.DEBUG)

        self._updateBuildableTroves(self.client,
                                    self.depState.getDependencyGraph(), 
                                    self.searchSource, limit=limit)
        log.setVerbosity(oldVerbosity)

    def _resolveBuildReqs(self, client, trv, searchSource):
        """
            Find the set of troves that must be installed for the set
            of buildreqs associated with this trove.

            Searches for build req and runtime req solutions in the following
            order:

            1. Search the group, w/o consideration of order
            2. Search the label of the trove we're building, followed
               by the reset of the labelPath
            2. Search the label path.
        """

        def _findBestSolution(trove, (name, versionSpec, flavorSpec), 
                              solutions):
            """Given a trove, a buildRequirement troveSpec, and a set of troves
               that may match that buildreq, find the best trove.
            """
            if len(solutions) == 1:
                return solutions[0]
            # flavorSpec _should_ have been handled by findTroves.
            # However, in some cases it's not - for example, if two different
            # flavors of a trove are in the same group (glibc, e.g.).
            filter = resolve.DepResolutionMethod(None, None)
            result = None
            affDict = dict.fromkeys(x[0] for x in solutions)
            for flavor in self.installFlavor:
                result = filter.selectResolutionTrove(trove, None, None,
                                                      solutions, flavor,
                                                      affDict)
                if result:
                    break
            return result

        if not trv.getBuildRequirements():
            return True, set(), None, None

        finalToInstall = {}

        # we allow build requirements to be matched against anywhere on the
        # install label.  Create a list of all of this trove's labels,
        # from latest on branch to earliest to use as search labels.
        self.logger.debug('   finding buildreqs for %s....' % trv.getName())
        start = time.time()

        # NOTE: turn off automatic adding of buildLabel to buildReq
        # search path.  The user can add it on their own if they'd
        # like, but there's no way to turn it off if we enable it...
        #
        #troveVersion = trv.getVersion()
        #troveLabel = troveVersion.trailingLabel()
        #if troveLabel.getNamespace() == 'LOCAL':
        #     # exception - if the namespace is LOCAL, it's a local
        #     # cook of a .recipe file - don't include the internal
	#     # repository in the search path
        #    if not troveVersion.branch().hasParentBranch():
        #        installLabelPath = []
        #    else:
        #        installLabelPath = [troveVersion.branch().parentBranch().label()]
        #else:
        #    installLabelPath = [troveLabel]

        if self.installLabelPath is None:
            installLabelPath = None
            searchFlavor = None
        else:
            installLabelPath = []
            installLabelPath.extend(self.installLabelPath)
            searchFlavor =  client.cfg.flavor

        result = searchSource.findTroves(installLabelPath,
                                         trv.getBuildRequirementSpecs(),
                                         searchFlavor, allowMissing=True,
                                         acrossLabels=False)

        okay = True

        buildReqTups = []
        missingBuildReqs = []
        for troveSpec in trv.getBuildRequirementSpecs():
            solutions = result.get(troveSpec, [])
            if not solutions:
                missingBuildReqs.append(troveSpec)
                okay = False
            else:
                sol = _findBestSolution(trv, troveSpec, solutions)
                buildReqTups.append(sol)

        if not okay:
            self.logger.debug('could not find all buildreqs')
            return False, None, missingBuildReqs, None

        self.logger.debug('   resolving deps for %s...' % trv.getName())
        start = time.time()
        itemList = [ (x[0], (None, None), (x[1], x[2]), True)
                                                for x in buildReqTups ]

        self.resolveSource.setLabelPath(installLabelPath)

        uJob = database.UpdateJob(None)
        uJob.setSearchSource(searchSource)
        jobSet = client._updateChangeSet(itemList, uJob, useAffinity=False)
        (depList, suggMap, cannotResolve, splitJob, keepList) = \
            client.resolver.resolveDependencies(uJob, jobSet, resolveDeps=True,
                                              useRepos=False, split=False,
                                              resolveSource=self.resolveSource)

        jobSet.update((x[0], (None, None), (x[1], x[2]), False) 
                      for x in itertools.chain(*suggMap.itervalues()))
        if cannotResolve or depList:
            self.logger.debug('Failed - unresolved deps - took %s seconds' % (time.time() - start))
            return False, None, [], depList + cannotResolve

        self.logger.debug('   took %s seconds' % (time.time() - start))
        return True, jobSet, None, None

    def _addPackages(self, searchSource, jobSet):
        """
            Adds packages for buildReqs we're installing (if they're
            not already added)
        """
        neededPackages = set((x[0].split(':')[0], x[2][0], x[2][1])
                             for x in jobSet)
        neededPackages.difference_update((x[0], x[2][0], x[2][1])
                                         for x in jobSet)
        hasTroves = searchSource.hasTroves(neededPackages)
        if isinstance(hasTroves, list):
            hasTroves = dict(itertools.izip(neededPackages, hasTroves))
        jobSet.update([(x[0][0], (None, None), (x[0][1], x[0][2]), False)
                       for x in hasTroves.items() if x[1]])


    def _addResolutionDeps(self, trv, jobSet):
        found = set()
        for name, oldInfo, newInfo, isAbs in jobSet:
            providingTroves = self.depState.getTrovesByPackage(name.split(':')[0])
            if not providingTroves:
                continue
            if self.depState.builtSource.hasTrove(name, *newInfo):
                continue

            for provTrove in providingTroves:
                if self.depState.isUnbuilt(provTrove):
                    if provTrove == trv:
                        # no point in delaying this trove if the only
                        # dependency is on ourselves!
                        continue
                    found.add(provTrove)
                    # FIXME: we need to have the actual dependency name!
                    self.depState.dependsOn(trv, provTrove, (trv.getNameVersionFlavor(), deps.parseDep('trove: %s' % name)))
        return found

    def _updateBuildableTroves(self, client, depGraph, searchSource, 
                               skipTroves=[], limit=1):
        """ Returns the set of troves that currently considered potentially 
            buildable, breaking a dependency cycle if necesa
        """

        def cycleNodeOrder(node):
            numParentsChildren = [len(list(depGraph.iterChildren(x))) 
                                    for x in depGraph.getParents(node)]
            if numParentsChildren:
                return min(numParentsChildren)
            else:
                return 0


        buildable = sorted(depGraph.getLeaves())
        needsBuildReqs = [ x for x in buildable if x.needsBuildreqs() ]
        skipped = []
        found = []
        if buildable and not needsBuildReqs:
            return True
        self.logger.debug('updating set of buildable troves')
        buildable = needsBuildReqs

        if buildable:
            skipped = [ x for x in buildable if x in skipTroves ]
            buildable = [ x for x in buildable if x not in skipTroves ]
            self.logger.debug('buildable: %s - attempting to resolve buildreqs' % buildable)
            buildable = sorted(buildable, reverse=True)
            while buildable:
                trv = buildable.pop()
                self.logger.debug('attempting to resolve buildreqs for %s=%s[%s]' % trv.getNameVersionFlavor())
                trv.troveResolvingBuildReqs()
                success, buildReqs, failedReqs, failedDeps \
                                = self._resolveBuildReqs(client, trv,
                                                         searchSource)
                if success:
                    self. _addPackages(searchSource, buildReqs)
                    newDeps = self._addResolutionDeps(trv, buildReqs)
                    if not newDeps:
                        trv.troveBuildable()
                        found.append(trv)
                        self.depState.troveBuildable(trv, buildReqs)
                        if limit and len(found) >= limit:
                            break
                    else:
                        # there are runtime reqs that are being
                        # rebuild.
                        # Try rebuilding those first, it is possible
                        # it will be needed by a lot of things so trying
                        # to build it now might help.
                        for depTrv in newDeps:
                            if depTrv in buildable:
                                buildable.remove(depTrv)
                                buildable.append(depTrv)
                        trv.troveResolvedButDelayed(newDeps)
                else:
                    if failedReqs:
                        trv.troveMissingBuildReqs(failedReqs)
                    else:
                        assert(failedDeps)
                        trv.troveMissingDependencies(failedDeps)
        if self.hasBuildableTroves() or depGraph.isEmpty():
            return True

        # no leaves in the dep graph at this point - we've got to break a dep
        # cycle.  There's no great way to break a cycle, unless you have some 
        # external knowledge about what packages are more 'basic'.
        checkedTroves = {}
        self.logger.debug('cycle detected!')

        while True:
            start = time.time()
            compGraph = depGraph.getStronglyConnectedGraph()
            self.logger.debug('building graph took %0.2f seconds' % (time.time() - start))
            leafCycles = compGraph.getLeaves()

            checkedSomething = False
            for cycleTroves in leafCycles:
                self.logger.debug('cycle involves %s troves' % len(cycleTroves))

                cycleTroves = [x[1] for x in sorted((cycleNodeOrder(x), x) \
                                                    for x in cycleTroves)]
                for trv in cycleTroves:
                    if trv in checkedTroves:
                        continue

                    checkedSomething = True
                    trv.troveResolvingBuildReqs()
                    success, buildReqs, failedReqs, failedDeps \
                                    = self._resolveBuildReqs(client, trv,
                                                             searchSource)
                    if success:
                        trv.troveBuildable()
                        self.depState.troveBuildable(trv, buildReqs)
                        self.logger.debug('Removing edge %s' % trv)
                        depGraph.deleteEdges(trv)
                        return True
                    elif failedReqs:
                        trv.troveMissingBuildReqs(failedReqs)
                    else:
                        assert(failedDeps)
                        trv.troveMissingDependencies(failedDeps)

            if not checkedSomething:
                return False

class DepHandlerSource(trovesource.TroveSourceStack):
    def __init__(self, builtTroveSource, troveListList, repos,
                 useInstallLabelPath=True):
        self.repos = repos
        if troveListList:
            troveSources = []
            for troveList in troveListList:
                allTroves = itertools.chain((x.getNameVersionFlavor() for x in troveList), *( x.iterTroveList(weakRefs=True, strongRefs=True) for x in troveList))
                troveSources.append(trovesource.SimpleTroveSource(allTroves))

            self.sources = [builtTroveSource] + troveSources
            if useInstallLabelPath:
                self.sources.append(repos)
        else:
            self.sources = [builtTroveSource, repos]

    def resolveDependenciesByGroups(self, troveList, depList):
        sugg = self.sources[0].resolveDependencies(None, depList)
        sugg2 = self.repos.resolveDependenciesByGroups(troveList, depList)
        for depSet, trovesByDep in sugg.iteritems():
            for idx, troveList in enumerate(trovesByDep):
                if not troveList:
                    troveList.extend(sugg2[depSet][idx])
        return sugg


class BuiltTroveSource(trovesource.SimpleTroveSource):
    """
        Trove source that is used for dep resolution and buildreq satisfaction 
        only - it does not contain references to the changesets that are added
    """
    def __init__(self):
        self.depDb = deptable.DependencyDatabase()
        trovesource.SimpleTroveSource.__init__(self)
        self.idMap = []
        self.idx = 0

    def addTrove(self, troveTuple, provides, requires):
        self._trovesByName.setdefault(troveTuple[0],set()).add(troveTuple)

        self.idMap.append(troveTuple)
        self.depDb.add(self.idx, provides, requires)
        self.idx += 1

    def addChangeSet(self, cs):
        for idx, trvCs in enumerate(cs.iterNewTroveList()):
            self.addTrove(trvCs.getNewNameVersionFlavor(), trvCs.getProvides(),
                          trvCs.getRequires())

    def resolveDependencies(self, label, depList):
        suggMap = self.depDb.resolve(label, depList)
        for depSet, solListList in suggMap.iteritems():
            newSolListList = []
            for solList in solListList:
                newSolListList.append([ self.idMap[x] for x in solList ])
            suggMap[depSet] = newSolListList
        return suggMap

class DepResolutionByTroveLists(resolve.DepResolutionMethod):
    """ 
        Resolve by trove list first and then resort back to label
        path.  Also respects intra-trove deps.  If foo:runtime
        requires foo:lib, it requires exactly the same version of foo:lib.
    """
    def __init__(self, cfg, db, troveLists):
        self.installLabelPath = cfg.installLabelPath
        self.searchByLabelPath = False
        self.troveListsIndex = 0
        self.troveLists = troveLists
        self.depList = None
        resolve.DepResolutionMethod.__init__(self, cfg, db)

    def setLabelPath(self, labelPath):
        self.installLabelPath = labelPath

    def _getIntraTroveDeps(self, depList):
        suggsByDep = {}
        intraDeps = {}
        for troveTup, depSet in depList:
            pkgName = troveTup[0].split(':', 1)[0]
            for dep in depSet.iterDepsByClass(deps.TroveDependencies):
                if (dep.name.startswith(pkgName) 
                    and dep.name.split(':', 1)[0] == pkgName):
                    troveToGet = (dep.name, troveTup[1], troveTup[2])
                    l = suggsByDep.setdefault(dep, [])
                    l.append(troveToGet)
                    intraDeps.setdefault(depSet, {}).setdefault(dep, l)
        return intraDeps

    def prepareForResolution(self, depList):
        newDepList = [x[1] for x in depList]
        if not depList:
            self.index = 0 
            self.troveListsIndex = 0
            return False
        if newDepList == self.depList:
            # no new dep resolution matches, increment counters
            # if lists are exhausted, return False.
            if not self.searchByLabelPath:
                self.troveListsIndex += 1
                if self.troveListsIndex == len(self.troveLists):
                    if not self.installLabelPath:
                        self.troveListsIndex = 0
                        return False
                    self.searchByLabelPath = True
                    self.index = 0
            else:
                self.index += 1
                if self.index == len(self.installLabelPath):
                    self.index = 0
                    self.troveListsIndex = 0
                    return False
        else:
            self.searchByLabelPath = not self.troveLists
            self.troveListsIndex = 0
            self.index = 0

        self.depList = newDepList

        # need to get intratrove deps while we still have the full dependency
        # request information - including what trove the dep arises from.
        intraDeps = self._getIntraTroveDeps(depList)
        self.intraDeps = intraDeps
        return True

    def _resolveIntraTroveDeps(self, intraDeps):
        trovesToGet = []
        for depSet, deps in intraDeps.iteritems():
            for dep, troveTups in deps.iteritems():
                trovesToGet.extend(troveTups)
        hasTroves = self.troveSource.hasTroves(trovesToGet)
        if isinstance(hasTroves, list):
            hasTroves = dict(itertools.izip(trovesToGet, hasTroves))

        results = {}
        for depSet, deps in intraDeps.iteritems():
            d = {}
            results[depSet] = d
            for dep, troveTups in deps.iteritems():
                d[dep] = [ x for x in troveTups if hasTroves[x] ]
        return results


    def resolveDependencies(self):
        intraDepSuggs = self._resolveIntraTroveDeps(self.intraDeps)
        if self.searchByLabelPath:
            sugg = self.troveSource.resolveDependencies(
                                          self.installLabelPath[self.index],
                                          self.depList)
        else:
            sugg = self.troveSource.resolveDependenciesByGroups(
                                        self.troveLists[self.troveListsIndex],
                                        self.depList)

        for depSet, intraDeps in self.intraDeps.iteritems():
            for idx, (depClass, dep) in enumerate(depSet.iterDeps(sort=True)):
                if depClass.tag == deps.DEP_CLASS_TROVES:
                    if (dep in intraDepSuggs[depSet]
                        and intraDepSuggs[depSet][dep]):
                        sugg[depSet][idx] = intraDepSuggs[depSet][dep]

        return sugg
