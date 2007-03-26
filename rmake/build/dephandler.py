#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Dependency Handler and DependencyState classes
"""

import time

from conary.deps import deps
from conary.lib import graph

from rmake.build.buildstate import AbstractBuildState

from rmake.lib.apiutils import freeze,thaw,register

FAILURE_REASON_FAILED = 0
FAILURE_REASON_BUILDREQ = 1
FAILURE_REASON_DEP = 2

class ResolveJob(object):
    def __init__(self, trove, buildCfg, builtTroves, inCycle=False):
        self.trove = trove
        self.buildCfg = buildCfg
        self.builtTroves = builtTroves
        self.inCycle = inCycle

    def getConfig(self):
        return self.buildCfg

    def getTrove(self):
        return self.trove

    def getBuiltTroves(self):
        return self.builtTroves

    def __freeze__(self):
        d = dict(trove=freeze('BuildTrove', self.trove),
                 buildCfg=freeze('BuildConfiguration', self.buildCfg),
                 builtTroves=freeze('troveTupleList', self.builtTroves),
                 inCycle=self.inCycle)
        return d

    @classmethod
    def __thaw__(class_, d):
        self = class_(**d)
        self.trove = thaw('BuildTrove', self.trove)
        self.buildCfg = thaw('BuildConfiguration', self.buildCfg)
        self.builtTroves = thaw('troveTupleList', self.builtTroves)
        return self
register(ResolveJob)


class DependencyBasedBuildState(AbstractBuildState):
    """
        Dependency based build state.  Contains information about what troves
        are buildable and also, there dependency relationships.
    """

    def __init__(self, sourceTroves, cfg):
        self.trovesByPackage = {}
        self.buildReqTroves = {}

        self.depGraph = graph.DirectedGraph()
        self.builtTroves = []

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

            # if we're loading something that we're also building
            # then we should make sure that we build the thing with the 
            # loadInstalled line secondly
            for loadSpec, sourceTup in trove.iterAllLoadedSpecs():
                name, label, flavor = loadSpec
                providingTroves = self.trovesByPackage.get(name, [])
                for provTrove in providingTroves:
                    if provTrove.getVersion() != sourceTup[1]:
                        continue
                    if (flavor is None or
                        provTrove.getFlavor().toStrongFlavor().satisfies(
                                                flavor.toStrongFlavor())):
                        # FIXME: we really shouldn't allow loadInstalled
                        # loops to occur.  It means that we're building
                        # two recipes that loadInstall each other which
                        # means that we can't even trust the buildReqs
                        # specified for each.
                        self.dependsOn(trove, provTrove, loadSpec)

    def dependsOn(self, trove, provTrove, req):
        self.depGraph.addEdge(trove, provTrove, req)

    def troveBuilt(self, trove, binaryTroveList):
        self.builtTroves.extend(binaryTroveList)
        self.buildReqTroves.pop(trove, False)
        self.depGraph.delete(trove)

    def getBuiltBinaries(self):
        return self.builtTroves

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

    def moreToDo(self):
        return not self.depGraph.isEmpty()

class DependencyHandler(object):
    """
        Updates what troves are buildable based on dependency information.
    """
    def __init__(self, statusLog, cfg, logger, buildTroves):
        self.depState = DependencyBasedBuildState(buildTroves, cfg)
        self.logger = logger
        self.cfg = cfg
        self._resolving = {}
        self.priorities = []
        self._delayed = {}

        statusLog.subscribe(statusLog.TROVE_BUILT, self.troveBuilt)
        statusLog.subscribe(statusLog.TROVE_BUILDING, self.troveBuilding)
        statusLog.subscribe(statusLog.TROVE_FAILED, self.troveFailed)
        statusLog.subscribe(statusLog.TROVE_RESOLVED,
                            self.resolutionComplete)
        statusLog.subscribe(statusLog.TROVE_STATE_UPDATED,
                            self.troveStateUpdated)

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

                if reqTrove == trove:
                    # don't refail ourselves
                    continue

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
                    trove.troveMissingBuildReqs([failReason],
                                                isPrimaryFailure=False)
                else:
                    trove.troveMissingDependencies([failReason],
                                                   isPrimaryFailure=False)
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
        # This trove built successfully, any troves that
        # were waiting for this trove to finish are now
        # fair game for dep resolution.
        for wasDelayed, delayers in self._delayed.items():
            delayers.discard(trove)
            if not delayers:
                self._delayed.pop(wasDelayed)


    def moreToDo(self):
        return self.depState.moreToDo()

    def _addResolutionDeps(self, trv, jobSet):
        found = set()
        for name, oldInfo, newInfo, isAbs in jobSet:
            providingTroves = self.depState.getTrovesByPackage(
                                                            name.split(':')[0])
            if not providingTroves:
                continue
            if (name, newInfo[0], newInfo[1]) in self.depState.builtTroves:
                continue

            for provTrove in providingTroves:
                if self.depState.isUnbuilt(provTrove):
                    if provTrove == trv:
                        # no point in delaying this trove if the only
                        # dependency is on ourselves!
                        continue
                    found.add(provTrove)
                    # FIXME: we need to have the actual dependency name!
                    self.depState.dependsOn(trv, provTrove, 
                                       (trv.getNameVersionFlavor(),
                                        deps.parseDep('trove: %s' % name)))
        return found

    def _getResolveJob(self, buildTrove, inCycle=False):
        return ResolveJob(buildTrove, self.cfg,
                          self.depState.getBuiltBinaries(),
                          inCycle=inCycle)

    def prioritize(self, trv):
        self.priorities.append(trv)

    def getPriority(self, trv):
        if trv in self.priorities:
            return self.priorities.index(trv)
        else:
            return len(self.priorities)

    def _filterTroves(self, troveList):
         return [ x for x in troveList
                  if (x.needsBuildreqs()
                      and not x in self._resolving
                      and not x in self._delayed) ]

    def getNextResolveJob(self):
        """
            Gets the info for the next trove that needs to be resolved.
        """
        depGraph = self.depState.depGraph
        if depGraph.isEmpty():
            return None

        leaves = sorted(depGraph.getLeaves(), key=self.getPriority)
        if not leaves:
            if self._resolving:
                return
            return self.getResolveJobFromCycle(depGraph)
        leaves = self._filterTroves(leaves)

        if leaves:
            self.logger.debug(
                '%s buildable: attempting to resolve buildreqs' % len(leaves))
            trv = leaves[0]
            self._resolving[trv] = True
            return self._getResolveJob(trv)

    def getResolveJobFromCycle(self, depGraph):
        def _cycleNodeOrder(node):
            """ 
            Helper fn to determine the order in which to try to break cycles.
            """
            numParentsChildren = [len(list(depGraph.iterChildren(x)))
                                    for x in depGraph.getParents(node)]
            if numParentsChildren:
                return min(numParentsChildren)
            else:
                return 0
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
                cycleTroves = self._filterTroves(cycleTroves)
                if not cycleTroves:
                    continue
                self.logger.debug('cycle involves %s troves' % len(cycleTroves))

                cycleTroves = [x[1] for x in sorted((_cycleNodeOrder(x), x) \
                                                    for x in cycleTroves)]
                trv = cycleTroves[0]
                self._resolving[trv] = True
            return self._getResolveJob(trv, inCycle=True)

    def resolutionComplete(self, trv, results):
        self._resolving.pop(trv, False)

        if trv in self.priorities:
            self.priorities.remove(trv)
        if results.success:
            buildReqs = results.getBuildReqs()
            # only compare components, since packages are not necessarily
            # stored in the build reqs for the trove.
            buildReqTups = set([ (x[0], x[2][0], x[2][1]) for x in buildReqs if ':' in x[0] ])

            if trv.getPrebuiltRequirements() is not None:
                preBuiltReqs = set(
                    [ x for x in trv.getPrebuiltRequirements() if ':' in x[0]])
                if buildReqTups == preBuiltReqs:
                    self.depState.depGraph.deleteEdges(trv)
                    trv.troveBuilt(trv.getPrebuiltBinaries())
                    return
            if results.inCycle:
                self.depState.depGraph.deleteEdges(trv)
                newDeps = None
            else:
                newDeps = self._addResolutionDeps(trv, buildReqs)
            if not newDeps:
                trv.troveBuildable()
                self.depState.troveBuildable(trv, buildReqs)
            else:
                # there are runtime reqs that are being
                # rebuild.
                # Try rebuilding those first, it is possible
                # it will be needed by a lot of things so trying
                # to build it now might help.
                # The trove that is delayed has had an extra link
                # added into the network.
                for depTrv in newDeps:
                    self.prioritize(depTrv)
                trv.troveResolvedButDelayed(newDeps)
        else:
            if results.hasMissingBuildReqs():
                trv.troveMissingBuildReqs(results.getMissingBuildReqs())
            else:
                assert(results.hasMissingDeps())
                trv.troveMissingDependencies(results.getMissingDeps())



    def updateBuildableTroves(self, limit=1):
        from rmake.worker import resolver
        # this is a backwards compatability method.
        # in general, we don't update buildable troves
        # from the dependency handler anymore

        count = 0
        resolver = resolver.DependencyResolver(self.logger)
        while not limit or count < limit:
            resolveJob = self.getNextResolveJob()
            if not resolveJob:
                return
            results = resolver.resolve(resolveJob)
            resolveJob.getTrove().troveResolved(results)
            count += 1
