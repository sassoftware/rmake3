#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import copy
import itertools
import time

from conary import conaryclient
from conary.conaryclient import resolve
from conary.deps import deps
from conary.lib import log
from conary.local import database
from conary.repository import trovesource

from rmake.lib import apiutils, flavorutil, recipeutil
from rmake.lib.apiutils import register, freeze, thaw
from rmake.worker import resolvesource

class ResolveResult(object):
    def __init__(self, inCycle=False):
        self.success = False
        self.buildReqs = []
        self.crossReqs = []
        self.missingBuildReqs = []
        self.missingDeps = []
        self.inCycle = inCycle

    def getBuildReqs(self):
        assert(self.success)
        return self.buildReqs

    def getCrossReqs(self):
        assert(self.success)
        return self.crossReqs

    def getMissingBuildReqs(self):
        return self.missingBuildReqs

    def getMissingDeps(self):
        return self.missingDeps

    def hasMissingBuildReqs(self):
        return bool(self.missingBuildReqs)

    def hasMissingDeps(self):
        return bool(self.missingDeps)

    def troveResolved(self, buildReqs, crossReqs):
        self.success = True
        self.buildReqs = buildReqs
        self.crossReqs = crossReqs

    def troveMissingBuildReqs(self, isCross, buildReqs):
        self.success = False
        self.missingBuildReqs = [ (isCross, x) for x in buildReqs ]

    def troveMissingDependencies(self, isCross, missingDeps):
        self.success = False
        self.missingDeps = [ (isCross, x) for x in missingDeps ]

    def __freeze__(self):
        d = self.__dict__.copy()
        d.update(missingBuildReqs=[(x[0], freeze('troveSpec', x[1])) for x in
                                    self.missingBuildReqs])
        d.update(buildReqs=freeze('installJobList', self.buildReqs))
        d.update(crossReqs=freeze('installJobList', self.crossReqs))
        d.update(missingDeps=freeze('dependencyMissingList', 
                                    self.missingDeps))
        return d

    @classmethod
    def __thaw__(class_, d):
        self = class_()
        self.__dict__.update(d)
        self.buildReqs = thaw('installJobList', self.buildReqs)
        self.crossReqs = thaw('installJobList', self.crossReqs)
        self.missingDeps = thaw('dependencyMissingList', self.missingDeps)
        self.missingBuildReqs = [(x[0], thaw('troveSpec', x[1])) 
                                 for x in self.missingBuildReqs]
        return self
register(ResolveResult)


