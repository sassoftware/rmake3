#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import copy
import fnmatch
import itertools
import re
import os
import shutil
import tempfile

from conary.build import cook, grouprecipe, recipe, use
from conary.build.cook import signAbsoluteChangeset
from conary.conaryclient import cmdline
from conary.deps import deps
from conary.lib import log, magic, util
from conary.repository import trovesource
from conary import checkin
from conary import errors as conaryerrors
from conary import state
from conary import versions

from rmake import errors
from rmake import compat
from rmake.cmdline import cmdutil
from rmake.lib import recipeutil
from rmake.build import buildjob, buildtrove

BUILD_RECURSE_GROUPS_NONE = 0   # don't recurse groups, build the group only
BUILD_RECURSE_GROUPS_BINARY = 1 # find and recurse the binary version of the 
                                # group
BUILD_RECURSE_GROUPS_SOURCE = 2 # find and recurce the source version of the
                                # group

def getBuildJob(buildConfig, conaryclient, troveSpecList,
                message=None, recurseGroups=BUILD_RECURSE_GROUPS_NONE, 
                configDict=None, oldTroveDict=None, updateSpecs=None,
                rebuild=False):
    trovesByContext = {}

    for troveSpec in list(troveSpecList):
        if not isinstance(troveSpec, tuple):
            troveSpec = cmdutil.parseTroveSpec(troveSpec)

        if len(troveSpec) == 3:
            context = ''
        else:
            context = troveSpec[3]
            troveSpec = troveSpec[:3]

        if troveSpec[2] is None:
            troveSpec = (troveSpec[0], troveSpec[1], deps.parseFlavor(''))
        trovesByContext.setdefault(context, []).append(troveSpec)

    job = buildjob.BuildJob()

    # don't store all the contexts with this job - they're useless past the
    # initialization step.
    if configDict:
        mainConfig = configDict['']
        job.setMainConfig(configDict[''])
    else:
        cfg = copy.deepcopy(buildConfig)
        cfg.dropContexts()
        mainConfig = cfg
    mainConfig.recurseGroups = int(recurseGroups)
    job.setMainConfig(mainConfig)

    baseMatchRules = mainConfig.matchTroveRule
    for contextStr, troveSpecList in trovesByContext.iteritems():
        contextBaseMatchRules = baseMatchRules
        if configDict and contextStr in configDict:
            cfg = configDict[contextStr]
        elif contextStr:
            # making this a copy is critical
            cfg = copy.deepcopy(buildConfig)
            for context in contextStr.split(','):
                cfg.setContext(context)
            cfg.dropContexts()
        else:
            # don't bother with baseMatchRules in the base config.
            contextBaseMatchRules = []
            cfg = copy.deepcopy(buildConfig)
            cfg.dropContexts()
            contextStr = ''
            job.setMainConfig(cfg)
        cfg.initializeFlavors()
        use.setBuildFlagsFromFlavor(None, cfg.buildFlavor, error=False)
        if not cfg.buildLabel and cfg.installLabelPath:
            cfg.buildLabel = cfg.installLabelPath[0]
        troveSpecList = list(set(troveSpecList))
        troveList = getTrovesToBuild(cfg, conaryclient, troveSpecList,
                         message=None,
                         recurseGroups=recurseGroups,
                         matchSpecs=contextBaseMatchRules + cfg.matchTroveRule,
                         reposName=mainConfig.reposName,
                         updateSpecs=updateSpecs)
        if updateSpecs and oldTroveDict and contextStr in oldTroveDict:
            troveList = _matchUpdateRestrictions(mainConfig.reposName,
                                                 oldTroveDict[contextStr],
                                                 troveList,
                                                 updateSpecs)
        if rebuild:
            prebuiltBinaries = _findLatestBinariesForTroves(conaryclient,
                                                        mainConfig.reposName,
                                                        troveList)
            if not job.getMainConfig().prebuiltBinaries:
                job.getMainConfig().prebuiltBinaries = prebuiltBinaries
            else:
                job.getMainConfig().prebuiltBinaries.extend(prebuiltBinaries)
        if mainConfig.prepOnly:
            buildType = buildtrove.TROVE_BUILD_TYPE_PREP
        else:
            buildType = buildtrove.TROVE_BUILD_TYPE_NORMAL

        for name, version, flavor in troveList:
            if flavor is None:
                flavor = deps.parseFlavor('')
            bt = buildtrove.BuildTrove(None, name, version, flavor,
                                       context=contextStr,
                                       buildType=buildType)
            job.addTrove(name, version, flavor, contextStr, bt)
            job.setTroveConfig(bt, cfg)
    return job


