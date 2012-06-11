#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


import copy
import time
from testrunner import testhelp

from conary import trove
from conary import versions
from conary.deps import deps
from conary.lib import log, util

from rmake import failure
from rmake.build import buildcfg
from rmake.build import buildtrove
from rmake.build import dephandler
from rmake.build import publisher
from rmake.lib import flavorutil
from rmake.worker import resolver

from rmake_test import rmakehelp


def _toJob(nvf):
    return (nvf[0], (None, None), (nvf[1], nvf[2]), False)

class BuildJobWrapper:
    def __init__(self, test, resolveTrovesOnly = False):
        self.test = test
        self.test.openRepository()
        self.toBuild = []
        self.logs = []
        self.configs = {}
        cfg = buildcfg.BuildConfiguration(False, conaryConfig=test.cfg,
                                          root=test.cfg.root)
        self.cfg = cfg
        cfg.resolveTroves = []
        cfg.defaultBuildReqs = []
        cfg.resolveTrovesOnly = resolveTrovesOnly
        self.publisher = publisher.JobStatusPublisher()

    def addContext(self, context):
        self.configs[context] = copy.deepcopy(self.cfg)
        self.configs[context].setContext(context)
        self.configs[context].dropContexts()

    def addBuildTrove(self, name, version='1', flavor='', context='', 
                       buildReqs=[], crossReqs=[], packages=[],
                       loadedSpecs=None):
        if not packages:
            packages = [name]
        if isinstance(buildReqs, str):
            buildReqs = [buildReqs]

        version = self.test._cvtVersion(version, source=True)

        trv = self.test.addComponent(name + ':source', version, '',
                                     existsOkay=True)
        toBuild = buildtrove.BuildTrove(None, trv.getName(), trv.getVersion(),
                                        deps.parseFlavor(flavor), 
                                        context=context)
        toBuild.setBuildRequirements(buildReqs)
        toBuild.setCrossRequirements(crossReqs)
        toBuild.setDerivedPackages(packages)
        toBuild.setPublisher(self.publisher)
        if loadedSpecs:
            toBuild.setLoadedSpecs(loadedSpecs)
        if context:
            toBuild.setConfig(self.configs.get(context, self.cfg))
        else:
            toBuild.setConfig(self.cfg)
        self.toBuild.append(toBuild)
        return toBuild

    def addResolveTrove(self, name, version, flavor='',
                        components=[':runtime'], provides='',
                        requires='', newGroup=False, filePrimer=0,
                        context=''):
        for idx, component in enumerate(components):
            compName = name + component
            self.test.addComponent(compName, version,
                                   flavor, filePrimer=idx,
                                   provides=provides, requires=requires,
                                   existsOkay=True)
        trv = self.test.addCollection(name, version,  [components],
                                       defaultFlavor=flavor,
                                       existsOkay=True)
        if not context:
            cfg = self.cfg
        else:
            cfg = self.configs.get(context, self.cfg)
        if not hasattr(cfg, 'resolveTroveTups'):
            cfg.resolveTroveTups = []
            cfg.resolveTroves = []
        if newGroup or not cfg.resolveTroves:
            cfg.resolveTroves.append([trv.getNameVersionFlavor()])
            cfg.resolveTroveTups.append([trv.getNameVersionFlavor()])
        else:
            cfg.resolveTroves[-1].append(trv.getNameVersionFlavor())
            cfg.resolveTroveTups[-1].append(trv.getNameVersionFlavor())
        return trv

    def addResolveComp(self, (trv, cs), newGroup=False):
        repos = self.test.openRepository()
        repos.commitChangeSet(cs)
        if newGroup or not self.cfg.resolveTroves:
            self.cfg.resolveTroves.append([trv.getNameVersionFlavor()])
            self.cfg.resolveTroveTups.append([trv.getNameVersionFlavor()])
        else:
            self.cfg.resolveTroves[-1].append(trv.getNameVersionFlavor())
            self.cfg.resolveTroveTups[-1].append(trv.getNameVersionFlavor())
        return trv


    def prepareForBuild(self, limit=1, breakCycles=True, update=True):
        self.logger = log
        logDir = self.test.workDir + '/graphs'
        util.mkdirChain(logDir)
        dh = dephandler.DependencyHandler(self.publisher,
                                          self.logger,
                                          self.toBuild, [], logDir)
        self.resolver = resolver.DependencyResolver(self.logger,
                                                    self.test.openRepository())
        self.dh = dh
        self.state = dh.depState
        if update:
            self.updateBuildableTroves(limit, breakCycles=breakCycles)
        return dh

    def updateBuildableTroves(self, limit=1, breakCycles=True):
        self.test.logFilter.add()
        if not limit:
            limit = 9000
        resolved = False
        for i in range(limit):
            resolveJob = self.dh.getNextResolveJob(breakCycles=breakCycles)
            if resolveJob is None:
                break
            resolved = True
            resolveJob.getTrove().troveResolvingBuildReqs()
            results = self.resolver.resolve(resolveJob)
            resolveJob.getTrove().troveResolved(results)
        self.logs.extend(self.test.logFilter.records)
        self.test.logFilter.clear()
        return resolved

    def getState(self):
        return self.state

    def getFailureReason(self, trove):
        return trove.getFailureReason()

    def getBuildReqTroves(self, trove, reqName=None):
        if reqName is None:
            return list(self.state.getBuildReqTroves(trove)[0])
        else:
            return [ x for x in list(self.state.getBuildReqTroves(trove)[0])
                     if x[0] == reqName ]

    def getCrossReqTroves(self, trove):
        return list(self.state.getBuildReqTroves(trove)[1])

    def troveFailed(self, trove):
        self.test.logFilter.add()
        trove.troveFailed(failure.BuildFailed('reason', 'traceback'))
        self.updateBuildableTroves()
        self.logs.extend(self.test.logFilter.records)
        self.test.logFilter.clear()

    def trovePrebuilt(self, trv, components=[':runtime'],
                      buildReqs=None, allowFastResolution=False,
                      update=True, builtTime=None):
        pkgName = trv.getName().split(':')[0]
        v = trv.getVersion().copy()
        v.incrementBuildCount()
        flavor = flavorutil.getBuiltFlavor(trv.getFlavor())
        for idx, component in enumerate(components):
            compName = pkgName +  component
            self.test.addComponent(compName, str(v),
                                   flavor, filePrimer=idx,
                                   existsOkay=True)
        buildTrv = self.test.addCollection(pkgName, v,  components,
                                      defaultFlavor=flavor,
                                      existsOkay=True)
        repos = self.test.openRepository()
        self.test.logFilter.add()
        if not buildReqs:
            buildReqs = []
        else:
            if isinstance(buildReqs[0], trove.Trove):
                buildReqs = [ x.getNameVersionFlavor() for x in buildReqs ]
        if not builtTime:
            builtTime = time.time()
        prebuilt = [buildTrv.getNameVersionFlavor()]
        prebuilt += [ (prebuilt[0][0] + x, prebuilt[0][1], prebuilt[0][2]) for x in components]
        trv.trovePrebuilt(buildReqs, prebuilt,
                            builtTime,
                            fastRebuild=allowFastResolution)
        if update:
            self.updateBuildableTroves(limit=1)
        self.logs.extend(self.test.logFilter.records)
        self.test.logFilter.clear()
        return buildTrv

    def _getTrovePackages(self, trove, provides='', requires='', 
                          components=[':runtime'], flavor=None):
        self.test.openRmakeRepository()
        pkgName = trove.getName().split(':')[0]
        builtVersion = trove.getVersion().copy()
        tag = builtVersion.trailingLabel().branch
        commitLabel = versions.Label('rmakehost@LOCAL:%s' % tag)
        v = builtVersion.createShadow(commitLabel)
        v.incrementBuildCount()
        if flavor is None:
            flavor = flavorutil.getBuiltFlavor(trove.getFlavor())
        else:
            flavor = deps.parseFlavor(flavor, raiseError=False)

        for idx, component in enumerate(components):
            compName = pkgName +  component
            if isinstance(provides, dict):
                compProvides = provides.get(component, '')
            else:
                compProvides = provides
            if isinstance(requires, dict):
                compRequires = requires.get(component, '')
            else:
                compRequires = requires

            self.test.addComponent(compName, str(v),
                                   flavor, filePrimer=idx,
                                   provides=compProvides,
                                   requires=compRequires,
                                   existsOkay=True)
        trv = self.test.addCollection(pkgName, v,  components,
                                      defaultFlavor=flavor,
                                      existsOkay=True)
        repos = self.test.openRepository()
        cs = repos.createChangeSet([(pkgName, (None, None),
                                    (v, flavor), True)])
        return trv, cs


    def troveBuilt(self, trove, provides='', requires='', 
                   components=[':runtime'], flavor=None, update=True):
        self.test.openRmakeRepository()
        trv, cs = self._getTrovePackages(trove, provides, requires, components,
                                         flavor=flavor)
        self.test.logFilter.add()
        trove.troveBuilt(cs)
        if update:
            self.updateBuildableTroves(limit=1)
        self.logs.extend(self.test.logFilter.records)
        self.test.logFilter.clear()
        return trv

    def troveAlreadyBuilt(self, trove, provides='', requires='',
                          components=[':runtime']):
        self.test.openRmakeRepository()
        builtVersion = trove.getVersion().copy()
        tag = builtVersion.trailingLabel().branch
        commitLabel = versions.Label('rmakehost@LOCAL:%s' % tag)
        v = builtVersion.createShadow(commitLabel)
        v.incrementBuildCount()
        trv = self.test.addCollection(trove.getName().split(':')[0], str(v),
                                      components,
                              changeSetFile=self.test.workDir + '/foo.ccs')
        troveList = [ x for x in trv.iterTroveList(strongRefs=True) ]
        troveList += [trv.getNameVersionFlavor()]
        self.test.logFilter.add()
        trove.troveDuplicate(troveList)
        self.updateBuildableTroves(limit=1)
        self.logs.extend(self.test.logFilter.records)
        self.test.logFilter.clear()
        return trv

    def checkAllBuildableTroves(self):
        self.test.logFilter.add()
        try:
            return self.updateBuildableTroves(limit=None)
        finally:
            self.logs.extend(self.test.logFilter.records)
            self.test.logFilter.clear()

    def getBuildableTroves(self):
        return self.state.getBuildableTroves()

    def getDepLeaves(self):
        return set(self.state.getDependencyGraph().getLeaves())


