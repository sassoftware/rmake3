#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import copy
import os
import re

from rmake_test import rmakehelp

from conary import versions
from conary.deps.deps import parseFlavor

from rmake.build import builder
from rmake.lib import recipeutil
from rmake import compat

from rmake_test import fixtures

class LoadTroveTest(rmakehelp.RmakeHelper):

    def testLoadInstalledFromResolveTroves(self):
        self.addComponent('loaded:source', ':branch/1', 
                           [('loaded.recipe', 
                             loadedRecipe.replace('@@', '1'))])
        self.addComponent('loaded:runtime', ':branch/1')
        trv = self.addCollection('loaded', ':branch/1', ['loaded:runtime'])

        loadInstalled = self.addComponent('loadinstalled:source', '1',
                            [('loadinstalled.recipe', loadInstalledRecipe)])
        buildCfg = copy.deepcopy(self.buildCfg)
        buildCfg.resolveTroveTups = [[trv.getNameVersionFlavor()]]
        job = self.newJob(loadInstalled, buildConfig=buildCfg)
        b = builder.Builder(self.rmakeCfg, job)
        b.initializeBuild()
        buildTrove = job.iterTroves().next()
        assert(buildTrove.packages == set(['loadinstalled', 'loaded-1']))

    def testLoadInstalledFromBuildingTroves(self):
        # this loaded is in resolveTroveTups
        self.addComponent('loaded:runtime', ':branch/1')
        trv = self.addCollection('loaded', ':branch/1', ['loaded:runtime'])

        # we're building this one though - it wins.  
        # We also need to see a build ordering here.
        loaded = self.addComponent('loaded:source', ':branch2/2',
                          [('loaded.recipe', loadedRecipe.replace('@@', '2'))])

        loadInstalled = self.addComponent('loadinstalled:source', '1',
                            [('loadinstalled.recipe', loadInstalledRecipe)])
        buildCfg = copy.deepcopy(self.buildCfg)
        buildCfg.resolveTroveTups = [[trv.getNameVersionFlavor()]]
        job = self.newJob(loadInstalled, loaded, buildConfig=buildCfg)
        b = builder.Builder(self.rmakeCfg, job)
        b.initializeBuild()
        buildTrove = [ x for x in job.iterTroves() 
                       if x.getName() == 'loadinstalled:source'][0]
        assert(buildTrove.packages == set(['loadinstalled', 'loaded-2']))
        resolveJob = b.dh.getNextResolveJob()
        assert(resolveJob.getTrove().getName() == 'loaded:source')
        assert(not b.dh.getNextResolveJob())

    def testLoadInstalledFallsBackToInstallLabelPath(self):
        # loaded is on the ILP, but loadInstalled:source doesn't mention
        # that label at all.
        self.addComponent('loaded:source', ':branch2/1', 
                           [('loaded.recipe', 
                             loadedRecipe.replace('@@', '1'))])
        loadInstalled = self.addComponent('loadinstalled:source', ':branch/1',
                            [('loadinstalled.recipe', loadInstalledRecipe)])
        buildCfg = copy.deepcopy(self.buildCfg)
        buildCfg.resolveTroveTups = []
        buildCfg.installLabelPath.append(
                                    versions.Label('localhost@rpl:branch2'))
        job = self.newJob(loadInstalled, buildConfig=buildCfg)
        b = builder.Builder(self.rmakeCfg, job)
        b.initializeBuild()
        buildTrove = job.iterTroves().next()
        assert(buildTrove.packages == set(['loadinstalled', 'loaded-1']))

    def testLoad2LevelsDeep(self):
        myLoadedRecipe = loadedRecipe.replace('@@', '1')
        myLoadedRecipe = "loadSuperClass('loaded2')\n" + myLoadedRecipe
        loadedSrc = self.addComponent('loaded:source', ':branch/1', 
                           [('loaded.recipe', myLoadedRecipe)])
        self.addComponent('loaded:runtime', ':branch/1')
        loaded = self.addCollection('loaded', ':branch/1', ['loaded:runtime'])

        loaded2 = self.addComponent('loaded2:source', ':branch2/1', 
                          [('loaded2.recipe', loaded2Recipe)])
        loadInstalled = self.addComponent('loadinstalled:source', '1',
                            [('loadinstalled.recipe', loadInstalledRecipe)])
        buildCfg = copy.deepcopy(self.buildCfg)
        buildCfg.resolveTroveTups = [[loaded.getNameVersionFlavor(),
                                      loaded2.getNameVersionFlavor()]]
        job = self.newJob(loadInstalled, buildConfig=buildCfg)
        b = builder.Builder(self.rmakeCfg, job)
        b.initializeBuild()
        buildTrove = job.iterTroves().next()
        assert(buildTrove.packages == set(['loadinstalled', 'loaded-1']))
        assert(buildTrove.getLoadedSpecs() ==
                 dict(loaded=(loadedSrc.getNameVersionFlavor(),
                              dict(loaded2=(loaded2.getNameVersionFlavor(),
                                             {})))))
        # make sure that the correct version are loaded using loadRecipeClass
        # normally using loadRecipeClass we'd just load out of the repository
        self.addComponent('loaded:source', '1', 
                          [('loaded.recipe', myLoadedRecipe)])
        n, v, f = loadInstalled.getNameVersionFlavor()
        repos = self.openRepository()
        repos = self.openRmakeRepository()
        loader, recipeClass = recipeutil.loadRecipeClass(repos, n, v, f,
                                   overrides = buildTrove.getLoadedSpecs())[0:2]
        if hasattr(loader, 'getLoadedSpecs'):
            assert(loader.getLoadedSpecs().values()[0][0]
                    == loadedSrc.getNameVersionFlavor())
        else:
            assert(recipeClass._loadedSpecs.values()[0][0] \
                    == loadedSrc.getNameVersionFlavor())

        # test that again, except for this time, make sure that cook
        # gets the same info - cook would never find these troves
        # without having it passed in from the outside.
        job = self.newJob(loadInstalled, buildConfig=buildCfg)
        b = builder.Builder(self.rmakeCfg, job)
        txt = self.captureOutput(b.build)[1]
        assert(b.job.isBuilt())
        buildTrove = b.job.iterTroves().next()
        builtTroves = repos.getTroves([ x for x in buildTrove.getBinaryTroves()
                                        if ':' not in x[0]])
        builtTroves = dict((x.getName(), x) for x in builtTroves)
        assert(set(builtTroves['loadinstalled'].getLoadedTroves()) ==
               set([loadedSrc.getNameVersionFlavor(),
                    loaded2.getNameVersionFlavor()]))

    def testLoadSuperClassMultipleFlavors(self):
        repos = self.openRepository()
        repos = self.openRmakeRepository()
        # load the same superclass with two different flavors
        self.addComponent('group-superclass:source', '1.0', '',
                            [('group-superclass.recipe', superClass)])
        main = self.addComponent('group-main:source', '1.0', '',
                          [('group-main.recipe', mainClass)])
        self.addComponent('foo:run', '1')
        mainSsl = (main.getName(), main.getVersion(), parseFlavor('ssl'))
        mainNoSsl = (main.getName(), main.getVersion(), parseFlavor('!ssl'))
        job = self.newJob(mainSsl, mainNoSsl)
        b = builder.Builder(self.rmakeCfg, job)
        b.initializeBuild()
        txt = self.captureOutput(b.build)[1]
        assert b.job.isBuilt(), b.job.getFailureReason()