def getTrovesToBuild(cfg, conaryclient, troveSpecList, message=None, 
                     recurseGroups=BUILD_RECURSE_GROUPS_NONE, matchSpecs=None, 
                     reposName=None, updateSpecs=None):
    toBuild = []
    toFind = {}
    groupsToFind = []
    if not matchSpecs:
        matchSpecs = []
    if reposName is None:
        reposName = cfg.reposName


    repos = conaryclient.getRepos()
    cfg.resolveTroveTups = _getResolveTroveTups(cfg, repos)
    cfg.recurseGroups = int(recurseGroups)

    cfg.buildTroveSpecs = []
    newTroveSpecs = []
    recipesToCook = []
    for troveSpec in list(troveSpecList):
        if not isinstance(troveSpec, tuple):
            troveSpec = cmdutil.parseTroveSpec(troveSpec)
        if len(troveSpec) == 3:
            context = ''
        else:
            context = troveSpec[3]
            troveSpec = troveSpec[:3]

        if (troveSpec[0].startswith('group-') and not recurseGroups
            and not compat.ConaryVersion().supportsCloneNonRecursive()):
            log.warning('You will not be able to commit this group build'
                        ' without upgrading conary.')
        if troveSpec[2] is None:
            troveSpec = (troveSpec[0], troveSpec[1], deps.parseFlavor(''))

        if (not troveSpec[1] and not os.path.isdir(troveSpec[0])
            and os.access(troveSpec[0], os.R_OK)
            and troveSpec[0].endswith('.recipe')):
            # don't rely on cwd, but do allow for symlinks to change
            # when restarting.  Is that sane?  Or should I just do realpath?
            troveSpec = (os.path.abspath(troveSpec[0]),) + troveSpec[1:]
            cfg.buildTroveSpecs.append(troveSpec)
            recipesToCook.append((os.path.realpath(troveSpec[0]), troveSpec[2]))
            continue
        cfg.buildTroveSpecs.append(troveSpec)

        if troveSpec[0].startswith('group-') and recurseGroups:
            groupsToFind.append(troveSpec)
            if recurseGroups == BUILD_RECURSE_GROUPS_SOURCE:
                newTroveSpecs.append(troveSpec)
        else:
            newTroveSpecs.append(troveSpec)

    localTroves = [(_getLocalCook(conaryclient, cfg, x[0], message), x[1])
                     for x in recipesToCook ]
    localTroves = [(x[0][0], x[0][1], x[1]) for x in localTroves]
    if recurseGroups == BUILD_RECURSE_GROUPS_SOURCE:
        compat.ConaryVersion().requireFindGroupSources()
        localGroupTroves = [ x for x in localTroves 
                             if x[0].startswith('group-') ]
        toBuild.extend(_findSourcesForSourceGroup(repos, reposName, cfg,
                                                  groupsToFind,
                                                  localGroupTroves,
                                                  updateSpecs))
    elif recurseGroups == BUILD_RECURSE_GROUPS_BINARY:
        newTroveSpecs.extend(_findSpecsForBinaryGroup(repos, reposName, cfg,
                                                      groupsToFind,
                                                      updateSpecs))

    for troveSpec in newTroveSpecs:
        sourceName = troveSpec[0].split(':')[0] + ':source'

        s = toFind.setdefault((sourceName, troveSpec[1], None), [])
        if troveSpec[2] not in s:
            s.append(troveSpec[2])


    results = repos.findTroves(cfg.buildLabel, toFind, None)

    for troveSpec, troveTups in results.iteritems():
        flavorList = toFind[troveSpec]
        for troveTup in troveTups:
            for flavor in flavorList:
                toBuild.append((troveTup[0], troveTup[1], flavor))

    toBuild.extend(localTroves)

    if matchSpecs:
        toBuild = _filterListByMatchSpecs(reposName, matchSpecs, toBuild)
    return toBuild

