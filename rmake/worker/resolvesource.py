#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import itertools
from conary.deps import deps
from conary.local import deptable

from conary.conaryclient import resolve
from conary.repository import trovesource

class DepHandlerSource(trovesource.TroveSourceStack):
    def __init__(self, builtTroveSource, troveListList, repos,
                 useInstallLabelPath=True):
        self.repos = repos
        if troveListList:
            troveSources = []
            for troveList in troveListList:
                allTroves = [ x.getNameVersionFlavor() for x in troveList ]
                childTroves = itertools.chain(*
                               (x.iterTroveList(weakRefs=True, strongRefs=True)
                                for x in troveList))
                allTroves.extend(childTroves)
                troveSources.append(trovesource.SimpleTroveSource(allTroves))
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
