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


from conary_test import rephelp

import tempfile

# conary
from conary.lib import util

#rmake
from rmake.lib import pluginlib

#test

class PluginTest(rephelp.RepositoryHelper):
    def testPluginLoading(self):
        d = tempfile.mkdtemp(prefix='rmake-plugintest')
        d2 = tempfile.mkdtemp(prefix='rmake-plugintest2')
        try:
            self.writeFile(d + '/fail.py', failedPlugin)
            self.writeFile(d + '/pass.py', plugin1)
            # this second pass.py is later on the directory list and 
            # so should get skipped.
            self.writeFile(d2 + '/pass.py', failedPlugin)
            self.writeFile(d2 + '/toomany.py', tooManyPlugins)
            self.writeFile(d + '/.backup', 'badplugincontents')
            compDir = d2 + '/comp'
            util.mkdirChain(compDir)
            self.writeFile(compDir + '/__init__.py',
                           complicatedPlugin)
            self.writeFile(compDir + '/part1.py',
                           complicatedPlugin_part1)
            self.writeFile(compDir + '/part2.py',
                           complicatedPlugin_part2)

            mgr = pluginlib.PluginManager([d, d2,
                                           d2 + 'somedirthatdoesntexist'])
            self.logFilter.add()
            mgr.loadPlugins()
            assert(len(self.logFilter.records) == 2)
            self.logFilter.records.sort()
            expected = [
                "warning: Failed to import plugin %s/fail.py: "
                    "name 'b' is not defined" % d,
                "warning: Failed to import plugin %s/toomany.py: "
                    "Can only define one plugin in a plugin module" % d2,
            ]
            expected.sort()
            for record, exp in zip(self.logFilter.records, expected):
                assert record.startswith(exp), "%s does not start with %s" % (
                    record, exp)
            # call function foo for all hooks
            # call function foo for all hooks
            rc, txt = self.captureOutput(mgr.callHook, 'all', 'foo')
            rc, txt2 = self.captureOutput(mgr.callHook, 'all', 'foo')
            assert(txt == 'comp: 1\nblah: 1\n')
            assert(txt2 == 'comp: 2\nblah: 2\n')
            mgr.unloadPlugin('comp')
            rc, txt3 = self.captureOutput(mgr.callHook, 'all', 'foo')
            assert(txt3 == 'blah: 3\n')
        finally:
            util.rmtree(d)
            util.rmtree(d2)

#####################
# Plugins
###################

failedPlugin = """
from rmake.lib import pluginlib
class FailedPlugin(pluginlib.Plugin):
    a = b
"""

tooManyPlugins = """
from rmake.lib import pluginlib
class TooManyPlugins(pluginlib.Plugin):
    def foo(self):
        pass

class TooManyPlugins2(pluginlib.Plugin):
    def foo(self):
        pass
"""

plugin1 = """
# try some other imports
import os
from xml.dom import NodeFilter
from rmake.lib import pluginlib

class BlahPlugin(pluginlib.Plugin):
    count = 0
    def foo(self):
        self.count += 1
        print 'blah: %s' % self.count
"""

complicatedPlugin = """
from rmake.lib import pluginlib
from __plugins__.comp import part1
import conary
# double import, should find the module in sys.modules
from __plugins__.comp.part1 import foo
class CompPlugin(pluginlib.Plugin):
    def foo(self):
        part1.foo()
"""

complicatedPlugin_part1 = """
from rmake.lib import pluginlib
def foo():
    from __plugins__.comp.part2 import bar
    return bar()
"""

complicatedPlugin_part2 = """
from rmake.lib import pluginlib
count = 0
def bar():
    global count
    count += 1
    print 'comp: %s' % count
"""
