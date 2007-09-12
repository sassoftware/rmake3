#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

import copy
import itertools
import os
import tempfile
import traceback

#conary
from conary.build import cook,loadrecipe,recipe,use
from conary import conarycfg
from conary import conaryclient
from conary.deps import deps
from conary.lib import log,util
from conary.deps.deps import Flavor
from conary.repository import trovesource

#rmake
from rmake import errors
from rmake import failure
from rmake.lib import flavorutil
from rmake.build import buildtrove


def getRecipes(repos, troveTups):
    fileIds = []
    troveSpecs = [ (x[0], x[1], Flavor()) for x in troveTups ]
    troves = repos.getTroves(troveSpecs)
    for i, trove in enumerate(troves):
        filename = trove.getName().split(':')[0] + '.recipe'
        found = False
        for (pathId, filePath, fileId, fileVersion) in trove.iterFileList():
            if filePath == filename:
                fileIds.append((fileId, fileVersion))
                found = True
                break
        if not found:
            raise RuntimeError, 'Could not find recipe for %s' % trove.getName()
    recipes = repos.getFileContents(fileIds)
    recipeList = []
    for i, recipe in enumerate(recipes):
        name = troves[i].getName().split(':')[0]
        (fd, recipeFile) = tempfile.mkstemp(".recipe", 'temp-%s-' %name)
        outF = os.fdopen(fd, "w")
        inF = recipe.get()
        util.copyfileobj(inF, outF)
        outF.close()
        inF.close()
        del inF
        del outF
        recipeList.append(recipeFile)
    return recipeList, troves

def loadRecipe(repos, name, version, flavor, recipeFile=None,
               defaultFlavor=None, loadInstalledSource=None,
               installLabelPath=None, buildLabel=None, groupRecipeSource=None,
               cfg=None):
    name = name.split(':')[0]
    try:
        if defaultFlavor is not None:
            fullFlavor = deps.overrideFlavor(defaultFlavor, flavor)
        else:
            fullFlavor = flavor
        # set up necessary flavors and track used flags before
        # calling loadRecipe, since even loading the class
        # may check some flags that may never be checked inside
        # the recipe
        recipeObj, loader = getRecipeObj(repos, name,
                                       version, fullFlavor, recipeFile,
                                       loadInstalledSource=loadInstalledSource,
                                       installLabelPath=installLabelPath,
                                       buildLabel=buildLabel,
                                       groupRecipeSource=groupRecipeSource,
                                       cfg=cfg)
        relevantFlavor = use.usedFlagsToFlavor(recipeObj.name)
        relevantFlavor = flavorutil.removeInstructionSetFlavor(relevantFlavor)
        # always add in the entire arch flavor.  We need to ensure the
        # relevant flavor is unique per architecture, also, arch flavors
        # can affect the macros used.
        if defaultFlavor is not None:
            relevantFlavor.union(flavor)
        relevantFlavor.union(flavorutil.getArchFlags(fullFlavor))
        relevantFlags = flavorutil.getFlavorUseFlags(relevantFlavor)
        flags = flavorutil.getFlavorUseFlags(fullFlavor)
        use.track(False)

        for flagSet in ('Use',):
        # allow local flags not to be used -- they are set to their default
            if flagSet not in relevantFlags:
                continue
            for flag in relevantFlags[flagSet]:
                if flag not in flags[flagSet]:
                    raise (RuntimeError,
                            "Recipe %s uses Flavor %s but value not known" %(name, flag))
        if 'Arch' in relevantFlags:
            for majarch in relevantFlags['Arch'].keys():
                for subarch in relevantFlags['Arch'][majarch]:
                    if not use.Arch[majarch][subarch]:
                        #negative values for subarches are assumed
                        continue
                    if subarch not in flags['Arch'][majarch]:
                        log.error("arch %s.%s used but not specified" % (
                                                         majarch, subarch))
                        raise RuntimeError, (
                                "arch %s.%s used but not specified" % (
                                                         majarch, subarch))
            use.resetUsed()
    except:
        log.error('Error Loading Recipe (%s, %s, %s):\n%s' %
                                    (name, version, fullFlavor,
                                     ''.join(traceback.format_exc())))
        raise
    return loader, recipeObj, relevantFlavor