def _filterListByMatchSpecs(reposName, matchSpecs, troveList):
    matchSpecs = [ cmdline.parseTroveSpec(x, allowEmptyName=True)
                    for x in matchSpecs ]
    hasAddSpec = False
    newTroveList = []
    for troveTup in troveList:
        if troveTup[2] is None:
            flavor = deps.parseFlavor('')
        else:
            flavor = troveTup[2]
        newTroveList.append((troveTup[0], troveTup[1], flavor))
    troveList = newTroveList

    troveMap = {}
    for troveTup in troveList:
        key = (troveTup[0].split(':')[0], troveTup[1], troveTup[2])
        troveMap.setdefault(key, []).append(troveTup)

    finalMatchSpecs = {}
    for matchSpec in matchSpecs:
        name = matchSpec[0]
        if name and name[0] == '-':
            removeSpec = True
            name = name[1:]
        else:
            hasAddSpec = True
            removeSpec = False
        if not name:
            filterFn = lambda x: True
        else:
            filterFn = lambda x: fnmatch.fnmatchcase(x[0], name)

        # add all packages that match glob (could be empty in which case
        # all packages are added.
        finalMatchSpecs.update(dict.fromkeys([(x[0], matchSpec[1],
                                        matchSpec[2]) for x in troveMap
                                        if filterFn(x)],
                                        removeSpec))


    troveSource = trovesource.SimpleTroveSource(troveMap)
    troveSource = recipeutil.RemoveHostSource(troveSource,
                                              reposName)
    results = troveSource.findTroves(None, finalMatchSpecs, None,
                                     allowMissing=True)
    toRemove = []
    toAdd = set()
    for matchSpec, resultList in results.iteritems():
        if not finalMatchSpecs[matchSpec]: # this matchSpec was prepended by
                                           # a - sign
            toAdd.update(resultList)
        else:
            toRemove.extend(resultList)
    if not hasAddSpec:
        toAdd = set(troveMap)
    toAdd.difference_update(toRemove)
    return list(itertools.chain(*(troveMap[x] for x in toAdd)))

def _matchUpdateRestrictions(reposName, oldTroveList,
                             newTroveList, updateSpecs, 
                             binaries=False):
    troveMap = {}
    for troveTup in itertools.chain(oldTroveList, newTroveList):
        if binaries:
            key = (troveTup[0].split(':')[0], troveTup[1], troveTup[2])
        else: 
            key = (troveTup[0].split(':')[0] + ':source', 
                   troveTup[1], troveTup[2])
        troveMap.setdefault(key, []).append(troveTup)

    updateDict = {}
    newUpdateSpecs = []
    if not updateSpecs:
        return newTroveList
    firstMatch = True
    for troveSpec in updateSpecs:
        if not isinstance(troveSpec, tuple):
            troveSpec = cmdutil.parseTroveSpec(troveSpec)

        if binaries:
            troveSpec = (troveSpec[0].split(':')[0], troveSpec[1], troveSpec[2])
        else:
            troveSpec = (troveSpec[0].split(':')[0] + ':source', 
                         troveSpec[1], troveSpec[2])
        if troveSpec[0] and troveSpec[0][0] == '-':
            sense = False
            troveSpec = (troveSpec[0][1:], troveSpec[1], troveSpec[2])
        else:
            sense = True

        name = troveSpec[0]
        if not name:
            filterFn = lambda x: True
        else:
            filterFn = lambda x: fnmatch.fnmatchcase(x[0], name)

        # add all packages that match glob (could be empty in which case
        # all packages are added.
        specs = set([(x[0], troveSpec[1], troveSpec[2]) for x in troveMap
                      if filterFn(x)])
        if not specs:
            newUpdateSpecs.append(troveSpec)
            updateDict[troveSpec] = sense
        updateDict.update(dict.fromkeys(specs, sense))
        for spec in specs:
            if spec in newUpdateSpecs:
                newUpdateSpecs.remove(spec)
        newUpdateSpecs.extend(specs)

    allNewNames = set([ x[0] for x in newTroveList ])
    allOldNames = set([ x[0] for x in oldTroveList ])
    oldTroveList = [ x for x in oldTroveList if x[0] in allNewNames ]

    oldTroves = trovesource.SimpleTroveSource(oldTroveList)
    oldTroves = recipeutil.RemoveHostSource(oldTroves, reposName)
    newTroves = trovesource.SimpleTroveSource(newTroveList)
    newTroves = recipeutil.RemoveHostSource(newTroves, reposName)

    toUse = set()
    firstMatch = True
    for updateSpec in newUpdateSpecs:
        positiveMatch = updateDict[updateSpec]
        oldResults = oldTroves.findTroves(None, [updateSpec], None,
                                          allowMissing=True).get(updateSpec, [])
        newResults = newTroves.findTroves(None, [updateSpec], None,
                                          allowMissing=True).get(updateSpec, [])
        oldNames = set(x[0] for x in oldResults)
        newNames = set(x[0] for x in newResults)
        if positiveMatch:
            if firstMatch:
                # if the user starts with --update info-foo then they want to
                # by default not update anything not mentioned
                toUse = set(oldTroveList)
                toUse.update(x for x in newTroveList 
                             if x[0] not in allOldNames)
                firstMatch = False
            # don't discard any packages for which we don't have
            toKeep = [ x for x in toUse if x[0] not in newNames ]
            toUse.difference_update(oldResults)
            toUse.update(newResults)
            toUse.update(toKeep)
        else:
            if firstMatch:
                # if the user starts with --update -info-foo then they want to
                # update everything _except_ info-foo
                toUse = set(newTroveList)
                firstMatch = False
            toKeep = [ x for x in toUse if x[0] not in oldNames ]
            toUse.difference_update(newResults)
            toUse.update(oldResults)
            toUse.update(toKeep)
    return list(toUse)

