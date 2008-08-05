from conary.lib.cfgtypes import CfgString, CfgDict, CfgInt, CfgList

from rmake.build import buildtrove
from rmake.build import trovesettings

class ImageTroveSettings(trovesettings.TroveSettings):
    urls = CfgList(CfgString)
    imageType = CfgString
    imageOptions = CfgDict(CfgString)
    imageBuildId = CfgInt
    productName = CfgString

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
