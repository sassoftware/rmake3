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


from conary.lib.cfgtypes import CfgString, CfgDict, CfgInt, CfgList

from rmake.build import buildtrove
from rmake.build import trovesettings

class ImageTroveSettings(trovesettings.TroveSettings):
    urls = CfgList(CfgString)
    imageType = CfgString
    imageOptions = CfgDict(CfgString)
    imageBuildId = CfgInt
    productName = CfgString
    buildName = CfgString

class ImageTrove(buildtrove.BuildTrove):
    troveType = 'image'
    settingsClass = ImageTroveSettings

    def __init__(self, *args, **kw):
        kw['buildType'] = buildtrove.TROVE_BUILD_TYPE_SPECIAL
        buildtrove.BuildTrove.__init__(self, *args, **kw)

    def setProductName(self, productName):
        self.settings['productName'] = productName

    def getProductName(self):
        return self.settings['productName']

    def setBuildName(self, buildName):
        self.settings['buildName'] = buildName

    def getBuildName(self):
        return self.settings['buildName']

    def setImageBuildId(self, buildId):
        self.settings['imageBuildId'] = buildId

    def getImageBuildId(self):
        return self.settings['imageBuildId']

    def setImageType(self, imageType):
        self.settings['imageType'] = imageType

    def getImageType(self):
        return self.settings['imageType']

    def getImageOptions(self):
        return self.settings['imageOptions']

    def setImageOptions(self, imageOptions):
        self.settings['imageOptions'] = imageOptions

    def setImageUrls(self, urls):
        self.settings['urls'] = urls

    def getImageUrls(self):
        return self.settings['url']

    def getCommand(self):
        return 'image'
