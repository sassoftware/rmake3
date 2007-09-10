#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import copy
import itertools
from conary.deps import deps
from conary.local import deptable

from conary.conaryclient import resolve
from conary.repository import findtrove,trovesource

from rmake.lib import flavorutil

class TroveSourceMesh(trovesource.SearchableTroveSource):
    def __init__(self, extraSource, mainSource, repos):
        trovesource.SearchableTroveSource.__init__(self)
        self.extraSource = extraSource
        self.mainSource = mainSource
        self.repos = repos
        trovesource.SearchableTroveSource.__init__(self)
        self.searchAsRepository()
        if self.mainSource:
            self._allowNoLabel = self.mainSource._allowNoLabel
            self._bestFlavor = self.mainSource._bestFlavor
            self._getLeavesOnly = self.mainSource._getLeavesOnly
            self._flavorCheck = self.mainSource._flavorCheck
        else:
            self._allowNoLabel = self.repos._allowNoLabel
            self._bestFlavor = self.repos._bestFlavor
            self._getLeavesOnly = self.repos._getLeavesOnly
            self._flavorCheck = self.repos._flavorCheck

        self.sources = [ self.extraSource]
        if self.mainSource:
            self.sources.append(self.mainSource)
        if self.repos:
            self.sources.append(self.repos)

    def __getattr__(self, key):
        if self.repos:
            return getattr(self.repos, key)
        return getattr(self.mainSource, key)

    def hasTroves(self, troveList):
        if self.repos:
            results = self.repos.hasTroves(troveList)
            if isinstance(results, dict):
                results = [ results[x] for x in troveList ]
        else:
            results = [ False for x in troveList ]
        if self.extraSource:
            hasTroves = self.extraSource.hasTroves(troveList)
            results = [ x[0] or x[1] for x in itertools.izip(results,
                                                                hasTroves) ]
        if self.mainSource:
            hasTroves = self.mainSource.hasTroves(troveList)
            results = [ x[0] or x[1] for x in itertools.izip(results,
                                                             hasTroves) ]
        return dict(itertools.izip(troveList, results))

    def trovesByName(self, name):
        return list(set(self.mainSource.trovesByName(name)) 
                    | set(self.extraSource.trovesByName(name)))

    def getTroves(self, troveList, *args, **kw):
        if self.repos:
            return self.repos.getTroves(troveList, *args, **kw)
        else:
            return self.mainSource.getTroves(troveList, *args, **kw)

    def _mergeTroveQuery(self, resultD, response):
        for troveName, troveVersions in response.iteritems():
            if not resultD.has_key(troveName):
                resultD[troveName] = {}
            versionDict = resultD[troveName]
            for version, flavors in troveVersions.iteritems():
                if version not in versionDict:
                    versionDict[version] = []
                resultD[troveName][version].extend(flavors)
        return resultD

    def _call(self, fn, query, *args, **kw):
        query = dict(query)
        d1 = getattr(self.extraSource, fn)(query, *args, **kw)
        result = {}
        self._mergeTroveQuery(result, d1)
        for name in query.keys():
            if name in d1 and len(query[name]) == 1:
                del query[name]
        if self.mainSource:
            d2 = getattr(self.mainSource, fn)(query, *args, **kw)
            self._mergeTroveQuery(result, d2)
        if self.repos:
            d3 = getattr(self.repos, fn)(query, *args, **kw)
            self._mergeTroveQuery(result, d3)
        return result

    def getTroveLatestByLabel(self, query, *args, **kw):
        return self._call('getTroveLatestByLabel', query, *args, **kw)

    def getTroveLeavesByLabel(self, query, *args, **kw):
        return self._call('getTroveLeavesByLabel', query, *args, **kw)

    def getTroveVersionsByLabel(self, query, *args, **kw):
        return self._call('getTroveVersionsByLabel', query, *args, **kw)

    def getTroveLeavesByBranch(self, query, *args, **kw):
        return self._call('getTroveLeavesByBranch', query, *args, **kw)

    def getTroveVersionsByBranch(self, query, *args, **kw):
        return self._call('getTroveVersionsByBranch', query, *args, **kw)

    def getTroveVersionFlavors(self, query, *args, **kw):
        return self._call('getTroveVersionFlavors', query, *args, **kw)

    def findTroves(self, labelPath, troveSpecs, defaultFlavor=None,
                   acrossLabels=False, acrossFlavors=False,
                   affinityDatabase=None, allowMissing=False,
                   bestFlavor=None, getLeaves=None,
                   troveTypes=trovesource.TROVE_QUERY_PRESENT, 
                   exactFlavors=False,
                   **kw):
        if self.mainSource is None:
            return trovesource.SearchableTroveSource.findTroves(self,
                                            labelPath, troveSpecs,
                                            defaultFlavor=defaultFlavor,
                                            acrossLabels=acrossLabels,
                                            acrossFlavors=acrossFlavors,
                                            affinityDatabase=affinityDatabase,
                                            troveTypes=troveTypes,
                                            exactFlavors=exactFlavors,
                                            allowMissing=True,
                                            **kw)
        results = {}
        if bestFlavor is not None:
            kw.update(bestFlavor=bestFlavor)
        if getLeaves is not None:
            kw.update(getLeaves=getLeaves)

        for source in self.sources:
            # FIXME: it should be possible to reuse the trove finder
            # but the bestFlavr and getLeaves data changes per source
            # and is passed into several TroveFinder sub objects.  
            # TroveFinder should be cleaned up
            foundTroves = source.findTroves(labelPath, troveSpecs, 
                                            defaultFlavor=defaultFlavor,
                                            acrossLabels=acrossLabels,
                                            acrossFlavors=acrossFlavors,
                                            affinityDatabase=affinityDatabase,
                                            troveTypes=troveTypes,
                                            exactFlavors=exactFlavors, 
                                            allowMissing=True,
                                            **kw)
            for troveSpec, troveTups in foundTroves.iteritems():
                results.setdefault(troveSpec, []).extend(troveTups)
        if not allowMissing:
            for troveSpec in troveSpecs:
                assert(troveSpec in finalResults)
        return results

    def resolveDependencies(self, label, depList, *args, **kw):
        sugg = self.extraSource.resolveDependencies(label, depList, *args, **kw)
        sugg2 = self.repos.resolveDependencies(label, depList, *args, **kw)
        for depSet, trovesByDep in sugg.iteritems():
            for idx, troveList in enumerate(trovesByDep):
                if not troveList:
                    troveList.extend(sugg2[depSet][idx])
        return sugg

    def resolveDependenciesByGroups(self, troveList, depList):
        sugg = self.extraSource.resolveDependencies(None, depList)
        sugg2 = self.repos.resolveDependenciesByGroups(troveList, depList)
        for depSet, trovesByDep in sugg.iteritems():
            for idx, troveList in enumerate(trovesByDep):
                if not troveList:
                    troveList.extend(sugg2[depSet][idx])
        return sugg




