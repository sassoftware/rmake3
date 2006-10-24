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

#rmake
from rmake import errors
from rmake.lib import flavorutil
from rmake.build import buildtrove
from rmake.build import failure


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

def loadRecipe(repos, name, version, flavor, recipeFile=None):
    name = name.split(':')[0]
    try:
        # set up necessary flavors and track used flags before
        # calling loadRecipe, since even loading the class
        # may check some flags that may never be checked inside
        # the recipe
        recipeObj, loader = getRecipeObj(repos, name,
                                         version, flavor, recipeFile)
        relevantFlavor = use.usedFlagsToFlavor(recipeObj.name)
        # always add in the entire arch flavor.  We need to ensure the
        # relevant flavor is unique per architecture, also, arch flavors
        # can affect the macros used.
        relevantFlavor.union(flavorutil.getArchFlags(flavor))
        relevantFlags = flavorutil.getFlavorUseFlags(relevantFlavor)
        flags = flavorutil.getFlavorUseFlags(flavor)
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
                                    (name, version, flavor,
                                     ''.join(traceback.format_exc())))
        raise
    return loader, recipeObj, relevantFlavor


def getRecipeObj(repos, name, version, flavor, recipeFile=None):
    cfg = conarycfg.ConaryConfiguration(False)
    cfg.initializeFlavors()
    branch = version.branch()
    label = version.branch().label()
    cfg.installLabelPath = [label]
    name = name.split(':')[0]
    use.LocalFlags._clear()
    assert(flavorutil.getArch(flavor))
    use.setBuildFlagsFromFlavor(name, flavor)
    use.resetUsed()
    use.track(True)
    if recipeFile:
        loader = loadrecipe.RecipeLoader(recipeFile[0], cfg, repos,
                                         name + ':source', branch,
                                         ignoreInstalled=True)
        recipeClass = loader.getRecipe()
        recipeClass._trove = recipeFile[1]
    else:
        loader = loadrecipe.recipeLoaderFromSourceComponent(name + ':source',
                                               cfg, repos, version.asString(),
                                               labelPath=[label],
                                               ignoreInstalled=True)
        recipeClass = loader[0].getRecipe()
    if recipe.isGroupRecipe(recipeClass):
        recipeObj = recipeClass(repos, cfg, label, None,
                                {'buildlabel' : label.asString()})
        recipeObj.sourceVersion = version
        recipeObj.setup()
    elif recipe.isPackageRecipe(recipeClass):
        recipeObj = recipeClass(cfg, None, None,
                                {'buildlabel' : label.asString()},
                                lightInstance=True)
        recipeObj.sourceVersion = version
        recipeObj.loadPolicy()
        recipeObj.setup()
    elif recipe.isInfoRecipe(recipeClass):
        recipeObj = recipeClass(cfg, None, None,
                                {'buildlabel' : label.asString()})
        recipeObj.sourceVersion = version
        recipeObj.setup()
    elif recipe.isRedirectRecipe(recipeClass):
        recipeObj = recipeClass(repos, cfg, label, flavor)
        recipeObj.sourceVersion = version
        recipeObj.setup()
    else:
        raise RuntimeError, 'Unknown class type %s for recipe %s' % (recipeClass, name)
    return recipeObj, loader

def loadRecipeClass(repos, name, version, flavor, recipeFile=None,
                    ignoreInstalled=True, root=None):
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
    use.setBuildFlagsFromFlavor(name, flavor)
    use.resetUsed()
    use.track(True)

    if recipeFile:
        loader = loadrecipe.RecipeLoader(recipeFile[0], cfg, repos,
                                         name + ':source', branch,
                                         ignoreInstalled=True)
        recipeClass = loader.getRecipe()
        recipeClass._trove = recipeFile[1]
    else:
        loader = loadrecipe.recipeLoaderFromSourceComponent(name + ':source',
                                               cfg, repos, version.asString(),
                                               labelPath=[label],
                                               ignoreInstalled=ignoreInstalled)
        recipeClass = loader[0].getRecipe()

    use.track(False)
    localFlags = flavorutil.getLocalFlags()
    usedFlags = use.getUsed()
    use.LocalFlags._clear()
    return loader, recipeClass, localFlags, usedFlags


def loadSourceTroves(job, repos, troveTupleList):
    """
       Load the source troves associated set of (name, version, flavor) tuples
       and return a list of source trove tuples with relevant information about
       their packages and build requirements.
    """
    total = len(troveTupleList)
    job.log('Downloading %s recipes...' % total)
    recipes, troves = getRecipes(repos, troveTupleList)

    buildTroves = []
    for idx, ((n,v,f), recipeFile, trove) in enumerate(itertools.izip(
                                                       troveTupleList, recipes,
                                                       troves)):
        job.log('Loading %s out of %s: %s' % (idx + 1, total, n))
        relevantFlavor = None
        try:
            (loader, recipeObj, relevantFlavor) = loadRecipe(repos,
                                                         n, v, f,
                                                         (recipeFile, trove))
            recipeType = buildtrove.getRecipeType(recipeObj)
            buildTrove = buildtrove.BuildTrove(None, n, v, relevantFlavor,
                                               recipeType=recipeType)
            buildTrove.setBuildRequirements(getattr(recipeObj, 'buildRequires', []))
            buildTrove.setDerivedPackages(getattr(recipeObj, 'packages', [recipeObj.name]))
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
    return buildTroves

def getSourceTrovesFromJob(job, conaryCfg):
    troveList = list(job.iterTroveList())
    repos = conaryclient.ConaryClient(conaryCfg).getRepos()
    buildFlavor = conaryCfg.buildFlavor
    sourceTroveTups = [ (x[0], x[1],
                         deps.overrideFlavor(buildFlavor, x[2]))
                         for x in troveList ]
    return loadSourceTroves(job, repos, sourceTroveTups)
