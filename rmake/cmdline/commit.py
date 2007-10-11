#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Commit command
"""
import itertools
import os
import shutil
import tempfile

from conary import checkin
from conary import state
from conary import versions
from conary.trove import Trove
from conary.build.cook import signAbsoluteChangeset
from conary.lib import log
from conary.conaryclient import callbacks
from conary.deps.deps import Flavor
from conary.repository import changeset
from conary.repository import trovesource

from rmake import compat

def commitJobs(conaryclient, jobList, reposName, message=None,
               commitOutdatedSources=False, sourceOnly = False,
               excludeSpecs=None):
    jobsToCommit = {}
    alreadyCommitted = []
    finalCs = changeset.ReadOnlyChangeSet()
    mapping = {}
    for job in jobList:
        if job.isCommitted():
            alreadyCommitted.append(job)
        else:
            jobsToCommit[job.jobId] = job
    jobsToCommit = jobsToCommit.values() # dedup job list

    if not jobsToCommit:
        err = 'Job(s) already committed'
        return False, err

    allTroves = []
    trovesByBranch = {}
    alreadyCommitted = False
    for job in jobsToCommit:
        mapping[job.jobId] = {}
        for trove in job.iterTroves():
            allTroves.append(trove)
            troveVersion = trove.getVersion()
            if troveVersion.getHost() == reposName:
                if not troveVersion.branch().hasParentBranch():
                    message = ('Cannot commit filesystem cook %s - '
                               ' nowhere to commit to!' % trove.getName())
                    return False, message
    assert(allTroves)
    source = trovesource.SimpleTroveSource()
    if excludeSpecs:
        excludeSpecsWithContext = {}
        troveMap = {}
        for excludeSpec in excludeSpecs:
            if len(excludeSpec) == 4:
                context = excludeSpec[3]
            else:
                context = None

            excludeSpecsWithContext.setdefault(
                                        excludeSpec[:3], []).append(context)
        excludeSpecs = [ x[:3] for x in excludeSpecs ]

        for trove in allTroves:
            troveTup = (trove.getName().split(':')[0],
                        trove.getVersion(),
                        trove.getFlavor())
            source.addTrove(*troveTup)
            troveMap.setdefault(troveTup, []).append(trove)

        source.searchAsDatabase()
        matches = source.findTroves(None, excludeSpecs, None, allowMissing=True)
        trvMatches = []
        for excludeSpec, matchList in matches.iteritems():
            contexts = excludeSpecsWithContext[excludeSpec]
            for match in matchList:
                for trv in troveMap[match]:
                    if trv.context in contexts or None in contexts:
                        trvMatches.append(trv)

        allTroves = [ x for x in allTroves if x not in trvMatches ]
        if not allTroves:
            message = ('All troves excluded - not committing')
            return False, message

    repos = conaryclient.getRepos()

    trovesByNBF = {}
    sourcesToCheck = []
    branchMap = {}
    trovesToClone = []
    for trove in allTroves:
        builtTroves = list(trove.iterBuiltTroves())
        if not builtTroves:
            continue
        if builtTroves[0][1].getHost() != reposName:
            alreadyCommitted = True
            for n,v,f in builtTroves:
                trovesByNBF[n, v.branch(), f] = (trove, v)
            continue

        troveVersion = trove.getVersion()
        if troveVersion.getHost() == reposName:
            sourceTup = (trove.getName(), troveVersion, Flavor())
            targetBranch = troveVersion.branch().parentBranch()
            branchMap[troveVersion.branch()] = targetBranch
            nbf = trove.getName(), targetBranch, Flavor()
            if nbf in trovesByNBF:
                if trovesByNBF[nbf][1] != troveVersion:
                    badVersion = trovesByNBF[nbf][1]
                    return False, ("Cannot commit two different versions of source component %s:"
                                   " %s and %s" % (trove.getName(), troveVersion, badVersion))
            trovesByNBF[nbf] = trove, troveVersion
            sourcesToCheck.append(sourceTup)
        if sourceOnly:
            continue

        for troveTup in builtTroves:
            branch = troveTup[1].branch()
            targetBranch = branch.parentBranch()
            # add mapping so that when the cloning is done
            # we can tell what commit resulted in what binaries.
            nbf = (troveTup[0], targetBranch, troveTup[2])
            if nbf in trovesByNBF:
                otherBinary = trovesByNBF[nbf][0].getBinaryTroves()[0]
                if otherBinary[1].branch() == targetBranch:
                    # this one's already committed.
                    break
                # discard the later of the two commits.
                if trovesByNBF[nbf][0].getVersion() > trove.getVersion():
                    # we're the earlier one
                    badTrove, badVersion = trovesByNBF[nbf]
                    newTrove = trove
                    newVersion = troveTup[1]
                else:
                    badTrove = trove
                    badVersion = troveTup[1]
                    newTrove, newVersion = trovesByNBF[nbf]
                name = nbf[0]
                flavor = nbf[2]

                skipped = []
                for badTroveTup in badTrove.iterBuiltTroves():
                    badNbf = (badTroveTup[0], targetBranch, badTroveTup[2])
                    if not ':' in badTroveTup[0]:
                        skipped.append(badTroveTup[0])

                    if badNbf in trovesByNBF and badTrove is trovesByNBF[badNbf][0]:
                        del trovesByNBF[badNbf]

                skipped = '%s' % (', '.join(skipped))
                log.warning("Not committing %s on %s[%s]%s - overridden by"
                            " %s[%s]%s" % (skipped, badTroveTup[1],
                             badTroveTup[2],
                             badTrove.getContextStr(), newVersion, flavor,
                             newTrove.getContextStr()))
                if trove is badTrove:
                    break

            trovesByNBF[nbf] = trove, troveTup[1]
            branchMap[branch] = targetBranch

    for nbf, (trove, tupVersion) in trovesByNBF.items():
        if tupVersion.branch() != nbf[1]:
            trovesToClone.append((nbf[0], tupVersion, nbf[2]))

    if not trovesToClone:
        if sourceOnly:
            err = 'Could not find sources to commit'
        elif alreadyCommitted:
            err = 'All built troves have already been committed'
        else:
            err = 'Can only commit built troves, none found'
        return False, err
    if sourcesToCheck and not commitOutdatedSources:
        outdated = _checkOutdatedSources(repos, sourcesToCheck)
        if outdated:
            outdated = ( '%s=%s (replaced by newer %s)' \
                         % (name, builtVer, newVer.trailingRevision())
                         for (name, builtVer, newVer) in outdated)
            err = ('The following source troves are out of date:\n%s\n\n'
                   'Use --commit-outdated-sources to commit anyway' %
                   '\n'.join(outdated))
            return False, err

    # only update build info if we'll be okay if some buildreqs are not 
    # updated
    updateBuildInfo = compat.ConaryVersion().acceptsPartialBuildReqCloning()
    callback = callbacks.CloneCallback(conaryclient.cfg, message)
    passed, cs = conaryclient.createTargetedCloneChangeSet(
                                        branchMap, trovesToClone,
                                        updateBuildInfo=updateBuildInfo,
                                        cloneSources=False,
                                        trackClone=False,
                                        callback=callback, fullRecurse=False)
    if passed:
        for troveCs in cs.iterNewTroveList():
            trv = Trove(troveCs)
            for _, childVersion, _ in trv.iterTroveList(strongRefs=True,
                                                        weakRefs=True):
                # make sure there are not 
                onRepos = childVersion.getHost() == reposName
                assert not onRepos, "Trove %s references repository" % trv
            n,v,f = troveCs.getNewNameVersionFlavor()
            trove, troveVersion = trovesByNBF[n, v.branch(), f]
            troveNVFC = trove.getNameVersionFlavor(withContext=True)
            # map jobId -> trove -> binaries
            mapping[trove.jobId].setdefault(troveNVFC, []).append((n,v,f))
    else:
        return False, 'Creating clone failed'

    # Sign the troves if we have a signature key.
    signatureKey = conaryclient.cfg.signatureKey
    if signatureKey:
        finalCs = signAbsoluteChangeset(cs, signatureKey)
    repos.commitChangeSet(cs, callback=callback)
    return True, mapping

def _checkOutdatedSources(repos, sourceTups):
    """
        Check to make sure that the source that we're cloning upstream is
        at the head.
    """
    def _getShadowedFrom(repos, shadowSpecs):
        results = repos.findTroves(None, shadowSpecs, None, getLeaves=False)
        shadowedFrom = {}
        for troveSpec, shadowedTups in results.iteritems():
            versions = (x[1] for x in shadowedTups)
            found = False
            # ordered by latest version first
            for version in sorted(versions, reverse=True):
                if version.isShadow() and not version.isModifiedShadow():
                    shadowedFrom[shadowSpecs[troveSpec]] = version.parentVersion()
                    found = True
                    break
        return shadowedFrom

    def _getLatest(repos, latestSpecs):
        results = repos.findTroves(None, latestSpecs, None,
                                   allowMissing=True)
        versions = [x[0][1] for x in results.values()]
        return dict(itertools.izip(results.keys(), versions))

    outdated = []
    shadowSpecs = {}
    latestSpecs = {}
    for (name, version, flavor) in sourceTups:
        upstreamSpec = name, version.branch().parentBranch(), flavor
        latestSpecs[upstreamSpec] = (name, version, flavor)
        shadowSpecs[name, version.branch(), flavor] = upstreamSpec

    shadowedFrom = _getShadowedFrom(repos, shadowSpecs)
    if shadowedFrom:
        latest = _getLatest(repos, latestSpecs)
        for troveSpec, shadowedFrom in shadowedFrom.iteritems():
            latestVersion = latest[troveSpec]
            if latestVersion != shadowedFrom:
                outdated.append((troveSpec[0], shadowedFrom, latestVersion))
    return outdated

def updateRecipes(repos, cfg, recipeList, committedSources):
    committedSourcesByNB = {}
    for name, version, flavor in committedSources:
        committedSourcesByNB[name, version.branch()] = version
    for recipe in recipeList:
        recipeDir = os.path.dirname(recipe)
        stateFilePath = recipeDir + '/CONARY'
        if not os.path.exists(stateFilePath):
            continue
        conaryStateFile = state.ConaryStateFromFile(stateFilePath)
        if not conaryStateFile.hasSourceState():
            continue
        context = conaryStateFile.getContext()
        stateFile = conaryStateFile.getSourceState()
        troveName = stateFile.getName()
        branch = stateFile.getBranch()
        if (troveName, branch) not in committedSourcesByNB:
            continue
        stateVersion = stateFile.getVersion()
        newVersion = committedSourcesByNB[troveName, branch]
        if stateVersion != versions.NewVersion():
            log.info('Updating %s after commit' % recipeDir)
            if compat.ConaryVersion().updateSrcTakesMultipleVersions():
                checkin.updateSrc(repos, [recipeDir])
            else:
                curDir = os.getcwd()
                try:
                    os.chdir(recipeDir)
                    checkin.updateSrc(repos)
                finally:
                    os.chdir(curDir)
        else:
            log.info('Replacing CONARY file %s after initial commit' % recipeDir)
            d = tempfile.mkdtemp(dir='/var/tmp',
                                 prefix='rmake-update-%s' % troveName)
            # check out the newly committed version of this recipe
            # (too much work, since we only want the CONARY file not
            # the file contents.  Oh well.) and update the CONARY state
            # file to it. This will not lose any local changes made after
            # the build started but _will_ cause any added/removed files
            # to need to be readded/removed via cvc add/remove
            checkin.checkout(repos, cfg, d, ['%s=%s' % (troveName, newVersion)])
            newConaryStateFile = state.ConaryStateFromFile(d + '/CONARY')
            newConaryStateFile.setContext(context)
            newConaryStateFile.write(stateFilePath)
