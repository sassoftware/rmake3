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


import os
import sys

#conary
from conary.deps import deps
from conary import versions
from conary.versions import VersionFromString as VFS

from rmake.lib import recipeutil

#test
from rmake_test import rmakehelp
from conary_test import recipes
from rmake_test import fixtures

class RecipeUtilTest(rmakehelp.RmakeHelper):

    def testPrimaryFlavorComesThrough(self):
        # we specified this flavor at the command line.  Even though 
        # it may not be needed for display, it's needed to ensure that the
        # flavor gets cooked in the right environ.
        trv = self.addComponent('simple:source', '1', 
                                [('simple.recipe', recipes.simpleRecipe)])
        flavor = deps.parseFlavor('!ssl,readline')
        repos = self.openRepository()
        job = self.newJob((trv.getName(), trv.getVersion(), flavor))
        results = recipeutil.getSourceTrovesFromJob(job, repos=repos,
            reposName=self.rmakeCfg.reposName)
        self.failUnless(results.values()[0].flavor.stronglySatisfies(
            deps.parseFlavor('readline,!ssl')))

    def testLoadInstalledInRoot(self):
        # make sure that we find this autoconf213 trove even though it's
        # been built.  (RMK-371)
        self.openRepository()
        repos = self.openRmakeRepository()

        sourceV = VFS('/localhost@rpl:1//autoconf213/2.13-1.1')
        binV = sourceV.createShadow(versions.Label('rmakehost@rpl:1'))
        binV.incrementBuildCount()

        loadInstalledRecipe = fixtures.loadInstalledRecipe.replace(
                                "loadInstalled('loaded')",
                                "loadInstalled('loaded=:autoconf213')")
        self.addComponent('loaded:runtime', str(binV))
        trv = self.addCollection('loaded', str(binV), [':runtime'])
        self.updatePkg('loaded=rmakehost@rpl:1')
        self.addComponent('loaded:source', str(sourceV),
                          [('loaded.recipe',
                            fixtures.loadedRecipe.replace('@@', '2.13'))])
        trv = self.addComponent('loadinstalled:source', '1',
                          [('loadinstalled.recipe', loadInstalledRecipe)])
        n,v,f = trv.getNameVersionFlavor()

        db = self.openDatabase()
        source = recipeutil.RemoveHostSource(db, 'rmakehost')
        (loader, recipeClass, localFlags, usedFlags) = \
            recipeutil.loadRecipeClass(repos, n, v, f,
                                       ignoreInstalled=False, 
                                       root=self.cfg.root,
                                       loadInstalledSource=source)
        assert(recipeClass.loadedVersion == '2.13')

    def testLoadRecipeUsingInternalRepos(self):
        self.openRepository()
        repos = self.openRmakeRepository()

        upstreamV = VFS('/localhost@rpl:1/1.0-1')
        sourceV = VFS('/localhost@rpl:1//rmakehost@rpl:1/1.0-1')

        self.addComponent('loaded:source', str(sourceV),
                          [('loaded.recipe', 
                            fixtures.loadedRecipe.replace('@@', '1.0'))])
        self.addComponent('loaded:source', str(upstreamV).replace('1.0', '2.0'),
                          [('loaded.recipe', 
                            fixtures.loadedRecipe.replace('@@', '2.0'))])
        trv = self.addComponent('load:source', str(sourceV),
                          [('load.recipe', fixtures.loadRecipe)])
        job = self.newJob(trv)
        results = recipeutil.getSourceTrovesFromJob(job, repos=repos)
        self.assertEqual(results.values()[0].packages,
            set(['load', 'loaded-2.0']))

    def testLoadFactoryRecipe(self):
        import conary.build.factory
        if not hasattr(conary.build.factory, 'generateFactoryRecipe'):
            raise testsuite.SkipTestException('Cooking Factories requires a newer conary')
        trv = self.addComponent('factory-simple:source', '1',
                                [('factory-simple.recipe',
                                recipes.simpleFactory)], factory="factory")
        repos = self.openRepository()
        job = self.newJob((trv.getName(), trv.getVersion(), trv.getFlavor()))
        results = recipeutil.getSourceTrovesFromJob(job, repos=repos,
            reposName=self.rmakeCfg.reposName)
        self.failUnless('setup:runtime'
            in results.values()[0].buildRequirements, 
            "Build Requirements were not loaded.")