def getRecipeObj(repos, name, version, flavor, recipeFile,
                 loadInstalledSource=None, installLabelPath=None, 
                 loadRecipeSpecs=None, buildLabel = None,
                 groupRecipeSource=None, cfg=None):
    if cfg:
        cfg = copy.deepcopy(cfg)
    else:
        cfg = conarycfg.ConaryConfiguration(False)
    cfg.initializeFlavors()
    branch = version.branch()
    if not buildLabel:
        buildLabel = version.branch().label()
    if not installLabelPath:
        cfg.installLabelPath = [buildLabel]
    else:
        cfg.installLabelPath = installLabelPath
    cfg.buildFlavor = flavor
    name = name.split(':')[0]
    use.LocalFlags._clear()
    assert(flavorutil.getArch(flavor))
    use.setBuildFlagsFromFlavor(name, flavor, error=False)
    use.resetUsed()
    use.track(True)
    ignoreInstalled = not loadInstalledSource
    macros = {'buildlabel' : buildLabel.asString(),
              'buildbranch' : version.branch().asString()}
    if recipeFile:
        loader = loadrecipe.RecipeLoader(recipeFile[0], cfg, repos,
                                         name + ':source', branch,
                                         ignoreInstalled=ignoreInstalled,
                                         db=loadInstalledSource,
                                         buildFlavor=flavor)
        recipeClass = loader.getRecipe()
        recipeClass._trove = recipeFile[1]
    else:
        loader = loadrecipe.recipeLoaderFromSourceComponent(name + ':source',
                                               cfg, repos, version.asString(),
                                               labelPath=installLabelPath,
                                               ignoreInstalled=ignoreInstalled,
                                               db=loadInstalledSource,
                                               buildFlavor=flavor)[0]
        recipeClass = loader.getRecipe()
    if recipe.isGroupRecipe(recipeClass):
        recipeObj = recipeClass(repos, cfg, buildLabel, None, None,
                            extraMacros=macros)
        recipeObj.sourceVersion = version
        recipeObj.setup()
        if groupRecipeSource:
            sourceComponents = recipeObj._findSources(groupRecipeSource)
            recipeObj.delayedRequires = sourceComponents
    elif recipe.isPackageRecipe(recipeClass):
        recipeObj = recipeClass(cfg, None, None, macros, lightInstance=True)
        recipeObj.sourceVersion = version
        if not recipeObj.needsCrossFlags():
            recipeObj.crossRequires = []
        recipeObj.loadPolicy()
        recipeObj.setup()
    elif recipe.isInfoRecipe(recipeClass):
        recipeObj = recipeClass(cfg, None, None, macros)
        recipeObj.sourceVersion = version
        recipeObj.setup()
    elif recipe.isRedirectRecipe(recipeClass):
        recipeObj = recipeClass(repos, cfg, buildLabel, flavor)
        recipeObj.sourceVersion = version
        recipeObj.setup()
    elif recipe.isFileSetRecipe(recipeClass):
        recipeObj = recipeClass(repos, cfg, buildLabel, flavor, extraMacros=macros)
        recipeObj.sourceVersion = version
        recipeObj.setup()
    else:
        raise RuntimeError, 'Unknown class type %s for recipe %s' % (recipeClass, name)
    return recipeObj, loader