class DepHandlerSource(TroveSourceMesh):
    def __init__(self, builtTroveSource, troveListList, repos=None,
                 useInstallLabelPath=True):
        if repos:
            flavorPrefs = repos._flavorPreferences
        else:
            flavorPrefs = []
        stack = trovesource.TroveSourceStack()
        stack.searchWithFlavor()
        stack.setFlavorPreferenceList(flavorPrefs)
        if isinstance(troveListList, trovesource.SimpleTroveSource):
            troveListList.setFlavorPreferenceList(flavorPrefs)
            self.stack.addSource(troveListList)
        else:
            if troveListList:
                troveSources = []
                for troveList in troveListList:
                    allTroves = [ x.getNameVersionFlavor() for x in troveList ]
                    childTroves = itertools.chain(*
                                   (x.iterTroveList(weakRefs=True,
                                                    strongRefs=True)
                                    for x in troveList))
                    allTroves.extend(childTroves)
                    source = trovesource.SimpleTroveSource(allTroves)
                    source.searchWithFlavor()
                    source.setFlavorPreferenceList(flavorPrefs)
                    stack.addSource(source)
                if not useInstallLabelPath:
                    repos = None
        if not stack.sources:
            stack = None
        TroveSourceMesh.__init__(self, builtTroveSource, stack, repos)

    def __repr__(self):
        return 'DepHandlerSource(%r,%r,%r)' % (self.extraSource, self.mainSource, self.repos)

    def copy(self):
        inst = self.__class__(self.source, None, self.repos)
        inst.repos = self.repos
        return inst


