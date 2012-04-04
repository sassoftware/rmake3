from rmake_test import rmakehelp

from testutils import mock

from rmake.build import buildstate

class BuildStateTest(rmakehelp.RmakeHelper):
    def testJobFinished(self):
        bs = buildstate.AbstractBuildState([])
        built = set([mock.MockObject()])
        failed = set([mock.MockObject()])
        duplicate = set([mock.MockObject()])
        prepared = set([mock.MockObject()])
        bs.getBuiltTroves = lambda: built
        bs.getFailedTroves = lambda: failed
        bs.getDuplicateTroves = lambda: duplicate
        bs.getPreparedTroves = lambda: prepared
        bs.troves = built | failed | duplicate | prepared
        assert(bs.jobFinished())
        assert(not bs.jobPassed())
        # add an unbuilt trove
        bs.troves |= set([mock.MockObject()])
        assert(not bs.jobFinished())
        bs.troves  = built | duplicate | prepared
        assert(bs.jobPassed())

        