def loadRecipeClass(repos, name, version, flavor, recipeFile=None,
                    ignoreInstalled=True, root=None, 
                    loadInstalledSource=None, overrides=None,
                    buildLabel=None, cfg=None):
    if cfg is None:
        cfg = conarycfg.ConaryConfiguration(False)
    else:
        cfg = copy.deepcopy(cfg)
    cfg.initializeFlavors()
    if root:
        cfg.root = root
    branch = version.branch()
    label = version.branch().label()
    cfg.installLabelPath = [label]
    cfg.buildLabel = label
    cfg.buildFlavor = flavor
    name = name.split(':')[0]

    use.LocalFlags._clear()
    use.setBuildFlagsFromFlavor(name, flavor, error=False)
    use.resetUsed()
    use.track(True)

    if recipeFile:
        loader = loadrecipe.RecipeLoader(recipeFile[0], cfg, repos,
                                         name + ':source', branch,
                                         ignoreInstalled=True,
                                         db=loadInstalledSource,
                                         overrides=overrides,
                                         buildFlavor=flavor)
        recipeClass = loader.getRecipe()
        recipeClass._trove = recipeFile[1]
    else:
        loader = loadrecipe.recipeLoaderFromSourceComponent(name + ':source',
                                               cfg, repos, version.asString(),
                                               labelPath=[label],
                                               ignoreInstalled=ignoreInstalled,
                                               db=loadInstalledSource,
                                               overrides=overrides,
                                               buildFlavor=flavor)
        recipeClass = loader[0].getRecipe()

    use.track(False)
    localFlags = flavorutil.getLocalFlags()
    usedFlags = use.getUsed()
    use.LocalFlags._clear()
    return loader, recipeClass, localFlags, usedFlags

def _getLoadedSpecs(recipeClass):
    loadedSpecs = getattr(recipeClass, '_loadedSpecs', {})
    if not loadedSpecs:
        return {}
    finalDict = {}
    toParse = [(finalDict, loadedSpecs)]
    while toParse:
        specDict, unparsedSpecs = toParse.pop()
        for troveSpec, (troveTup, recipeClass) in unparsedSpecs.items():
            newDict = {}
            specDict[troveSpec] = (troveTup, newDict)
            toParse.append((newDict, getattr(recipeClass, '_loadedSpecs', {})))
    return finalDict

def loadSourceTroves(job, repos, buildFlavor, troveList,
                     loadInstalledSource=None, installLabelPath=None,
                     groupRecipeSource=None, total=0, count=0):
    """
       Load the source troves associated set of (name, version, flavor) tuples
       and return a list of source trove tuples with relevant information about
       their packages and build requirements.
    """
    if not total:
        total = len(troveList)
    job.log('Downloading %s recipes...' % len(troveList))
    troveList = sorted(troveList, key=lambda x: x.getName())
    recipes, troves = getRecipes(repos,
                          [x.getNameVersionFlavor() for x in troveList])

    buildTroves = []
    try:
        for idx, (buildTrove, recipeFile, trove) in enumerate(itertools.izip(
                                                           troveList, recipes,
                                                           troves)):
            n,v,f = buildTrove.getNameVersionFlavor()
            job.log('Loading %s out of %s: %s' % (count + idx + 1, total, n))
            relevantFlavor = None
            try:
                (loader, recipeObj, relevantFlavor) = loadRecipe(repos,
                                     n, v, f,
                                     (recipeFile, trove),
                                     buildFlavor,
                                     loadInstalledSource=loadInstalledSource,
                                     installLabelPath=installLabelPath,
                                     groupRecipeSource=groupRecipeSource,
                                     cfg=job.getTroveConfig(buildTrove))
                recipeType = buildtrove.getRecipeType(recipeObj)
                buildTrove.setFlavor(relevantFlavor)
                buildTrove.setRecipeType(recipeType)
                buildTrove.setLoadedSpecs(_getLoadedSpecs(recipeObj))
                buildTrove.setDerivedPackages(getattr(recipeObj, 'packages',
                                                      [recipeObj.name]))
                if 'delayedRequires' in recipeObj.__dict__:
                    buildTrove.setDelayedRequirements(recipeObj.delayedRequires)
                buildTrove.setBuildRequirements(getattr(recipeObj, 'buildRequires', []))
                buildTrove.setCrossRequirements(getattr(recipeObj, 'crossRequires', []))
            except Exception, err:
                if relevantFlavor is None:
                    relevantFlavor = f
                buildTrove.setFlavor(relevantFlavor)
                if isinstance(err, errors.RmakeError):
                    # we assume our internal errors have enough info
                    # to determine what the bug is.
                    fail = failure.LoadFailed(str(err))
                else:
                    fail = failure.LoadFailed(str(err), traceback.format_exc())
                buildTrove.troveFailed(fail)
            buildTroves.append(buildTrove)
            os.remove(recipeFile)
    finally:
        for recipeFile in recipes:
            if os.path.exists(recipeFile):
                os.remove(recipeFile)
    return buildTroves

