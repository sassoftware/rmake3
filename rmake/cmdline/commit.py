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
"""
Commit command
"""
import itertools

from conary.build.cook import signAbsoluteChangeset
from conary.lib import log
from conary.conaryclient import callbacks
from conary.deps.deps import Flavor

from rmake import compat

def commitJob(conaryclient, job, rmakeConfig, message=None,
              commitOutdatedSources=False, sourceOnly = False):
    trovesByBranch = {}
    if job.isCommitted():
         err = 'Job already committed'
         return False, err


    for troveTup in job.iterTroveList():
        if (troveTup[0].startswith('group-') 
            and not compat.ConaryVersion().supportsCloneNonRecursive()):
            err = ('You need to upgrade your conary before you can '
                   'commit group builds')
            return False, err
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

    importantTups = []
    for targetBranch, troves in trovesByBranch.iteritems():
        sourcesToCheck = []
        cloneTroves = []
        for trove in troves:
            builtTroves = list(trove.iterBuiltTroves())
            if builtTroves:
                if not sourceOnly:
                    cloneTroves.extend(builtTroves)
                if trove.getVersion().branch() != targetBranch:
                    sourceTup = (trove.getName(), trove.getVersion(),
                                 Flavor())
                    cloneTroves.append(sourceTup)
                    sourcesToCheck.append(sourceTup)
        if not cloneTroves:
            if sourceOnly:
                err = 'This job has no sources to commit'
            else:
                err = 'Can only commit built troves, this job has none'
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
        if compat.ConaryVersion().supportsCloneCallback():
            callback = callbacks.CloneCallback(conaryclient.cfg, message)
            kw['callback'] = callback
        else:
            callback = callbacks.ChangesetCallback()

        if compat.ConaryVersion().supportsCloneNonRecursive():
            kw['fullRecurse'] = False

        passed, cs = conaryclient.createCloneChangeSet(
                                            targetBranch,
                                            cloneTroves,
                                            updateBuildInfo=True,
                                            **kw)
        if passed:
            # Sign the troves if we have a signature key.
            signatureKey = conaryclient.cfg.signatureKey
            if signatureKey:
                cs = signAbsoluteChangeset(cs, signatureKey)

            repos.commitChangeSet(cs, callback=callback)
            importantTups.extend(cs.getPrimaryTroveList())
            importantTups.extend(x.getNewNameVersionFlavor()
                                 for x in cs.iterNewTroveList()
                                 if x.getName().endswith(':source'))
        else:
            return False, 'Creating clone failed'
    return True, importantTups

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
