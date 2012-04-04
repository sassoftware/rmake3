
from testutils import mock
from rmake_test import rmakehelp

from rmake.build import imagetrove

class ImageTroveTest(rmakehelp.RmakeHelper):
    def testImageTrove(self):
        trv = imagetrove.ImageTrove(1, *self.makeTroveTuple('group-foo'))
        assert(trv.isSpecial())
        trv.setProductName('foo')
        assert(trv.getProductName() == 'foo')
        trv.setImageBuildId(23)
        assert(trv.getImageBuildId() == 23)
        assert(trv.getCommand() == 'image')
        trv.setImageType('imageType')
        assert(trv.getImageType() == 'imageType')
        options = trv.getImageOptions() 
        assert(options == {})
        trv.setImageOptions({'foo' : 'bar'})
        assert(trv.getImageOptions()  == {'foo' : 'bar'})

