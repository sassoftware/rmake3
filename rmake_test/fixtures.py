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

from conary.deps.deps import parseFlavor
from conary import conaryclient
from conary import versions

from rmake.cmdline import buildcmd
from rmake.lib import recipeutil

def addBuildReq(self):
    buildReqRun = self.addComponent('buildreq:runtime', '1', ['/buildreq'])
    buildReq = self.addCollection('buildreq', '1', [':runtime'])
    return buildReq, buildReqRun

def addTestCase1(self):
    buildReq, buildReqRun = addBuildReq(self)
    trv = self.addComponent('testcase:source', '1', '',
                [('testcase.recipe', workingRecipe % {'root' : self.rootDir})])

    v = trv.getVersion().copy()
    v = v.createShadow(versions.Label('rmakehost@local:linux'))
    v.incrementBuildCount()
    builtComp = self.addComponent('testcase:runtime', v, 'ssl')
    builtColl = self.addCollection('testcase', v, [':runtime'], 
                                   buildReqs=[buildReqRun, buildReq],
                                   defaultFlavor='ssl')
    return trv, builtComp, builtColl, buildReq

def addTestCase2(self):
    trv = self.addComponent('testcase2:source', '1', '',
                [('testcase2.recipe', workingRecipe2 % {'name' : 'testcase2'})])
    v = trv.getVersion().copy()
    v = v.createShadow(versions.Label('rmakehost@local:linux'))
    v.incrementBuildCount()

    builtComp = self.addComponent('testcase2:runtime', v, filePrimer=3)
    builtColl = self.addCollection('testcase2', v, [':runtime'])
    return trv, builtComp, builtColl

def addTestCase2Branch2(self, fail=False):
    trv = self.addComponent('testcase2:source', ':branch2/1', '',
                [('testcase2.recipe', workingRecipe2 % {'name' : 'testcase2'})])
    v = trv.getVersion().copy()
    v = v.createShadow(versions.Label('rmakehost@local:linux'))
    v.incrementBuildCount()

    if not fail:
        builtComp = self.addComponent('testcase2:runtime', v, filePrimer=3)
        builtColl = self.addCollection('testcase2', v, [':runtime'])
        return trv, builtComp, builtColl
    return trv

def addTestCase3(self, version='1'):
    trv = self.addComponent('testcase3:source', version, '',
                [('testcase3.recipe', workingRecipe2 % {'name' : 'testcase3'})])

    v = trv.getVersion().copy()
    v = v.createShadow(versions.Label('rmakehost@local:linux'))
    v.incrementBuildCount()
    builtComp = self.addComponent('testcase3:runtime', v)
    builtComp2 = self.addComponent('testcase3-pkg:runtime', v, 
                                    sourceName='testcase3:source')
    builtColl = self.addCollection('testcase3', v, [':runtime'])
    builtColl2 = self.addCollection('testcase3-pkg', v, [':runtime'],
                                    sourceName='testcase3:source')
    return trv, [builtComp, builtComp2], [builtColl, builtColl2]

def addBuiltJob1(self):
    self.openRepository()
    trv, builtComp, builtColl, buildReq = addTestCase1(self)

    buildConfig = copy.deepcopy(self.buildCfg)
    buildConfig.resolveTroves = [[(buildReq.getName(), None, None)]]

    job = _buildJob(self, buildConfig,
                    [('testcase', None, parseFlavor('ssl'))],
                     {'testcase' : [builtColl, builtComp]})
    return job.jobId

def updateBuiltJob1(self):
    self.addComponent('testcase:source', '2',
        [('testcase.recipe',
            workingRecipe % {'root' : self.rootDir})])

def updateBuiltJob1BuildReq(self, id='2'):
    buildReqRun = self.addComponent('buildreq:runtime', id, ['/buildreq'])
    buildReq = self.addCollection('buildreq', id, [':runtime'])
    return buildReq

