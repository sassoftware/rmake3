#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import itertools
import time

from conary import conaryclient
from conary.conaryclient import resolve
from conary.lib import log
from conary.local import database
from conary.repository import trovesource

from rmake.lib import apiutils
from rmake.lib.apiutils import register, freeze, thaw
from rmake.worker import resolvesource

class ResolveResult(object):
    def __init__(self, inCycle=False):
        self.success = False
        self.buildReqs = []
        self.missingBuildReqs = []
        self.missingDeps = []
        self.inCycle = inCycle

    def getBuildReqs(self):
        assert(self.success)
        return self.buildReqs

    def getMissingBuildReqs(self):
        return self.missingBuildReqs

    def getMissingDeps(self):
        return self.missingDeps

    def hasMissingBuildReqs(self):
        return bool(self.missingBuildReqs)

    def hasMissingDeps(self):
        return bool(self.missingDeps)

    def troveResolved(self, buildReqs):
        self.success = True
        self.buildReqs = buildReqs

    def troveMissingBuildReqs(self, buildReqs):
        self.success = False
        self.missingBuildReqs = buildReqs

    def troveMissingDependencies(self, missingDeps):
        self.success = False
        self.missingDeps = missingDeps

    def __freeze__(self):
        d = self.__dict__.copy()
        d.update(missingBuildReqs=freeze('troveSpecList',
                                         self.missingBuildReqs))
        d.update(buildReqs=freeze('installJobList', self.buildReqs))
        d.update(missingDeps=freeze('dependencyList', self.missingDeps))
        return d

    @classmethod
    def __thaw__(class_, d):
        self = class_()
        self.__dict__.update(d)
        self.buildReqs = thaw('installJobList', self.buildReqs)
        self.missingDeps = thaw('dependencyList', self.missingDeps)
        self.missingBuildReqs = thaw('troveSpecList', self.missingBuildReqs)
        return self
register(ResolveResult)


class DependencyResolver(object):
    """
        Resolves dependencies for one trove.
    """
    def __init__(self, logger, repos=None):
        self.logger = logger
        self.repos = repos

    def getSources(self, resolveJob):
        cfg = resolveJob.getConfig()
        builtTroves = self.repos.getTroves(resolveJob.getBuiltTroves(),
                                           withFiles=False)
        builtTroveSource = resolvesource.BuiltTroveSource(builtTroves)
        if cfg.resolveTroveTups:
            return self.getSourcesWithResolveTroves(cfg, cfg.resolveTroveTups,
                                                    builtTroveSource)

        searchSource = resolvesource.DepHandlerSource(builtTroveSource,
                                                      [], self.repos)
        resolveSource = resolvesource.DepResolutionByTroveLists(cfg, None, [])
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
                           useInstallLabelPath=not cfg.resolveTrovesOnly)
        resolveSource = resolvesource.DepResolutionByTroveLists(cfg, None,
                                                        searchSourceTroves)
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
            searchFlavor = None
        else:
            installLabelPath = cfg.installLabelPath
            searchFlavor = cfg.flavor

        searchSource, resolveSource = self.getSources(resolveJob)

        self.logger.debug('attempting to resolve buildreqs for %s=%s[%s]' % resolveJob.getTrove().getNameVersionFlavor())

        resolveResult = ResolveResult(inCycle=resolveJob.inCycle)

        if not trv.getBuildRequirements():
            resolveResult.troveResolved([])
            return resolveResult

        finalToInstall = {}

        # we allow build requirements to be matched against anywhere on the
        # install label.  Create a list of all of this trove's labels,
        # from latest on branch to earliest to use as search labels.
        self.logger.debug('   finding buildreqs for %s....' % trv.getName())
        start = time.time()

        # don't follow redirects when resolving buildReqs
        result = searchSource.findTroves(installLabelPath,
                                     trv.getBuildRequirementSpecs(),
                                     searchFlavor, allowMissing=True,
                                     acrossLabels=False,
                                     troveTypes=trovesource.TROVE_QUERY_NORMAL)
        okay = True

        buildReqTups = []
        missingBuildReqs = []
        for troveSpec in trv.getBuildRequirementSpecs():
            solutions = result.get(troveSpec, [])
            if not solutions:
                missingBuildReqs.append(troveSpec)
                okay = False
            else:
                sol = _findBestSolution(trv, troveSpec, solutions, searchFlavor)
                buildReqTups.append(sol)

        if not okay:
            self.logger.debug('could not find all buildreqs: %s' % (missingBuildReqs,))
            resolveResult.troveMissingBuildReqs(missingBuildReqs)
            return resolveResult

        self.logger.debug('   resolving deps for %s...' % trv.getName())
        start = time.time()
        itemList = [ (x[0], (None, None), (x[1], x[2]), True)
                                                for x in buildReqTups ]

        resolveSource.setLabelPath(installLabelPath)

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
            self.logger.debug('Failed - unresolved deps - took %s seconds' % (time.time() - start))
            self.logger.debug('Missing: %s' % ((depList + cannotResolve),))
            resolveResult.troveMissingDependencies(depList + cannotResolve)
            return resolveResult

        self._addPackages(searchSource, jobSet)
        self.logger.debug('   took %s seconds' % (time.time() - start))
        self.logger.info('   Resolved troves:')
        self.logger.info('\n    '.join('%s=%s[%s]' % (x[0], x[2][0], x[2][1])
                               for x in sorted(jobSet)))
        resolveResult.troveResolved(jobSet)
        return resolveResult

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
                      solutions, searchFlavor):
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
    for flavor in searchFlavor:
        result = filter.selectResolutionTrove(trove, None, None,
                                              solutions, flavor,
                                              affDict)
        if result:
            break
    return result

