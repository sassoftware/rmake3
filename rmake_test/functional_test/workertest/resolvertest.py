#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

from conary import versions
from conary.lib import log
from conary.deps.deps import parseFlavor, parseDep, overrideFlavor

from rmake.lib.apiutils import freeze, thaw
from rmake.lib import logger
from rmake.worker import resolver
from rmake.build import dephandler

from rmake_test import rmakehelp

class ResolverTest(rmakehelp.RmakeHelper):

    def testResolveResult(self):
        trv = self.addComponent('foo:runtime', '1.0', 'ssl')
        tup = trv.getNameVersionFlavor()
        job = (tup[0], (None, None), (tup[1], tup[2]), False)

        r = resolver.ResolveResult()
        r.troveResolved([job], [], [])
        r2 = thaw('ResolveResult', freeze('ResolveResult', r))
        assert(r2.getBuildReqs() == [ job  ])
        assert(r2.success)
        assert(not r2.inCycle)

        r = resolver.ResolveResult(inCycle=True)
        r.troveMissingBuildReqs(True, [('foo', None, parseFlavor('ssl'))])
        r2 = thaw('ResolveResult', freeze('ResolveResult', r))
        assert(not r2.hasMissingDeps())
        assert(r2.hasMissingBuildReqs())
        assert(r2.getMissingBuildReqs() == [(True, ('foo', '', parseFlavor('ssl')))])
        assert(not r2.success)
        assert(r2.inCycle)

        r = resolver.ResolveResult(inCycle=True)
        r.troveMissingDependencies(True, [(trv.getNameVersionFlavor(), 
                                     parseDep('trove: foo trove: bar'))])
        r2 = thaw('ResolveResult', freeze('ResolveResult', r))
        assert(r.getMissingDeps() == r2.getMissingDeps())
        assert(r2.hasMissingDeps())
        assert(not r2.success)
        assert(r2.inCycle)

    def testFindWrongArchInBuiltTroves(self):
        # wrong flavor in builtTroves list
        self.buildCfg.flavor = [parseFlavor('is:x86')]

        self.openRmakeRepository()
        trv = self.addComponent('foo:runtime',
                               '/localhost@rpl:linux//rmakehost@rpl:linux/1.0',
                               'is:x86_64')
        builtTroves = [trv.getNameVersionFlavor()]

        # right flavor sitting in the repos
        self.addComponent('foo:runtime', '1.0', 'is:x86')

        trv = self.addComponent('bam:source')
        bt = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        bt.setBuildRequirements(['foo:runtime'])
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, builtTroves, [])
        self.logFilter.add()
        res = resolver.DependencyResolver(log, self.openRepository())
        result = res.resolve(resolveJob)
        # flavor should be the x86 one.
        assert(result.success
                and str(list(result.getBuildReqs())[0][2][1]) == 'is: x86')

        #####
        # now let's try when it's in the resolveTroves list
        self.buildCfg.resolveTroveTups = [builtTroves]
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, [], [])
        result = res.resolve(resolveJob)
        assert(result.success
                and str(list(result.getBuildReqs())[0][2][1]) == 'is: x86')

    def testResolveWrongArchInBuiltTroves(self):
        # wrong flavor in builtTroves list
        self.buildCfg.flavor = [parseFlavor('is:x86')]
        self.openRmakeRepository()
        trv = self.addComponent('foo:runtime', '/localhost@rpl:linux//rmakehost@rpl:linux/1.0', 'is:x86_64')
        builtTroves = [trv.getNameVersionFlavor()]

        # right flavor sitting in the repos
        self.addComponent('foo:runtime', '1.0', 'is:x86')
        # there's another one on a branch.  We'll put that one in our
        # crossTroves list which shouldn't be used because we're not looking
        # for crossRequirements
        trv = self.addComponent('foo:runtime', '/localhost@rpl:linux//rmakehost@rpl:linux/1.0', 'ssl is:x86')
        crossTroves = [trv.getNameVersionFlavor()]

        self.addComponent('bar:runtime', '1.0', 'is:x86',
                          requires='trove:foo:runtime')

        trv = self.addComponent('bam:source')
        bt = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        bt.setBuildRequirements(['bar:runtime'])
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, builtTroves, 
                                            crossTroves)
        self.logFilter.add()
        res = resolver.DependencyResolver(log, self.openRepository())
        result = res.resolve(resolveJob)
        # flavor should be the x86 one.
        assert(result.success)
        flavors = set([ str(x[2][1]) for x in result.getBuildReqs() ])
        assert(flavors == set(['is: x86']))

        #####
        # now let's try when it's in the resolveTroves list
        self.buildCfg.resolveTroveTups = [builtTroves]
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, [], crossTroves)
        result = res.resolve(resolveJob)
        assert(result.success)
        flavors = set([ str(x[2][1]) for x in result.getBuildReqs() ])
        assert(flavors == set(['is: x86']))

    def testResolveCrossDependencies(self):
        self.openRmakeRepository()
        # resolving cross root dependencies have a couple of odd features about 
        # them:
        # 1. the flavor is !cross even if the build flavor is cross
        # 2. the flavor moves the target: flavor is to the is: spot
        # 3. file: dependencies are ignored
        # 4. it includes troves in crossTroves list.
        # We test some of these here.
        self.addComponent('foo:runtime', '1.0', 'cross is:x86_64')
        self.addComponent('foo:runtime', '1.0', '!cross is:x86_64')
        self.addComponent('foo:runtime', '1.0', 'cross is:x86')
        self.addComponent('foo:runtime', '1.0', '!cross is:x86')

        self.addComponent('bar:runtime', '1.0', 'cross is:x86_64',
                            requires='trove:foo:runtime file: /tmp/blah')
        self.addComponent('bar:runtime', '1.0', '!cross is:x86_64',
                            requires='trove:foo:runtime file: /tmp/blah')
        self.addComponent('bar:runtime', '1.0', 'cross is:x86',
                            requires='trove:foo:runtime file: /tmp/blah')
        self.addComponent('bar:runtime', '1.0', '!cross is:x86',
                            requires='trove:foo:runtime file: /tmp/blah')
        self.addComponent('blah:runtime', '1.0',  'cross is:x86',
                           provides='file: /tmp/blah')
        trv = self.addComponent('bam:source')

        bt = self.newBuildTrove(1, trv.getName(), trv.getVersion(),
                                parseFlavor('cross is:x86 target:x86_64'))
        bt.setBuildRequirements(['bar:runtime'])
        bt.setCrossRequirements(['bar:runtime'])
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, [], [])
        self.buildCfg.flavor = [overrideFlavor(self.buildCfg.buildFlavor,
                                parseFlavor('cross is:x86 target:x86_64'))]
        res = resolver.DependencyResolver(log, self.openRepository())
        self.logFilter.add()
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReqNames = set([ x[0] for x in result.getBuildReqs()])
        buildReqFlavors = set([ str(x[2][1]) for x in result.getBuildReqs()])
        assert(buildReqNames == set(['bar:runtime', 'foo:runtime',
                                     'blah:runtime']))
        crossReqNames = set([ x[0] for x in result.getCrossReqs()])
        crossReqFlavors = set([ str(x[2][1]) for x in result.getCrossReqs()])
        assert(crossReqNames == set(['bar:runtime', 'foo:runtime']))
        assert(crossReqFlavors == set(['!cross is: x86_64']))
        assert(buildReqFlavors == set(['cross is: x86']))

    def testIntraTroveDepsInBuiltTroves(self):
        self.openRmakeRepository()
        builtFooRun = self.addComponent('foo:runtime', 
                                '/localhost@rpl:linux//rmakehost@rpl:linux/1.0',
                                        'is:x86',
                                        requires='trove:foo:lib')
        builtFooLib = self.addComponent('foo:lib',
                                '/localhost@rpl:linux//rmakehost@rpl:linux/1.0',
                                        'is:x86')
        fooLib = self.addComponent('foo:lib', '1.0', 'is:x86')

        builtTroves = [builtFooRun.getNameVersionFlavor(),
                       builtFooLib.getNameVersionFlavor()]
        resolveTroves = [ fooLib.getNameVersionFlavor()]
        self.buildCfg.resolveTroveTups = [resolveTroves]
        self.buildCfg.resolveTrovesOnly = True

        trv = self.addComponent('bam:source')
        bt = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        bt.setBuildRequirements(['foo:runtime'])
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, builtTroves, [])
        self.logFilter.add()
        res = resolver.DependencyResolver(log, self.openRepository())

        # make sure that we don't grab the foo:lib from the resolveTroves
        # list even though it's a better match (intraTroveDeps should stop that)
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReqs = result.getBuildReqs()
        assert(len(set([x[2][0] for x in buildReqs])) == 1)

        #####
        # now let's try when it's in the resolveTroves list
        self.buildCfg.resolveTroveTups = [builtTroves]
        self.buildCfg.resolveTrovesOnly = False
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, [], [])
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReqs = result.getBuildReqs()
        assert(len(set([x[2][0] for x in buildReqs])) == 1)

    def testNonIntraTroveDepsInBuiltTroves(self):
        self.openRmakeRepository()
        depStr = 'soname: ELF32/foo.so.1(SysV)'
        builtFooRun = self.addComponent('foo:runtime',
                            '/localhost@rpl:linux//rmakehost@rpl:linux/1.0',
                            'is:x86',
                            requires=depStr)
        builtFooLib = self.addComponent('foo:lib',
                            '/localhost@rpl:linux//rmakehost@rpl:linux/1.0',
                            'is:x86',
                            provides=depStr)
        fooLib = self.addComponent('foo:lib', '1.0', 'is:x86',
                                   provides=depStr)

        builtTroves = [builtFooRun.getNameVersionFlavor(),
                       builtFooLib.getNameVersionFlavor()]
        resolveTroves = [ fooLib.getNameVersionFlavor()]
        self.buildCfg.resolveTroveTups = [resolveTroves]
        self.buildCfg.resolveTrovesOnly = True

        trv = self.addComponent('bam:source')
        bt = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        bt.setBuildRequirements(['foo:runtime'])
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, builtTroves, [])
        self.logFilter.add()
        res = resolver.DependencyResolver(log, self.openRepository())

        # make sure that we don't grab the foo:lib from the resolveTroves
        # list even though it's a better match (intraTroveDeps should stop that)
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReqs = list(result.getBuildReqs())
        # assert both foo:run and foo:lib have the same version
        assert(str(buildReqs[0][2][0].trailingLabel()) == 'rmakehost@rpl:linux')
        assert(len(set([x[2][0] for x in buildReqs])) == 1)

        #####
        # now let's try when it's in the resolveTroves list
        self.buildCfg.resolveTroveTups = [builtTroves]
        self.buildCfg.resolveTrovesOnly = False
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, [], [])
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReqs = list(result.getBuildReqs())
        # assert both foo:run and foo:lib have the same version
        assert(str(buildReqs[0][2][0].trailingLabel()) == 'rmakehost@rpl:linux')
        assert(len(set([x[2][0] for x in buildReqs])) == 1)

    def testFindTrovesPrefersBuiltTroves(self):
        self.openRmakeRepository()
        depStr = 'soname: ELF32/foo.so.1(SysV)'
        builtFooRun = self.addComponent('foo:runtime',
                    '/localhost@rpl:linux//branch//rmakehost@rpl:branch/1.0',
                    'is:x86')
        fooRun = self.addComponent('foo:runtime', '1.0', 'is:x86')
        trv = self.addComponent('bam:source')
        bt = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        bt.setBuildRequirements(['foo:runtime'])
        self.buildCfg.installLabelPath = [
                                    versions.Label('localhost@rpl:branch'),
                                    versions.Label('localhost@rpl:linux') ]

        builtTroves = [builtFooRun.getNameVersionFlavor()]
        resolveTroves = [ fooRun.getNameVersionFlavor()]
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, builtTroves)
        self.logFilter.add()
        res = resolver.DependencyResolver(log, self.openRepository())
        self.buildCfg.resolveTroveTups = [resolveTroves]
        self.buildCfg.resolveTrovesOnly = False

        result = res.resolve(resolveJob)
        assert(result.success)
        buildReq, = result.getBuildReqs()
        assert(str(buildReq[2][0].trailingLabel())  == 'rmakehost@rpl:branch')

    def testFindTrovesPrefersResolveTroves(self):
        self.openRmakeRepository()
        # prefer resolveTroves to the repository when using findTroves.
        resolveFooRun = self.addComponent('foo:runtime',
                                        '/localhost@rpl:branch/1.0',
                                        'is:x86')
        fooRun = self.addComponent('foo:runtime', '1.0', 'is:x86')
        trv = self.addComponent('bam:source')

        bt = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        bt.setBuildRequirements(['foo:runtime'])
        resolveTroves = [ resolveFooRun.getNameVersionFlavor()]
        self.buildCfg.resolveTroveTups = [resolveTroves]
        self.buildCfg.resolveTrovesOnly = False
        builtTroves = []
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, builtTroves)
        self.logFilter.add()
        res = resolver.DependencyResolver(log, self.openRepository())

        result = res.resolve(resolveJob)
        assert(result.success)
        buildReq, = result.getBuildReqs()
        assert(str(buildReq[2][0].trailingLabel())  == 'localhost@rpl:branch')

    def testFindTrovesPrefersResolveTrovesOnILP(self):
        self.openRmakeRepository()
        resolveFooRun = self.addComponent('foo:runtime',
                                        '/localhost@rpl:linux/1.0',
                                        'is:x86')
        resolveFooRun2 = self.addComponent('foo:runtime',
                                        '/localhost@rpl:branch/1.0',
                                        'is:x86')
        trv = self.addComponent('bam:source')

        bt = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        bt.setBuildRequirements(['foo:runtime'])
        resolveTroves = [ x.getNameVersionFlavor() for x in (resolveFooRun,
                                                             resolveFooRun2) ]
        self.buildCfg.resolveTroveTups = [resolveTroves]
        self.buildCfg.resolveTrovesOnly = True
        builtTroves = []
        self.logFilter.add()
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, builtTroves)
        res = resolver.DependencyResolver(log, self.openRepository())
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReq, = result.getBuildReqs()
        assert(str(buildReq[2][0].trailingLabel())  == 'localhost@rpl:linux')
        self.buildCfg.installLabelPath = [
                            versions.Label('localhost@rpl:branch'),
                            versions.Label('localhost@rpl:linux')]
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReq, = result.getBuildReqs()
        assert(str(buildReq[2][0].trailingLabel())  == 'localhost@rpl:branch')

        builtFooRun = self.addComponent('foo:runtime',
                    '/localhost@rpl:linux//branch//rmakehost@rpl:branch/1.0',
                    'is:x86')
        builtTroves = [ builtFooRun.getNameVersionFlavor() ]

        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, builtTroves)
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReq, = result.getBuildReqs()
        assert(str(buildReq[2][0].trailingLabel())  == 'rmakehost@rpl:branch')
        self.buildCfg.installLabelPath = [
                            versions.Label('localhost@rpl:linux'),
                            versions.Label('localhost@rpl:branch')]
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReq, = result.getBuildReqs()
        assert(str(buildReq[2][0].trailingLabel())  == 'rmakehost@rpl:branch')

    def testFindTrovesWillUseBuiltTroveFromArbitraryLabel(self):
        self.openRmakeRepository()
        self.openRepository()
        builtFooRun = self.addComponent('foo:runtime',
                    '/localhost@rpl:linux//branch//rmakehost@local:branch/1.0',
                     'is:x86')
        resolveBarRun = self.addComponent('bar:runtime=1.0[is:x86]')
        resolveTroves = [ x.getNameVersionFlavor() for x in (resolveBarRun,) ]
        builtTroves = [ builtFooRun.getNameVersionFlavor() ]
        self.buildCfg.installLabelPath = [versions.Label('localhost@rpl:linux')]
        trv = self.addComponent('bam:source')
        bt = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        bt.setBuildRequirements(['foo:runtime'])
        self.buildCfg.resolveTroveTups = [resolveTroves]
        self.buildCfg.resolveTrovesOnly = False
        res = resolver.DependencyResolver(log, self.openRepository())
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, builtTroves)
        self.logFilter.add()
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReq, = result.getBuildReqs()
        assert(str(buildReq[2][0].trailingLabel())  == 'rmakehost@local:branch')

    def testFindTrovesWillUseTroveFoundEarlierInResolveTroves(self):
        self.openRepository()
        fooResolve1 = self.addComponent('foo:runtime=/localhost@rpl:linux-devel/1-1-1')
        fooResolve2 = self.addComponent('foo:runtime=/localhost@rpl:linux/1-1-1')
        resolveTroves = [ [x.getNameVersionFlavor()] for x in (fooResolve1,
                                                             fooResolve2,) ]
        builtTroves = []
        trv = self.addComponent('bam:source')
        bt = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        bt.setBuildRequirements(['foo:runtime'])
        self.buildCfg.resolveTroveTups = resolveTroves
        self.buildCfg.resolveTrovesOnly = False
        res = resolver.DependencyResolver(log, self.openRepository())
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, builtTroves)
        self.logFilter.add()
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReq, = result.getBuildReqs()
        assert(str(buildReq[2][0].trailingLabel())  == 'localhost@rpl:linux-devel')

    def testFindTrovesHandlesDifferentVersionsForX86AndX86_64(self):
        self.openRmakeRepository()
        self.openRepository()
        builtFooRun = self.addComponent('foo:runtime',
              '/localhost@rpl:linux//rmakehost@local:branch/1.0-1-0.1',
              'is:x86')
        builtFooRun2 = self.addComponent('foo:runtime',
              '/localhost@rpl:linux//rmakehost@local:branch/1.0-1-0.2',
              'is:x86_64')
        resolveFooRun = self.addComponent('foo:runtime',
              '/localhost@rpl:linux/1.0-1',
              'is:x86_64')
        builtTroves = [builtFooRun.getNameVersionFlavor(),
                       builtFooRun2.getNameVersionFlavor()]
        resolveTroves = [ resolveFooRun.getNameVersionFlavor()]
        self.buildCfg.resolveTroveTups = [resolveTroves]
        self.buildCfg.resolveTrovesOnly = True
        self.buildCfg.flavor = [parseFlavor('is:x86_64'), parseFlavor('is:x86 x86_64') ]
        trv = self.addComponent('bam:source')
        bt = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        bt.setBuildRequirements(['foo:runtime'])
        resolveJob = dephandler.ResolveJob(bt, self.buildCfg, builtTroves, [])
        self.logFilter.add()
        res = resolver.DependencyResolver(log, self.openRepository())

        # make sure that we don't grab the foo:lib from the resolveTroves
        # list even though it's a better match (intraTroveDeps should stop that)
        result = res.resolve(resolveJob)
        assert(result.success)
        buildReqs = result.getBuildReqs()
        buildReq, = buildReqs
        assert((buildReq[0], buildReq[2][0], buildReq[2][1])
                == builtFooRun2.getNameVersionFlavor())