def _getResolveTroveTups(cfg, repos):
    # get resolve troves - use installLabelPath and install flavor
    # for these since they're used for dep resolution
    try:
        allResolveTroves = itertools.chain(*cfg.resolveTroves)
        results = repos.findTroves(cfg.installLabelPath,
                                   list(allResolveTroves), cfg.flavor)
    except Exception, err:
        context = cfg.context
        if not context:
            context = 'default'
        raise errors.RmakeError("Could not find resolve troves for [%s] context: %s\n" % (context, err))

    resolveTroves = []
    for resolveTroveSpecList in cfg.resolveTroves:
        lst = []
        for troveSpec in resolveTroveSpecList:
            lst.extend(results[troveSpec])
        resolveTroves.append(lst)

    return resolveTroves



def _getLocalCook(conaryclient, cfg, recipePath, message):
    if not hasattr(cook, 'getRecipeInfoFromPath'):
        raise errors.RmakeError('Local cooks require at least conary 1.0.19')
    recipeDir = os.path.dirname(recipePath)

    # We do not want to sign commits to the local repository, doing so
    # would require that we manage keys in this repository as well.
    oldKey = cfg.signatureKey
    oldMap = cfg.signatureKeyMap
    oldInteractive = cfg.interactive
    try:
        cfg.signatureKey = None
        cfg.signatureKeyMap = {}
        cfg.interactive = False

        if os.access(recipeDir + '/CONARY', os.R_OK):
            stateFile = state.ConaryStateFromFile(recipeDir + '/CONARY')
            if stateFile.hasSourceState():
                stateFile = stateFile.getSourceState()
                if stateFile.getVersion() != versions.NewVersion():
                    return _shadowAndCommit(conaryclient, cfg, recipeDir, 
                                            stateFile, message)
                else:
                    return _commitRecipe(conaryclient, cfg, recipePath, message,
                                         branch=stateFile.getBranch())
        return _commitRecipe(conaryclient, cfg, recipePath, message)
    finally:
        cfg.signatureKey = oldKey
        cfg.signatureKeyMap = oldMap
        cfg.interactive = oldInteractive

