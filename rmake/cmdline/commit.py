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
from conary.build.cook import signAbsoluteChangeset
from conary.conaryclient import callbacks
from conary.deps.deps import Flavor

from rmake import compat

def commitJob(conaryclient, job, rmakeConfig, message=None):
    trovesByBranch = {}
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
        cloneTroves = []
        for trove in troves:
            builtTroves = list(trove.iterBuiltTroves())
            if builtTroves:
                cloneTroves.extend(builtTroves)
                if trove.getVersion().branch() != targetBranch:
                    cloneTroves.append((trove.getName(), trove.getVersion(),
                                        Flavor()))
        if not cloneTroves:
            log.error('Can only commit built troves,'
                      ' this job has none')
            return False

        kw = {}
        if compat.ConaryVersion().supportsCloneCallback():
            callback = callbacks.CloneCallback(conaryclient.cfg, message)
            kw['callback'] = callback
        else:
            callback = callbacks.ChangesetCallback()

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


