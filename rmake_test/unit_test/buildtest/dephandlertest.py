from testutils import mock

from rmake_test import rmakehelp

from rmake.build import buildtrove
from rmake.build import dephandler
from rmake.build import imagetrove

class DephandlerTest(rmakehelp.RmakeHelper):
    def testHasSpecialTroves(self):
        dh = mock.MockInstance(dephandler.DependencyHandler)
        dh._mock.enableMethod('hasSpecialTroves')
        dh._mock.set(inactiveSpecial=['foo'])
        assert(dh.hasSpecialTroves())
        dh._mock.set(inactiveSpecial = [])
        assert(not dh.hasSpecialTroves())

    def testInit(self):
        bt = buildtrove.BuildTrove(1, *self.makeTroveTuple('foo:source'))
        bt.setConfig(self.buildCfg)
        it = imagetrove.ImageTrove(1, *self.makeTroveTuple('group-foo'))
        publisher = mock.MockObject()
        dh = dephandler.DependencyHandler(publisher, None,
                                          [bt], [it])
        assert(dh.moreToDo())
        bt.troveBuilt([])
        assert(dh.hasSpecialTroves())
        assert(dh.popSpecialTrove() == it)
        assert(dh.specialTroves)



