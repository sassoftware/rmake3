#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

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
        del inF
        del outF
        recipeList.append(recipeFile)
    return recipeList, troves

def loadRecipe(repos, name, version, flavor, recipeFile=None,
               defaultFlavor=None, loadInstalledSource=None,
               installLabelPath=None, buildLabel=None):
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
                                       buildLabel=buildLabel)
        relevantFlavor = use.usedFlagsToFlavor(recipeObj.name)
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
                 loadRecipeSpecs=None, buildLabel = None):
    cfg = conarycfg.ConaryConfiguration(False)
    cfg.initializeFlavors()
    branch = version.branch()
    if not buildLabel:
        buildLabel = version.branch().label()
    if not installLabelPath:
        cfg.installLabelPath = [buildLabel]
    else:
        cfg.installLabelPath = installLabelPath
    name = name.split(':')[0]
    use.LocalFlags._clear()
    assert(flavorutil.getArch(flavor))
    use.setBuildFlagsFromFlavor(name, flavor, error=False)
    use.resetUsed()
    use.track(True)
    ignoreInstalled = not loadInstalledSource
    if recipeFile:
        loader = loadrecipe.RecipeLoader(recipeFile[0], cfg, repos,
                                         name + ':source', branch,
                                         ignoreInstalled=ignoreInstalled,
                                         db=loadInstalledSource)
        recipeClass = loader.getRecipe()
        recipeClass._trove = recipeFile[1]
    else:
        loader = loadrecipe.recipeLoaderFromSourceComponent(name + ':source',
                                               cfg, repos, version.asString(),
                                               labelPath=installLabelPath,
                                               ignoreInstalled=ignoreInstalled,
                                               db=loadInstalledSource)[0]
        recipeClass = loader.getRecipe()
    if recipe.isGroupRecipe(recipeClass):
        recipeObj = recipeClass(repos, cfg, buildLabel, None,
                                {'buildlabel' : buildLabel.asString()})
        recipeObj.sourceVersion = version
        recipeObj.setup()
    elif recipe.isPackageRecipe(recipeClass):
        recipeObj = recipeClass(cfg, None, None,
                                {'buildlabel' : buildLabel.asString()},
                                lightInstance=True)
        recipeObj.sourceVersion = version
        recipeObj.loadPolicy()
        recipeObj.setup()
    elif recipe.isInfoRecipe(recipeClass):
        recipeObj = recipeClass(cfg, None, None,
                                {'buildlabel' : buildLabel.asString()})
        recipeObj.sourceVersion = version
        recipeObj.setup()
    elif recipe.isRedirectRecipe(recipeClass):
        recipeObj = recipeClass(repos, cfg, buildLabel, flavor)
        recipeObj.sourceVersion = version
        recipeObj.setup()
    else:
        raise RuntimeError, 'Unknown class type %s for recipe %s' % (recipeClass, name)
    return recipeObj, loader

def loadRecipeClass(repos, name, version, flavor, recipeFile=None,
                    ignoreInstalled=True, root=None, 
                    loadInstalledSource=None, overrides=None,
                    buildLabel=None):
    cfg = conarycfg.ConaryConfiguration(False)
    cfg.initializeFlavors()
    if root:
        cfg.root = root
    branch = version.branch()
    label = version.branch().label()
    cfg.installLabelPath = [label]
    cfg.buildLabel = label
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
                                         overrides=overrides)
        recipeClass = loader.getRecipe()
        recipeClass._trove = recipeFile[1]
    else:
        loader = loadrecipe.recipeLoaderFromSourceComponent(name + ':source',
                                               cfg, repos, version.asString(),
                                               labelPath=[label],
                                               ignoreInstalled=ignoreInstalled,
                                               db=loadInstalledSource,
                                               overrides=overrides)
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

