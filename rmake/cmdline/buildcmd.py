import itertools
import os
import shutil
import tempfile

from conary.build import cook
from conary.build.cook import signAbsoluteChangeset
from conary.conaryclient import cmdline
from conary.lib import log
from conary import checkin
from conary import state
from conary import versions

from rmake import errors

def getResolveTroveTups(cfg, repos):
    # get resolve troves - use installLabelPath and install flavor
    # for these since they're used for dep resolution
    try:
        allResolveTroves = itertools.chain(*cfg.resolveTroves)
        results = repos.findTroves(cfg.installLabelPath,
                                   allResolveTroves, cfg.flavor)
    except Exception, err:
        raise errors.RmakeError("Could not find resolve troves: %s\n" % err)

    resolveTroves = []
    for resolveTroveSpecList in cfg.resolveTroves:
        lst = []
        for troveSpec in resolveTroveSpecList:
            lst.extend(results[troveSpec])
        resolveTroves.append(lst)

    return resolveTroves



def getTrovesToBuild(conaryclient, troveSpecList, limitToHosts=None, 
                     message=None):
    toBuild = []
    toFind = {}
    groupsToFind = []

    repos = conaryclient.getRepos()
    cfg = conaryclient.cfg

    cfg.resolveTroveTups = getResolveTroveTups(cfg, repos)

    cfg.limitToHosts = limitToHosts
    cfg.buildTroveSpecs = []
    newTroveSpecs = []
    recipesToCook = []
    for troveSpec in list(troveSpecList):
        if not isinstance(troveSpec, tuple):
            troveSpec = cmdline.parseTroveSpec(troveSpec)
            if (not troveSpec[1] and not os.path.isdir(troveSpec[0]) 
                and os.access(troveSpec[0], os.R_OK)):
                cfg.buildTroveSpecs.append((troveSpec[0], None, troveSpec[2]))
                recipesToCook.append((os.path.realpath(troveSpec[0]), troveSpec[2]))
                continue
        cfg.buildTroveSpecs.append(troveSpec)

        if troveSpec[0].startswith('group-'):
            groupsToFind.append(troveSpec)
        else:
            newTroveSpecs.append(troveSpec)


    results = repos.findTroves(cfg.buildLabel,
                               groupsToFind, cfg.buildFlavor)
    groups = repos.getTroves(list(itertools.chain(*results.itervalues())))
    for group in groups:
        troveTups = list(group.iterTroveList(strongRefs=True,
                                             weakRefs=True))
        troveTups = ((x[0].split(':')[0], x[1], x[2])
                         for x in troveTups)
        troveTups = (x for x in troveTups
                     if not x[0].startswith('group-'))
        if limitToHosts:
            troveTups = (x for x in troveTups
                         if (x[1].trailingLabel().getHost()
                             in limitToHosts))
        troveTups = list(set(troveTups))
        troveList = repos.getTroves(troveTups, withFiles=False)
        for trove in troveList:
            n = trove.getSourceName()
            newTroveSpecs.append((n,
                        trove.getVersion().getSourceVersion().branch(),
                        trove.getFlavor()))

    for troveSpec in newTroveSpecs:
        sourceName = troveSpec[0].split(':')[0] + ':source'

        s = toFind.setdefault((sourceName, troveSpec[1], None), [])
        if troveSpec[2] not in s:
            log.debug("building troveSpec: %s", troveSpec)
            s.append(troveSpec[2])

    log.debug("using buildLabel: %s", cfg.buildLabel)
    log.debug("using installLabelPath (for finding dep troves): %s", cfg.installLabelPath)

    results = repos.findTroves(cfg.buildLabel, toFind, None)

    for troveSpec, troveTups in results.iteritems():
        flavorList = toFind[troveSpec]
        for troveTup in troveTups:
            for flavor in flavorList:
                toBuild.append((troveTup[0], troveTup[1], flavor))

    localTroves = [(_getLocalCook(conaryclient, x[0], message), x[1])
                     for x in recipesToCook]
    toBuild.extend((x[0][0], x[0][1], x[1]) for x in localTroves)
    return toBuild

def _getLocalCook(conaryclient, recipePath, message):
    if not hasattr(cook, 'getRecipeInfoFromPath'):
        raise errors.RmakeError('Local cooks require at least conary 1.0.19')
    recipeDir = os.path.dirname(recipePath)

    if os.access(recipeDir + '/CONARY', os.R_OK):
        stateFile = state.ConaryStateFromFile(recipeDir + '/CONARY')
        if stateFile.hasSourceState():
            stateFile = stateFile.getSourceState()
            if stateFile.getVersion() != versions.NewVersion():
                return _shadowAndCommit(conaryclient, recipeDir, stateFile, 
                                        message)
    return _commitRecipe(conaryclient, recipePath, message)

