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
"""
The dispatcher is in charge of taking a build request and monitoring it
until the build completes.
"""
import traceback

from conary.repository import changeset
from conary import conaryclient

from rmake.build import failure
from rmake.build import rootmanager

class Dispatcher(object):
    def __init__(self, serverCfg):
        self.serverCfg = serverCfg
        self._buildingTroves = []
        self._chroots = []

    def buildTrove(self, buildCfg, trove, buildReqs, targetLabel,
                   logHost='', logPort=0):
        chrootManager = self.getChrootManager(trove.jobId, buildCfg)
        try:
            chroot = chrootManager.createRoot(buildReqs, trove)
            self._chroots.append(chroot)
        except Exception, err:
            f = failure.ChrootFailed(str(err), traceback.format_exc())
            # sends off messages to all listeners that this trove failed.
            trove.troveFailed(f)
            return
        n,v,f = trove.getNameVersionFlavor()
        logPath, pid = chroot.buildTrove(buildCfg, targetLabel, n, v, f,
                                         logHost, logPort)
        # sends off message that this trove is building.
        trove.troveBuilding(logPath, pid)
        self._buildingTroves.append((chrootManager, chroot, trove))

    def getChrootManager(self, jobId, buildCfg):
        return rootmanager.ChrootManager(jobId, self.serverCfg.buildDir,
                                         self.serverCfg.chrootHelperPath,
                                         buildCfg, self.serverCfg)
    def _checkForResults(self, buildCfg):
        repos = conaryclient.ConaryClient(buildCfg).getRepos()
        foundResult = False
        for chrootManager, chroot, trove in list(self._buildingTroves):
            try:
                buildResult = chroot.checkResults(*trove.getNameVersionFlavor())
                if not buildResult:
                    continue
                foundResult = True
                self._buildingTroves.remove((chrootManager, chroot, trove))
                if buildResult.isBuildSuccess():
                    csFile = buildResult.getChangeSetFile()
                    cs = changeset.ChangeSetFromFile(csFile)
                    repos.commitChangeSet(cs)
                    # sends off message that this trove built successfully
                    troveList = [x.getNewNameVersionFlavor() for
                                 x in cs.iterNewTroveList() ]
                    trove.troveBuilt(troveList)
                    del cs # this makes sure the changeset closes the fd.
                    if buildCfg.cleanAfterCook:
                        chrootManager.cleanRoot(chroot.getPid())
                    else:
                        chrootManager.killRoot(chroot.getPid())
                    continue
                else:
                    reason = buildResult.getFailureReason()
                    trove.troveFailed(reason)
                    # passes through to killRoot at the bottom.
            except Exception, e:
                reason = failure.InternalError(str(e), traceback.format_exc())
                trove.troveFailed(reason)
            chrootManager.killRoot(chroot.getPid())
        return foundResult
