#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


import sys
import time
import traceback

from rmake import errors
from rmake.worker import command
from rmake.worker import rbuilderclient

class ImageCommand(command.AttachedCommand):

    name = 'image-command'

    def __init__(self, serverCfg, commandId, jobId, eventHandler, imageCfg,
                 trove,  logData=None, logPath=None):
        super(ImageCommand, self).__init__(serverCfg, commandId, jobId,
            eventHandler, trove=trove)
        self.imageCfg = imageCfg
        self.logData = logData
        self.logPath = logPath
        self.client = rbuilderclient.RbuilderClient(self.imageCfg.rbuilderUrl,
                                                    self.imageCfg.rmakeUser[0],
                                                    self.imageCfg.rmakeUser[1])

    def runAttachedCommand(self):
        trove = self.trove
        try:
            buildId = self.client.newBuildWithOptions(trove.getProductName(),
                                                      trove.getName(),
                                                      trove.getVersion(),
                                                      trove.getFlavor(),
                                                      trove.getImageType(),
                                                      trove.getBuildName(),
                                                      trove.getImageOptions())
            trove.setImageBuildId(buildId)
            self.client.startImage(buildId)
            trove.troveBuilding(0, trove.settings.items())
            curStatus, message = self.watchImage(buildId)
            if curStatus == 300:
                time.sleep(2)
                #urls = self.client.getBuildFilenames(buildId)
                #trove.log('Images built: %s' % '\n'.join(urls))
                #trove.setImageUrls(urls)
                trove.troveBuilt([])
            else:
                trove.troveFailed(message)
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
        return curStatus['status'], curStatus['message']