def loadSourceTroves(job, repos, buildFlavor, troveTupleList,
                     loadInstalledSource=None, installLabelPath=None):
    """
       Load the source troves associated set of (name, version, flavor) tuples
       and return a list of source trove tuples with relevant information about
       their packages and build requirements.
    """
    total = len(troveTupleList)
    job.log('Downloading %s recipes...' % total)
    recipes, troves = getRecipes(repos, troveTupleList)

    buildTroves = []
    try:
        for idx, ((n,v,f), recipeFile, trove) in enumerate(itertools.izip(
                                                           troveTupleList, recipes,
                                                           troves)):
            job.log('Loading %s out of %s: %s' % (idx + 1, total, n))
            relevantFlavor = None
            try:
                (loader, recipeObj, relevantFlavor) = loadRecipe(repos,
                                     n, v, f,
                                     (recipeFile, trove),
                                     buildFlavor,
                                     loadInstalledSource=loadInstalledSource,
                                     installLabelPath=installLabelPath)
                recipeType = buildtrove.getRecipeType(recipeObj)
                buildTrove = buildtrove.BuildTrove(None, n, v, relevantFlavor,
                                                   recipeType=recipeType)
                # remove reference to recipe from the loadedSpecs tuple
                buildTrove.setLoadedSpecs(_getLoadedSpecs(recipeObj))
                buildTrove.setBuildRequirements(getattr(recipeObj,
                                                    'buildRequires', []))
                buildTrove.setDerivedPackages(getattr(recipeObj, 'packages',
                                                      [recipeObj.name]))
            except Exception, err:
                if relevantFlavor is None:
                    relevantFlavor = f
                buildTrove = buildtrove.BuildTrove(None, n, v, relevantFlavor)
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

def getSourceTrovesFromJob(job, buildCfg, serverCfg, repos):
    # called by builder.
    troveList = sorted(job.iterTroveList())
    buildFlavor = buildCfg.buildFlavor
    resolveTroveTups = buildCfg.resolveTroveTups
    # create fake "packages" for all the troves we're building so that
    # they can be found for loadInstalled.
    buildTrovePackages = [ (x[0].split(':')[0], x[1], x[2]) for x in troveList ]
    buildTroveSource = trovesource.SimpleTroveSource(buildTrovePackages)
    buildTroveSource = RemoveHostSource(buildTroveSource,
                                        serverCfg.serverName)
    # don't search the internal repository explicitly for loadRecipe
    # sources - they may be a part of some bogus build.
    repos = RemoveHostRepos(repos, serverCfg.serverName)

    loadInstalledList = [ trovesource.TroveListTroveSource(repos, x)
                            for x in resolveTroveTups ]
    loadInstalledSource = trovesource.stack(buildTroveSource,
                                            *loadInstalledList)
    repos = trovesource.stack(*(loadInstalledList + [repos]))
    return loadSourceTroves(job, repos, buildFlavor, troveList,
                            loadInstalledSource=loadInstalledSource,
                            installLabelPath=buildCfg.installLabelPath)

class RemoveHostRepos(object):
    def __init__(self, troveSource, host):
        self.troveSource = troveSource
        self.host = host

    def __getattr__(self, attr):
        return getattr(self.troveSource, attr)

    def findTroves(self, labelPath, *args, **kw):
        if labelPath is not None:
            newPath = []
            for label in labelPath:
                if label.getHost() != self.host:
                    newPath.append(label)
            labelPath = newPath
        return self.troveSource.findTroves(labelPath, *args, **kw)

class RemoveHostSource(trovesource.SearchableTroveSource):
    def __init__(self, troveSource, host):
        self.troveSource = troveSource
        self.host = host
        trovesource.SearchableTroveSource.__init__(self)

    def trovesByName(self, name):
        return self.troveSource.trovesByName(name)

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
        import epdb
        epdb.st()
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
        results = trovesource.SearchableTroveSource._filterByVersionQuery(
                                                        self, versionType,
                                                        versionMap.keys(),
                                                        versionQuery)
        return dict((x[0], [versionMap[y] for y in x[1]])
                     for x in results.items())