def _getPathList(repos, cfg, recipePath, relative=False):
    loader, recipeClass, sourceVersion = cook.getRecipeInfoFromPath(repos, cfg,
                                                                recipePath)

    log.info("Getting relevant path information from %s..." % recipeClass.name)
    recipeDir = os.path.dirname(recipeClass.filename)
    srcdirs = [ recipeDir ]
    recipeObj = None
    buildLabel = sourceVersion.trailingLabel()
    macros = {'buildlabel' : buildLabel.asString(),
              'buildbranch' : sourceVersion.branch().asString()}
    if recipe.isPackageRecipe(recipeClass):
        recipeObj = recipeClass(cfg, None, srcdirs, macros, lightInstance=True)
    elif recipe.isGroupRecipe(recipeClass):
        recipeObj = recipeClass(repos, cfg, buildLabel, None, None, 
                                srcdirs=srcdirs,
                                extraMacros=macros)
    else:
        # no included files for the rest of the recipe types
        return recipeClass, [recipePath]

    try:
        if hasattr(recipeObj, 'loadPolicy'):
            recipeObj.loadPolicy()
        cook._callSetup(cfg, recipeObj)
    except (conaryerrors.ConaryError, conaryerrors.CvcError), msg:
        raise errors.RmakeError("could not initialize recipe: %s" % (msg))
    pathList = recipeObj.fetchLocalSources() + [recipePath ]
    if relative:
        finalPathList = []
        for path in pathList:
            if path[0] == '/':
                path = path[(len(recipeDir) +1):]
            finalPathList.append(path)
    else:
        finalPathList = pathList
    return recipeClass, finalPathList


def _getConfigInfo(fileName):
    fileMagic = magic.magic(fileName)
    if (checkin.cfgRe.match(fileName) 
        or (fileMagic and isinstance(fileMagic, magic.script))):
        return True
    else:
        return False

