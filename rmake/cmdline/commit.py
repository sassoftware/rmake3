#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Commit command
"""
import itertools

from conary.build.cook import signAbsoluteChangeset
from conary.lib import log
from conary.conaryclient import callbacks
from conary.deps.deps import Flavor
from conary.repository import changeset

from rmake import compat

def commitJobs(conaryclient, jobList, rmakeConfig, message=None,
               commitOutdatedSources=False, sourceOnly = False):
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
    for job in jobsToCommit:
        mapping[job.jobId] = {}
        for trove in job.iterTroves():
            allTroves.append(trove)
            troveVersion = trove.getVersion()
            if troveVersion.getHost() == rmakeConfig.serverName:
                if not troveVersion.branch().hasParentBranch():
                    message = ('Cannot commit filesystem cook %s - '
                               ' nowhere to commit to!' % trove.getName())
                    return False, message
    assert(allTroves)

    repos = conaryclient.getRepos()

    trovesByNBF = {}
    sourcesToCheck = []
    branchMap = {}
    trovesToClone = []
    for trove in allTroves:
        builtTroves = list(trove.iterBuiltTroves())
        if not builtTroves:
            continue

        troveVersion = trove.getVersion()
        if troveVersion.getHost() == rmakeConfig.serverName:
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
        trovesToClone.append((nbf[0], tupVersion, nbf[2]))

    if not trovesToClone:
        if sourceOnly:
            err = 'Could not find sources to commit'
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

    callback = callbacks.CloneCallback(conaryclient.cfg, message)
    passed, cs = conaryclient.createTargetedCloneChangeSet(
                                        branchMap, trovesToClone,
                                        updateBuildInfo=True,
                                        cloneSources=False,
                                        trackClone=False,
                                        callback=callback, fullRecurse=False)
    if passed:
        for troveCs in cs.iterNewTroveList():
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