superClass = """
class SuperClass(GroupRecipe):
    name = 'group-superclass'
    version = '1.0'
    clearBuildReqs()

    if Use.ssl:
        var1 = 'ssl'
    else:
        var2 = ''
"""
mainClass = """
loadRecipe('group-superclass')
class MainPackage(SuperClass):
    name = 'group-main'
    version = '1.0'
    def setup(r):
        if Use.ssl:
            r.add('foo:run', flavor=r.var1)
        else:
            r.add('foo:run', flavor=r.var2)
"""

loadedRecipe = """
class LoadedRecipe(PackageRecipe):
    name = 'loaded'
    version = '@@'

    def setup(r):
        r.Create('/bar')
"""

loaded2Recipe = """
class Loaded2Recipe(PackageRecipe):
    name = 'loaded2'
    version = '@@'

    def setup(r):
        r.Create('/bar')
"""

loadInstalledRecipe = """
loadInstalled('loaded')
class LoadInstalledRecipe(PackageRecipe):
    name = 'loadinstalled'
    version = '1'
    if Use.krb:
        pass

    clearBuildReqs()
    # note there's no build requirement on loaded - that needs to be added 
    # manually.
    def setup(r):
        r.Create('/foo')
        r.Create('/asdf/foo')
        r.PackageSpec('loaded-%s' % LoadedRecipe.version, '/asdf/.*')
"""

groupRecipe = """

class GroupFoo(GroupRecipe):
    name = 'group-test'
    version = '1'
    clearBuildReqs()

    def setup(r):
        r.add('simple')
"""

packageRecipe = """
class PackageRecipe(packagerecipe.AbstractPackageRecipe):
    name = 'package'
    version = '1'

    abstractBaseClass = 1

    buildRequires = [
        'bzip2:runtime',
        'gzip:runtime',
        'tar:runtime',
        'cpio:runtime',
        'patch:runtime',
        ]

    def __init__(self, *args, **kwargs):
        packagerecipe.AbstractPackageRecipe.__init__(self, *args, **kwargs)
        for name, item in build.__dict__.items():
            if inspect.isclass(item) and issubclass(item, action.Action):
                self._addBuildAction(name, item)

    def setupAbstractBaseClass(r):
        r.addSource(r.name + '.recipe', dest = str(r.cfg.baseClassDir) + '/')
"""

groupTargetRecipe = """
class GroupFoo(GroupRecipe):
    name = 'group-test'
    version = '1'
    clearBuildReqs()

    assert(Arch.ppc)

    def setup(r):
        assert(Arch.ppc)
        r.add('foo:run')
"""

packageTargetRecipe = """
class PackageFoo(PackageRecipe):
    name = 'test'
    version = '1'
    clearBuildReqs()
    assert(Arch.ppc)

    def setup(r):
        assert(Arch.ppc)
        r.Create('/foo')
"""