def _shadowAndCommit(conaryclient, cfg, recipeDir, stateFile, message):
    repos = conaryclient.getRepos()
    conaryCompat = compat.ConaryVersion()

    oldSourceVersion = stateFile.getVersion()
    targetLabel = cfg.getTargetLabel(oldSourceVersion)
    if not targetLabel: 
        raise errors.RmakeError(
                    'Cannot cook local recipes unless a target label is set')
    skipped, cs = conaryclient.createShadowChangeSet(str(targetLabel),
                                           [stateFile.getNameVersionFlavor()])
    recipePath = recipeDir + '/' + stateFile.getName().split(':')[0] + '.recipe'
    recipeClass, pathList = _getPathList(repos, cfg, recipePath, relative=True)

    troveName = stateFile.getName()
    troveVersion = stateFile.getVersion()

    if not skipped:
        signAbsoluteChangeset(cs, None)
        repos.commitChangeSet(cs)

    log.info("Shadowing %s to internal repository..." % troveName)
    shadowBranch = troveVersion.createShadow(targetLabel).branch()
    shadowVersion = repos.findTrove(None,
                                    (troveName, str(shadowBranch), 
                                    None), None)[0][1]


    cwd = os.getcwd()
    prefix = 'rmake-shadow-%s-' % troveName.split(':')[0]
    shadowSourceDir = tempfile.mkdtemp(prefix=prefix)
    try:
        log.info("Committing local changes to %s to the"
                  " internal repository..." % troveName)
        log.resetErrorOccurred()
        checkin.checkout(repos, cfg, shadowSourceDir,
                        ['%s=%s' % (troveName, shadowVersion)])

        if compat.ConaryVersion().stateFileVersion() > 0:
            kw = dict(repos=repos)
        else:
            kw = {}
        # grab new and old state and make any modifications due to adding
        # or deleting of files (we assume files that don't exist are 
        # autosource and can be ignored)
        oldState = conaryCompat.ConaryStateFromFile(recipeDir + '/CONARY',
                                                    repos=repos).getSourceState()
        newConaryState = conaryCompat.ConaryStateFromFile(
                                                shadowSourceDir + '/CONARY',
                                                repos=repos)
        newState = newConaryState.getSourceState()

        neededFiles = set(x[1] for x in oldState.iterFileList()
                          if os.path.exists(os.path.join(recipeDir, x[1])))
        neededFiles.update(pathList)
        autoSourceFiles = set(x[1] for x in oldState.iterFileList()
                          if oldState.fileIsAutoSource(x[0]))

        existingFiles = set(x[1] for x in newState.iterFileList()
                        if os.path.exists(os.path.join(shadowSourceDir, x[1])))
        toCopy = neededFiles & existingFiles
        toDel = existingFiles - neededFiles
        toAdd = neededFiles - existingFiles
        for sourceFile in (toCopy | toAdd):
            newPath = os.path.join(shadowSourceDir, sourceFile)
            if os.path.dirname(sourceFile):
                util.mkdirChain(os.path.dirname(newPath))
            if os.path.isdir(sourceFile):
                util.mkdirChain(newPath)
            else:
                shutil.copyfile(os.path.join(recipeDir, sourceFile), newPath)

        os.chdir(shadowSourceDir)
        if hasattr(cfg.sourceSearchDir, '_getUnexpanded'):
            cfg.configKey('sourceSearchDir',
                          cfg.sourceSearchDir._getUnexpanded())

        for f in toDel:
            checkin.removeFile(f)
        if toDel:
            # toDel modifies the CONARY file on disk, so reload with the
            # changes made there.
            newState = conaryCompat.ConaryStateFromFile(
                                            shadowSourceDir + '/CONARY',
                                            repos=repos).getSourceState()

        if conaryCompat.stateFileVersion() == 0:
            checkin.addFiles(toAdd)
        else:
            oldPathIds = dict((x[1], x[0]) for x in oldState.iterFileList())
            for path in toAdd:
                if path in oldPathIds:
                    isConfig = oldState.fileIsConfig(oldPathIds[path])
                else:
                    isConfig = _getConfigInfo(path)
                checkin.addFiles([path], binary=not isConfig, text=isConfig)
            if toAdd:
                # get the new pathIDs for all the added troves, 
                # since we can't set the refresh setting without the 
                # needed pathIds
                newState = conaryCompat.ConaryStateFromFile(
                                                shadowSourceDir + '/CONARY',
                                                repos=repos).getSourceState()
            newPathIds = dict((x[1], x[0]) for x in newState.iterFileList())

            for path in (toCopy | toAdd):
                if path in oldPathIds:
                    isConfig = oldState.fileIsConfig(oldPathIds[path])
                else:
                    isConfig = _getConfigInfo(path)

                newState.fileIsConfig(newPathIds[path], isConfig)

            for path in autoSourceFiles:
                if path in newPathIds:
                    needsRefresh = oldState.fileNeedsRefresh(oldPathIds[path])
                    newState.fileNeedsRefresh(newPathIds[path], needsRefresh)

            # we may have modified the state file. Write it back out to 
            # disk so it will be picked up by the commit.
            newConaryState.setSourceState(newState)
            newConaryState.write(shadowSourceDir + '/CONARY')

        if message is None and compat.ConaryVersion().supportsCloneCallback():
            message = 'Automated rMake commit'

        _doCommit('%s/%s' % (recipeDir, troveName), repos, cfg, message)

        newState = state.ConaryStateFromFile(shadowSourceDir + '/CONARY', **kw)
        return newState.getSourceState().getNameVersionFlavor()
    finally:
        os.chdir(cwd)
        if hasattr(cfg.sourceSearchDir, '_getUnexpanded'):
            cfg.configKey('sourceSearchDir',
                          cfg.sourceSearchDir._getUnexpanded())
        shutil.rmtree(shadowSourceDir)

def _doCommit(recipePath, repos, cfg, message):
    try:
        kw = {}
        if compat.ConaryVersion().supportsForceCommit():
            kw.update(force=True)
        rv = checkin.commit(repos, cfg, message, **kw)
    except (conaryerrors.CvcError, conaryerrors.ConaryError), msg:
        raise errors.RmakeError("Could not commit changes to build"
                                " recipe %s: %s" % (recipePath, msg))

    if log.errorOccurred():
        raise errors.RmakeError("Could not commit changes to build"
                                " local file %s" % recipePath)
    return rv

