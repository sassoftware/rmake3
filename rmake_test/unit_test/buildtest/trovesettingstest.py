from rmake_test import rmakehelp

from rmake.build import trovesettings
from rmake.lib import apiutils

from conary.lib import cfgtypes

class TestTroveSettings(rmakehelp.RmakeHelper):
    def testTroveSettings(self):
        class MyTroveSettings(trovesettings.TroveSettings):
            cfgOption = cfgtypes.CfgString 

        xx = MyTroveSettings()
        xx.cfgOption = 'foobar'
        yy = apiutils.thaw('TroveSettings', apiutils.freeze('TroveSettings', xx))
        assert(yy.cfgOption == 'foobar')

