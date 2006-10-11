#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
"""

Example commands accepted from rmake via xml:


<version>1</version>
<buildConfig>
    <option><name>buildFlavor</name><value>!builddocs,foo</value></option>
    <option><name>installLabelPath</name><value>conary.rpath.com@rpl:1</option>
    <option><name>resolveTroves</name><value>group-dist</option>
    <option><name>subscribe</name><value>rbuilder xmlrpc http://conary.rpath.com/rmakesubscribe/</option>
    <option><name>uuid</name><value>40charsofhex</value></option>
</buildConfig>
<command>
    <name>build</name>
    <trove><troveName>name</troveName><troveVersion>version</troveVersion>
           <troveFlavor>flavor</troveFlavor></trove>
</command>

Other possible commands, not yet implemented:
    commit job
    stop job
"""

import sys
from xml.dom import minidom

from conary import conarycfg
from conary.deps import deps

from rmake.build import buildcfg
from rmake.cmdline import helper
from rmake import errors

sys.excepthook = errors.genExcepthook()



class RmakeXMLCommandParser(object):

    VERSION = '1'

    def __init__(self, root='/'):
        self.root = root

    def _getText(self, node):
        return str(''.join(x.data for x in node.childNodes if x.nodeType == x.TEXT_NODE))

    def _parse_build_config(self, dom):
        configs = dom.getElementsByTagName('buildConfig')
        configLines = {}
        if configs:
            for option in configs[0].getElementsByTagName('option'):
                name = self._getText(option.getElementsByTagName('name')[0])
                value = self._getText(option.getElementsByTagName('value')[0])
                configLines.setdefault(name, []).append(value)

        conaryConfig = conarycfg.ConaryConfiguration(True)
        buildConfig = buildcfg.BuildConfiguration(True, self.root,
                                                  conaryConfig=conaryConfig)
        buildConfig.initializeFlavors()
        if buildConfig.context:
            buildConfig.setContext(buildConfig.context)

        for key, values in configLines.iteritems():
            # FIXME: add an API for config file to get this info out
            # in a cleaner way
            if key.lower() == 'includeconfigfile':
                for value in values:
                    assert(value.startswith('http://') or value.startswith('https://'))
            else:
                key = buildConfig._lowerCaseMap[key.lower()]
                buildConfig[key] = buildConfig.getDefaultValue(key)

            for value in values:
                buildConfig.configLine('%s %s' % (key, value))
        return buildConfig

    def _check_version(self, dom):
        versionTag = dom.getElementsByTagName('version')
        if versionTag:
            version = self._getText(versionTag[0])
            assert(version == self.VERSION)

    def _parse_command(self, buildConfig, command):
        commandName = self._getText(command.getElementsByTagName('name')[0])

        fnName = '_parsecmd_' + commandName
        if not hasattr(self, fnName):
            raise RuntimeError, 'Unknown command %s' % commandName
        return getattr(self, fnName)(buildConfig, command)

    def _parsecmd_build(self, buildConfig, command):
        troveSpecs = []
        for trove in command.getElementsByTagName('trove'):
            troveName = self._getText(trove.getElementsByTagName('troveName')[0])
            troveVersion = self._getText(trove.getElementsByTagName('troveVersion')[0])
            troveFlavor = self._getText(trove.getElementsByTagName('troveFlavor')[0])
            troveSpec = (troveName, troveVersion, deps.parseFlavor(troveFlavor))
            troveSpecs.append(troveSpec)

        return 'buildTroves', [troveSpecs]

    def _parsecmd_commit(self, buildConfig, command):
        return 'commitJob', [buildConfig.uuid]

    def _parsecmd_stop(self, buildConfig, command):
        return 'stopJob', [buildConfig.uuid]

    def parse(self, file):
        commandList = []
        dom = minidom.parse(file)

        self._check_version(dom)
        buildConfig = self._parse_build_config(dom)
        for command in dom.getElementsByTagName('command'):
            commandList.append(self._parse_command(buildConfig, command))
        dom.unlink()

        return buildConfig, commandList

def main(argv):
    parser = RmakeXMLCommandParser()
    buildConfig, commandList = parser.parse(sys.argv[1])
    client = helper.rMakeHelper(buildConfig=buildConfig, guiPassword=True)

    for command, options in commandList:
        getattr(client, command)(*options)
