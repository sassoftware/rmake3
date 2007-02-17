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
        err = 'Job already committed'
        return False, err

    trovesByBranch = {}
    for job in jobsToCommit:
        mapping[job.jobId] = {}
        for troveTup in job.iterTroveList():
            trove = job.getTrove(*troveTup)
            troveVersion = trove.getVersion()
            if troveVersion.getHost() == rmakeConfig.serverName:
                if troveVersion.branch().hasParentBranch():
                    targetBranch = troveVersion.branch().parentBranch()
                else:
                    message = ('Cannot commit filesystem cook %s - '
                               ' nowhere to commit to!' % troveTup[0])
                    return False, message
            else:
                targetBranch = trove.getVersion().branch()
            trovesByBranch.setdefault(targetBranch, []).append(trove)
    assert(trovesByBranch)

    repos = conaryclient.getRepos()

    for targetBranch, troves in trovesByBranch.iteritems():
        sourcesToCheck = []
        cloneTroves = []
        trovesByNF = {}
        for trove in troves:
            builtTroves = list(trove.iterBuiltTroves())
            if builtTroves:
                if not sourceOnly:
                    cloneTroves.extend(builtTroves)
                    for troveTup in builtTroves:
                        # add mapping so that when the cloning is done
                        # we can tell what commit resulted in what binaries.
                        nf = (troveTup[0], troveTup[2])
                        if nf in trovesByNF:
                            # our mapping cannot be made - throw up our
                            # hands.
                            message = "Cannot clone two troves with same name, target branch and version in the same commit: %s=%s[%s]" % (nf[0], targetBranch, nf[1])
                            return False, message
                        trovesByNF[nf] = trove
                if trove.getVersion().branch() != targetBranch:
                    sourceTup = (trove.getName(), trove.getVersion(),
                                 Flavor())
                    cloneTroves.append(sourceTup)
                    trovesByNF[trove.getName(), Flavor()] = trove
                    sourcesToCheck.append(sourceTup)
        if not cloneTroves:
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
        kw = {}
        callback = callbacks.CloneCallback(conaryclient.cfg, message)
        kw['callback'] = callback
        kw['fullRecurse'] = False

        if compat.ConaryVersion().supportsCloneNoTracking():
            kw['trackClone'] = False

        passed, cs = conaryclient.createCloneChangeSet(
                                            targetBranch,
                                            cloneTroves,
                                            updateBuildInfo=True,
                                            **kw)
        if passed:
            for troveCs in cs.iterNewTroveList():
                n,v,f = troveCs.getNewNameVersionFlavor()
                trove = trovesByNF[n, f]
                troveNVF = trove.getNameVersionFlavor()
                # map jobId -> trove -> binaries
                mapping[trove.jobId].setdefault(troveNVF, []).append((n,v,f))
            finalCs.merge(cs)
        else:
            return False, 'Creating clone failed'

    # Sign the troves if we have a signature key.
    signatureKey = conaryclient.cfg.signatureKey
    if signatureKey:
        finalCs = signAbsoluteChangeset(finalCs, signatureKey)
    repos.commitChangeSet(finalCs, callback=callback)
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
            assert(found)
        return shadowedFrom

    def _getLatest(repos, latestSpecs):
        results = repos.findTroves(None, latestSpecs, None)
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
    latest = _getLatest(repos, latestSpecs)
    for troveSpec, shadowedFrom in shadowedFrom.iteritems():
        latestVersion = latest[troveSpec]
        if latestVersion != shadowedFrom:
            outdated.append((troveSpec[0], shadowedFrom, latestVersion))
    return outdated
