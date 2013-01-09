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


from StringIO import StringIO
import os

from rmake_test import rmakehelp

from conary import conarycfg
from conary.deps import deps

from rmake.build import buildcfg
from rmake.lib import apiutils


class BuildCfgTest(rmakehelp.RmakeHelper):

    def testFreeze(self):
        cfg = buildcfg.BuildConfiguration(readConfigFiles=False)
        os.environ['HOME'] = self.workDir
        cfg.configLine('policyDirs ~/policy')
        newCfg = apiutils.thaw('BuildConfiguration',
                               apiutils.freeze('BuildConfiguration', cfg))
        assert(newCfg.policyDirs[0]._getUnexpanded() == self.workDir + '/policy')


    def testTroveSpec(self):
        cfg = buildcfg.BuildConfiguration(readConfigFiles=False)
        cfg.configLine('resolveTroves group-dist=1.0[!krb]')
        cfg.configLine('resolveTroves group-foo=2.0')
        cfg.configLine('resolveTroves group-foo[k]')
        assert(cfg.resolveTroves == [
                        [('group-dist', '1.0', deps.parseFlavor('!krb'))],
                        [('group-foo', '2.0', None)],
                        [('group-foo', None, deps.parseFlavor('k'))]])
        out = StringIO()
        cfg.displayKey('resolveTroves', out)
        assert(out.getvalue() ==
                    'resolveTroves             \'group-dist=1.0[!krb]\'\n'
                    'resolveTroves             \'group-foo=2.0\'\n'
                    'resolveTroves             \'group-foo[k]\'\n')
        cfg = cfg.__thaw__(cfg.__freeze__())
        assert(cfg.resolveTroves == [
                        [('group-dist', '1.0', deps.parseFlavor('!krb'))],
                        [('group-foo', '2.0', None)],
                        [('group-foo', None, deps.parseFlavor('k'))]])

    def testSubscribe(self):
        cfg = buildcfg.BuildConfiguration(readConfigFiles=False)
        cfg.configLine('subscribe dbcMail mailto dbc@rpath.com')
        cfg.configLine('subscribe dbcMail toName David Christian')
        cfg.configLine('subscribe rBuilder xmlrpc http://rbuilder.rpath.com/')
        cfg.resolveTroves = []

        def _test(cfg):
            s = cfg.subscribe['dbcMail']
            assert(s['toName'] == 'David Christian')
            assert(s.uri == 'dbc@rpath.com')
            s = cfg.subscribe['rBuilder']
            assert(s.uri == 'http://rbuilder.rpath.com/')
            assert(cfg.resolveTroves == [])
        _test(cfg)
        _test(cfg.__thaw__(cfg.__freeze__()))

    def testUUID(self):
        cfg = buildcfg.BuildConfiguration(readConfigFiles=False)
        cfg.configLine('uuid 2630b2e0-f724-11da-974d-0800200c9a66')
        assert(cfg.uuid == '2630b2e0f72411da974d0800200c9a66')
        self.assertRaises(buildcfg.ParseError, cfg.configLine, 
                          'uuid 2630b2e0-f724-11da-974d-0800200c9a666')
        self.assertRaises(buildcfg.ParseError, cfg.configLine, 
                          'uuid 2630b2e0-f724-11da-974d-0800200c9a6k')
        cfg.configLine('uuid ')
        assert(cfg.uuid == '')

    def testOverrideFromConaryConfig(self):
        cfg = buildcfg.BuildConfiguration(readConfigFiles=False)
        cfg.strictMode = False
        cfg.copyInConfig = True
        cfg.configLine('buildLabel foo.rpath.org@rpl:devel')
        cfg.configLine('flavor foo')
        cfg.useConaryConfig(self.cfg)
        assert(cfg.installLabelPath == self.cfg.installLabelPath)
        assert(str(cfg.buildLabel) == 'foo.rpath.org@rpl:devel')
        assert(str(cfg.flavor[0]) == 'foo')
        cfg.initializeFlavors()
        assert(cfg.flavor[0] == deps.overrideFlavor(self.cfg.flavor[0],
                                                    deps.parseFlavor('foo')))

    def testOverrideFromConaryConfig2(self):
        # make sure that things that should be default are default.
        cfg = buildcfg.BuildConfiguration(readConfigFiles=False)
        conaryConfig = conarycfg.ConaryConfiguration(False)
        cfg.useConaryConfig(conaryConfig)
        assert(cfg.isDefault('installLabelPath'))

    def testStrictMode(self):
        self.cfg.autoLoadRecipes = ['foo', 'bar']
        cfg = buildcfg.BuildConfiguration(readConfigFiles=False)
        cfg.resetToDefault('autoLoadRecipes')
        cfg.configLine('strictMode True')
        cfg.useConaryConfig(self.cfg)
        assert(cfg.autoLoadRecipes == ['foo', 'bar'])