def _commitRecipe(conaryclient, cfg, recipePath, message, branch=None):
    repos = conaryclient.getRepos()
    conaryCompat = compat.ConaryVersion()

    recipeClass, pathList = _getPathList(repos, cfg, recipePath)
    sourceName = recipeClass.name + ':source'


    log.info("Creating a copy of %s in the rMake internal repository..." % recipeClass.name)

    cwd = os.getcwd()
    recipeDir = tempfile.mkdtemp()
    log.resetErrorOccurred()
    try:
        fileNames = []
        # Create a source trove that matches the recipe we're trying to cook
        if not branch:
            branch = versions.Branch([cfg.buildLabel])
        targetLabel = cfg.getTargetLabel(branch)
        if compat.ConaryVersion().supportsNewPkgBranch():
            buildBranch = branch.createShadow(targetLabel)
            kw = dict(buildBranch=buildBranch)
        else:
            buildBranch = versions.Branch([targetLabel])
            kw={}
            cfg.buildLabel = targetLabel

        if not repos.getTroveLeavesByBranch(
            { sourceName : { buildBranch : None } }).get(sourceName, None):
            # we pass it None for repos to avoid the label-based check for
            # existing packages.
            checkin.newTrove(None, cfg, recipeClass.name, dir=recipeDir, **kw)
        else:
            # see if this package exists on our build branch
            checkin.checkout(repos, cfg, recipeDir,
                             ['%s=%s' % (sourceName, buildBranch)])

        os.chdir(recipeDir)

        sourceState = state.ConaryStateFromFile(recipeDir + '/CONARY').getSourceState()
        fileNames = dict((os.path.basename(x), x) for x in pathList)

        for (pathId, baseName, fileId, version) in list(sourceState.iterFileList()):
            # update or remove any currently existing files
            if baseName not in fileNames:
                sourceState.removeFilePath(baseName)
            else:
                shutil.copyfile(fileNames[baseName],
                                os.path.join(recipeDir, baseName))
                del fileNames[baseName]

        for baseName, path in fileNames.iteritems():
            shutil.copyfile(path, os.path.join(recipeDir, baseName))

        if conaryCompat.stateFileVersion() > 0:
            # mark all the files as binary - this this version can
            # never be checked in, it doesn't really matter, but
            # conary likes us to give a value.
            for fileName in fileNames:
                isConfig = _getConfigInfo(fileName)
                checkin.addFiles([fileName], binary=not isConfig, text=isConfig)
        else:
            checkin.addFiles(fileNames)

        _doCommit(recipePath, repos, cfg, 'Temporary recipe build for rmake')

        newState = conaryCompat.ConaryStateFromFile(recipeDir + '/CONARY',
                                                    repos=repos)
        return newState.getSourceState().getNameVersionFlavor()
    finally:
        os.chdir(cwd)
        shutil.rmtree(recipeDir)


def _findSpecsForBinaryGroup(repos, reposName, cfg, groupsToFind, updateSpecs):
    newTroveSpecs = []
    results = repos.findTroves(cfg.buildLabel,
                               groupsToFind, cfg.buildFlavor)
    groupTuples = []
    for troveSpec, troveList in results.iteritems():
        for troveTup in troveList:
            groupTuples.append((troveTup[0], troveTup[1], troveTup[2]))
    groupTuples = _matchUpdateRestrictions(reposName,
                                           cfg.recursedGroupTroves,
                                           troveList,
                                           updateSpecs, binaries=True)

    groups = repos.getTroves(groupTuples)
    groups = dict(itertools.izip(groupTuples, groups))
    cfg.recursedGroupTroves.extend(groupTuples)
    # line up troveSpec flavors to trovetuples
    troveSpecsByName = {}
    for troveSpec in groupsToFind:
        troveSpecsByName.setdefault(troveSpec[0], []).append(troveSpec[2])
    for groupTup in groupTuples:
        group = groups[groupTup]
        for flavor in troveSpecsByName[groupTup[0]]:
            groupSource = (group.getSourceName(),
                           group.getVersion().getSourceVersion(False),
                           flavor)
            newTroveSpecs.append(groupSource)

        troveTups = list(group.iterTroveList(strongRefs=True,
                                             weakRefs=True))
        troveTups = ((x[0].split(':')[0], x[1], x[2])
                         for x in troveTups)
        troveTups = (x for x in troveTups
                     if not x[0].startswith('group-'))
        troveTups = list(set(troveTups))
        troveList = repos.getTroves(troveTups, withFiles=False)
        for trove in troveList:
            n = trove.getSourceName()
            newTroveSpecs.append((n,
                        trove.getVersion().getSourceVersion().branch(),
                        trove.getFlavor()))
    return newTroveSpecs

