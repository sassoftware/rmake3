from rmake_test import rmakehelp

class TestBuildJob(rmakehelp.RmakeHelper):
    def testIterTroveList(self):
        job = self.newJob(self.makeTroveTuple('foo:source'),
                          self.makeTroveTuple('bar:source'))
        trvs = dict((x.getName(), x) for x in job.iterTroves())
        assert(list(job.iterLoadableTroveList()))
        assert(list(job.iterLoadableTroveList()) == list(job.iterTroveList(True)))
        assert(list(job.iterLoadableTroves()) == list(job.iterTroves()))
        foo = trvs['foo:source']
        bar = trvs['bar:source']
        foo.isSpecial = lambda: True
        assert(list(job.iterLoadableTroves()) == [bar])
        assert(list(job.getSpecialTroves()) == [foo])


    

if __name__ == '__main__':
    testsetup.main()
