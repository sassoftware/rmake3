#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import copy
import itertools
from conary.deps import deps
from conary.local import deptable

from conary.conaryclient import resolve
from conary.repository import trovesource

from rmake.lib import flavorutil

class DepHandlerSource(trovesource.TroveSourceStack):
    def __init__(self, builtTroveSource, troveListList, repos=None,
                 useInstallLabelPath=True):
        self.repos = repos
        if isinstance(troveListList, trovesource.SimpleTroveSource):
            self.sources = [ builtTroveSource, troveListList]
            if repos:
                self.sources.append(repos)
        else:
            if troveListList:
                troveSources = []
                for troveList in troveListList:
                    allTroves = [ x.getNameVersionFlavor() for x in troveList ]
                    childTroves = itertools.chain(*
                                   (x.iterTroveList(weakRefs=True, strongRefs=True)
                                    for x in troveList))
                    allTroves.extend(childTroves)
                    source = trovesource.SimpleTroveSource(allTroves)
                    source.searchWithFlavor()
                    troveSources.append(source)
                self.sources = [builtTroveSource] + troveSources
                if useInstallLabelPath:
                    self.sources.append(repos)
            else:
                self.sources = [builtTroveSource, repos]

    def copy(self):
        inst = self.__class__(self.sources[0], None, self.sources[-1])
        inst.sources = list(self.sources)
        return inst

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
    def __init__(self, troves):
        self.depDb = deptable.DependencyDatabase()
        trovesource.SimpleTroveSource.__init__(self)
        self.idMap = []
        self.idx = 0
        for trove in troves:
            self.addTrove(trove.getNameVersionFlavor(), trove.getProvides(),
                          trove.getRequires())
        self.searchWithFlavor()

    def addTrove(self, troveTuple, provides, requires):
        self._trovesByName.setdefault(troveTuple[0],set()).add(troveTuple)

        self.idMap.append(troveTuple)
        self.depDb.add(self.idx, provides, requires)
        self.idx += 1

    def addChangeSet(self, cs):
        for idx, trvCs in enumerate(cs.iterNewTroveList()):
            self.addTrove(trvCs.getNewNameVersionFlavor(), trvCs.getProvides(),
                          trvCs.getRequires())

    def resolveDependencies(self, label, depList, leavesOnly=False):
        suggMap = self.depDb.resolve(label, depList)
        for depSet, solListList in suggMap.iteritems():
            newSolListList = []
            for solList in solListList:
                newSolListList.append([ self.idMap[x] for x in solList ])
            suggMap[depSet] = newSolListList
        return suggMap


class DepResolutionByTroveLists(resolve.ResolutionStack):
    """ 
        Resolve by trove list first and then resort back to label
        path.  Also respects intra-trove deps.  If foo:runtime
        requires foo:lib, it requires exactly the same version of foo:lib.
    """
    def __init__(self, cfg, builtTroveSource, troveLists, repos):
        self.removeFileDependencies = False
        self.builtTroveSource = builtTroveSource
        self.troveLists = troveLists
        self.repos = repos
        self.cfg = cfg
        self.repos = repos
        self.flavor = cfg.flavor
        sources = []
        builtResolveSource = resolve.BasicResolutionMethod(cfg, None)
        builtResolveSource.setTroveSource(builtTroveSource)
        sources = [builtResolveSource]
        if troveLists:
            troveListSources = [resolve.DepResolutionByTroveList(cfg, None, x)
                                 for x in troveLists]
            [ x.setTroveSource(self.repos) for x in troveListSources ]
            sources.extend(troveListSources)

        resolve.ResolutionStack.__init__(self, *sources)

    def setLabelPath(self, labelPath):
        if labelPath:
            source = resolve.DepResolutionByLabelPath(self.cfg, None, labelPath)
            source.setTroveSource(self.repos)
            self.sources.append(source)

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

    def filterDependencies(self, depList):
        if self.removeFileDependencies:
            depList = [(x[0], flavorutil.removeFileDeps(x[1]))
                       for x in depList ]
            return [ x for x in depList if not x[1].isEmpty() ]
        return depList

    def prepareForResolution(self, depList):
        # need to get intratrove deps while we still have the full dependency
        # request information - including what trove the dep arises from.
        intraDeps = self._getIntraTroveDeps(depList)
        self.intraDeps = intraDeps
        return resolve.ResolutionStack.prepareForResolution(self, depList)

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
        sugg = resolve.ResolutionStack.resolveDependencies(self)
        intraDepSuggs = self._resolveIntraTroveDeps(self.intraDeps)
        for depSet, intraDeps in self.intraDeps.iteritems():
            for idx, (depClass, dep) in enumerate(depSet.iterDeps(sort=True)):
                if depClass.tag == deps.DEP_CLASS_TROVES:
                    if (dep in intraDepSuggs[depSet]
                        and intraDepSuggs[depSet][dep]):
                        sugg[depSet][idx] = intraDepSuggs[depSet][dep]
        return sugg