def addBuiltJob2(self):
    self.openRepository()
    buildConfig = copy.deepcopy(self.buildCfg)
    trv, builtComp, builtColl = addTestCase2(self)

    job = _buildJob(self, buildConfig,
                    [('testcase2', None, parseFlavor(''))],
                    {'testcase2' : [builtColl, builtComp]})
    return job.jobId

def addFailedJob1(self):
    # one built, one failed, on different branches.
    trv, builtComp, builtColl, buildReq = addTestCase1(self)
    addTestCase2Branch2(self, fail=True)
    buildConfig = copy.deepcopy(self.buildCfg)
    job = _buildJob(self, buildConfig,
                    ['testcase2=:branch2', 'testcase'],
                    {'testcase' : [builtColl, builtComp]})
    return job.jobId

def addMultiContextJob1(self):
    trv, builtComps, builtColls = addTestCase3(self)
    trv2, builtComps2, builtColls2 = addTestCase3(self, version='1-2')
    buildConfig = copy.deepcopy(self.buildCfg)
    buildConfig.setSection('nossl')
    buildConfig.configLine('flavor !ssl')
    buildConfig.initializeFlavors()

    job = _buildJob(self, buildConfig,
                    ['testcase3=1-1', 'testcase3{nossl}'],
                    {'testcase3' : {'' : builtColls +  builtComps,
                                   'nossl' : builtColls2 + builtComps2}})
    return job.jobId


def _buildJob(self, buildConfig, buildTroveSpecs, builtMapping):
    client = conaryclient.ConaryClient(buildConfig)
    job = buildcmd.getBuildJob(buildConfig, client, buildTroveSpecs)
    db = self.openRmakeDatabase()
    db.addJob(job)
    db.subscribeToJob(job)
    loadResults = recipeutil.getSourceTrovesFromJob(job,
        repos=client.getRepos())
    for trove in job.iterLoadableTroves():
        result = loadResults.get(trove.getNameVersionFlavor(True), None)
        if result:
            trove.troveLoaded(result)
    job.setBuildTroves(list(job.iterTroves()))
    for buildTrove in job.iterTroves():
        binaries =  builtMapping.get(buildTrove.getName().split(':')[0], None)
        if isinstance(binaries, dict):
            binaries = binaries.get(buildTrove.getContext(), None)
        if binaries:
            buildTrove.troveBuilt([x.getNameVersionFlavor() for x in binaries])
        else:
            buildTrove.troveFailed('Failure')
    job.jobPassed('passed')
    return job


workingRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'testcase'
    version = '1.0'

    clearBuildReqs()
    buildRequires = ['buildreq:runtime']

    def setup(r):
        r.Run('if [ -e %(root)s/buildreq ]; then exit 1; fi')
        if Use.ssl:
            r.Create('/foo', contents='foo')
        else:
            r.Create('/bar', contents='foo')
"""

workingRecipe2 = """\
class TestRecipe(PackageRecipe):
    name = '%(name)s'
    version = '1.0'

    clearBuildReqs()

    def setup(r):
        r.Create('/%(name)s', contents='foo')
"""

loadedRecipe = """
class LoadedRecipe(PackageRecipe):
    name = 'loaded'
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
    loadedVersion = LoadedRecipe.version
    # note there's no build requirement on loaded - that needs to be added 
    # manually.
    def setup(r):
        r.Create('/asdf/foo')
        r.PackageSpec('loaded-%s' % LoadedRecipe.version, '.*')
"""

loadRecipe = """
loadSuperClass('loaded')
class LoadInstalledRecipe(PackageRecipe):
    name = 'load'
    version = '1'
    if Use.krb:
        pass

    clearBuildReqs()
    loadedVersion = LoadedRecipe.version
    # note there's no build requirement on loaded - that needs to be added 
    # manually.
    def setup(r):
        r.Create('/asdf/foo')
        r.PackageSpec('loaded-%s' % LoadedRecipe.version, '.*')
"""