class DepHandlerTest(rmakehelp.RmakeHelper):

    def testIntraTroveDeps(self):
        wrapper = BuildJobWrapper(self)
        trv = self.addComponent('automake:runtime', '1.9',
                                requires='trove:automake:data')
        self.addComponent('automake:data',    '1.9', filePrimer=1)
        self.addComponent('automake:runtime', ':branch/1.4', filePrimer=2,
                          requires='trove:automake:data')
        data14 = self.addComponent('automake:data',
                                   ':branch/1.4', filePrimer=3)

        self.addCollection('automake', '1.9', [':data', ':runtime'])
        self.addCollection('automake', ':branch/1.4', [':data', ':runtime'])

        trv    = wrapper.addResolveTrove('automake', '1.9')
        data14 = wrapper.addResolveTrove('automake', ':branch/1.4')

        foo = wrapper.addBuildTrove('foo', '1',
                                    buildReqs=['automake:runtime=:branch'])
        wrapper.prepareForBuild()

        assert(wrapper.getBuildableTroves() == set([foo]))
        buildReqs = wrapper.getBuildReqTroves(foo)
        data14Job = ('automake:data', (None, None), 
                     (data14.getVersion(), data14.getFlavor()), False)
        assert([ x for x in buildReqs if x[0] == 'automake:data'] 
                == [data14Job])

        # grab the intra-trove dependency from a built changeset,
        # not from the repos
        wrapper = BuildJobWrapper(self)
        trv    = wrapper.addResolveTrove('automake', '1.9')
        foo = wrapper.addBuildTrove('foo', '1',
                                    buildReqs=['automake:runtime=:branch'])
        automake14 = wrapper.addBuildTrove('automake', ':branch/1.4')

        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([automake14]))
        trv14 = wrapper.troveBuilt(automake14, components=[':data', ':runtime'],
                                   requires='trove: automake:data')
        data14Job = ('automake:data', (None, None), 
                     (trv14.getVersion(), trv14.getFlavor()), False)

        assert(wrapper.getBuildableTroves() == set([foo]))
        buildReqs = wrapper.getBuildReqTroves(foo)
        assert([ x for x in buildReqs if x[0] == 'automake:data'] 
                == [data14Job])

        # turn off resolveTroves - use installLabelPath only
        wrapper = BuildJobWrapper(self)
        foo = wrapper.addBuildTrove('foo', '1',
                                    buildReqs=['automake:runtime=:branch'])
        wrapper.prepareForBuild()

        assert(wrapper.getBuildableTroves() == set([foo]))
        buildReqs = wrapper.getBuildReqTroves(foo)
        data14Job = ('automake:data', (None, None), 
                     (data14.getVersion(), data14.getFlavor()), False)
        assert([ x for x in buildReqs if x[0] == 'automake:data'] 
                == [data14Job])

    def testMultiArchIntraTroveDeps(self):
        wrapper = BuildJobWrapper(self)
        C = self.Component
        barRun_x86 = wrapper.addResolveComp(C('bar:runtime', '1', 'is:x86',
                                             filePrimer=1))
        barRun_x86_64 = wrapper.addResolveComp(C('bar:runtime', '1',
                                                'is:x86_64', filePrimer=1))
        wrapper.addResolveComp(C('bar:lib', '1', 'is:x86', 
                             requires='trove:bar:runtime',
                             provides='trove:bar:lib(x86)',
                             filePrimer=2))
        wrapper.addResolveComp(C('bar:lib', '1', 'is:x86_64',
                             requires='trove:bar:runtime trove:blah:runtime',
                             filePrimer=3))
        wrapper.addResolveComp(C('bam:lib', '1', 'is:x86',
                             requires='trove:bar:lib(x86)',
                             filePrimer=4))
        wrapper.addResolveComp(C('baz:lib', '1', 'is:x86_64',
                             requires='trove:bar:lib',
                             filePrimer=5))
        wrapper.addResolveComp(C('blah:runtime', '1', 'is:x86_64', 
                                 filePrimer=6))

        foo = wrapper.addBuildTrove('foo', '2', 'is:x86_64',
                                     buildReqs=['baz:lib', 'bam:lib'])

        override = deps.overrideFlavor
        wrapper.cfg.flavor = [override(wrapper.cfg.flavor[0],
                                       deps.parseFlavor('is: x86_64')),
                              override(wrapper.cfg.flavor[0],
                                       deps.parseFlavor('is: x86_64 x86'))]
        wrapper.prepareForBuild()
        buildReqs = wrapper.getBuildReqTroves(foo)
        barRunReqs = [ (x[0], x[2][0], x[2][1])
                       for x in buildReqs if x[0] == 'bar:runtime' ]
        assert(barRunReqs == [barRun_x86_64.getNameVersionFlavor()])

    def testFailedTrove(self):
        wrapper = BuildJobWrapper(self)
        foo = wrapper.addBuildTrove('foo', '2')
        bar = wrapper.addBuildTrove('bar', '2',
                                            buildReqs=['foo:runtime'])
        wrapper.prepareForBuild()
        wrapper.troveFailed(foo)

        assert(not wrapper.getBuildableTroves())

        assert(isinstance(wrapper.getFailureReason(foo), failure.BuildFailed))
        assert(wrapper.getFailureReason(bar) == failure.MissingBuildreqs([('foo:runtime', None, None)]))

    def testCycleDetection(self):
        wrapper = BuildJobWrapper(self)
        bam = wrapper.addBuildTrove('bam', '2')
        foo = wrapper.addBuildTrove('foo', '2',
                                    buildReqs=['bar:runtime', 'bam:runtime'])
        bar = wrapper.addBuildTrove('bar', '2',
                                    buildReqs=['foo:runtime', 'bam:runtime'])
        wrapper.prepareForBuild()
        wrapper.troveBuilt(bam)
        # we need to tell the dependency handler to check twice:
        # once to see if foo is buildable and another to see if bar is 
        # buildable
        wrapper.updateBuildableTroves()

        # neither of the two troves are buildable, since neither of their
        # buildreqs are satisfied.
        assert(len(wrapper.getBuildableTroves()) == 0)
        assert(wrapper.getFailureReason(foo) == failure.MissingBuildreqs([('bar:runtime', None, None)]))
        assert(wrapper.getFailureReason(bar) == failure.MissingBuildreqs([('foo:runtime', None, None)]))

    def testCycleDetection2(self):
        log.setVerbosity(log.DEBUG)
        wrapper = BuildJobWrapper(self)
        bam = wrapper.addBuildTrove('bam', '2')
        foo = wrapper.addBuildTrove('foo', '2',
                                    buildReqs=['bar:runtime', 'bam:runtime'])
        bar = wrapper.addBuildTrove('bar', '2',
                                    buildReqs=['foo:runtime', 'bam:runtime', 'bzt:runtime'])
        baz = wrapper.addBuildTrove('baz', '2',
                                    buildReqs=['foo:runtime'])
        bzt = wrapper.addBuildTrove('bzt', '2',
                                    buildReqs=['baz:runtime'])
        wrapper.addResolveTrove('foo', '1')

        wrapper.prepareForBuild()

        # We should have a buildable trove this time.
        assert(wrapper.getBuildableTroves() == set([bam]))
        wrapper.troveBuilt(bam)
        wrapper.updateBuildableTroves()
        wrapper.updateBuildableTroves()
        # We should have a buildable trove this time.
        assert('''\
+ Cycle 1 (4 packages):
     bar:source=/localhost@rpl:linux/2-1[]{}
     baz:source=/localhost@rpl:linux/2-1[]{}
     bzt:source=/localhost@rpl:linux/2-1[]{}
     foo:source=/localhost@rpl:linux/2-1[]{}''' in wrapper.logs)
        expected = '''\
+ Cycle 1: Shortest Cycles:
 bar:source=/localhost@rpl:linux/2-1[]{}
   -> foo:source=/localhost@rpl:linux/2-1[]{}
   -> bar:source=/localhost@rpl:linux/2-1[]{}

 baz:source=/localhost@rpl:linux/2-1[]{}
   -> foo:source=/localhost@rpl:linux/2-1[]{}
   -> bar:source=/localhost@rpl:linux/2-1[]{}
   -> bzt:source=/localhost@rpl:linux/2-1[]{}
   -> baz:source=/localhost@rpl:linux/2-1[]{}'''
        assert(expected in wrapper.logs), \
       "missing text %s\n\nin\n\n%s" % (expected, '\n'.join(wrapper.logs))
        assert(wrapper.getBuildableTroves() == set([baz]))
        wrapper.troveBuilt(baz)
        assert(wrapper.getBuildableTroves() == set([bzt]))
        wrapper.troveBuilt(bzt)
        # at this point there's another, smaller cycle, so 
        # we have to call updatebuildableTroves again
        wrapper.updateBuildableTroves()
        assert(wrapper.getBuildableTroves() == set([bar]))
        wrapper.troveBuilt(bar)
        assert(wrapper.getBuildableTroves() == set([foo]))
        wrapper.troveBuilt(foo)
        assert(len(wrapper.getBuildableTroves()) == 0)

    def testCycleOfOne(self):
        # this trove requires itself, and is not built yet!
        wrapper = BuildJobWrapper(self)
        bam = wrapper.addBuildTrove('foo', '2',
                                    buildReqs=['foo:runtime'])
        wrapper.prepareForBuild()
        assert(len(wrapper.getBuildableTroves()) == 0)
    
    def testCycleOfOne2(self):
        wrapper = BuildJobWrapper(self)
        bam = wrapper.addBuildTrove('foo', '2',
                                    buildReqs=['foo:runtime'])
        wrapper.addResolveTrove('foo', '1')
        wrapper.prepareForBuild()
        # we'll use the pre-built foo to satisfy this dep.
        assert(len(wrapper.getBuildableTroves()) == 1)

    def testFlavoredDeps(self):
        wrapper = BuildJobWrapper(self)
        foonorl = wrapper.addBuildTrove('foo', '1', '!readline',
                                        buildReqs=[])
        foorl = wrapper.addBuildTrove('foo', '1', 'readline',
                                      buildReqs=['foo:runtime[!readline]'])
        bar = wrapper.addBuildTrove('bar', '1',
                                    buildReqs=['foo:runtime[readline]'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([foonorl]))
        wrapper.troveBuilt(foonorl)
        assert(wrapper.getBuildableTroves() == set([foorl]))
        wrapper.troveBuilt(foorl)
        assert(wrapper.getBuildableTroves() == set([bar]))

    def testFlavoredDeps2(self):
        wrapper = BuildJobWrapper(self)
        foonorl = wrapper.addBuildTrove('foo', '1', '!readline',
                                        buildReqs=[])
        foorl = wrapper.addBuildTrove('foo', '1', 'readline',
                                      buildReqs=['foo:runtime[!readline]'])
        bar = wrapper.addBuildTrove('bar', '1',
                                    buildReqs=['foo:runtime[!readline]'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([foonorl]))
        wrapper.troveBuilt(foonorl)
        assert(wrapper.getDepLeaves() == set([foorl, bar]))

    def testMultipleSatisfyOneFails(self):
        wrapper = BuildJobWrapper(self)
        foo1 = wrapper.addBuildTrove('foo', '1')
        foo2 = wrapper.addBuildTrove('foo', '2')
        bar  = wrapper.addBuildTrove('bar', '1', buildReqs=['foo:runtime'])
        wrapper.prepareForBuild()
        assert(len(wrapper.getDepLeaves()) == 2)
        wrapper.troveFailed(foo1)
        assert(len(wrapper.getBuildableTroves()) == 1)
        wrapper.troveBuilt(foo2)
        assert(len(wrapper.getBuildableTroves()) == 1)

    def testRequiresMainAutoconf(self):
        # autoconf from autoconf213 shouldn't be allowed to satisfy 
        # a request for autoconf:runtime, only autoconf:runtime=:autoconf213
        # FIXME: What's really going on here is that darby is keeping
        # foo from being built until both autoconfs are built.
        # this will change if we try to make two troves buildable at once.
        wrapper = BuildJobWrapper(self)
        ac213 = wrapper.addBuildTrove('autoconf', ':autoconf213/213')
        ac = wrapper.addBuildTrove('autoconf', '1')
        foo = wrapper.addBuildTrove('foo', '1', buildReqs=['autoconf:runtime'])
        wrapper.prepareForBuild()
        assert(wrapper.getDepLeaves() == set([ac213, ac]))
        wrapper.troveBuilt(ac213)
        assert(wrapper.getDepLeaves() == set([ac]))
        wrapper.troveBuilt(ac)
        assert(wrapper.getBuildableTroves() == set([foo]))

    def testRequiresOnly(self):
        # troves only have a dependency relationship based on runtime 
        # requirements
        # c has a buildreq on b, which.
        # b has a runtime requirement on a.
        wrapper = BuildJobWrapper(self)
        a = wrapper.addResolveTrove('a', '1',
                                    provides='trove: a:runtime file:/bin/foo')
        a = wrapper.addResolveTrove('c', '1')
        a = wrapper.addBuildTrove('a', '1')
        b = wrapper.addBuildTrove('b', '1')
        c = wrapper.addBuildTrove('c', '1', buildReqs=['b'])
        wrapper.prepareForBuild(limit=3)
        assert(wrapper.getBuildableTroves() == set([a, b]))

        trvLog = c.getPublisher()
        messages = []
        def _update(trv, state, msg):
            if trv == c:
                messages.append(msg)
        trvLog.subscribe(trvLog.TROVE_STATE_UPDATED, _update)

        # we're testing two things here - 1. c has a runtime req on 
        # a through two different dependencies - make sure that doesn't
        # cause rMake to show that two troves are needed for dep resolution
        # 2. c also requires itself to build.  But that's not interesting
        # to rMake because it can't resolve that dep cycle anyway.
        wrapper.troveBuilt(b,
                requires='trove: a:runtime file:/bin/foo trove: c:runtime')
        wrapper.checkAllBuildableTroves()
        assert('Resolved buildreqs include 1 other troves scheduled to be built - delaying: \na:source=/localhost@rpl:linux/1-1[]{}' in messages)

        # c is not buildable because it needs a
        assert(wrapper.getBuildableTroves() == set([a]))
        assert(wrapper.getDepLeaves() == set([a]))

        wrapper.troveBuilt(a,
                provides='trove: a:runtime file:/bin/foo')
        assert(wrapper.getBuildableTroves() == set([c]))
        assert(wrapper.getDepLeaves() == set([c]))

    def testMissingDependency(self):
        wrapper = BuildJobWrapper(self)
        a = wrapper.addResolveTrove('a', '1', requires='trove: foo')
        b = wrapper.addBuildTrove('b', '1', buildReqs=['a:runtime'])
        wrapper.prepareForBuild()
        assert(not wrapper.getBuildableTroves())
        _, v, f = a.getNameVersionFlavor()
        assert(wrapper.getFailureReason(b) == failure.MissingDependencies(
                        [(('a:runtime', v, f), deps.parseDep('trove: foo'))]))


    def testLabelMultiplicity(self):
        wrapper = BuildJobWrapper(self)
        a1 = wrapper.addResolveTrove('a',
                                     '/localhost@rpl:branch1//linux/1-1-1')
        a2 = wrapper.addResolveTrove('a',
                     '/localhost@rpl:branch2//linux/1-1-1', newGroup=False)
        b = wrapper.addBuildTrove('b', '1', buildReqs=['a:runtime'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([b]))
        assert(list(wrapper.getBuildReqTroves(b))[0][2][0] == a2.getVersion())

    def testLookingUpstreamForBuildReqs(self):
        wrapper = BuildJobWrapper(self)
        a1 = wrapper.addResolveTrove('a', '/localhost@rpl:automake/1-1-1')
        b = wrapper.addBuildTrove('b', '/localhost@rpl:linux//foo:linux/1-1-1',
                                  buildReqs=['a=:automake'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([b]))

    def testLookingInGroupFirstForBuildreqs(self):
        wrapper = BuildJobWrapper(self)
        t1 = self.addComponent('test:run', ':b1/1')
        self.addCollection('test', ':b1/1', [':run'])
        self.addComponent('test:run', ':b2/1')
        self.addCollection('test', ':b2/1', [':run'])

        grp = self.addCollection('group-dist', ':b1/1', ['test'])
        wrapper.cfg.resolveTroves.append([grp.getNameVersionFlavor()])
        wrapper.cfg.resolveTroveTups.append([grp.getNameVersionFlavor()])

        self.addComponent('tobuild:source', ':b2/1')
        b = wrapper.addBuildTrove('tobuild', '/localhost@rpl:b2//b3/1-1', 
                                  buildReqs=['test:run'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([b]))
        assert(list(wrapper.getBuildReqTroves(b))[0][2][0] == t1.getVersion())

    def testLookingInGroupOnlyForBuildreqs(self):
        # this will fail because the dep is only available via the
        # installLabelPath and we've got resolveTrovesOnly on
        wrapper = BuildJobWrapper(self, resolveTrovesOnly=True)
        t1 = self.addComponent('test:run', ':b1/1')
        self.addCollection('test', ':b1/1', [':run'])
        self.addComponent('test:run', ':b2/1')
        self.addCollection('test', ':b2/1', [':run'])

        grp = self.addCollection('group-dist', ':b1/1', ['test'])
        wrapper.cfg.resolveTroves.append([grp.getNameVersionFlavor()])
        wrapper.cfg.resolveTroveTups.append([grp.getNameVersionFlavor()])

        self.addComponent('tobuild:source', ':b2/1')
        b = wrapper.addBuildTrove('tobuild', '/localhost@rpl:b2//b3/1-1', 
                                  buildReqs=['test:run'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([b]))
        assert(list(wrapper.getBuildReqTroves(b))[0][2][0] == t1.getVersion())



    def testTwoFlavoredSolutionsInGroup(self):
        wrapper = BuildJobWrapper(self)
        t1 = self.addComponent('test:run', '1', 'readline,ssl')
        t2 = self.addComponent('test:run', '2', '~readline')
        t3 = self.addComponent('test:run', '3', '!readline')

        grp = self.addCollection('group-dist', '1', [
                                    ('test:run', '1', 'readline,ssl'),
                                    ('test:run', '2', '~readline'),
                                    ('test:run', '3', '!readline')])
        wrapper.cfg.resolveTroves.append([grp.getNameVersionFlavor()])
        wrapper.cfg.resolveTroveTups.append([grp.getNameVersionFlavor()])

        self.addComponent('tobuild:source', '1')
        b = wrapper.addBuildTrove('tobuild', '1', buildReqs=['test:run'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([b]))
        assert(list(wrapper.getBuildReqTroves(b))[0][2][0] == t2.getVersion())

    def testFallBackToTroveLabel(self):
        # NOTE - I've turned off the feature here, I don't think it's
        # actually the right solution.  I think the right solution is to 
        # allow people to order label paths vs. groups.

        # If a dependency cannot be resolved within the specified group,
        # we should search for it on the installLabelPath of a)
        # the trove that's being installed and b) the installLabelPath.


        # so, here's one example where we pull the buildreq based on the 
        # label of the thing we're building

        wrapper = BuildJobWrapper(self)
        t1 = self.addComponent('foo:run', '1')

        wrapper.cfg.resolveTroves.append([t1.getNameVersionFlavor()])
        wrapper.cfg.resolveTroveTups.append([t1.getNameVersionFlavor()])

        origLabelProv = self.addComponent('prov:run', '1')
        prov = self.addComponent('prov:run',  ':b3/1', 
                                 requires='trove:prov2:run')
        prov = self.addComponent('prov2:run', ':b3/1')


        self.addComponent('tobuild:source', ':b2/1')
        b = wrapper.addBuildTrove('tobuild', '/localhost@rpl:b2//b3/1-1', 
                                  buildReqs=['prov:run'])

        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([b]))
        assert(list(wrapper.getBuildReqTroves(b))[0][2][0] 
                    == origLabelProv.getVersion())

    def testFallBackToLabelPath(self):
        # like above example, except that it falls back to the installLabelPath
        wrapper = BuildJobWrapper(self)
        t1 = self.addComponent('foo:run', '1')

        wrapper.cfg.resolveTroves.append([t1.getNameVersionFlavor()])
        wrapper.cfg.resolveTroveTups.append([t1.getNameVersionFlavor()])

        prov = self.addComponent('prov:run', '1', requires='trove:prov2:run')
        prov = self.addComponent('prov2:run', '1')

        self.addComponent('tobuild:source', ':b2/1')
        b = wrapper.addBuildTrove('tobuild', '/localhost@rpl:b2//b3/1-1', 
                                  buildReqs=['prov:run'])

        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([b]))
        assert(list(wrapper.getBuildReqTroves(b))[0][2][0] == prov.getVersion())

    def testFallBackToLabelPathWithResolveTrovesOnly(self):
        # we've turned off support for falling back to the label path -
        # resolveTrovesOnly is on
        wrapper = BuildJobWrapper(self, resolveTrovesOnly=True)

        t1 = self.addComponent('foo:run', '1', requires='trove:prov:run')
        wrapper.cfg.resolveTroves.append([t1.getNameVersionFlavor()])
        wrapper.cfg.resolveTroveTups.append([t1.getNameVersionFlavor()])

        prov = self.addComponent('prov:run', '1', requires='trove:prov2:run')
        prov = self.addComponent('prov2:run', '1')

        self.addComponent('tobuild:source', ':b2/1')
        b = wrapper.addBuildTrove('tobuild', '/localhost@rpl:b2//b3/1-1', 
                                  buildReqs=['prov:run'])

        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set())

        # test 2 - dep resolution fails
        wrapper = BuildJobWrapper(self, resolveTrovesOnly=True)

        wrapper.cfg.resolveTroves.append([t1.getNameVersionFlavor()])
        wrapper.cfg.resolveTroveTups.append([t1.getNameVersionFlavor()])
        b = wrapper.addBuildTrove('tobuild', '/localhost@rpl:b2//b3/1-1', 
                                  buildReqs=['foo:run'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set())

    def testOrderedResolveTroveList(self):
        # resolveTrove lists are now "ordered" - if you list resolveTroves
        # on separate lines, they go into separate buckets.

        # so here we have in bucket #1 something on an unusual branch,
        # rmake should still prefer it over the more standard trove in
        # bucket #2

        wrapper = BuildJobWrapper(self, resolveTrovesOnly=True)
        fooBranch = wrapper.addResolveTrove('foo', ':branch/1',
                                            requires='trove:bar')
        foo = wrapper.addResolveTrove('foo', '1', newGroup=True)
        bar = wrapper.addResolveTrove('bar', '1') #make sure we can resolve from
                                                  # the second list.
        b = wrapper.addBuildTrove('tobuild', '1',
                                  buildReqs=['foo:runtime'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([b]))
        assert('bar' in [x[0] for x in wrapper.getBuildReqTroves(b)])
        fooVer = [ x[2][0] for x in wrapper.getBuildReqTroves(b) if x[0] == 'foo:runtime'][0]
        assert(fooVer == fooBranch.getVersion())

    def testInstallPackagesForBuildReq(self):
        wrapper = BuildJobWrapper(self)
        a1 = wrapper.addResolveTrove('a', '1')
        self.addComponent('b:runtime', '1')
        c = wrapper.addBuildTrove('c', '1', buildReqs=['a:runtime',
                                                       'b:runtime'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([c]))
        assert(len(wrapper.getBuildReqTroves(c)) == 3)
        names = set(x[0] for x in wrapper.getBuildReqTroves(c))
        assert(names == set(['a', 'a:runtime', 'b:runtime']))

    def testResolveMightUseRedirects(self):
        self.addComponent('foo:runtime', '2', redirect=['blah:r'])
        self.addCollection('foo', '2', [':runtime'], redirect=['blah'])
        branched = self.addComponent('foo:runtime', ':branch/1')
        branchedColl = self.addCollection('foo', ':branch/1', [':runtime'])

        wrapper = BuildJobWrapper(self)
        wrapper.cfg.installLabelPath += [versions.Label('localhost@rpl:branch')]
        c = wrapper.addBuildTrove('c', '1', buildReqs=['foo:runtime'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([c]))
        troves  = set([(x[0], x[2][0], x[2][1])
                       for x in wrapper.getBuildReqTroves(c) ])
        assert(troves == set([branched.getNameVersionFlavor(), 
                              branchedColl.getNameVersionFlavor()]))

    def testCrossCompileOrdering1(self):
        # if we're cross compiling an x86_64 trove on an x86 box, it doesn't
        # satisfy a buildreq.

        # in this case, foo is going to end up is: x86_64 and so isn't a good
        # buildreq.
        self.addComponent('foo:runtime', '1', 'is:x86')
        wrapper = BuildJobWrapper(self)
        bar = wrapper.addBuildTrove('bar', '1',
                        '!cross is: x86 target: x86_64', 
                        buildReqs=['foo:runtime'])
        foo = wrapper.addBuildTrove('foo', '1',
                              '!cross is: x86 target: x86_64')
        wrapper.prepareForBuild(2)
        assert(wrapper.getBuildableTroves() == set([foo, bar]))

    def testCrossCompileOrdering2(self):
        # bar requires foo (x86 flavor).
        # foo provides an x86 flavored trove since it's cross compiling.
        self.cfg.flavor = [deps.parseFlavor('!cross is:x86')]
        self.cfg.flavor[0] = deps.overrideFlavor(self.cfg.flavor[0],
                                     deps.parseFlavor('~cross target: x86_64'))
        self.addComponent('foo:runtime', '1', 'is:x86')
        wrapper = BuildJobWrapper(self)
        bar = wrapper.addBuildTrove('bar', '1',
                        '!cross is: x86 target: x86_64', 
                        buildReqs=['foo:runtime'])
        foo = wrapper.addBuildTrove('foo', '1',
                              'cross is: x86 target: x86_64')
        wrapper.prepareForBuild(2)
        assert(wrapper.getBuildableTroves() == set([foo]))
        fooBin = wrapper.troveBuilt(foo).getNameVersionFlavor()
        assert(wrapper.getBuildableTroves() == set([bar]))
        assert(_toJob(fooBin) in wrapper.getBuildReqTroves(bar))

    def testCrossCompileOrdering3(self):
        # if a has a cross requirement on b, but we're building b 
        # for the wrong arch, don't add a dependency.
        self.addComponent('foo:devel', '1', 'is: x86_64')
        wrapper = BuildJobWrapper(self)
        bar = wrapper.addBuildTrove('bar', '1',
                        '!cross is: x86 target: x86_64', 
                        crossReqs=['foo:devel'])
        # this is a cross-compiling version of foo, it's final is: will be
        # x86, not appropriate for installing in the sys-root
        foo = wrapper.addBuildTrove('foo', '1',
                              'cross is: x86 target: x86_64')
        wrapper.prepareForBuild(2)
        assert(wrapper.getBuildableTroves() == set([foo, bar]))

    def testCrossCompileOrdering4(self):
        # if a has a cross requirement on b, but we're building b 
        # for the right arch, add a dependency.
        self.addComponent('foo:devel', '1', 'is: x86_64')
        wrapper = BuildJobWrapper(self)
        bar = wrapper.addBuildTrove('bar', '1',
                        '!cross is: x86 target: x86_64',
                        crossReqs=['foo:devel'])
        # this is a cross-compiling version of foo, it's final is: will be
        # x86, not appropriate for installing in the sys-root
        foo = wrapper.addBuildTrove('foo', '1',
                              '!cross is: x86 target: x86_64')
        wrapper.prepareForBuild(2)
        assert(wrapper.getBuildableTroves() == set([foo]))
        fooBin = wrapper.troveBuilt(foo, 
                        components=[':devel']).getNameVersionFlavor()
        assert(wrapper.getBuildableTroves() == set([bar]))
        assert(_toJob(fooBin) in wrapper.getCrossReqTroves(bar))

    def testCrossCompileOrdering5(self):
        # don't use something built by a cross compiler trove as a buildreq
        # for something that's being built w/ that cross compiler.
        self.addComponent('bash:runtime', '1', 'is: x86')
        self.addComponent('gcc:runtime', '1', 'cross is: x86 target: x86')
        self.overrideBuildFlavor('~cross is: x86 target:x86')
        self.cfg.flavor = [ self.cfg.buildFlavor ]

        wrapper = BuildJobWrapper(self)
        gcc = wrapper.addBuildTrove('gcc', '1',
                        'cross is: x86 target: x86')
        bash = wrapper.addBuildTrove('bash', '1',
                                '!cross is: x86 target: x86',
                                buildReqs=['gcc:runtime[cross]'])
        foo = wrapper.addBuildTrove('foo', '1',
                                '!cross is: x86 target: x86', 
                            buildReqs=['gcc:runtime[cross]', 'bash:runtime'])
        wrapper.prepareForBuild(3)
        assert(wrapper.getBuildableTroves() == set([gcc]))
        gccBin = wrapper.troveBuilt(gcc).getNameVersionFlavor()
        wrapper.updateBuildableTroves(3)
        assert(wrapper.getBuildableTroves() == set([bash, foo]))
        assert(_toJob(gccBin) in wrapper.getBuildReqTroves(bash))
        bashBin = wrapper.troveBuilt(bash).getNameVersionFlavor()
        assert(wrapper.getBuildableTroves() == set([foo]))
        assert(_toJob(gccBin) in wrapper.getBuildReqTroves(foo))
        assert(_toJob(bashBin) not in wrapper.getBuildReqTroves(foo))

    def testCrossCompileOrderingFull(self):
        # x86/x86_64 provides are used as a shortcut for soname dependencies
        for arch in 'x86', 'x86_64':
            flavor = '~!bootstrap is:%s' % arch
            self.addComponent('binutils:runtime', '1', flavor,
                              requires='trove: binutils:lib(%s)' % arch)
            self.addComponent('binutils:lib', '1', flavor,
                               filePrimer=1, provides='trove:binutils:lib(%s)' % arch)
            self.addComponent('gcc:runtime', '1', '~!bootstrap is: %s' % arch,
                              requires='trove: binutils:runtime trove:gcc:lib(%s)' % arch)
            self.addComponent('gcc:lib', '1', '~!bootstrap is:%s' % arch,
                              provides='trove: gcc:lib(%s)' % arch,
                              requires='trove: glibc:lib(%s)' % arch)
            self.addComponent('glibc:lib', '1', '~!bootstrap is:%s' % arch,
                              provides='trove:glibc:lib(%s)' % arch)
            self.addComponent('glibc:devel', '1', '~!bootstrap is:%s' % arch,
                              requires='trove:glibc:lib(%s) trove:ukh:devel' % arch)
            self.addComponent('ukh:devel', '1', 'is:%s' % arch)

        wrapper = BuildJobWrapper(self)
        flavor = wrapper.cfg.flavor[0]
        flavor = deps.overrideFlavor(flavor, deps.parseFlavor('~bootstrap,~cross is: x86(~i486,~i586,~i686) target: x86_64'))
        buildFlavor = deps.overrideFlavor(flavor,
                deps.parseFlavor('is: x86(~i486,~i586,~i686) target: x86_64'))
        wrapper.cfg.flavor = [flavor]
        wrapper.cfg.buildFlavor = buildFlavor
        defaultCReqs = ['binutils:runtime',
                        'binutils:lib',
                        'gcc:runtime',
                        'gcc:lib',
                        'glibc:devel',
                        'glibc:lib']
        localCReqs = ['binutils:runtime[!cross]', 'gcc:runtime[!cross]']

        troves = {}
        for buildInfo in  [
               ('ukh', '1', '!cross is: x86 target: x86_64',
                            ['binutils:runtime[!cross]',
                             'gcc:runtime[!cross]']),
               ('glibc-headers', '1', 'cross is: x86 target: x86_64',
                ['binutils:runtime[!cross]',
                 'gcc:runtime[!cross]'], ['ukh:devel']),
               ('binutils', '1', 'cross is: x86 target: x86_64', 
                ['binutils:runtime[!cross]', 'gcc:runtime[!cross]',
                 'glibc:devel'], []),
               ('gcc', '1', 'cross,~core is: x86 target: x86_64',
                localCReqs + ['glibc-headers:devel[cross]',
                              'binutils:runtime[cross]'],
                              ['ukh:devel']),
               ('glibc', '1', '!cross is: x86 target: x86_64',
               (['gcc:runtime[cross,core]', 'glibc:devel', 
                 'binutils:runtime'] +
                localCReqs + ['glibc-headers:devel[cross]']), 
                ['ukh:devel']),
               ('gcc', '1', 'cross is: x86 target: x86_64',
                defaultCReqs + localCReqs,  ['glibc:devel']),
               ('binutils', '1', '!cross is: x86 target: x86_64',
                defaultCReqs + localCReqs, ['glibc:devel']),
               ('gcc', '1', '!cross is: x86 target: x86_64',
                ['gcc[cross,!core]'] + localCReqs,
                ['glibc:devel', 'ukh:devel'])]:
            name, version, flavor = buildInfo[:3]
            buildInfo = buildInfo[3:]
            buildReqs = crossReqs = []
            if buildInfo:
                buildReqs = buildInfo[0]
            if len(buildInfo) == 2:
                crossReqs = buildInfo[1]
            trv = wrapper.addBuildTrove(name, version, flavor, 
                                    buildReqs=buildReqs, crossReqs=crossReqs)
            troves.setdefault(name, []).append(trv)

        wrapper.prepareForBuild(limit=100, breakCycles=False)
        ukh, = troves['ukh']
        binutils_cross, binutils_nocross = troves['binutils']
        glibc_headers, = troves['glibc-headers']
        gcc_core, gcc_cross, gcc_nocross  = troves['gcc']
        glibc, = troves['glibc']

        assert(wrapper.getBuildableTroves() == set([ukh, binutils_cross]))
        wrapper.troveBuilt(ukh, components=[':devel'])
        wrapper.updateBuildableTroves(limit=100, breakCycles=False)
        assert(wrapper.getBuildableTroves() == set([glibc_headers, binutils_cross]))
        wrapper.troveBuilt(glibc_headers, components=[':devel'])
        assert(wrapper.getBuildableTroves() == set([binutils_cross]))
        target = 'target-x86_64-unknown-linux'
        wrapper.troveBuilt(binutils_cross, components=[':runtime', ':lib'],
               provides={':lib' : 'trove: binutils:lib(%s)' % target,
                         ':runtime' : 'trove: binutils:runtime(%s)' % target},
               requires={':runtime' : 'trove: binutils:lib(%s) trove: glibc:lib(x86)' % target})
        wrapper.updateBuildableTroves(limit=100, breakCycles=False)
        assert(wrapper.getBuildableTroves() == set([gcc_core]))
        wrapper.troveBuilt(gcc_core, components=[':runtime', ':lib'],
               provides={':lib' : 'trove: gcc:lib(%s)' % target,
                         ':runtime' : 'trove: gcc:runtime(%s)' % target},
               requires={':runtime' : 'trove: gcc:lib(%s) trove: glibc:lib(x86) trove:binutils:runtime(%s)' % (target, target)})
        wrapper.updateBuildableTroves(limit=100, breakCycles=False)
        assert(wrapper.getBuildableTroves() == set([glibc]))
        wrapper.troveBuilt(glibc, components=[':runtime', ':lib', ':devel'],
               provides={':devel' : 'trove: glibc:devel(x86_64)',
                         ':lib' : 'trove: glibc:lib(x86_64)',
                         ':runtime' : 'trove: glibc:runtime file: /sbin/ldconfig' },
               requires={':runtime' : 'trove: glibc:lib(x86_64)',
                         ':lib'     : 'file: /sbin/ldconfig',
                         ':devel'   : 'trove: glibc:lib(x86_64)'})
        wrapper.updateBuildableTroves(limit=100, breakCycles=False)
        assert(wrapper.getBuildableTroves() == set([gcc_cross]))
        wrapper.troveBuilt(gcc_cross,
               components=[':runtime', ':lib'],
               provides={':lib' : 'trove: gcc:lib(%s)' % target,
                         ':runtime' : 'trove: gcc:runtime(%s)' % target},
               requires={':runtime' : 'trove: gcc:lib(%s) trove: glibc:lib(x86) trove:binutils:runtime(%s)' % (target, target)})
        wrapper.updateBuildableTroves(limit=100, breakCycles=False)
        assert(wrapper.getBuildableTroves() == set([binutils_nocross,
                                                    gcc_nocross]))
        # TODO - add some trove that's not being bootstrapped (needs
        # different flavor, requires allowing multiple flavors in the same
        # job.)

    def testDependencyReqOverriddenByBuildReqs(self):
        wrapper = BuildJobWrapper(self)
        a = wrapper.addBuildTrove('a', '1',
                                  buildReqs=['b:runtime'])
        b = wrapper.addBuildTrove('b', '1',
                                  buildReqs=['c:runtime'])
        c = wrapper.addBuildTrove('c', '1',
                                  buildReqs=['d:runtime'])
        self.addComponent('d:runtime', '1', requires='trove:a:runtime')
        self.addComponent('a:runtime', '1')
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([c]))

    def testPrebuiltDependencies(self):
        wrapper = BuildJobWrapper(self)
        a = wrapper.addBuildTrove('a', '1',
                                  buildReqs=['b:runtime'])
        wrapper.prepareForBuild()
        wrapper.trovePrebuilt(a)
        assert(wrapper.dh.depState.isUnbuilt(a))

    def testPackagePrebuiltButDifferentBuildReqs(self):
        wrapper = BuildJobWrapper(self)
        a = wrapper.addBuildTrove('a', '1',
                                  buildReqs=['b:runtime'])
        b = self.addComponent('b:runtime=1', filePrimer=1)
        c = self.addComponent('c:runtime=1', filePrimer=2)
        b2 = self.addComponent('b:runtime=2', requires='trove: d:runtime',
                                filePrimer=1)
        d2 = self.addComponent('d:runtime=d2', filePrimer=3)
        wrapper.prepareForBuild(update=False)
        wrapper.trovePrebuilt(a, buildReqs=[b.getNameVersionFlavor(), 
                                            c.getNameVersionFlavor()])
        assert(a.isUnbuilt())
        assert(not a.isPrebuilt())
        assert([
            '+ Could count a:source=/localhost@rpl:linux/1-1[]{} as prebuilt'
            ' - the following changes have been made in its buildreqs:',
            '+ Update  b:runtime (/localhost@rpl:linux/1-1-1'
            ' -> /localhost@rpl:linux/2-1-1)',
            '+ Erase   c:runtime=/localhost@rpl:linux/1-1-1',
            '+ Install d:runtime=/localhost@rpl:linux/d2-1-1',
            '+ ...Rebuilding'] == wrapper.logs[-5:])

    def testBuiltTwoSameNoArch(self):
        wrapper = BuildJobWrapper(self)
        a = wrapper.addBuildTrove('a', '1', 'is:x86_64')
        a2 = wrapper.addBuildTrove('a', '1', 'is:x86', context='2')
        b1 = wrapper.addBuildTrove('b', '1', 'is:x86_64', buildReqs='a:runtime')
        b2 = wrapper.addBuildTrove('b', '1', 'is:x86', context='2', buildReqs='a:runtime')
        wrapper.prepareForBuild()
        wrapper.troveBuilt(a, flavor='')
        wrapper.troveAlreadyBuilt(a2)
        assert(a2.isDuplicate())
        wrapper.updateBuildableTroves(2)
        assert(wrapper.getBuildableTroves() == set([b1, b2]))

    def testBuiltTwoSameNoArchDifferentComponents(self):
        wrapper = BuildJobWrapper(self)
        a = wrapper.addBuildTrove('a', '1')
        a2 = wrapper.addBuildTrove('a', '1', context='2')
        wrapper.prepareForBuild()
        wrapper.troveBuilt(a)
        wrapper.troveAlreadyBuilt(a2, components=[':data'])
        assert(a2.isFailed())

    def testBuildReqCycleResolvesInWrongOrder(self):
        # round 1: a is unbuildable (has hard dependency on b)
        # round 1: b is buildable
        # round 2: a is buildable
        # round 3: c is buildange
        wrapper = BuildJobWrapper(self)
        self.addComponent('c:runtime')
        a = wrapper.addBuildTrove('a', '1', buildReqs=['b:runtime',
                                                       'c:runtime'])
        b = wrapper.addBuildTrove('b', '1', buildReqs='c:runtime')
        c = wrapper.addBuildTrove('c', '1', buildReqs=['a:runtime',
                                                       'd:runtime'])
        d = wrapper.addBuildTrove('d', '1', buildReqs='a:runtime')
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set())
        assert(a.getStateName() == 'Initialized')
        assert(a.status == 'Trove in cycle could not resolve build requirements: b:runtime')
        assert(wrapper.dh.depState.hasHardDependency(a))
        wrapper.updateBuildableTroves(limit=1)
        assert(wrapper.getBuildableTroves() == set())
        assert(wrapper.dh.depState.hasHardDependency(c))
        wrapper.updateBuildableTroves(limit=1)
        assert(wrapper.getBuildableTroves() == set([b]))
        wrapper.troveBuilt(b)
        assert(not wrapper.dh.depState.hasHardDependency(a))
        assert(wrapper.getBuildableTroves() == set([a]))
        wrapper.troveBuilt(a)
        assert(wrapper.getBuildableTroves() == set([d]))
        wrapper.troveBuilt(d)
        assert(wrapper.getBuildableTroves() == set([c]))

    def testCycleMissingTroveDependencyChangesOrder(self):
        # a has a hard dep on c because b has a missing dependency on 
        # c.
        wrapper = BuildJobWrapper(self)
        self.addComponent('b:runtime', requires='trove: c:runtime')
        a = wrapper.addBuildTrove('a', '1', buildReqs=['b:runtime'])
        b = wrapper.addBuildTrove('b', '1', buildReqs='c:runtime')
        c = wrapper.addBuildTrove('c', '1', buildReqs=['a:runtime'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set())
        wrapper.updateBuildableTroves()
        assert(a.getStateName() == 'Initialized')
        assert(a.status == "Trove could not resolve dependencies, waiting until troves are built: [(('b:runtime', VFS('/localhost@rpl:linux/1.0-1-1'), Flavor('')), ThawDep('4#c::runtime'))]")
        assert(wrapper.dh.depState.hasHardDependency(a))

    def testMissingTroveDependencyChangesOrder(self):
        wrapper = BuildJobWrapper(self)
        self.addComponent('b:runtime', requires='trove: c:runtime')
        a = wrapper.addBuildTrove('a', '1', buildReqs=['b:runtime'])
        c = wrapper.addBuildTrove('c', '1')
        wrapper.prepareForBuild(update=False)
        assert(wrapper.getBuildableTroves() == set())
        # before we try to update, we don't know that a requires c
        assert(not list(wrapper.dh.depState.getTrovesRequiringTrove(c)))
        wrapper.updateBuildableTroves()
        # after an attempt to resolve, we add a dependency
        assert(wrapper.getBuildableTroves() == set())
        assert(list(wrapper.dh.depState.getTrovesRequiringTrove(c))[0][0] == a)
        assert(a.status == "Trove could not resolve dependencies, waiting until troves are built: [(('b:runtime', VFS('/localhost@rpl:linux/1.0-1-1'), Flavor('')), ThawDep('4#c::runtime'))]")

    def testTwoCycles(self):
        wrapper = BuildJobWrapper(self, resolveTrovesOnly=True)
        wrapper.addResolveTrove('b', '1')
        wrapper.addResolveTrove('d', '1')
        a = wrapper.addBuildTrove('a', '1', buildReqs=['b:runtime'])
        b = wrapper.addBuildTrove('b', '1', buildReqs=['a:runtime'])
        c = wrapper.addBuildTrove('c', '1', buildReqs=['d:runtime'])
        d = wrapper.addBuildTrove('d', '1', buildReqs=['c:runtime'])
        wrapper.prepareForBuild()
        wrapper.updateBuildableTroves()
        assert(wrapper.getBuildableTroves() == set([a,c]))

    def testDependencyResolutionSelectsFromResolutionTrove(self):
        wrapper = BuildJobWrapper(self, resolveTrovesOnly=True)
        wrapper.cfg.flavor = [ deps.parseFlavor('is:x86 x86_64') ]
        wrapper.cfg.flavorPreferences = [ deps.parseFlavor('is:x86_64'),
                                          deps.parseFlavor('is:x86') ]
        self.cfg.flavorPreferences = wrapper.cfg.flavorPreferences
        aRes = wrapper.addResolveTrove('a', '1', 'is:x86_64')
        bRes = wrapper.addResolveTrove('b', '1', 'is:x86_64',
                                       requires='trove:a:runtime')
        a = wrapper.addBuildTrove('a', '1')
        b = wrapper.addBuildTrove('b', '1', buildReqs=['a:runtime'])
        c = wrapper.addBuildTrove('c', '1', buildReqs=['b:runtime'])
        wrapper.prepareForBuild()
        assert(wrapper.getBuildableTroves() == set([a]))
        wrapper.troveBuilt(a, flavor='is:x86')

        assert(wrapper.getBuildableTroves() == set([b]))
        buildReq, = wrapper.getBuildReqTroves(b, 'a:runtime')
        # make sure we used the better match - the x86_64 trove,
        # even though there's an x86 prebuilt.
        assert(buildReq[2][0] == aRes.getVersion())
        wrapper.troveBuilt(b, flavor='is:x86', requires='trove:a:runtime')

        assert(wrapper.getBuildableTroves() == set([c]))
        buildReq, = wrapper.getBuildReqTroves(c, 'b:runtime')
        assert(buildReq[2][0] == bRes.getVersion())
        buildReq, = wrapper.getBuildReqTroves(c, 'a:runtime')
        assert(buildReq[2][0] == aRes.getVersion())

    def testDependencyResolutionPicksBadTrove(self):
        if 'x86_64' in str(self.getArchFlavor()):
            raise testhelp.SkipTestException('this test doesnt work on x86_64')
        wrapper = BuildJobWrapper(self, resolveTrovesOnly=True)
        wrapper.cfg.configLine('[x86_64]')
        wrapper.cfg.configLine('flavor is:x86 x86_64')
        wrapper.cfg.configLine('installLabelPath localhost@rpl:linux')
        wrapper.cfg.configLine('[x86]')
        wrapper.cfg.configLine('flavor is:x86')
        wrapper.cfg.configLine('installLabelPath localhost@rpl:linux')
        wrapper.cfg._sections['x86_64'].flavorPreferences = [
                                          deps.parseFlavor('is:x86_64'),
                                          deps.parseFlavor('is:x86') ]
        wrapper.addContext('x86')
        wrapper.addContext('x86_64')

        trovesByContext = {}
        for context in ('x86', 'x86_64'):
            wrapper.addResolveTrove('a', '1', 'is:' + context, context=context)
            d = trovesByContext[context] = {}
            flavor = context
            if context == 'x86_64':
                flavor = 'x86 x86_64'
            flavor = 'is:' + flavor
            d['a'] = wrapper.addBuildTrove('a', '1', flavor,
                                        buildReqs=['b:runtime'],
                                        context=context)
            d['b'] = wrapper.addBuildTrove('b', '1', flavor, 
                                      buildReqs=['a:runtime'],
                                      context=context)
            d['c'] = wrapper.addBuildTrove('c', '1', flavor,
                                          context=context)

            d['d'] = wrapper.addBuildTrove('d', '1', flavor,
                                      buildReqs=['c:runtime'],
                                      context=context)
        wrapper.prepareForBuild()
        d = trovesByContext['x86']
        a_x86, b_x86, c_x86, d_x86 = d['a'], d['b'], d['c'], d['d']
        d = trovesByContext['x86_64']
        a_x86_64, b_x86_64, c_x86_64, d_x86_64 = d['a'], d['b'], d['c'], d['d']
        wrapper.updateBuildableTroves(6)
        assert(wrapper.getBuildableTroves() == set([b_x86, b_x86_64, 
                                                    c_x86, c_x86_64]))
        wrapper.troveBuilt(b_x86)
        wrapper.troveBuilt(c_x86_64, requires='trove:b:runtime')
        # note that even though there's a b:runtime that could be used to
        # resolve c's requirement, it's the wrong flavor, being an x86 package
        # when there's an x86_64 package available.
        assert(wrapper.getBuildableTroves() == set([a_x86, b_x86_64, c_x86]))

    def testCycleDependsOnPackageOutsideOfCycle(self):
        raise testhelp.SkipTestException('not fixed yet')
        wrapper = BuildJobWrapper(self)
        a = wrapper.addBuildTrove('a', '1', buildReqs='b:runtime')
        b = wrapper.addBuildTrove('b', '1', buildReqs=['a:runtime',
                                                       'c:runtime'])
        c = wrapper.addBuildTrove('c', '1', buildReqs=['a:runtime',
                                                       'b:runtime'])
        d = wrapper.addBuildTrove('d', '1', buildReqs=['c:runtime'])
        wrapper.addResolveTrove('b', '1')
        wrapper.addResolveTrove('c', '1')
        wrapper.prepareForBuild()
        wrapper.updateBuildableTroves(5)
        assert(wrapper.getBuildableTroves() == set([a]))
        wrapper.troveBuilt(a, requires='soname: ELF32/d.so.1(SysV)')
        wrapper.updateBuildableTroves(5)
        assert(wrapper.getBuildableTroves() == set([d]))

    def testBadCrossTrove(self):
        wrapper = BuildJobWrapper(self)
        a = wrapper.addBuildTrove('a', '1', crossReqs='b:runtime')
        b = wrapper.addBuildTrove('b', '1')
        try:
            wrapper.prepareForBuild()
            assert(0)
        except Exception, err:
            assert(str(err) == 'Error adding buildreqs to a:source: AssertionError: ')
            assert(a.isFailed())

    def testDepLoopWithBuildReqWithNoFlavor(self):
        wrapper = BuildJobWrapper(self)
        wrapper.addResolveTrove('a', '1', 'ssl')
        wrapper.addResolveTrove('b', '1', 'ssl')
        wrapper.addBuildTrove('a', '1', 'is:x86', buildReqs='b:runtime')
        wrapper.addBuildTrove('b', '1', 'is:x86', buildReqs='a:runtime')
        wrapper.prepareForBuild(update=False)
        wrapper.updateBuildableTroves(1)
        assert(wrapper.getBuildableTroves())

    def testDepLoopExits(self):
        wrapper = BuildJobWrapper(self)
        wrapper.addResolveTrove('a', '1', 'ssl', requires='trove:c:runtime')
        wrapper.addResolveTrove('b', '1', 'ssl', requires='trove:c:runtime')
        a = wrapper.addBuildTrove('a', '1', 'is:x86', buildReqs='b:runtime')
        b = wrapper.addBuildTrove('b', '1', 'is:x86', buildReqs='a:runtime')
        b = wrapper.addBuildTrove('c', '1', 'is:x86', buildReqs='a:runtime')
        wrapper.prepareForBuild(update=False)
        assert(wrapper.updateBuildableTroves(1))
        assert(wrapper.dh.moreToDo())
        assert(wrapper.updateBuildableTroves(1))
        assert(wrapper.updateBuildableTroves(1))
        assert(not wrapper.dh.moreToDo())
        assert(a.isFailed())
        assert(b.isFailed())

    def testDepLoopPullsInPackage(self):
        wrapper = BuildJobWrapper(self)
        wrapper.addResolveTrove('conary', '1',
                                requires=('trove:conary-policy:runtime'
                                          ' trove:pycrypto:runtime'))
        wrapper.addResolveTrove('conary-policy', '1')
        wrapper.addResolveTrove('pycrypto', '1')
        wrapper.addResolveTrove('gcc', '1')

        php = wrapper.addBuildTrove('pycrypto', '1', 'is:x86',
                                     buildReqs=['conary:runtime', 
                                                'gcc:runtime'])
        php = wrapper.addBuildTrove('php', '1', 'is:x86',
                                  buildReqs=['httpd:runtime', 'conary:runtime', 
                                             'gcc:runtime'])
        httpd = wrapper.addBuildTrove('httpd', '1', 'is:x86',
                                      buildReqs=['conary:runtime'])
        sendmail = wrapper.addBuildTrove('sendmail', '1', 'is:x86',
                                         buildReqs=['conary:runtime'])
        cp = wrapper.addBuildTrove('conary-policy',
                              buildReqs=['conary:runtime'])
        con = wrapper.addBuildTrove('conary', buildReqs=['conary:runtime'])
        gcc = wrapper.addBuildTrove('gcc', buildReqs=['conary:runtime',
                                                # really gcc ->
                                                # gtk -> cups -> php
                                                'php:runtime'])
        wrapper.prepareForBuild(update=False)
        wrapper.troveBuilt(httpd, requires='trove:sendmail:runtime', 
                           update=False)
        wrapper.troveBuilt(con,
                requires='trove:pycrypto:runtime trove:conary-policy:runtime',
                update=False)
        wrapper.updateBuildableTroves(5)
        assert(not php.isFailed())

    def testBuildEndsWhenTroveHasMissingSonameDep(self):
        wrapper = BuildJobWrapper(self)
        self.addComponent('foo:runtime',
                          requires='soname: ELF32/bar.so.1(SysV)')
        b = wrapper.addBuildTrove('tobuild', buildReqs=['foo:runtime'])
        wrapper.prepareForBuild(update=False)
        wrapper.updateBuildableTroves(5)
        assert(not wrapper.dh.moreToDo())

    def testFastRestart(self):
        #raise testsuite.SkipTestException('RMK-620 - fast restart broken')
        # when resolveTrovesOnly is used and the resolveTroves used haven't
        # changed, we can speed up the restart checks.
        # However, fast resolution ends if 
        # 1. any trove goes through the resolution process and is not marked
        # as prebuilt
        # 2. we run out prebuilt packages
        aRun = self.addComponent('a:runtime=1')
        wrapper = BuildJobWrapper(self, resolveTrovesOnly=True)
        prebuiltA = wrapper.addResolveTrove('a', '2')
        a = wrapper.addBuildTrove('a', '1')
        b = wrapper.addBuildTrove('b', '1', buildReqs=['a:runtime'])
        wrapper.prepareForBuild(update=False)
        wrapper.trovePrebuilt(a, allowFastResolution=True, update=False)
        assert(not wrapper.updateBuildableTroves())
        assert(a.isBuilt())

    def testFastRestart2(self):
        # make sure we don't mark things as rebuild when really they cannot be.
        # job one: straight ling building.
        wrapper = BuildJobWrapper(self)
        gp = wrapper.addBuildTrove('gnome-python',
                                   buildReqs=['eel:source'])
        gm = wrapper.addBuildTrove('gnome-menus',
                                   buildReqs=['gnome-python:runtime'])
        e = wrapper.addBuildTrove('eel',
                                  buildReqs=['gnome-python:runtime'])
        gpRun = self.addComponent('gp:runtime', '1')
        gpBuilt = self.addCollection('gp', '1', [':runtime'])

        wrapper.prepareForBuild(update=False)
        gmBuilt = wrapper.trovePrebuilt(gm, allowFastResolution=True,
                                        update=False, builtTime=2,
                                    buildReqs=[gpBuilt])
        eelBuilt = wrapper.trovePrebuilt(e, allowFastResolution=True,
                                    update=False, builtTime=3,
                                    buildReqs=[gmBuilt])
        wrapper.updateBuildableTroves(limit=1)
        assert(not e.isBuilt())

    def testFastRestart3(self):
        # make sure we don't mark things as rebuild when really they cannot be.
        # job one: straight ling building.
        wrapper = BuildJobWrapper(self)
        a = self.addComponent('a:runtime', '1')
        aBuilt = self.addCollection('a', '1', [':runtime'])
        a = wrapper.addBuildTrove('a')
        bBuilt = wrapper.addResolveTrove('b', '1', requires='trove:a:runtime')
        c = wrapper.addBuildTrove('c', buildReqs=['b:runtime'])
        wrapper.prepareForBuild(update=False)
        cRun = wrapper.trovePrebuilt(c, allowFastResolution=True,
                                     update=False, builtTime=2,
                                     buildReqs=[bBuilt, aBuilt])
        wrapper.updateBuildableTroves(limit=1)
        assert(not c.isBuilt())


    def testLoadedSpecsRespectArch(self):
        # RMK-631 - loadInstalled deps were not respecting architecture
        wrapper = BuildJobWrapper(self)
        a1 = wrapper.addBuildTrove('a', flavor='is:x86')
        a2 = wrapper.addBuildTrove('a', flavor='is:x86_64')
        b1 = wrapper.addBuildTrove('b', flavor='is:x86', loadedSpecs={'a' : (a1.getNameVersionFlavor(), {})} )
        b2 = wrapper.addBuildTrove('b', flavor='is:x86_64', loadedSpecs={'a' : (a2.getNameVersionFlavor(), {})} )
        wrapper.prepareForBuild(update=False)
        g =  wrapper.dh.depState.depGraph
        assert(g.getChildren(b1) == [a1])
        assert(g.getChildren(b2) == [a2])

    def testIgnoreExternalRebuildDeps1(self):
        wrapper = BuildJobWrapper(self)
        wrapper.cfg.ignoreExternalRebuildDeps = True
        aBuilt1 = self.addCollection('a=1', [':runtime'])
        aBuilt2 = wrapper.addResolveTrove('a', '2')
        bBuilt1 = wrapper.addResolveTrove('b', '1')
        b = wrapper.addBuildTrove('b', '2', buildReqs=['a:runtime'])
        c = wrapper.addBuildTrove('c', '1', buildReqs=['b:runtime'])
        wrapper.prepareForBuild(update=False)
        bBuilt2 = wrapper.trovePrebuilt(b, buildReqs=[aBuilt1])
        cBuilt1 = wrapper.trovePrebuilt(c, buildReqs=[bBuilt1])
        wrapper.updateBuildableTroves(limit=1)
        assert(b.isBuilt())
        # c should be marked as built because although it finds
        # b as a buildreq from the job, which is different than
        # what was used previously, b is not being rebuilt.
        wrapper.updateBuildableTroves(limit=1)
        assert(c.isBuilt())

    def testIgnoreExternalRebuildDeps2(self):
        # make sure that if an internal buildreq changed
        # we also rebuild a package.
        wrapper = BuildJobWrapper(self)
        wrapper.cfg.ignoreExternalRebuildDeps = True
        aBuilt1 = self.addCollection('a=1', [':runtime'])
        aBuilt2 = wrapper.addResolveTrove('a', '2')
        bBuilt2 = wrapper.addResolveTrove('b', '1')
        b = wrapper.addBuildTrove('b', '2', buildReqs=['a:runtime'])
        c = wrapper.addBuildTrove('c', '1', buildReqs=['b:runtime'])
        wrapper.prepareForBuild(update=False)
        cBuilt1 = wrapper.trovePrebuilt(c, buildReqs=[bBuilt2])
        wrapper.updateBuildableTroves(limit=1)
        assert(wrapper.getBuildableTroves() == set([b]))
        wrapper.troveBuilt(b)
        wrapper.updateBuildableTroves(limit=1)
        assert(wrapper.getBuildableTroves() == set([c]))

    def testIgnoreAllRebuildDeps(self):
        wrapper = BuildJobWrapper(self)
        wrapper.cfg.ignoreAllRebuildDeps = True
        aBuilt1 = self.addCollection('a=1', [':runtime'])
        aBuilt2 = wrapper.addResolveTrove('a', '2')
        bBuilt2 = wrapper.addResolveTrove('b', '1')
        b = wrapper.addBuildTrove('b', '2', buildReqs=['a:runtime'])
        c = wrapper.addBuildTrove('c', '1', buildReqs=['b:runtime'])
        wrapper.prepareForBuild(update=False)
        cBuilt1 = wrapper.trovePrebuilt(c, buildReqs=[bBuilt2])
        wrapper.updateBuildableTroves(limit=1)
        assert(wrapper.getBuildableTroves() == set([b]))
        wrapper.troveBuilt(b)
        wrapper.updateBuildableTroves(limit=1)
        assert(c.isBuilt())