class BuiltTroveSource(trovesource.SimpleTroveSource):
    """
        Trove source that is used for dep resolution and buildreq satisfaction 
        only - it does not contain references to the changesets that are added
    """
    def __init__(self, troves, repos):
        self.depDb = deptable.DependencyDatabase()
        trovesource.SimpleTroveSource.__init__(self)
        self.setFlavorPreferenceList(repos._flavorPreferences)
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
                if not self._allowNoLabel and label:
                    newSolListList.append([ self.idMap[x] for x in solList if self.idMap[x][1].trailingLabel == label])
                else:
                    newSolListList.append([ self.idMap[x] for x in solList ])
            suggMap[depSet] = newSolListList
        return suggMap


class ResolutionMesh(resolve.BasicResolutionMethod):
    def __init__(self, cfg, extraMethod, mainMethod):
        resolve.BasicResolutionMethod.__init__(self, cfg, None)
        self.extraMethod = extraMethod
        self.mainMethod = mainMethod

    def filterSuggestions(self, depList, sugg, suggMap):
        return self.mainMethod.filterSuggestions(depList, sugg, suggMap)

    def prepareForResolution(self, depList):
        self.extraMethod.prepareForResolution(depList)
        return self.mainMethod.prepareForResolution(depList)

    def resolveDependencies(self):
        suggMap = self.extraMethod.resolveDependencies()
        suggMap2 = self.mainMethod.resolveDependencies()
        for depSet, results in suggMap.iteritems():
            finalResults = []
            mainResults = suggMap2[depSet]
            for troveList1, troveList2 in itertools.izip(results, mainResults):
                troveList2.extend(troveList1)
        return suggMap2

    def searchLeavesOnly(self):
        self.extraMethod.searchLeavesOnly()
        self.mainMethod.searchLeavesOnly()

    def searchLeavesFirst(self):
        self.extraMethod.searchLeavesFirst()
        self.mainMethod.searchLeavesFirst()

    def searchAllVersions(self):
        self.extraMethod.searchAllVersions()
        self.mainMethod.searchAllVersions()

class rMakeResolveSource(ResolutionMesh):
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

        sources = []
        if troveLists:
            troveListSources = [resolve.DepResolutionByTroveList(cfg, None, x)
                                 for x in troveLists]
            [ x.setTroveSource(self.repos) for x in troveListSources ]
            sources.extend(troveListSources)

        mainMethod = resolve.ResolutionStack(*sources)
        flavorPreferences = self.repos._flavorPreferences
        for source in sources:
            source.setFlavorPreferences(flavorPreferences)
        ResolutionMesh.__init__(self, cfg, builtResolveSource, mainMethod)

    def setLabelPath(self, labelPath):
        if labelPath:
            source = resolve.DepResolutionByLabelPath(self.cfg, None, labelPath)
            source.setTroveSource(self.repos)
            self.mainMethod.addSource(source)

    def prepareForResolution(self, depList):
        # need to get intratrove deps while we still have the full dependency
        # request information - including what trove the dep arises from.
        intraDeps = self._getIntraTroveDeps(depList)
        self.intraDeps = intraDeps
        return ResolutionMesh.prepareForResolution(self, depList)

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
        sugg = ResolutionMesh.resolveDependencies(self)
        intraDepSuggs = self._resolveIntraTroveDeps(self.intraDeps)
        for depSet, intraDeps in self.intraDeps.iteritems():
            for idx, (depClass, dep) in enumerate(depSet.iterDeps(sort=True)):
                if depClass.tag == deps.DEP_CLASS_TROVES:
                    if (dep in intraDepSuggs[depSet]
                        and intraDepSuggs[depSet][dep]):
                        sugg[depSet][idx] = intraDepSuggs[depSet][dep]
        return sugg

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
