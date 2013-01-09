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


from conary.deps import deps

from rmake.build import builder
from rmake.build import buildjob
from rmake.lib import logfile
from rmake.lib import repocache

nocrossRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'nocross'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        if Use.cross:
            r.Create('/iscross-%(target)s', contents='foo')
        else:
            r.Create('/notcross-%(target)s', contents='foo')
        r.ComponentSpec(':devel', '.*')
"""

crosstoolRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'crosstool'
    version = '1.0'

    clearBuildReqs()
    def setup(r):
        if Use.cross:
            r.Create('/iscross-%(target)s', contents='foo')
        else:
            r.Create('/notcross-%(target)s', contents='foo')
"""

crosscompiledRecipe = """\
class TestRecipe(PackageRecipe):
    name = 'crosscompiled'
    version = '1.0'

    clearBuildReqs()
    buildRequires = ['nocross:devel', 'crosstool:runtime']

    def setup(r):
        r.Run('if [ -e %s/iscross-%%(target)s -a -e %s%%(sysroot)s/notcross-%%(target)s ] ; then touch %%(destdir)s/foo; else exit 1; fi')
"""

class CrossCompileTest(rmakehelp.RmakeHelper):

    def testBasic(self):
        trv = self.addComponent('nocross:source', '1.0-1', '',
                                [('nocross.recipe', nocrossRecipe)])
        trv2 = self.addComponent('crosstool:source', '1.0-1', '',
                                [('crosstool.recipe', crosstoolRecipe)])
        ccRoot = self.rmakeCfg.buildDir + '/chroots/crosscompiled'
        trv3 = self.addComponent('crosscompiled:source', '1.0-1', '',
                                [('crosscompiled.recipe', crosscompiledRecipe % (ccRoot, ccRoot))])
        self.openRmakeRepository()

        troveList = [
                (trv.getName(), trv.getVersion(), 
                 deps.parseFlavor('!cross target: x86_64')),
                (trv2.getName(), trv2.getVersion(), 
                 deps.parseFlavor('cross target: x86_64')),
                (trv3.getName(), trv3.getVersion(),
                 deps.parseFlavor('!cross target: x86_64')) ]
        db = self.openRmakeDatabase()
        self.buildCfg.flavor = [deps.overrideFlavor(self.buildCfg.flavor[0], deps.parseFlavor('~cross is:x86 target:x86_64'))]
        job = self.newJob(*troveList)
        db.subscribeToJob(job)
        b = builder.Builder(self.rmakeCfg, job)
        self.logFilter.add()
        logFile = logfile.LogFile(self.workDir + '/buildlog')
        logFile.redirectOutput()
        try:
            b.build()
        except Exception:
            b.worker.stopAllCommands()
            raise
        logFile.restoreOutput()

        assert(set([x.getName() for x in b.dh.depState.getBuiltTroves()])
               == set([trv.getName(), trv2.getName(), trv3.getName()]))