def getSourceTrovesFromJob(job, serverCfg, repos):
    # called by builder.
    troveList = sorted(job.iterTroveList())
    repos = CachingSource(repos)

    # create fake "packages" for all the troves we're building so that
    # they can be found for loadInstalled.
    buildTrovePackages = [ (x[0].split(':')[0], x[1], x[2]) for x in troveList ]
    buildTroveSource = trovesource.SimpleTroveSource(buildTrovePackages)
    buildTroveSource = RemoveHostSource(buildTroveSource,
                                        serverCfg.reposName)
    # don't search the internal repository explicitly for loadRecipe
    # sources - they may be a part of some bogus build.
    repos = RemoveHostRepos(repos, serverCfg.reposName)

    groupRecipeSource = trovesource.SimpleTroveSource(troveList)

    trovesByConfig = {}
    for trove in job.iterTroves():
        trovesByConfig.setdefault(trove.getContext(), []).append(trove)

    allTroves = []
    total = len(list(job.iterTroves()))
    count = 0
    for context, troveList in trovesByConfig.items():
        buildCfg = troveList[0].cfg

        buildFlavor = buildCfg.buildFlavor

        resolveTroveTups = buildCfg.resolveTroveTups
        loadInstalledList = [ trovesource.TroveListTroveSource(repos, x)
                                for x in resolveTroveTups ]
        loadInstalledList.append(repos)
        loadInstalledSource = trovesource.stack(buildTroveSource,
                                                *loadInstalledList)
        loadInstalledList = [ trovesource.TroveListTroveSource(repos, x)
                                for x in resolveTroveTups ]
        loadInstalledList.append(repos)
        repos = trovesource.stack(*loadInstalledList)

        if isinstance(repos, trovesource.TroveSourceStack):
            for source in repos.iterSources():
                source._getLeavesOnly = True
                source.searchWithFlavor()
                # keep allowNoLabel set.

        allTroves.extend(loadSourceTroves(job, repos, buildFlavor, troveList,
                         total=total, count=count,
                         loadInstalledSource=loadInstalledSource,
                         installLabelPath=buildCfg.installLabelPath,
                         groupRecipeSource=groupRecipeSource))
        count = len(allTroves)
    return allTroves

class RemoveHostRepos(object):
    def __init__(self, troveSource, host):
        self.troveSource = troveSource
        self.host = host

    def __getattr__(self, attr):
        return getattr(self.troveSource, attr)

    def findTroves(self, labelPath, *args, **kw):
        if labelPath is not None:
            labelPath = [ x for x in labelPath if x.getHost() != self.host]
        return self.troveSource.findTroves(labelPath, *args, **kw)

    def findTrove(self, labelPath, *args, **kw):
        if labelPath is not None:
            labelPath = [ x for x in labelPath if x.getHost() != self.host]
        return self.troveSource.findTrove(labelPath, *args, **kw)

