from rmake_test import rmakehelp

from rmake.build import buildtrove
from rmake.build import imagetrove


class BuildTroveTest(rmakehelp.RmakeHelper):
    def testRegisteredBuildTrove(self):
        assert(buildtrove._troveClassesByType['build'] == buildtrove.BuildTrove)
        assert(buildtrove._troveClassesByType['image'] == imagetrove.ImageTrove)

    def testIsSpecial(self):
        bt = buildtrove.BuildTrove(1, *self.makeTroveTuple('foo:source'))
        assert(not bt.isSpecial())
        bt = imagetrove.ImageTrove(1, *self.makeTroveTuple('foo'))
        assert(bt.isSpecial())

    def testGetClassForTroveType(self):
        assert(buildtrove.getClassForTroveType('build') == buildtrove.BuildTrove)
        assert(buildtrove.getClassForTroveType('image') == imagetrove.ImageTrove)

    def testDisplay(self):
        bt = buildtrove.BuildTrove(1, *self.makeTroveTuple('foo:source'))
        assert(str(bt) == "<BuildTrove('foo:source=localhost@rpl:linux[]')>")
    

