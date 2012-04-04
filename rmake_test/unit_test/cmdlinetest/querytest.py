from rmake_test import rmakehelp
from testutils import mock

from rmake.build import imagetrove
from rmake.cmdline import query

class TestDisplay(rmakehelp.RmakeHelper):

    def testDisplaySettings(self):
        trv = imagetrove.ImageTrove(1, *self.makeTroveTuple('group-foo'))
        trv.setProductName('product')
        trv.setImageType('imageType')
        job = self.newJob()
        job.addBuildTrove(trv)
        dcfg = query.DisplayConfig(mock.MockObject())
        rc, txt = self.captureOutput(query.displayTroveDetail, dcfg, job, trv)
        assert(txt == '''\
     group-foo=:linux/1-1-1
       State: Initialized         
imageType                 imageType
productName               product
urls                      []
''')