class DependencyResolver(object):
    """
        Resolves dependencies for one trove.
    """
    def __init__(self, logger, repos=None):
        self.logger = logger
        self.repos = repos

    def getSources(self, resolveJob, cross=False):
        cfg = resolveJob.getConfig()

        if cross:
            buildFlavor = deps.overrideFlavor(resolveJob.buildCfg.buildFlavor,
                                              resolveJob.getTrove().getFlavor())
            buildFlavor = deps.overrideFlavor(buildFlavor,
                                              deps.parseFlavor('!cross'))
            builtTroveTups = (resolveJob.getCrossTroves()
                              + resolveJob.getBuiltTroves())
            cfg = copy.deepcopy(cfg)
            cfg.flavor = [ flavorutil.setISFromTargetFlavor(buildFlavor) ]
        else:
            builtTroveTups = resolveJob.getBuiltTroves()

        builtTroves = self.repos.getTroves(builtTroveTups, withFiles=False)
        builtTroveSource = resolvesource.BuiltTroveSource(builtTroves,
                                                          self.repos)
        if builtTroves:
            # this makes sure that if someone searches for a buildreq on
            # :branch, and the only thing we have is on :branch/rmakehost,
            # the trove will be found.
            rMakeHost = builtTroves[0].getVersion().trailingLabel().getHost()
            builtTroveSource = recipeutil.RemoveHostSource(builtTroveSource,
                                                           rMakeHost)
        if cfg.resolveTrovesOnly:
            searchSource, resolveSource = self.getSourcesWithResolveTroves(cfg,
                                                    cfg.resolveTroveTups,
                                                    builtTroveSource)
        else:
            searchSource = resolvesource.DepHandlerSource(builtTroveSource,
                                                          [], self.repos,
                                                      expandLabelQueries=True)
            resolveSource = resolvesource.rMakeResolveSource(cfg,
                                                        builtTroveSource, [],
                                                        None,
                                                        self.repos)
        if cross:
            resolveSource.removeFileDependencies = True
        return searchSource, resolveSource

    def getSourcesWithResolveTroves(self, cfg, resolveTroveTups,
                                    builtTroveSource):
        resolveTroves = []
        searchSourceTroves = []
        allResolveTroveTups = list(itertools.chain(*cfg.resolveTroveTups))
        allResolveTroves = self.repos.getTroves(allResolveTroveTups,
                                                withFiles=False)
        resolveTrovesByTup = dict((x.getNameVersionFlavor(), x)
                                  for x in allResolveTroves)

        for resolveTupList in cfg.resolveTroveTups:
            resolveTroves = [ resolveTrovesByTup[x]
                              for x in resolveTupList ]
            searchSourceTroves.append(resolveTroves)

        searchSource = resolvesource.DepHandlerSource(builtTroveSource,
                           searchSourceTroves,
                           self.repos,
                           useInstallLabelPath=not cfg.resolveTrovesOnly,
                           expandLabelQueries=True)
        resolveSource = resolvesource.rMakeResolveSource(cfg,
                                                builtTroveSource,
                                                searchSource.resolveTroveSource,
                                                searchSourceTroves,
                                                self.repos)
        return searchSource, resolveSource

    def resolve(self, resolveJob):
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
        log.setMinVerbosity(log.DEBUG)
        trv = resolveJob.getTrove()
        cfg = resolveJob.getConfig()
        client = conaryclient.ConaryClient(cfg)
        if not self.repos:
            self.repos = client.repos
        else:
            client.repos = self.repos

        if cfg.resolveTrovesOnly:
            installLabelPath = None
            searchFlavor = cfg.flavor
        else:
            installLabelPath = cfg.installLabelPath
            searchFlavor = cfg.flavor

        searchSource, resolveSource = self.getSources(resolveJob)

        self.logger.debug('attempting to resolve buildreqs for %s=%s[%s]' % resolveJob.getTrove().getNameVersionFlavor())

        resolveResult = ResolveResult(inCycle=resolveJob.inCycle)

        buildReqs = trv.getBuildRequirementSpecs()
        crossReqs = trv.getCrossRequirementSpecs()
        if not (buildReqs or crossReqs):
            resolveResult.troveResolved([], [])
            return resolveResult
        self.logger.debug('   finding buildreqs for %s....' % trv.getName())
        self.logger.debug('   resolving deps for %s...' % trv.getName())
        start = time.time()
        buildReqJobs = crossReqJobs = []
        if buildReqs:
            success, results = self._resolve(cfg, resolveResult, trv,
                                             searchSource, resolveSource,
                                             installLabelPath, searchFlavor,
                                             buildReqs)
            if success:
                buildReqJobs = results
            else:
                return resolveResult
        if crossReqs:
            searchSource, resolveSource = self.getSources(resolveJob,
                                                          cross=True)
            searchFlavor = resolveSource.flavor
            success, results = self._resolve(cfg, resolveResult, trv,
                                             searchSource, resolveSource,
                                             installLabelPath, searchFlavor,
                                             crossReqs, isCross=True)
            if success:
                crossReqJobs = results
            else:
                return resolveResult
        self.logger.debug('   took %s seconds' % (time.time() - start))
        self.logger.info('   Resolved troves:')
        if crossReqJobs:
            self.logger.info('   Cross Requirements:')
            self.logger.info('\n    '.join(['%s=%s[%s]' % (x[0], x[2][0], x[2][1])
                                   for x in sorted(crossReqJobs)]))
        if buildReqJobs:
            self.logger.info('   Build Requirements:')
            self.logger.info('\n    '.join(['%s=%s[%s]' % (x[0],
                                                          x[2][0], x[2][1])
                               for x in sorted(buildReqJobs)]))
        resolveResult.troveResolved(buildReqJobs, crossReqJobs)
        return resolveResult


    def _resolve(self, cfg, resolveResult, trove, searchSource, resolveSource,
                 installLabelPath, searchFlavor, reqs, isCross=False):
        resolveSource.setLabelPath(installLabelPath)
        client = conaryclient.ConaryClient(cfg)

        finalToInstall = {}

        # we allow build requirements to be matched against anywhere on the
        # install label.  Create a list of all of this trove's labels,
        # from latest on branch to earliest to use as search labels.

        # don't follow redirects when resolving buildReqs
        result = searchSource.findTroves(installLabelPath,
                                     reqs,
                                     searchFlavor, allowMissing=True,
                                     acrossLabels=False,
                                     troveTypes=trovesource.TROVE_QUERY_NORMAL)
        okay = True

        buildReqTups = []
        missingBuildReqs = []
        for troveSpec in reqs:
            solutions = result.get(troveSpec, [])
            if not solutions:
                missingBuildReqs.append(troveSpec)
                okay = False
            else:
                sol = _findBestSolution(trove, troveSpec, solutions,
                                        searchFlavor, resolveSource)
                if sol is None:
                    missingBuildReqs.append(troveSpec)
                    okay = False
                buildReqTups.append(sol)

        if not okay:
            self.logger.info('Could not find all buildreqs: %s' % (missingBuildReqs,))
            resolveResult.troveMissingBuildReqs(isCross, missingBuildReqs)
            return False, None

        itemList = [ (x[0], (None, None), (x[1], x[2]), True)
                                                for x in buildReqTups ]

        uJob = database.UpdateJob(None)
        uJob.setSearchSource(searchSource)
        jobSet = client._updateChangeSet(itemList, uJob, useAffinity=False)
        (depList, suggMap, cannotResolve, splitJob, keepList) = \
        client.resolver.resolveDependencies(uJob, jobSet,
                                            resolveDeps=True,
                                            useRepos=False, split=False,
                                            resolveSource=resolveSource)

        jobSet.update((x[0], (None, None), (x[1], x[2]), False) 
                      for x in itertools.chain(*suggMap.itervalues()))
        if cannotResolve or depList:
            self.logger.info('Missing: %s' % ((depList + cannotResolve),))
            resolveResult.troveMissingDependencies(isCross, depList + cannotResolve)
            return False, resolveResult

        self._addPackages(searchSource, jobSet)
        return True, jobSet

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


def _findBestSolution(trove, (name, versionSpec, flavorSpec), 
                      solutions, searchFlavor, resolveSource):
    """Given a trove, a buildRequirement troveSpec, and a set of troves
       that may match that buildreq, find the best trove.
    """
    if len(solutions) == 1:
        return solutions[0]
    # flavorSpec _should_ have been handled by findTroves.
    # However, in some cases it's not - for example, if two different
    # flavors of a trove are in the same group (glibc, e.g.).
    affDict = dict.fromkeys((x[0] for x in solutions), [])
    return resolveSource.selectResolutionTrove(trove, None, None,
                                                 solutions, None,
                                                 affDict)