def _findSourcesForSourceGroup(repos, reposName, cfg, groupsToFind, 
                               localGroups, updateSpecs):
    findSpecs = {}
    for troveSpec in groupsToFind:
        sourceName = troveSpec[0].split(':')[0] + ':source'
        l = findSpecs.setdefault((sourceName, troveSpec[1], None), [])
        l.append(troveSpec[2])
    results = repos.findTroves(cfg.buildLabel, findSpecs, cfg.flavor)
    allTups = []
    groupTuples = []
    for troveSpec, troveTupList in results.iteritems():
        flavors = findSpecs[troveSpec]
        for flavor in flavors:
            for troveTup in troveTupList:
                name, version = troveTup[0:2]
                groupTuples.append((name, version, flavor))
    groupTuples += localGroups
    groupTuples = _matchUpdateRestrictions(reposName,
                                           cfg.recursedGroupTroves,
                                           groupTuples,
                                           updateSpecs)

    cfg.recursedGroupTroves = groupTuples
    for name, version, flavor in groupTuples:
        localRepos = recipeutil.RemoveHostRepos(repos, reposName)
        if version.getHost() == reposName:
            realLabel = version.branch().parentBranch().label()
        else:
            realLabel = version.trailingLabel()
        (loader, recipeObj, relevantFlavor) = \
                recipeutil.loadRecipe(repos, name, version, flavor,
                              defaultFlavor=cfg.buildFlavor,
                              installLabelPath=cfg.installLabelPath,
                              buildLabel=realLabel)
        troveTups = grouprecipe.findSourcesForGroup(localRepos, recipeObj)
        allTups.extend(troveTups)

    allTups = [ x for x in allTups if not x[0].startswith('group-') ]
    return allTups

def displayBuildInfo(job, verbose=False, quiet=False):
    trovesByContext = {}
    configDict = job.getConfigDict()
    for (n,v,f, context) in sorted(job.iterTroveList(withContexts=True)):
        trovesByContext.setdefault(context, []).append((n,v,f))
    if not quiet:
        if '' not in trovesByContext:
            print '\n{Default Context}\n'
            config = configDict['']
            if verbose:
                config.setDisplayOptions(hidePasswords=True)
                config.display()
            else:
                config.displayKey('copyInConary')
                config.displayKey('copyInConfig')

    for context, troveList in sorted(trovesByContext.iteritems()):
        if not quiet:
            config = configDict[context]
            if not context:
                print '\n{Default Context}\n'
            else:
                print '\n{%s}\n' % context
            print 'ResolveTroves:'
            for idx, resolveTroveList in enumerate(config.resolveTroveTups):
                print ''
                for n,v,f in sorted(resolveTroveList):
                    print '%s=%s[%s]' % (n, v, f)
            print ''
            print 'Configuration:'
            config.setDisplayOptions(hidePasswords=True)
            if verbose:
                config.display()
            else:
                if not context:
                    config.displayKey('copyInConfig')
                    config.displayKey('copyInConary')
                config.displayKey('buildFlavor')
                config.displayKey('flavor')
                config.displayKey('installLabelPath')
                config.displayKey('repositoryMap')
                config.displayKey('resolveTrovesOnly')
                config.displayKey('user')
            print ''
            print 'Building:'
        for n,v,f in troveList:
            if f is not None and not f.isEmpty():
                f = '[%s]' % f
            else:
                f = ''
            if context:
                contextStr = '{%s}' % context
            else:
                contextStr = ''
            print '%s=%s/%s%s%s' % (n, v.trailingLabel(),
                                    v.trailingRevision(), f,
                                    contextStr)


def _findLatestBinariesForTroves(conaryclient, reposName, troveList):
    # The only possible built binaries are those with exactly the same
    # branch.
    repos = conaryclient.getRepos()
    troveSpecs = []
    for troveTup in troveList:
        if (troveTup[1].trailingLabel().getHost() == reposName
            and troveTup[1].branch().hasParentBranch()):
            troveSpecs.append((troveTup[0].split(':')[0],
                              str(troveTup[1].branch().parentBranch().label()),
                              None))
        else:
            troveSpecs.append((troveTup[0].split(':')[0],
                              str(troveTup[1].trailingLabel()),
                              None))
    results = repos.findTroves(None, troveSpecs, None, allowMissing=True)
    binaryTroveList = list(itertools.chain(*results.itervalues()))
    return binaryTroveList

