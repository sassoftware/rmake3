#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