def _getPathList(repos, cfg, recipePath):
    loader, recipeClass, sourceVersion = cook.getRecipeInfoFromPath(repos, cfg,
                                                                recipePath)

    log.info("Getting relevant path information from %s..." % recipeClass.name)
    srcdirs = [ os.path.dirname(recipeClass.filename) ]
    recipeObj = recipeClass(cfg, None, srcdirs, cfg.macros, lightInstance=True)
    cook._callSetup(cfg, recipeObj)
    pathList = recipeObj.fetchLocalSources() + [recipePath ]
    return recipeClass, pathList



def _shadowAndCommit(conaryclient, recipeDir, stateFile, message):
    cfg = conaryclient.cfg
    repos = conaryclient.getRepos()

    oldSourceVersion = stateFile.getVersion()
    targetLabel = cfg.getTargetLabel(oldSourceVersion)
    if not targetLabel: 
        raise errors.RmakeError(
                    'Cannot cook local recipes unless a target label is set')
    skipped, cs = conaryclient.createShadowChangeSet(str(targetLabel),
                                           [stateFile.getNameVersionFlavor()])

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

        # grab new and old state and make any modifications due to adding
        # or deleting of files (we assume files that don't exist are 
        # autosource and can be ignored)
        oldState = state.ConaryStateFromFile(recipeDir + '/CONARY').getSourceState()
        newState = state.ConaryStateFromFile(shadowSourceDir + '/CONARY').getSourceState()

        neededFiles = set(x[1] for x in oldState.iterFileList()
                          if os.path.exists(os.path.join(recipeDir, x[1])))

        existingFiles = set(x[1] for x in newState.iterFileList()
                        if os.path.exists(os.path.join(shadowSourceDir, x[1])))
        toCopy = neededFiles & existingFiles
        toDel = existingFiles - neededFiles
        toAdd = neededFiles - existingFiles

        for sourceFile in (toCopy | toAdd):
            newPath = os.path.join(shadowSourceDir, sourceFile)
            shutil.copyfile(os.path.join(recipeDir, sourceFile), newPath)

        os.chdir(shadowSourceDir)

        checkin.addFiles(toAdd)
        for f in toDel:
            checkin.removeFile(f)

        cfg.signatureKey = None
        cfg.signatureKeyMap = {}

        if message is None:
            message = 'Automated rMake commit'

        checkin.commit(repos, cfg, message)
        if log.errorOccurred():
            raise errors.RmakeError("Could not commit changes to build"
                                 " local file %s/%s" % (recipeDir, troveName))

        newState = state.ConaryStateFromFile(shadowSourceDir + '/CONARY')
        return newState.getSourceState().getNameVersionFlavor()
    finally:
        os.chdir(cwd)
        shutil.rmtree(shadowSourceDir)

def _commitRecipe(conaryclient, recipePath, message):
    cfg = conaryclient.cfg
    repos = conaryclient.getRepos()

    recipeClass, pathList = _getPathList(repos, cfg, recipePath)
    sourceName = recipeClass.name + ':source'


    log.info("Creating a copy of %s in the rMake internal repository..." % recipeClass.name)

    cwd = os.getcwd()
    recipeDir = tempfile.mkdtemp()
    log.resetErrorOccurred()
    try:
        # Create a source trove that matches the recipe we're trying to cook
        cfg.buildLabel = cfg.getTargetLabel(cfg.buildLabel)
        if repos.getTroveLeavesByLabel(
            { sourceName : { cfg.buildLabel : None } }).get(sourceName, None):
            # see if this package exists on our build branch

            checkin.checkout(repos, cfg, recipeDir, [sourceName])
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
            checkin.addFiles(fileNames)
        else:
            checkin.newTrove(repos, cfg, recipeClass.name, dir=recipeDir)
            os.chdir(recipeDir)
            cfg.recipeTemplate = None
            fileList = []
            for path in pathList:
                newFile = os.path.basename(path)
                fileList.append(newFile)
                shutil.copyfile(path, os.path.join(recipeDir, newFile))
            checkin.addFiles(fileList)

        checkin.commit(repos, cfg, 'Temporary recipe build for rmake')

        if log.errorOccurred():
            raise errors.RmakeError("Could not commit changes to build"
                                    " local recipe '%s'" % (recipePath))

        newState = state.ConaryStateFromFile(recipeDir + '/CONARY')
        return newState.getSourceState().getNameVersionFlavor()
    finally:
        os.chdir(cwd)
        shutil.rmtree(recipeDir)