class CachingSource(object):
    """
        Trovesource that caches calls to findTrove(s).
    """
    def __init__(self, troveSource):
        self.troveSource = troveSource
        self._cache = {}

    def __getattr__(self, key):
        return getattr(self.troveSource, key)

    def findTroves(self, installLabelPath, troveTups, *args, **kw):
        """
            Caching findTroves call.
        """
        finalResults = {}
        toFind = []
        # cache is {troveTup : [((ILP, *args, **kw), result)]}
        # first find troveTup in cache then search all the ILP, args, kw
        # pairs we've cached before.
        key = (installLabelPath, args, sorted(kw.items()))
        for troveTup in troveTups:
            if troveTup in self._cache:
                results = [ x[1] for x in self._cache[troveTup] if x[0] == key ]
                if results:
                    finalResults[troveTup] = results[0]
                    continue
            toFind.append(troveTup)
        newResults = self.troveSource.findTroves(installLabelPath, toFind, *args, **kw)
        for troveTup, troveList in newResults.iteritems():
            self._cache.setdefault(troveTup, []).append((key, troveList))
        finalResults.update(newResults)
        return finalResults

    def findTrove(self, labelPath, troveTup, *args, **kw):
        return self.findTroves(labelPath, [troveTup], *args, **kw)[troveTup]

class RemoveHostSource(trovesource.SearchableTroveSource):
    def __init__(self, troveSource, host):
        self.troveSource = troveSource
        self.host = host
        trovesource.SearchableTroveSource.__init__(self)
        self._bestFlavor = troveSource._bestFlavor
        self._getLeavesOnly = troveSource._getLeavesOnly
        self._flavorCheck = troveSource._flavorCheck
        self._allowNoLabel = troveSource._allowNoLabel

    def resolveDependencies(self, label, *args, **kw):
        if self._allowNoLabel:
            return self.troveSource.resolveDependencies(label, *args, **kw)

        suggMap = self.troveSource.resolveDependencies(None, *args, **kw)
        for depSet, solListList in suggMap.iteritems():
            newSolListList = []
            for solList in solListList:
                newSolList = []
                for sol in solList:
                    trailingLabel = sol[1].trailingLabel()
                    if trailingLabel == label:
                        newSolList.append(sol)
                    if trailingLabel.getHost() != self.host:
                        continue
                    if not sol[1].branch().hasParentBranch():
                        continue
                    if sol[1].branch().parentBranch().label() != label:
                        continue
                    newSolList.append(sol)
                newSolListList.append(newSolList)
            suggMap[depSet] = newSolListList
        return suggMap


    def resolveDependenciesByGroups(self, *args, **kw):
        return self.troveSource.resolveDependenciesByGroups(*args, **kw)

    def trovesByName(self, name):
        return self.troveSource.trovesByName(name)

    def hasTroves(self, *args, **kw):
        return self.troveSource.hasTroves(*args, **kw)

    def findTroves(self, labelPath, *args, **kw):
        if labelPath is not None:
            newPath = []
            for label in labelPath:
                if label.getHost() != self.host:
                    newPath.append(label)
            labelPath = newPath
        return trovesource.SearchableTroveSource.findTroves(self, labelPath,
                                                            *args, **kw)

    def _filterByVersionQuery(self, versionType, versionList, versionQuery):
        versionMap = {}
        for version in versionList:
            upVersion = version
            if version.trailingLabel().getHost() == self.host:
                if version.hasParentVersion():
                    upVersion = version.parentVersion()
                elif version.branch().hasParentBranch():
                    branch = version.branch().parentBranch()
                    shadowLength = version.shadowLength() - 1
                    revision = version.trailingRevision().copy()
                    revision.buildCount.truncateShadowCount(shadowLength)
                    revision.sourceCount.truncateShadowCount(shadowLength)
                    upVersion = branch.createVersion(revision)
                    if list(revision.buildCount.iterCounts())[-1] == 0:
                        upVersion.incrementBuildCount()
            versionMap[upVersion] = version
            versionMap[version] = version
        results = trovesource.SearchableTroveSource._filterByVersionQuery(
                                                        self, versionType,
                                                        versionMap.keys(),
                                                        versionQuery)
        return dict((x[0], [versionMap[y] for y in x[1]])
                     for x in results.items())


