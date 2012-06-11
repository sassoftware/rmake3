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
