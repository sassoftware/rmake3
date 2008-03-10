#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Dependency Handler and DependencyState classes
"""

import itertools
import sys
import time
import traceback

from conary.deps import deps
from conary.lib import graph
from conary import display
from conary import trove
from conary import versions

from rmake import errors
from rmake import failure
from rmake.build.buildstate import AbstractBuildState

from rmake.lib.apiutils import freeze,thaw,register
from rmake.lib import flavorutil

FAILURE_REASON_FAILED = 0
FAILURE_REASON_BUILDREQ = 1
FAILURE_REASON_DEP = 2

class ResolveJob(object):
    def __init__(self, trove, buildCfg, builtTroves=None, crossTroves=None,
                 inCycle=False):
        self.trove = trove
        self.buildCfg = buildCfg
        if builtTroves is None:
            builtTroves = []
        self.builtTroves = builtTroves
        if crossTroves is None:
            crossTroves = []
        self.crossTroves = crossTroves
        self.inCycle = inCycle

    def getConfig(self):
        return self.buildCfg

    def getTrove(self):
        return self.trove

    def getBuiltTroves(self):
        return self.builtTroves

    def getCrossTroves(self):
        # crossTroves are troves that were cross compiled, exclding
        # cross compilers themselves.  They shouldn't be installed in /
        # for other troves that are being cross compiled.  This is 
        # only important when cross compiling for your current arch.
        return self.crossTroves

    def __freeze__(self):
        d = dict(trove=freeze('BuildTrove', self.trove),
                 buildCfg=freeze('BuildConfiguration', self.buildCfg),
                 builtTroves=freeze('troveTupleList', self.builtTroves),
                 crossTroves=freeze('troveTupleList', self.crossTroves),
                 inCycle=self.inCycle)
        return d

    @classmethod
    def __thaw__(class_, d):
        self = class_(**d)
        self.trove = thaw('BuildTrove', self.trove)
        self.buildCfg = thaw('BuildConfiguration', self.buildCfg)
        self.builtTroves = thaw('troveTupleList', self.builtTroves)
        self.crossTroves = thaw('troveTupleList', self.crossTroves)
        return self
register(ResolveJob)

class DependencyGraph(graph.DirectedGraph):
    # FIXME: remove with next release of conary
    def __contains__(self, trove):
        return trove in self.data.hashedData

    def generateDotFile(self, out, filterFn=None):
        def formatNode(node):
            name, version, flavor, context = node.getNameVersionFlavor(True)
            name = name.split(':')[0]
            versionStr = '%s' % (version.trailingRevision())
            archFlavor = flavorutil.getArchFlags(flavor, withFlags=False)
            restFlavor = flavorutil.removeInstructionSetFlavor(flavor)
            archFlavor.union(restFlavor)
            if context:
                contextStr = '{%s}' % context
            else:
                contextStr = ''
            return '%s=%s[%s]%s' % (name, versionStr, archFlavor, contextStr)

        def formatEdge(fromNode, toNode, value):
            isCross = value[0]
            if isinstance(value[1][0], str):
                name, version, flavor = value[1]
                if version:
                    version = '=%s' % version
                else:
                    version = ''
                if flavor is not None:
                    flavor = '[%s]' % flavor
                else:
                    flavor = ''
                buildReq = '%s%s%s' % (name, version,flavor)
                return str(buildReq)
            else:
                return str(value[1])

        graph.DirectedGraph.generateDotFile(self, out, formatNode, formatEdge, 
                                            filterFn)


class DependencyBasedBuildState(AbstractBuildState):
    """
        Dependency based build state.  Contains information about what troves
        are buildable and also, there dependency relationships.
    """

    def __init__(self, sourceTroves, logger):
        self.logger = logger
        self.trovesByPackage = {}
        self.buildReqTroves = {}
        self.groupsByNameVersion = {}

        self.depGraph = DependencyGraph()
        self.hardDepGraph = DependencyGraph()
        self.builtTroves = {}
        self.rejectedDeps = {}
        self.disallowed = set()

        AbstractBuildState.__init__(self, sourceTroves)


    def _addReq(self, trove, buildReq, isCross=False):
        name, label, flavor = buildReq
        pkg = name.split(':')[0]
        providingTroves = self.trovesByPackage.get(pkg, [])
        for provTrove in providingTroves:
            # this trove must be built after the providing trove,
            # which means that provTrove should be a leaf first.
            if (not isCross and trove.hasTargetArch()
                and provTrove.isCrossCompiled()):
                self.rejectDep(trove, provTrove, isCross)
            elif self._flavorsMatch(trove.getFlavor(), provTrove.getFlavor(),
                                  flavor, isCross):
                # only add edges for nodes that are
                # likely to be on a satisfying branch or flavor,
                # otherwise we'll create unnecessary cycles.
                self.dependsOn(trove, provTrove, (isCross, buildReq))
            else:
                self.rejectDep(trove, provTrove, isCross)

    def troveDuplicate(self, duplicateTrove, matchedTrove):
        if not matchedTrove.isBuilt():
            for child, req in self.depGraph.iterChildren(duplicateTrove,
                                                         withEdges=True):
                self.dependsOn(matchedTrove, duplicateTrove, req)
            for parent, req in self.depGraph.getParents(duplicateTrove,
                                                        withEdges=True):
                self.dependsOn(parent, matchedTrove, req)
        self.disallow(duplicateTrove)
        self.buildReqTroves.pop(duplicateTrove, False)
        self.depGraph.delete(duplicateTrove)

    def _flavorsMatch(self, troveFlavor, provFlavor, reqFlavor, isCross):
        if isCross:
            troveFlavor = flavorutil.getSysRootFlavor(troveFlavor)
        archFlavor = flavorutil.getBuiltFlavor(flavorutil.getArchFlags(
                                               troveFlavor, getTarget=False,
                                               withFlags=False))
        if reqFlavor is None:
            reqFlavor = archFlavor
        else:
            reqFlavor = deps.overrideFlavor(archFlavor, reqFlavor)
        if flavorutil.getArchFlags(provFlavor).isEmpty():
            provFlavor = deps.overrideFlavor(archFlavor, provFlavor)

        if flavorutil.getBuiltFlavor(provFlavor).toStrongFlavor().satisfies(
                                                reqFlavor.toStrongFlavor()):
            return True
        return False

    def addTroves(self, sourceTroves):
        AbstractBuildState.addTroves(self, sourceTroves)
        sourceTroves = [ x for x in sourceTroves if not x.isFailed() ]
        [ self.depGraph.addNode(trove) for trove in sourceTroves ]
        for trove in sourceTroves:
            if trove.isPrepOnly():
                continue
            for package in trove.getDerivedPackages():
                self.trovesByPackage.setdefault(package, []).append(trove)

        for trove in sourceTroves:
            try:
                if trove.isPrimaryTrove():
                    self.hasPrimaryTroves = True
                trove.addBuildRequirements(trove.cfg.defaultBuildReqs)
                if trove.isPrepOnly():
                    continue
                for buildReq in trove.getBuildRequirementSpecs():
                    self._addReq(trove, buildReq, False)

                for crossReq in trove.getCrossRequirementSpecs():
                    self._addReq(trove, crossReq, True)
            except Exception, err:
                errMsg =  'Error adding buildreqs to %s: %s: %s' % (trove.getName(), err.__class__.__name__, err)
                failureReason = failure.LoadFailed(errMsg,
                                                   traceback.format_exc())
                trove.troveFailed(failureReason)
                # We can't continue the build now
                raise errors.RmakeError, errMsg, sys.exc_info()[2]

            # if're loading something that we're also building
            # then we should make sure that we build the thing with the 
            # loadInstalled line secondly
            for loadSpec, sourceTup in trove.iterAllLoadedSpecs():
                name, label, flavor = loadSpec
                providingTroves = self.trovesByPackage.get(name, [])
                for provTrove in providingTroves:
                    if provTrove.getVersion() != sourceTup[1]:
                        continue
                    elif self._flavorsMatch(trove.getFlavor(),
                                            provTrove.getFlavor(),
                                            flavor, False):
                        # FIXME: we really shouldn't allow loadInstalled
                        # loops to occur.  It means that we're building
                        # two recipes that loadInstall each other which
                        # means that we can't even trust the buildReqs
                        # specified for each.
                        self.dependsOn(trove, provTrove, (False, loadSpec))
                    else:
                        self.rejectDep(trove, provTrove, False)

            # If we have multiple groups that are building w/ the same
            # name and version, we send them to be built together.
            if trove.isGroupRecipe():
                name, version = trove.getName(), trove.getVersion()
                if (name, version) not in self.groupsByNameVersion:
                    self.groupsByNameVersion[name, version] = []
                self.groupsByNameVersion[name, version].append(trove)

            # Troves like groups, redirects, etc, have requirements
            # that control when they can be built.
            for sourceTup in trove.getDelayedRequirements():
                name, version, flavor = sourceTup
                package = name.split(':')[0]
                providingTroves = self.trovesByPackage.get(package, [])
                for provTrove in providingTroves:
                    if provTrove.getVersion() != sourceTup[1]:
                        continue
                    if (flavor is None or
                        provTrove.getFlavor().toStrongFlavor().satisfies(
                                                flavor.toStrongFlavor())):
                        self.dependsOn(trove, provTrove,
                                        (False, (name, version, flavor)))
        for troveList in self.groupsByNameVersion.values():
            if len(troveList) <= 1:
                continue
            flavorList = [ x.getFullFlavor() for x in troveList ]
            loadedSpecsList = [ x.getLoadedSpecs() for x in troveList ]
            headNode = troveList[0]
            troveList[0].setFlavorList(flavorList)
            troveList[0].setLoadedSpecsList(loadedSpecsList)
            # mark the rest as prebuilt
            # yuck, we haven't subscribed to these troves yet.
            for trove in troveList[1:]:
                trove.troveDuplicate([])
                self.troveDuplicate(trove, troveList[0])
                self._setState(trove, trove.state)


    def dependsOn(self, trove, provTrove, req):
        if trove == provTrove:
            return
        self.depGraph.addEdge(trove, provTrove, req)

    def hardDependencyOn(self, trove, provTrove, req):
        if trove == provTrove:
            return
        self.hardDepGraph.addEdge(trove, provTrove, req)

    def hasHardDependency(self, trove):
        return (trove in self.hardDepGraph
                and trove not in self.hardDepGraph.getLeaves())

    def areRelated(self, trove1, trove2):
        if trove1 == trove2:
            return
        index1 = self.depGraph.data.getIndex(trove1)
        index2 = self.depGraph.data.getIndex(trove2)
        starts, finishes, trees = self.depGraph.doDFS(start=trove1)
        # this should move in to graph.py at some point.  Basically checks
        # to see if two troves are linked by seeing if you can follow a DFS
        # starting at one and get to the the other.  We have to check
        # both directions on the graph in case trove2 -> trove1.
        if finishes[index2] < finishes[index1]:
            # we started at 1, finished at 2, and then finished at 1,
            # ergo we reached 2 from 1.
            return True
        starts, finishes, trees = self.depGraph.doDFS(start=trove2)
        if finishes[index1] < finishes[index2]:
            # we started at 2, finished at 1, and then finished at 2,
            # ergo we reached 1 from 2.
            return True
        return False

    def rejectDep(self, trove, provTrove, isCross):
        self.rejectedDeps.setdefault(trove, []).append((provTrove, isCross))

    def isRejectedDep(self, trove, provTrove, isCross):
        return (provTrove, isCross) in self.rejectedDeps.setdefault(trove, [])

    def troveBuilt(self, trove, binaryTroveList):
        self.buildReqTroves.pop(trove, False)
        self.depGraph.delete(trove)
        self.hardDepGraph.delete(trove)

        newBuilt = {}
        for binaryTup in binaryTroveList:
            nbf = binaryTup[0], binaryTup[1].branch(), binaryTup[2]
            # if we already used this in
            if nbf in self.builtTroves:
                self.logger.warning("Already built %s - will not commit %s" % (self.builtTroves[nbf], trove))
                self.disallow(trove)
                return
            newBuilt[nbf] = binaryTup
        self.builtTroves.update(newBuilt)

    def trovePrepared(self, trove):
        self.buildReqTroves.pop(trove, False)
        self.depGraph.delete(trove)
        self.hardDepGraph.delete(trove)

    def getAllBinaries(self):
        return self.builtTroves.values()

    def disallow(self, trove):
        self.disallowed.add(trove)

    def getCrossCompiledBinaries(self):
        return list(itertools.chain(*[x.getBinaryTroves() for x in self.troves
                                     if x.isBuilt() and x.isCrossCompiled()
                                        and x not in self.disallowed]))

    def getNonCrossCompiledBinaries(self):
        return list(itertools.chain(*[x.getBinaryTroves() for x in self.troves
                                  if x.isBuilt() and not x.isCrossCompiled()
                                     and x not in self.disallowed]))

    def troveFailed(self, trove):
        self.depGraph.delete(trove)
        self.buildReqTroves.pop(trove, False)

    def troveBuildable(self, trove, buildReqs, crossReqs):
        self.buildReqTroves[trove] = (buildReqs, crossReqs)

    def hasCrossRequirements(self, trove):
        for childTrove, reason in self.depGraph.getChildren(trove,
                                                            withEdges=True):
            if reason[0]:
                return True
        return False

    def hasCrossRequirers(self, trove):
        for parentTrove, reason in self.depGraph.getParents(trove,
                                                            withEdges=True):
            if reason[0]:
                return True
        return False

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
    def __init__(self, statusLog, logger, buildTroves, logDir=None):
        self.depState = DependencyBasedBuildState(buildTroves, logger)
        self.logger = logger
        self.logDir = logDir
        self.graphCount = 0
        self._resolving = {}
        self.priorities = []
        self._delayed = {}
        self._cycleChecked = {}
        self._seenCycles = []
        self._allowFastResolution = True
        self._possibleDuplicates = {}
        self._prebuiltBinaries = set()
        self._hasPrimaryTroves = False

        statusLog.subscribe(statusLog.TROVE_BUILT, self.troveBuilt)
        statusLog.subscribe(statusLog.TROVE_PREPARED, self.trovePrepared)
        statusLog.subscribe(statusLog.TROVE_DUPLICATE, self.troveDuplicate)
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
        self._delayed.pop(trove, False)
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
                if isinstance(failReason[1][0], str):
                    trove.troveMissingBuildReqs([failReason[1]],
                                                isPrimaryFailure=False)
                else:
                    trove.troveMissingDependencies([failReason[1]],
                                                   isPrimaryFailure=False)
                depState.troveFailed(trove)
            else:
                depState.troveFailed(trove)

    def troveBuilding(self, trove, pid=0):
        self._seenCycles = [ x for x in self._seenCycles if trove not in x ]

    def popBuildableTrove(self):
        return self.depState.popBuildableTrove()

    def jobPassed(self):
        return self.depState.jobPassed()

    def trovePrepared(self, trove):
        self.depState.trovePrepared(trove)

    def troveBuilt(self, trove, troveList):
        self.depState.troveBuilt(trove, troveList)
        # This trove built successfully, any troves that were 
        # delayed due to missing deps may be buildable again
        # FIXME: this could be a much more fine-grained test if we had the
        # deps provided by the newly built troves.
        self._delayed = {}

        if trove in self._possibleDuplicates:
            # there were troves that returned as "duplicate"
            # before that we're waiting to compare to this package.
            # now that we have it, do the duplicate comparison again
            for matchedTrove, troveList in self._possibleDuplicates.pop(trove):
                self.troveDuplicate(matchedTrove, troveList)


    def troveDuplicate(self, trove, troveList):
        package = trove.getName().split(':')[0]
        possibleMatches = self.depState.getTrovesByPackage(package)
        for match in possibleMatches:
            if match is trove:
                continue
            elif match.getBinaryTroves() == set(troveList):
                self.depState.troveDuplicate(trove, match)
                return
            elif set(match.getBinaryTroves()) & set(troveList):
                trove.troveFailed('Two versions of %s=%s[%s] were built at the same time but resulted in different components.  If these packages should have different flavors, then add flavor information to them.  Otherwise, try building only one of them.' % trove.getNameVersionFlavor())
                return
            elif not match.getBinaryTroves() and match.isBuilding():
                # it's possible that the two results just came back in the 
                # wrong order
                self._possibleDuplicates.setdefault(match, []).append((trove, 
                                                                 troveList))
                return
        trove.troveFailed('Package was committed at the same time as the same package was built in another job.  Make sure no-one else is building the same packages as you, and that you didn\'t accidentally build the same package twice with the same flavor.')

    def moreToDo(self):
        return self.depState.moreToDo()

    def _addResolutionDeps(self, trv, jobSet, crossJobSet, inCycle=False):
        found = set()
        for jobs, isCross in ((jobSet, False), (crossJobSet, True)):
            for (name, oldInfo, newInfo, isAbs) in jobs:
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
                        if (not isCross and trv.hasTargetArch()
                            and provTrove.isCrossCompiled()):
                            continue
                        if (flavorutil.isCrossCompiler(newInfo[1]) !=
                            flavorutil.isCrossCompiler(provTrove.getFlavor())):
                            continue
                        if not self.depState._flavorsMatch(trv.getFlavor(),
                                       provTrove.getFlavor(), None, isCross):
                            # if this trove is for the wrong architecture
                            # (due to cross compiling), don't delay for it.
                            continue
                        if self.depState.isRejectedDep(trv, provTrove, isCross):
                            continue
                        if (inCycle and not self.depState._flavorsMatch(
                                                trv.getFlavor(),newInfo[1],
                                                None, isCross)):
                            self.depState.hardDependencyOn(trv, provTrove, 
                                          deps.parseDep('trove: %s' % name))
                            found.add(provTrove)
                            break
                        if self.depState.areRelated(trv, provTrove):
                            # if these two are already related in any way
                            # via other dependencies, then the ordering is
                            # already determined, and adding another link 
                            # won't help.  This gives buildReqs priority over
                            # dep resolution reqs.
                            continue
                        found.add(provTrove)
                        # FIXME: we need to have the actual dependency name!
                        self.depState.dependsOn(trv, provTrove,
                                           (isCross, 
                                            (trv.getNameVersionFlavor(),
                                            deps.parseDep('trove: %s' % name))))
                        break
        # there are runtime reqs that are being
        # rebuild.
        # Try rebuilding those first, it is possible
        # it will be needed by a lot of things so trying
        # to build it now might help.
        # The trove that is delayed has had an extra link
        # added into the network.
        for depTrv in found:
            self.prioritize(depTrv)
        return found

    def trovePrebuilt(self, buildTrove, cycleTroves=None):
        self._prebuiltBinaries.update(buildTrove.getPrebuiltBinaries())
        buildTrove.troveBuilt(buildTrove.getPrebuiltBinaries(),
                              prebuilt=True)

        if cycleTroves:
            for cycleTrove in cycleTroves:
                self._cycleChecked.pop(cycleTrove, False)

    def _buildHasOccurred(self):
        return set(self.depState.getAllBinaries()) - self._prebuiltBinaries

    def _getResolveJob(self, buildTrove, inCycle=False, cycleTroves=None):
        if buildTrove.isPrebuilt():
            if (self._hasPrimaryTroves
                and not buildTrove.isPrimary()
                and self._buildHasOccurred()):
                self.trovePrebuilt(buildTrove, cycleTroves)
                return
            elif not buildTrove.prebuiltIsSourceMatch():
                # this should fall out and get a new resolve job.
                pass
            elif buildTrove.getConfig().ignoreAllRebuildDeps:
                self.trovePrebuilt(buildTrove, cycleTroves)
                return
            elif (buildTrove.getConfig().ignoreExternalRebuildDeps
                  and not self.buildHasOccurred()):
                # if nothing's been changed in this build job there's no
                # way this one could be part of a build
                self.trovePrebuilt(buildTrove, cycleTroves)
                return
            elif buildTrove.allowFastRebuild() and self._allowFastResolution:
                buildReqs = buildTrove.getPrebuiltRequirements()
                buildReqs = [ (x[0], (None, None), (x[1], x[2]), False)
                               for x in buildReqs ]
                newDeps = self._addResolutionDeps(buildTrove, buildReqs, [],
                                                  inCycle)
                if newDeps:
                    return
                self.trovePrebuilt(buildTrove, cycleTroves)
                return
        self._resolving[buildTrove] = cycleTroves
        if buildTrove.hasTargetArch():
            builtTroves = self.depState.getNonCrossCompiledBinaries()
            crossTroves = self.depState.getCrossCompiledBinaries()
        else:
            builtTroves = self.depState.getAllBinaries()
            crossTroves = []

        return ResolveJob(buildTrove, buildTrove.cfg, builtTroves, crossTroves,
                          inCycle=inCycle)

    def prioritize(self, trv):
        self.priorities.append(trv)

    def getPriority(self, trv):
        if trv in self.priorities:
            return self.priorities.index(trv), -trv.getPrebuiltTime()
        else:
            return len(self.priorities), -trv.getPrebuiltTime()

    def _filterTroves(self, troveList):
         return [ x for x in troveList
                  if (x.needsBuildreqs()
                      and not x in self._resolving
                      and not x in self._cycleChecked
                      and not x in self._delayed
                      and not self.depState.hasHardDependency(x)) ]

    def _attemptFastResolve(self, nodeLists, breakCycles=True):
        nodeLists = [ (sorted(x.getPrebuiltTime() for x in y 
                              if x.getPrebuiltTime()), y) for y in nodeLists ]
        nodeLists.sort()
        withPrebuilt = [ x[1] for x in nodeLists if x[0] ]
        if withPrebuilt:
            if self._resolving:
                return
            # get the first strongly connected graph off of the queue. 
            # It has the oldest prebuilt package.
            withPrebuilt = withPrebuilt[0]
            if len(withPrebuilt) == 1:
                return self._getResolveJob(list(withPrebuilt)[0])
            elif breakCycles:
                # if we're in a cycle and some of the packages in the
                # cycle are new, then the whole cycle is suspect -
                # it could have been used in a previous build.
                allPrebuilt = not [ x for x in withPrebuilt
                                    if not x.isPrebuilt() ]
                if allPrebuilt:
                    return self._getResolveJobFromCycle(self.depState.depGraph,
                                                        withPrebuilt)
        self._allowFastResolution = False

    def getNextResolveJob(self, breakCycles=True):
        """
            Gets the info for the next trove that needs to be resolved.
        """
        depGraph = self.depState.depGraph
        if depGraph.isEmpty():
            return None
        if len(self._resolving) >= 10:
            return None

        compGraph = self.depState.depGraph.getStronglyConnectedGraph()
        leafCycles = compGraph.getLeaves()
        if self._allowFastResolution:
            result = self._attemptFastResolve(breakCycles=breakCycles,
                                              nodeLists=leafCycles)
            if result or self._allowFastResolution:
                return result

        leafCycles = [ (min(self.getPriority(x) for x in leafCycle), 
                       sorted(leafCycle, key=self.getPriority))
                        for leafCycle in leafCycles ]
        leafCycles = [ x[1] for x in sorted(leafCycles) ]
        newCycles = [ x for x in leafCycles if (len(x) > 1
                                             and x not in self._seenCycles
                                             and self._filterTroves(x) == x) ]
        if newCycles:
            # try to only display cycle information about cycles that
            # we haven't seen before.
            self._seenCycles.extend(newCycles)
            self._displayCycleInfo(depGraph, newCycles)

        for leafCycle in leafCycles:
            if len(leafCycle) > 1:
                if not breakCycles:
                    continue
                found = False
                for trv in leafCycle:
                    if trv in self._resolving:
                        found = True
                        break
                if not found:
                    resolveJob = self._getResolveJobFromCycle(depGraph,
                                                              leafCycle)
                    if resolveJob:
                        return resolveJob
            else:
                leaves = self._filterTroves(leafCycle)
                if not leaves:
                    continue
                trv = leaves[0]
                resolveJob = self._getResolveJob(trv)
                if resolveJob:
                    return resolveJob
        # no resolve job found.  That's ok if work is going on elsewhere
        # in the system.
        if self.depState.hasBuildableTroves() or self._resolving:
            return
        # otherwise, we've got a bunch of troves that were delayed
        # because they have dependencies that couldn't be matched.
        # fail 'em.
        for trv,missingDeps in self._delayed.items():
            trv.troveMissingDependencies(missingDeps)
        self._delayed = {}

    def _getResolveJobFromCycle(self, depGraph, cycleTroves):
        def _cycleNodeOrder(node):
            """ 
            Helper fn to determine the order in which to try to break cycles.
            """
            hasCrossReqs = self.depState.hasCrossRequirements(node)
            hasCrossProvs = self.depState.hasCrossRequirers(node)
            if hasCrossProvs and not hasCrossReqs:
                # This is something required by other cross
                return -1
            numParentsChildren = [len(list(depGraph.iterChildren(x)))
                                    for x in depGraph.getParents(node)]
            if numParentsChildren:
                numParentsChildren = min(numParentsChildren)
            else:
                numParentsChildren = 0
            return numParentsChildren

        buildableTroves = self._filterTroves(cycleTroves)
        if not buildableTroves:
            return
        self.logger.debug('cycle involves %s troves' % len(cycleTroves))
        # if it's got a hard dependency on anything, it's
        # not buildable now.
        # if we built it first before, that this is a good
        # indication that it's a good place to break a cycle.
        sortKeys = [(-int(x.isPrebuilt()), # -1 if this thing has been prebuilt
                                           #  0 if it hasn't (-1 is better)
                     x.getPrebuiltTime(),
                     _cycleNodeOrder(x),
                     x.getNameVersionFlavor(True),
                     x) for x in buildableTroves ]
        sortKeys.sort()
        buildableTroves = [ x[-1] for x in sortKeys ]
        trv = buildableTroves[0]
        return self._getResolveJob(trv, inCycle=True, cycleTroves=cycleTroves)

    def _displayCycleInfo(self, depGraph, leafCycles):
        self.logger.debug('Found %s cycles' % len(leafCycles))
        leafCycles = [([x.getNameVersionFlavor(True) for x in cycle], cycle) 
                        for cycle in leafCycles]
        leafCycles.sort()
        leafCycles = [ x[1] for x in leafCycles ]
        for idx, cycleTroves in enumerate(leafCycles):
            cycleTroves = sorted(
                ['%s=%s[%s]{%s}' % x.getNameVersionFlavor(True)
                 for x in cycleTroves])
            txt = '\n     '.join(str(x) for x in cycleTroves)
            self.logger.debug('Cycle %s (%s packages):\n     %s' % (idx + 1, 
                                                                    len(cycleTroves),
                                                                    txt))
        for idx, cycleTroves in enumerate(leafCycles):
            if len(cycleTroves) <= 2:
                # don't bother displaying "shortest cycle" if the cycles
                # only involve 1 or 2 troves
                continue
            shortest = self._getShortestCycles(depGraph, cycleTroves)
            shortest = [['%s=%s[%s]{%s}' % x.getNameVersionFlavor(True) \
                            for x in y] for y in shortest ]
            txt = '\n\n '.join('\n   -> '.join(str(x) for x in y)
                                               for y in shortest)
            self.logger.debug('Cycle %s: Shortest Cycles:\n %s' % \
                                    (idx + 1, txt))


    def _getShortestCycles(self, depGraph, cycleTroves):
        remainingTroves = set(cycleTroves)
        cycles = []
        map = {}
        for trove in cycleTroves:
            l = []
            for child in depGraph.iterChildren(trove):
                if child != trove:
                    map[trove, child] = []
        changed = True
        entries = sorted(map.items())
        while entries:
            newEntries = []
            for (fromTrove,toTrove), steps in entries:
                if fromTrove == toTrove:
                    continue
                for child in sorted(depGraph.iterChildren(toTrove)):
                    if child == fromTrove:
                        cycleSteps = [fromTrove] + steps + [toTrove, fromTrove]
                        if set(cycleSteps) & remainingTroves:
                            remainingTroves.difference_update(cycleSteps)
                            cycles.append(cycleSteps)
                        if not remainingTroves:
                            return cycles
                    elif child == toTrove:
                        continue
                    elif (fromTrove,child) not in map:
                        map[fromTrove,child] = steps + [toTrove]
                        newEntries.append(((fromTrove, child), map[fromTrove,child]))
            entries = sorted(newEntries)

    def resolutionComplete(self, trv, results):
        cycleTroves = self._resolving.pop(trv, False)
        oldFastResolve = self._allowFastResolution
        self._allowFastResolution = False

        if trv in self.priorities:
            self.priorities.remove(trv)
        if results.success:
            buildReqs = results.getBuildReqs()
            crossReqs = results.getCrossReqs()
            newDeps = self._addResolutionDeps(trv, buildReqs, crossReqs,
                                              results.inCycle)
            if not newDeps and results.inCycle:
                self.depState.depGraph.deleteEdges(trv)
            if newDeps:
                trv.troveResolvedButDelayed(newDeps)
                return
            elif (trv.getPrebuiltRequirements() is not None
                  and not trv.isGroupRecipe()):
                # groups always get recooked, we may check them later
                # to see if anything in them has changed

                preBuiltReqComps = set(
                    [ x for x in trv.getPrebuiltRequirements() if ':' in x[0]])
                # only compare components, since packages are not necessarily
                # stored in the build reqs for the trove.
                buildReqTups = set((x[0], x[2][0], x[2][1])
                                    for x in buildReqs if ':' in x[0])
                buildReqComps = set(x for x in buildReqTups if ':' in x[0])
                if trv.getConfig().ignoreExternalRebuildDeps or self._hasPrimaryTroves:
                    found = False
                    binaries = set(self.depState.getAllBinaries())
                    binaries.difference_update(self._prebuiltBinaries)
                    if not set(binaries).intersection(buildReqTups):
                        self.trovePrebuilt(trv, cycleTroves)
                        return
                if buildReqComps == preBuiltReqComps:
                    self.depState.depGraph.deleteEdges(trv)
                    self._allowFastResolution = oldFastResolve
                    self.trovePrebuilt(trv, cycleTroves)
                    return
                else:
                    self._logDifferenceInPrebuiltReqs(trv, buildReqComps,
                                                      preBuiltReqComps)

            if cycleTroves:
                for cycleTrove in cycleTroves:
                    self._cycleChecked.pop(cycleTrove, False)
            trv.troveBuildable()
            self.depState.troveBuildable(trv, buildReqs, crossReqs)
        else:
            # FIXME: there's probably a case here where self._cycleTroves
            # is empty but a missing dependency could expand the cycle
            # to include something that's buildable (see below where
            # we don't resolve anything but do break the cycle due to 
            # added dependencies)
            if results.inCycle:
                self._cycleChecked[trv] = True
                remainingCycleTroves = [ x for x in cycleTroves 
                                         if x not in self._cycleChecked ]
            if results.inCycle and remainingCycleTroves:
                # there more troves in this cycle that may be buildable
                # check around to see if there's a better order to build things
                # in.
                if results.hasMissingBuildReqs():
                    for isCross, buildReq in results.getMissingBuildReqs():
                        n,v,f = buildReq
                        for child, edge in self.depState.depGraph.iterChildren(trv, withEdges=True):
                            edgeIsCross, (edgeN, edgeV, edgeF)  = edge
                            if edgeV is None:
                                edgeV = ''
                            if v is None:
                                v = ''
                            if f is not None and f.isEmpty():
                                f = None
                            if edgeF is not None and edgeF.isEmpty():
                                edgeF = None
                            if (edgeIsCross == isCross 
                                and (edgeN, edgeV, edgeF) == (n,v,f)):
                                self.depState.hardDependencyOn(trv, child, edge)
                    trv.troveInCycleUnresolvableBuildReqs(
                                                results.getMissingBuildReqs())
                else:
                    self._linkMissingDeps(trv, results.getMissingDeps(),
                                          cycleTroves)
                return
            elif results.hasMissingBuildReqs():
                trv.troveMissingBuildReqs(results.getMissingBuildReqs())
            else:
                assert(results.hasMissingDeps())
                self._linkMissingDeps(trv, results.getMissingDeps(),
                                      cycleTroves)

    def _linkMissingDeps(self, trv, missingDeps, cycleTroves):
        depsAdded = set()
        for isCross, (troveTup, depSet) in missingDeps:
            for troveDep in depSet.iterDepsByClass(
                                            deps.TroveDependencies):
                neededTrove = troveDep.getName()[0]
                package = neededTrove.split(':', 1)[0]
                providers = [ x for x in self.depState.getTrovesByPackage(package) if x != trv ]
                if not providers:
                    trv.troveMissingDependencies([(troveTup, depSet)])
                    return
                for provider in providers:
                    self.depState.dependsOn(trv, provider, 
                                            (isCross, 
                                         (trv.getNameVersionFlavor(), depSet)))
                    self.depState.hardDependencyOn(trv, 
                                              provider,
                                              (isCross, depSet))
                    depsAdded.add(provider)

        # regenerate any cycles since we've changed the dep graph.
        # in any case mark this trove an unresolvable
        if cycleTroves:
            for cycleTrove in cycleTroves:
                if cycleTrove in self._cycleChecked:
                    depsAdded.discard(cycleTrove)
            if not depsAdded:
                trv.troveMissingDependencies(
                    [x[1] for x in missingDeps])
                return
            for cycleTrove in cycleTroves:
                self._cycleChecked.pop(cycleTrove, False)
        self._delayed[trv] = [x[1] for x in missingDeps]
        trv.troveUnresolvableDepsReset(
                [x[1] for x in missingDeps])


    def _logDifferenceInPrebuiltReqs(self, trv, buildReqTups, preBuiltReqs):
        existsTrv = trove.Trove('@update',  
                               versions.NewVersion(),
                               deps.Flavor(), None)
        availableTrv = trove.Trove('@update', 
                                   versions.NewVersion(), 
                                   deps.Flavor(), None)
        for troveNVF in preBuiltReqs:
            existsTrv.addTrove(*troveNVF)
        for troveNVF in buildReqTups:
            availableTrv.addTrove(*troveNVF)
        jobs = availableTrv.diff(existsTrv)[2]
        formatter = display.JobTupFormatter(affinityDb=None)
        formatter.dcfg.setTroveDisplay(fullVersions=True,
                                       fullFlavors=True,
                                       showComponents=True)
        formatter.dcfg.setJobDisplay(compressJobs=True)
        formatter.prepareJobLists([jobs])
        self.logger.info('Could count %s=%s[%s]{%s} as prebuilt - the'
                         ' following changes have been made in its'
                         ' buildreqs:' % trv.getNameVersionFlavor(
                                                            withContext=True))
        for line in formatter.formatJobTups(jobs):
            self.logger.info(line)
        self.logger.info('...Rebuilding')


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
