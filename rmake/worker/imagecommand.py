#
# Copyright (c) 2006-2008 rPath, Inc.  All Rights Reserved.
#
import sys
import time
import traceback

from rmake import errors
from rmake.worker import command
from rmake.worker import rbuilderclient

class ImageCommand(command.TroveCommand):

    name = 'image-command'

    def __init__(self, serverCfg, commandId, jobId, eventHandler, imageCfg,
                 trove,  logData=None, logPath=None):
        command.TroveCommand.__init__(self, serverCfg, commandId,
                                      jobId, eventHandler, trove)
        self.imageCfg = imageCfg
        self.logData = logData
        self.logPath = logPath
        self.client = rbuilderclient.RbuilderClient(self.imageCfg.rbuilderUrl,
                                                    self.imageCfg.rmakeUser[0],
                                                    self.imageCfg.rmakeUser[1])

    def runTroveCommand(self):
        trove = self.trove
        try:
            buildId = self.client.newBuildWithOptions(trove.getProductName(),
                                                      trove.getName(),
                                                      trove.getVersion(),
                                                      trove.getFlavor(),
                                                      trove.getImageType(),
                                                      trove.getImageOptions())
            trove.setImageBuildId(buildId)
            self.client.startImage(buildId)
            trove.troveBuilding()
            self.watchImage(buildId)
            trove.troveBuilt([])
            return
        except Exception, err:
            # sends off messages to all listeners that this trove failed.
            self.logger.error(traceback.format_exc())
            trove.troveFailed(str(err), traceback.format_exc())
            return

    def watchImage(self, buildId):
        curStatus = None
        while True:
            error, buildStatus = self.client.server.getBuildStatus(buildId)
            if error:
                raise errors.RmakeError(buildStatus)
            if curStatus != buildStatus:
                curStatus = buildStatus
                print '%s: %s' % (buildId, curStatus['message'])
                sys.stdout.flush()
                if curStatus['status'] > 200:
                    break
            time.sleep(2)
