from rmake_test import rmakehelp
from testutils import mock

from rmake.cmdline import buildcmd 

class BuildCommandTest(rmakehelp.RmakeHelper):
    def testGetConfigInfo(self):
        'RMK-973'
        fakeMan = self.workDir + '/not.a.man.7'
        file(fakeMan, 'w').write('\0')
        self.assertEquals(buildcmd._getConfigInfo(fakeMan), False)
        script = self.workDir + '/foo.sh'
        file(script, 'w').write('#!/bin/sh')
        self.assertEquals(buildcmd._getConfigInfo(script), True)
        fakescript = self.workDir + '/foo.fsh'
        file(fakescript, 'w').write('#!/bin/sh\n\0')
        self.assertEquals(buildcmd._getConfigInfo(fakescript), False)
        gif = self.workDir + '/foo.gif'
        file(gif, 'w').write('')
        self.assertEquals(buildcmd._getConfigInfo(gif), False)


